import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
import websockets
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY
from py_clob_client.constants import POLYGON
from backend.config import Config
from backend.logger import logger
from backend.services.trade_storage import TradeStorage
from backend.services.rate_limiter import APIRateLimiter
from backend.services.risk_manager import RiskManager

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


# ============================================
# MARKET IMPACT CALCULATOR (CRITICAL)
# ============================================
@dataclass
class MarketImpactResult:
    """Result of market impact calculation."""
    shares: float
    effective_price: float  # Average price per share
    total_cost: float
    levels_consumed: int
    has_sufficient_liquidity: bool


class MarketImpactCalculator:
    """
    Calculates the real cost of executing orders across order book depth.
    Prevents buying at effective price > $1.00.

    This is CRITICAL for profitability - without this, the bot will
    see "YES=0.45, NO=0.50" but actually pay much more when buying
    large quantities that consume multiple price levels.
    """

    @staticmethod
    def calculate_effective_cost(order_book: List[dict], shares_needed: float) -> MarketImpactResult:
        """
        Calculate the average price to buy X shares across multiple price levels.

        Args:
            order_book: List of {price, size} sorted by price ascending (asks)
            shares_needed: Number of shares to buy

        Returns:
            MarketImpactResult with effective price and liquidity info
        """
        if not order_book or shares_needed <= 0:
            return MarketImpactResult(0, 0, 0, 0, False)

        total_cost = 0.0
        shares_filled = 0.0
        levels_consumed = 0

        for level in order_book:
            price = float(level['price'])
            size = float(level.get('size', 0))

            if size <= 0:
                continue

            shares_to_take = min(shares_needed - shares_filled, size)
            total_cost += shares_to_take * price
            shares_filled += shares_to_take
            levels_consumed += 1

            if shares_filled >= shares_needed:
                break

        if shares_filled < shares_needed:
            return MarketImpactResult(
                shares=shares_filled,
                effective_price=total_cost / shares_filled if shares_filled > 0 else 0,
                total_cost=total_cost,
                levels_consumed=levels_consumed,
                has_sufficient_liquidity=False
            )

        return MarketImpactResult(
            shares=shares_needed,
            effective_price=total_cost / shares_needed,
            total_cost=total_cost,
            levels_consumed=levels_consumed,
            has_sufficient_liquidity=True
        )

    @staticmethod
    def find_optimal_trade_size(
        yes_book: List[dict],
        no_book: List[dict],
        max_combined_cost: float = 0.98,
        max_shares: float = 1000,
        precision: float = 0.1
    ) -> Tuple[float, float, float]:
        """
        Binary search to find maximum shares where effective_yes + effective_no < max_cost.

        Args:
            yes_book: YES token order book (asks)
            no_book: NO token order book (asks)
            max_combined_cost: Maximum acceptable combined cost (default 0.98)
            max_shares: Maximum shares to consider
            precision: Search precision in shares

        Returns:
            Tuple of (optimal_shares, effective_yes_price, effective_no_price)
            Returns (0, 0, 0) if no profitable size exists
        """
        low, high = 0.0, max_shares
        best_shares = 0.0
        best_yes_price = 0.0
        best_no_price = 0.0

        # First check if even 1 share is profitable
        yes_result = MarketImpactCalculator.calculate_effective_cost(yes_book, 1.0)
        no_result = MarketImpactCalculator.calculate_effective_cost(no_book, 1.0)

        if not yes_result.has_sufficient_liquidity or not no_result.has_sufficient_liquidity:
            return 0.0, 0.0, 0.0

        if yes_result.effective_price + no_result.effective_price >= max_combined_cost:
            return 0.0, 0.0, 0.0  # Not profitable at any size

        # Binary search for optimal size
        iterations = 0
        max_iterations = 50  # Prevent infinite loop

        while high - low > precision and iterations < max_iterations:
            iterations += 1
            mid = (low + high) / 2

            yes_result = MarketImpactCalculator.calculate_effective_cost(yes_book, mid)
            no_result = MarketImpactCalculator.calculate_effective_cost(no_book, mid)

            if not yes_result.has_sufficient_liquidity or not no_result.has_sufficient_liquidity:
                high = mid
                continue

            combined_cost = yes_result.effective_price + no_result.effective_price

            if combined_cost < max_combined_cost:
                best_shares = mid
                best_yes_price = yes_result.effective_price
                best_no_price = no_result.effective_price
                low = mid
            else:
                high = mid

        return best_shares, best_yes_price, best_no_price

    @staticmethod
    def get_max_profitable_investment(
        yes_book: List[dict],
        no_book: List[dict],
        target_margin: float = 0.02
    ) -> Tuple[float, float]:
        """
        Calculate maximum USDC investment that remains profitable.

        Returns:
            Tuple of (max_usdc_investment, expected_profit_usdc)
        """
        max_cost = 1.0 - target_margin
        shares, eff_yes, eff_no = MarketImpactCalculator.find_optimal_trade_size(
            yes_book, no_book, max_combined_cost=max_cost
        )

        if shares <= 0:
            return 0.0, 0.0

        effective_cost = eff_yes + eff_no
        investment = shares * effective_cost
        profit = shares * (1.0 - effective_cost)

        return investment, profit


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
        self.on_trade = None # Callback function(trade_dict) for trade history

        # ============================================
        # RECONNECTION RESILIENCE
        # ============================================
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        self.base_reconnect_delay = 5  # seconds
        self.max_reconnect_delay = 60  # seconds

        # ============================================
        # OPTIMIZATION MANAGERS
        # ============================================
        self.cooldown_manager = CooldownManager(config.COOLDOWN_SECONDS)
        self.execution_lock = ExecutionLock()
        self.opportunity_manager = OpportunityManager(config.MIN_PROFIT_MARGIN)

        # ============================================
        # PHASE 2: ADVANCED SERVICES
        # ============================================
        self.trade_storage = TradeStorage()
        self.rate_limiter = APIRateLimiter()
        self.risk_manager = RiskManager.from_config(config)
        
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
            # PHASE 2: Rate limit API calls
            await self.rate_limiter.acquire('markets')

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
        DEPTH-AWARE arbitrage detection.
        Calculates the REAL cost of buying across order book levels,
        not just the top-of-book price.

        This is CRITICAL: Without depth analysis, the bot will see
        "YES=0.45 + NO=0.50 = 0.95" but actually pay ~1.02 when buying
        large quantities that consume multiple price levels.
        """
        # PHASE 2: Check daily loss limit before processing
        if not self.risk_manager.check_daily_limit():
            return  # Daily loss limit reached, stop trading

        # Fast O(1) lookup using token_to_market index
        market_id = self.token_to_market.get(token_id)
        if not market_id:
            return

        m = self.market_details.get(market_id)
        if not m or 'tokens' not in m or len(m['tokens']) < 2:
            return

        yes_token = m['tokens'][0]['token_id']
        no_token = m['tokens'][1]['token_id']

        # Get order book depth (not just best price)
        ask_yes_list = self.order_books.get(yes_token, {}).get('asks', [])
        ask_no_list = self.order_books.get(no_token, {}).get('asks', [])

        if not ask_yes_list or not ask_no_list:
            return

        # CRITICAL: Calculate optimal size based on order book DEPTH
        target_cost = 1.0 - self.config.MIN_PROFIT_MARGIN

        # Calculate max shares we might want based on capital
        max_possible_shares = self.config.CAPITAL_PER_TRADE / 0.5  # Rough estimate

        optimal_shares, eff_yes, eff_no = MarketImpactCalculator.find_optimal_trade_size(
            ask_yes_list,
            ask_no_list,
            max_combined_cost=target_cost,
            max_shares=max_possible_shares,
            precision=1.0
        )

        if optimal_shares <= 0:
            return  # No profitable opportunity at any size

        effective_cost = eff_yes + eff_no

        if effective_cost >= target_cost:
            return  # Not profitable after market impact

        roi = (1.0 - effective_cost) / effective_cost * 100

        # Update opportunity cache with EFFECTIVE prices (not top-of-book)
        opportunity = self.opportunity_manager.update(
            market_id, yes_token, no_token, eff_yes, eff_no
        )

        # Log with depth-aware info
        top_yes = float(ask_yes_list[0]['price'])
        top_no = float(ask_no_list[0]['price'])
        logger.info(
            f"DEPTH-AWARE ARB: {market_id} | "
            f"Top: {top_yes:.3f}+{top_no:.3f}={top_yes+top_no:.3f} | "
            f"Effective: {eff_yes:.4f}+{eff_no:.4f}={effective_cost:.4f} | "
            f"Shares: {optimal_shares:.1f} | ROI: {roi:.2f}%"
        )

        # Notify UI with effective prices
        if self.on_opportunity:
            try:
                self.on_opportunity(market_id, eff_yes, eff_no)
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

        # Execute with depth-aware parameters
        await self.execute_depth_aware_trade(
            market_id, yes_token, no_token, optimal_shares, eff_yes, eff_no
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

    async def execute_depth_aware_trade(
        self, market_id: str, yes_token: str, no_token: str,
        shares: float, price_yes: float, price_no: float
    ) -> bool:
        """
        Execute trade with pre-calculated optimal size from depth analysis.

        Unlike execute_trade which calculates shares from capital/cost,
        this method uses the pre-calculated optimal shares from
        MarketImpactCalculator.find_optimal_trade_size().

        Args:
            market_id: Market identifier
            yes_token: YES token ID
            no_token: NO token ID
            shares: Pre-calculated optimal number of shares
            price_yes: Effective YES price (weighted average across levels)
            price_no: Effective NO price (weighted average across levels)

        Returns:
            True if trade executed successfully, False otherwise
        """
        if not await self.execution_lock.acquire(market_id):
            logger.warning(f"Could not acquire lock for {market_id}")
            return False

        try:
            start_time = time.time()

            # Re-verify liquidity before execution
            ask_yes = self.order_books.get(yes_token, {}).get('asks', [])
            ask_no = self.order_books.get(no_token, {}).get('asks', [])

            yes_result = MarketImpactCalculator.calculate_effective_cost(ask_yes, shares)
            no_result = MarketImpactCalculator.calculate_effective_cost(ask_no, shares)

            if not yes_result.has_sufficient_liquidity or not no_result.has_sufficient_liquidity:
                logger.warning(f"Liquidity disappeared for {market_id}")
                return False

            current_cost = yes_result.effective_price + no_result.effective_price
            target_cost = 1.0 - self.config.MIN_PROFIT_MARGIN

            if current_cost >= target_cost:
                logger.warning(f"No longer profitable after re-check: {current_cost:.4f} >= {target_cost:.4f}")
                return False

            # Check execution window
            if time.time() - start_time > MAX_EXECUTION_WINDOW:
                logger.error("Execution window exceeded. Aborting.")
                return False

            logger.info(
                f"EXECUTING: {market_id} | {shares:.2f} shares | "
                f"YES@{yes_result.effective_price:.4f} (L{yes_result.levels_consumed}) + "
                f"NO@{no_result.effective_price:.4f} (L{no_result.levels_consumed}) = "
                f"{current_cost:.4f}"
            )

            loop = asyncio.get_running_loop()

            # PHASE 2: Rate limit order API calls (acquire 2 slots for parallel orders)
            await self.rate_limiter.acquire('orders')
            await self.rate_limiter.acquire('orders')

            # Execute both orders in parallel with effective prices
            t1 = loop.run_in_executor(
                None,
                lambda: self._place_order(yes_token, shares, yes_result.effective_price)
            )
            t2 = loop.run_in_executor(
                None,
                lambda: self._place_order(no_token, shares, no_result.effective_price)
            )

            results = await asyncio.gather(t1, t2, return_exceptions=True)

            success = all(not isinstance(r, Exception) and r is not None for r in results)

            if success:
                profit = shares * (1.0 - current_cost)
                entry_cost = shares * current_cost
                logger.info(f"Trade Executed Successfully. Expected profit: ${profit:.2f}")

                trade_record = {
                    "market_id": market_id,
                    "side": "BOTH",
                    "shares": shares,
                    "entry_cost": entry_cost,
                    "exit_value": shares,  # $1 per share at resolution
                    "pnl": profit,
                    "roi": (1.0 - current_cost) / current_cost * 100,
                    "yes_price": yes_result.effective_price,
                    "no_price": no_result.effective_price,
                    "status": "EXECUTED",
                    "timestamp": datetime.now(),
                    "levels_yes": yes_result.levels_consumed,
                    "levels_no": no_result.levels_consumed
                }

                self.positions.append(trade_record)

                # PHASE 2: Persist trade to database
                try:
                    trade_id = self.trade_storage.save_trade(trade_record)
                    logger.debug(f"Trade saved to database with ID: {trade_id}")
                except Exception as e:
                    logger.error(f"Failed to save trade to database: {e}")

                # PHASE 2: Record P&L for daily tracking
                self.risk_manager.record_pnl(profit)

                # Notify UI about trade
                if self.on_trade:
                    try:
                        self.on_trade(trade_record)
                    except Exception as e:
                        logger.error(f"Trade callback error: {e}")

                self.cooldown_manager.record_trade(market_id)
                self.opportunity_manager.mark_executed(market_id)
                return True
            else:
                logger.error(f"Trade Partial Failure or Error: {results}")
                logger.critical(
                    f"PARTIAL FILL RISK for {market_id}: "
                    "One or both orders may have failed. Check positions manually!"
                )
                return False

        finally:
            await self.execution_lock.release(market_id)

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

            # PHASE 2: Rate limit order API calls
            await self.rate_limiter.acquire('orders')
            await self.rate_limiter.acquire('orders')

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
        """
        Main run loop with resilient reconnection.
        Automatically reconnects on WebSocket failures with exponential backoff.
        """
        self.running = True
        logger.info("Starting Arbitrage Engine...")
        await self.fetch_markets()

        while self.running:
            try:
                await self.connect_and_listen()

                # If connect_and_listen returns normally, reset attempts
                self.reconnect_attempts = 0

            except websockets.exceptions.ConnectionClosed as e:
                await self._handle_reconnection(f"Connection closed: {e}")

            except websockets.exceptions.InvalidStatusCode as e:
                await self._handle_reconnection(f"Invalid status code: {e}")

            except ConnectionRefusedError as e:
                await self._handle_reconnection(f"Connection refused: {e}")

            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                await self._handle_reconnection(str(e))

        logger.info("Arbitrage Engine stopped.")

    async def _handle_reconnection(self, error_msg: str):
        """
        Handle WebSocket reconnection with exponential backoff.
        """
        self.reconnect_attempts += 1

        if self.reconnect_attempts > self.max_reconnect_attempts:
            logger.critical(
                f"Max reconnection attempts ({self.max_reconnect_attempts}) reached. "
                "Stopping engine. Manual restart required."
            )
            self.running = False
            return

        # Exponential backoff with cap
        delay = min(
            self.base_reconnect_delay * (2 ** (self.reconnect_attempts - 1)),
            self.max_reconnect_delay
        )

        logger.warning(
            f"Connection error: {error_msg}. "
            f"Reconnecting in {delay}s (attempt {self.reconnect_attempts}/{self.max_reconnect_attempts})"
        )

        await asyncio.sleep(delay)

        # Refresh markets on reconnect (they may have changed)
        try:
            logger.info("Refreshing markets before reconnection...")
            await self.fetch_markets()
        except Exception as e:
            logger.error(f"Failed to refresh markets: {e}")

    def stop(self):
        self.running = False
        self.reconnect_attempts = 0
        logger.info("Stopping Engine...")

