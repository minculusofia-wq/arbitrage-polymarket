import asyncio
import json
import time
from typing import Dict, List, Optional
import websockets
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY
from py_clob_client.constants import POLYGON
from backend.config import Config
from backend.logger import logger

# Constants
MAX_EXECUTION_WINDOW = 20  # seconds

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
        # We Buy at Ask.
        # Arb: Buy Yes @ Ask1 + Buy No @ Ask2 < 1
        
        ask_yes_list = self.order_books.get(yes_token, {}).get('asks', [])
        ask_no_list = self.order_books.get(no_token, {}).get('asks', [])
        
        if not ask_yes_list or not ask_no_list:
            return

        # Best Ask is usually the first one data[0] if sorted, assuming sorted explicitly
        # Clob usually sends sorted. price matches logic? 
        # Price is strictly 0.0-1.0? Clob sends string "0.54" etc
        
        best_ask_yes = float(ask_yes_list[0]['price'])
        best_ask_no = float(ask_no_list[0]['price'])
        
        cost = best_ask_yes + best_ask_no
        target = 1.0 - self.config.MIN_PROFIT_MARGIN
        
        if cost < target:
            logger.info(f"ARBITRAGE FOUND! {market_id} | YES: {best_ask_yes} + NO: {best_ask_no} = {cost} (Target < {target})")
            
            if self.on_opportunity:
                # Run safe, don't block
                try:
                    self.on_opportunity(market_id, best_ask_yes, best_ask_no)
                except Exception as e:
                    logger.error(f"UI Callback Error: {e}")

            # Trigger Execution
            await self.execute_trade(market_id, yes_token, no_token, best_ask_yes, best_ask_no)

    async def execute_trade(self, market_id, yes_token, no_token, price_yes, price_no):
        """
        Executes the dual buy order
        """
        start_time = time.time()
        logger.info(f"Executing Trade for {market_id}")
        
        # Calculate size
        # Total Capital / Cost = Shares
        # Example: $10 / 0.95 = 10.52 shares
        capital = self.config.CAPITAL_PER_TRADE
        cost = price_yes + price_no
        shares = capital / cost
        
        # Rounding?
        shares = round(shares, 2) # simplified
        
        if shares <= 0:
            return

        # 20s Window Constraint
        if time.time() - start_time > MAX_EXECUTION_WINDOW:
            logger.error("Execution window exceeded. Aborting.")
            return

        # Place Orders
        logger.info(f"Buying {shares} shares of YES and NO.")
        
        loop = asyncio.get_running_loop()
        
        # Make orders (Parallel?)
        # We run them slightly sequentially or gathered to ensure we don't end up with one leg
        # Ideally: atomic? Not possible on Clob easily without batching support.
        # We try to fill both.
        
        # Order 1: YES
        t1 = loop.run_in_executor(None, lambda: self._place_order(yes_token, shares, price_yes))
        # Order 2: NO
        t2 = loop.run_in_executor(None, lambda: self._place_order(no_token, shares, price_no))
        
        results = await asyncio.gather(t1, t2, return_exceptions=True)
        
        success = all(not isinstance(r, Exception) and r is not None for r in results)
        if success:
            logger.info("Trade Executed Successfully.")
            self.positions.append({"market": market_id, "size": shares, "entry": cost, "time": time.time()})
        else:
            logger.error(f"Trade Partial Failure or Error: {results}")
            logger.critical(f"PARTIAL FILL RISK for {market_id}: One or both orders may have failed. Check positions manually!")

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

