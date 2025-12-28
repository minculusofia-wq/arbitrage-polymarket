import asyncio
import json
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set
import websockets
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY
from py_clob_client.constants import POLYGON
from backend.config import Config
from backend.logger import logger

# Constants
MAX_EXECUTION_WINDOW = 20  # seconds


# ============================================
# OPTIMIZATION 1: Cooldown Manager
# ============================================
class CooldownManager:
    """
    Prevents spam trading by enforcing a cooldown period per market.
    """
    def __init__(self, cooldown_seconds: float = 30.0):
        self.last_trade: Dict[str, float] = {}
        self.cooldown = cooldown_seconds

    def can_trade(self, market_id: str) -> bool:
        """Check if enough time has passed since last trade on this market."""
        last = self.last_trade.get(market_id, 0)
        return time.time() - last > self.cooldown

    def record_trade(self, market_id: str):
        """Record a trade timestamp for cooldown tracking."""
        self.last_trade[market_id] = time.time()

    def time_remaining(self, market_id: str) -> float:
        """Returns seconds remaining in cooldown, 0 if can trade."""
        last = self.last_trade.get(market_id, 0)
        remaining = self.cooldown - (time.time() - last)
        return max(0, remaining)


# ============================================
# OPTIMIZATION 2: Execution Lock
# ============================================
class ExecutionLock:
    """
    Prevents duplicate execution on the same market.
    Thread-safe async lock.
    """
    def __init__(self):
        self.executing: Set[str] = set()
        self._lock = asyncio.Lock()

    async def acquire(self, market_id: str) -> bool:
        """Try to acquire lock for a market. Returns False if already executing."""
        async with self._lock:
            if market_id in self.executing:
                return False
            self.executing.add(market_id)
            return True

    async def release(self, market_id: str):
        """Release the lock for a market."""
        async with self._lock:
            self.executing.discard(market_id)

    def is_executing(self, market_id: str) -> bool:
        """Check if a market is currently being executed."""
        return market_id in self.executing


# ============================================
# OPTIMIZATION 3: Opportunity Cache
# ============================================
@dataclass
class OpportunityCache:
    """Cached arbitrage opportunity with metadata."""
    market_id: str
    yes_token: str
    no_token: str
    yes_price: float
    no_price: float
    cost: float
    roi: float
    timestamp: float
    executed: bool = False


class OpportunityManager:
    """
    Manages and caches arbitrage opportunities.
    Enables profitability ranking and deduplication.
    """
    def __init__(self, min_profit_margin: float):
        self.opportunities: Dict[str, OpportunityCache] = {}
        self.min_margin = min_profit_margin

    def update(self, market_id: str, yes_token: str, no_token: str,
               yes_price: float, no_price: float) -> Optional[OpportunityCache]:
        """Update opportunity cache. Returns opportunity if profitable."""
        cost = yes_price + no_price
        target = 1.0 - self.min_margin

        if cost < target and cost > 0:
            roi = (1.0 - cost) / cost * 100
            opp = OpportunityCache(
                market_id=market_id,
                yes_token=yes_token,
                no_token=no_token,
                yes_price=yes_price,
                no_price=no_price,
                cost=cost,
                roi=roi,
                timestamp=time.time()
            )
            self.opportunities[market_id] = opp
            return opp

        # Remove if no longer profitable
        self.opportunities.pop(market_id, None)
        return None

    def get_best(self, n: int = 5) -> List[OpportunityCache]:
        """Returns the N best opportunities sorted by ROI (descending)."""
        valid = [o for o in self.opportunities.values() if not o.executed]
        return sorted(valid, key=lambda x: x.roi, reverse=True)[:n]

    def mark_executed(self, market_id: str):
        """Mark an opportunity as executed."""
        if market_id in self.opportunities:
            self.opportunities[market_id].executed = True

    def get(self, market_id: str) -> Optional[OpportunityCache]:
        """Get a specific opportunity."""
        return self.opportunities.get(market_id)

    def clear_stale(self, max_age: float = 60.0):
        """Remove opportunities older than max_age seconds."""
        now = time.time()
        stale = [k for k, v in self.opportunities.items() if now - v.timestamp > max_age]
        for k in stale:
            del self.opportunities[k]


# ============================================
# SLIPPAGE CHECK UTILITY
# ============================================
def check_slippage(expected_cost: float, current_cost: float, max_slippage: float = 0.005) -> bool:
    """
    Check if slippage is within acceptable range.
    Returns True if slippage is acceptable, False otherwise.
    """
    if expected_cost <= 0:
        return False
    slippage = abs(current_cost - expected_cost) / expected_cost
    return slippage <= max_slippage

class ArbitrageBot:
    def __init__(self, config: Config):
        self.config = config
        self.running = False
        self.positions: List[dict] = []
        self.order_books: Dict[str, dict] = {} # market_id -> {bids: [], asks: []}
        self.market_details: Dict[str, dict] = {} # condition_id -> market_info
        self.token_to_market: Dict[str, str] = {} # token_id -> market_id (for fast O(1) lookup)
        self.markets_whitelist: List[str] = [] # condition_ids or token_ids
        self.on_opportunity = None # Callback function(market_id, yes_price, no_price)

        # ============================================
        # OPTIMIZATION MANAGERS
        # ============================================
        self.cooldown_manager = CooldownManager(config.COOLDOWN_SECONDS)
        self.execution_lock = ExecutionLock()
        self.opportunity_manager = OpportunityManager(config.MIN_PROFIT_MARGIN)
        
        # Initialize Clob Client (Synchronous)
        # We will run blocking calls in executor
        try:
            self.client = ClobClient(
                "https://clob.polymarket.com", 
                key=config.POLY_API_KEY, 
                chain_id=POLYGON,
                signature_type=1, # 1=L2 (API Key), 2=L1 (Metamask/EOA) - User provided Private Key usually implies specific setup.
                # However, usually API Key is enough for L2 if configured via dashboard.
                # If User provided PRIVATE_KEY, we might need to use it for L1 or L2 Proxy.
                # Assuming Standard L2 API Key setup + Private Key for specific signing if needed.
                # For this implementation, we assume the API Key setup is sufficient for L2 orders 
                # OR we use the private key to sign if creating order requires it.
                # PyClobClient uses the private key to derive the signer.
                funder=config.PRIVATE_KEY # This argument handles the signing key
            )
            # Passphrase/Secret are headers usually, py-clob-client uses 'creds' object or args
            self.client.set_api_creds(
                api_key=config.POLY_API_KEY,
                api_secret=config.POLY_API_SECRET,
                api_passphrase=config.POLY_API_PASSPHRASE
            )
            logger.info("Clob Client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Clob Client: {e}")
            self.client = None

        self.simulated_balance = config.FALLBACK_BALANCE  # Fallback if API fails to read balance

    async def fetch_markets(self):
        """
        Fetches active markets to monitor.
        Filters by volume and categories.
        """
        logger.info("Fetching markets...")
        try:
            # Run blocking call in executor
            loop = asyncio.get_running_loop()
            # Fetching simplified list - in prod strict filtering needed
            # We fetch markets with volume > configured
            # Using next_cursor logic if needed, simplified here to get top 100 relevant
            markets = await loop.run_in_executor(
                None, 
                lambda: self.client.get_markets(
                    limit=50, 
                    active=True, 
                    volume_min=self.config.MIN_MARKET_VOLUME
                )
            )
            
            # Filter for Binary Yes/No
            # Polymarket 'markets' return structure check needed. assuming standard return.
            # We need to map Token IDs to Markets for the WebSocket
            self.markets_whitelist = []
            for m in markets:
                # Basic filter: 2 tokens (Binary)
                if len(m.get('tokens', [])) == 2:
                    condition_id = m['condition_id']
                    self.markets_whitelist.append(condition_id)
                    self.market_details[condition_id] = m

                    # Build token to market index for fast O(1) lookup
                    for token in m['tokens']:
                        self.token_to_market[token['token_id']] = condition_id

            logger.info(f"Monitoring {len(self.markets_whitelist)} markets with significant volume.")
            
        except Exception as e:
            logger.error(f"Error fetching markets: {e}")

    async def connect_and_listen(self):
        """
        Main WebSocket Loop
        """
        if not self.markets_whitelist:
            logger.warning("No markets to monitor. Waiting...")
            return

        async with websockets.connect(self.config.CLOB_WS_URL) as ws:
            logger.info("Connected to Polymarket WebSocket.")
            
            # Subscribe to order books (level 2) or tickers
            # Asking for market updates
            payload = {
                "type": "Usage", # or appropriate subscribe message for Market Data
                # Clob uses specific subscription implementation
                # Usually: { "assets_ids": [...], "type": "market" }
            }
            # Simplified subscription logic for Clob:
            # We subscribe to the Condition IDs or Token IDs
            subscribe_msg = {
                "type": "subscribe",
                "channel": "book",
                "market": "" # Loop over markets or batch
            }
            
            # Batch subscribe? Polymarket WS usually takes list of token_ids
            token_ids = []
            for cid in self.markets_whitelist:
                m = self.market_details[cid]
                token_ids.extend([t['request_id'] for t in m.get('token_specs', [])]) # or tokens
                # Actually, simply subscribing to the condition_id might not work, usually token_id
                # py-clob-client has get_markets -> tokens -> token_id
                # Let's assume we subscribe to the token_ids of YES and NO outcome
                if 'tokens' in m:
                     token_ids.append(m['tokens'][0]['token_id'])
                     token_ids.append(m['tokens'][1]['token_id'])

            # Limit subscription to avoid 429 or overflow 
            token_ids = token_ids[:self.config.MAX_TOKENS_MONITOR]  # Limit tokens for reliability
            
            for tid in token_ids:
                msg = {"type": "subscribe", "channel": "level2", "token_id": tid}
                await ws.send(json.dumps(msg))
            
            logger.info(f"Subscribed to price feeds for {len(token_ids)} tokens.")

            while self.running:
                try:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    await self.process_message(data)
                except websockets.exceptions.ConnectionClosed:
                    logger.error("WebSocket connection closed. Reconnecting...")
                    break
                except Exception as e:
                    logger.error(f"WS Error: {e}")
                    await asyncio.sleep(1)

    async def process_message(self, data: dict):
        """
        Updates local orderbook and triggers check
        """
        # Parse Level 2 updates
        # Structure: { "token_id": "...", "bids": [...], "asks": [...] }
        # We handle 'snapshots' and 'updates'
        # Simplified for robustness:
        # Just update internal state
        
        # Check event type?
        # Assuming typical message structure
        if 'token_id' in data:
            tid = data['token_id']
            # naive update
            if tid not in self.order_books:
                self.order_books[tid] = {'bids': [], 'asks': []}
            
            # Apply updates (simplified: Replace logic if snapshot, merge if update)
            # For this exercise, we treat incoming as latest snapshot if full book sent
            if 'asks' in data:
                self.order_books[tid]['asks'] = data['asks']
            if 'bids' in data:
                self.order_books[tid]['bids'] = data['bids']
            
            # Find which market this token belongs to
            # Then check Arb for that market
            await self.check_arbitrage(tid)

    async def check_arbitrage(self, token_id: str):
        """
        Checks if YES + NO < 1 - Margin
        Uses optimization managers for cooldown, locking, and caching.
        """
        # Fast O(1) lookup using token_to_market index
        market_id = self.token_to_market.get(token_id)
        if not market_id:
            return

        m = self.market_details.get(market_id)
        if not m or 'tokens' not in m or len(m['tokens']) < 2:
            return

        yes_token = m['tokens'][0]['token_id']
        no_token = m['tokens'][1]['token_id']

        # Get best asks
        ask_yes_list = self.order_books.get(yes_token, {}).get('asks', [])
        ask_no_list = self.order_books.get(no_token, {}).get('asks', [])

        if not ask_yes_list or not ask_no_list:
            return

        best_ask_yes = float(ask_yes_list[0]['price'])
        best_ask_no = float(ask_no_list[0]['price'])

        # Update opportunity cache (handles profitability check internally)
        opportunity = self.opportunity_manager.update(
            market_id, yes_token, no_token, best_ask_yes, best_ask_no
        )

        if not opportunity:
            return  # Not profitable

        logger.info(f"ARBITRAGE FOUND! {market_id} | YES: {best_ask_yes} + NO: {best_ask_no} = {opportunity.cost:.4f} | ROI: {opportunity.roi:.2f}%")

        # Notify UI
        if self.on_opportunity:
            try:
                self.on_opportunity(market_id, best_ask_yes, best_ask_no)
            except Exception as e:
                logger.error(f"UI Callback Error: {e}")

        # OPTIMIZATION: Check cooldown before execution
        if not self.cooldown_manager.can_trade(market_id):
            remaining = self.cooldown_manager.time_remaining(market_id)
            logger.debug(f"Market {market_id} in cooldown ({remaining:.1f}s remaining)")
            return

        # OPTIMIZATION: Check if already executing
        if self.execution_lock.is_executing(market_id):
            logger.debug(f"Market {market_id} already executing")
            return

        # Execute with slippage protection
        await self.execute_with_slippage_check(
            market_id, yes_token, no_token, best_ask_yes, best_ask_no
        )

    async def execute_with_slippage_check(self, market_id: str, yes_token: str, no_token: str,
                                           expected_yes: float, expected_no: float) -> bool:
        """
        Execute trade with slippage protection.
        Verifies current prices haven't moved significantly before executing.
        """
        # Get current prices from order books
        ask_yes_list = self.order_books.get(yes_token, {}).get('asks', [])
        ask_no_list = self.order_books.get(no_token, {}).get('asks', [])

        if not ask_yes_list or not ask_no_list:
            logger.warning(f"Order books empty for {market_id}")
            return False

        current_yes = float(ask_yes_list[0].get('price', 0))
        current_no = float(ask_no_list[0].get('price', 0))

        expected_cost = expected_yes + expected_no
        current_cost = current_yes + current_no

        if current_cost <= 0:
            logger.warning(f"Invalid current cost for {market_id}")
            return False

        # Check slippage
        if not check_slippage(expected_cost, current_cost, self.config.MAX_SLIPPAGE):
            slippage = abs(current_cost - expected_cost) / expected_cost * 100
            logger.warning(f"Slippage too high for {market_id}: {slippage:.2f}% > {self.config.MAX_SLIPPAGE * 100}%")
            return False

        # Execute with current prices (more accurate)
        return await self.execute_trade(market_id, yes_token, no_token, current_yes, current_no)

    async def execute_trade(self, market_id, yes_token, no_token, price_yes, price_no) -> bool:
        """
        Executes the dual buy order with execution lock.
        Returns True if successful, False otherwise.
        """
        # OPTIMIZATION: Acquire execution lock
        if not await self.execution_lock.acquire(market_id):
            logger.warning(f"Could not acquire lock for {market_id}")
            return False

        try:
            start_time = time.time()
            logger.info(f"Executing Trade for {market_id}")

            # Calculate size
            capital = self.config.CAPITAL_PER_TRADE
            cost = price_yes + price_no
            shares = capital / cost
            shares = round(shares, 2)

            if shares <= 0:
                return False

            # 20s Window Constraint
            if time.time() - start_time > MAX_EXECUTION_WINDOW:
                logger.error("Execution window exceeded. Aborting.")
                return False

            logger.info(f"Buying {shares} shares of YES and NO.")

            loop = asyncio.get_running_loop()

            # Execute both orders in parallel
            t1 = loop.run_in_executor(None, lambda: self._place_order(yes_token, shares, price_yes))
            t2 = loop.run_in_executor(None, lambda: self._place_order(no_token, shares, price_no))

            results = await asyncio.gather(t1, t2, return_exceptions=True)

            success = all(not isinstance(r, Exception) and r is not None for r in results)
            if success:
                logger.info("Trade Executed Successfully.")
                self.positions.append({"market": market_id, "size": shares, "entry": cost, "time": time.time()})

                # OPTIMIZATION: Record trade for cooldown and mark opportunity as executed
                self.cooldown_manager.record_trade(market_id)
                self.opportunity_manager.mark_executed(market_id)
                return True
            else:
                logger.error(f"Trade Partial Failure or Error: {results}")
                logger.critical(f"PARTIAL FILL RISK for {market_id}: One or both orders may have failed. Check positions manually!")
                return False

        finally:
            # OPTIMIZATION: Always release lock
            await self.execution_lock.release(market_id)

    def _place_order(self, token_id, amount, price):
        if self.client is None:
            raise RuntimeError("Client not initialized - cannot place order")
        try:
            # Create Order
            # Using FOK (Fill or Kill) or IOC to avoid partial fills creating unhedged risk
            # For Arb, FillOrKill is safest.
            # However, Limit orders are standard.
            resp = self.client.create_and_post_order(
                OrderArgs(
                    price=price,
                    size=amount,
                    side=BUY,
                    token_id=token_id,
                    order_type=OrderType.FOK 
                )
            )
            return resp
        except Exception as e:
            logger.error(f"Order Failed: {e}")
            raise e

    async def run(self):
        self.running = True
        logger.info("Starting Arbitrage Engine...")
        await self.fetch_markets()
        await self.connect_and_listen()

    def stop(self):
        self.running = False
        logger.info("Stopping Engine...")

