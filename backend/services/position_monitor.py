"""
Position Monitor - Active monitoring and automatic exit execution.

Continuously monitors open positions and executes exits when:
- Stop-loss threshold is breached
- Take-profit threshold is reached
- Market resolution is imminent
"""
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Callable
from backend.logger import logger
from backend.services.risk_manager import RiskManager


class PositionMonitor:
    """
    Background service that monitors positions and triggers exits.

    Runs as an async task alongside the main trading loop.
    """

    def __init__(
        self,
        risk_manager: RiskManager,
        check_interval: float = 5.0,
        on_exit_signal: Optional[Callable] = None
    ):
        """
        Initialize position monitor.

        Args:
            risk_manager: RiskManager instance for threshold checks.
            check_interval: Seconds between position checks.
            on_exit_signal: Callback when exit is triggered (position, reason).
        """
        self.risk_manager = risk_manager
        self.check_interval = check_interval
        self.on_exit_signal = on_exit_signal

        self.positions: List[Dict] = []
        self.order_books: Dict[str, dict] = {}
        self.token_to_market: Dict[str, str] = {}
        self.market_details: Dict[str, dict] = {}

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._exit_queue: asyncio.Queue = asyncio.Queue()

    def update_positions(self, positions: List[Dict]):
        """Update the list of positions to monitor."""
        self.positions = positions

    def update_order_books(self, order_books: Dict[str, dict]):
        """Update order book data for price checks."""
        self.order_books = order_books

    def update_market_data(
        self,
        token_to_market: Dict[str, str],
        market_details: Dict[str, dict]
    ):
        """Update market mapping data."""
        self.token_to_market = token_to_market
        self.market_details = market_details

    def _get_current_prices(self, position: Dict) -> tuple:
        """
        Get current YES and NO prices for a position.

        Returns:
            Tuple of (yes_price, no_price) or (None, None) if unavailable.
        """
        market_id = position.get('market_id')
        if not market_id:
            return None, None

        market = self.market_details.get(market_id)
        if not market or 'tokens' not in market or len(market['tokens']) < 2:
            return None, None

        yes_token = market['tokens'][0]['token_id']
        no_token = market['tokens'][1]['token_id']

        # Get best ask prices (what we'd pay to buy/sell)
        yes_asks = self.order_books.get(yes_token, {}).get('asks', [])
        no_asks = self.order_books.get(no_token, {}).get('asks', [])

        # For exit valuation, use bid prices (what we'd receive if selling)
        yes_bids = self.order_books.get(yes_token, {}).get('bids', [])
        no_bids = self.order_books.get(no_token, {}).get('bids', [])

        if not yes_bids or not no_bids:
            # Fallback to asks if no bids
            if yes_asks and no_asks:
                return float(yes_asks[0]['price']), float(no_asks[0]['price'])
            return None, None

        return float(yes_bids[0]['price']), float(no_bids[0]['price'])

    async def _check_positions(self):
        """Check all positions for exit conditions."""
        exits_triggered = []

        for position in self.positions:
            if position.get('status') != 'EXECUTED':
                continue

            yes_price, no_price = self._get_current_prices(position)
            if yes_price is None or no_price is None:
                continue

            should_exit, reason = self.risk_manager.check_position(
                position, yes_price, no_price
            )

            if should_exit:
                exit_info = {
                    'position': position,
                    'reason': reason,
                    'current_yes_price': yes_price,
                    'current_no_price': no_price,
                    'timestamp': datetime.now()
                }
                exits_triggered.append(exit_info)

                logger.warning(
                    f"EXIT SIGNAL: {reason} for {position.get('market_id')} | "
                    f"Entry: ${position.get('entry_cost', 0):.2f} | "
                    f"Current: ${position.get('shares', 0) * (yes_price + no_price):.2f}"
                )

                # Add to exit queue for processing
                await self._exit_queue.put(exit_info)

                # Trigger callback if set
                if self.on_exit_signal:
                    try:
                        await self.on_exit_signal(position, reason)
                    except Exception as e:
                        logger.error(f"Exit signal callback error: {e}")

        return exits_triggered

    async def _monitor_loop(self):
        """Main monitoring loop."""
        logger.info(
            f"Position Monitor started (interval: {self.check_interval}s)"
        )

        while self._running:
            try:
                if self.positions:
                    await self._check_positions()
            except Exception as e:
                logger.error(f"Position monitor error: {e}")

            await asyncio.sleep(self.check_interval)

        logger.info("Position Monitor stopped")

    def start(self):
        """Start the monitoring task."""
        if self._running:
            logger.warning("Position Monitor already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Position Monitor starting...")

    def stop(self):
        """Stop the monitoring task."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("Position Monitor stopping...")

    async def get_pending_exits(self) -> List[Dict]:
        """Get all pending exit signals from the queue."""
        exits = []
        while not self._exit_queue.empty():
            try:
                exit_info = self._exit_queue.get_nowait()
                exits.append(exit_info)
            except asyncio.QueueEmpty:
                break
        return exits

    def get_status(self) -> Dict:
        """Get current monitor status."""
        return {
            'running': self._running,
            'positions_monitored': len(self.positions),
            'check_interval': self.check_interval,
            'pending_exits': self._exit_queue.qsize()
        }

    async def manual_exit(self, position_id: str) -> bool:
        """
        Trigger a manual exit for a specific position.

        Args:
            position_id: Market ID or position identifier to exit.

        Returns:
            True if exit signal was queued, False if position not found.
        """
        # Find the position
        target_position = None
        for pos in self.positions:
            if (pos.get('market_id') == position_id or
                pos.get('id') == position_id):
                if pos.get('status') == 'EXECUTED':
                    target_position = pos
                    break

        if not target_position:
            logger.warning(f"Manual exit: Position not found: {position_id}")
            return False

        # Get current prices
        yes_price, no_price = self._get_current_prices(target_position)
        if yes_price is None:
            logger.error(f"Manual exit: Cannot get prices for {position_id}")
            return False

        exit_info = {
            'position': target_position,
            'reason': 'MANUAL_EXIT',
            'current_yes_price': yes_price,
            'current_no_price': no_price,
            'timestamp': datetime.now()
        }

        logger.info(
            f"MANUAL EXIT queued for {position_id} | "
            f"Current value: ${target_position.get('shares', 0) * (yes_price + no_price):.2f}"
        )

        # Add to exit queue
        await self._exit_queue.put(exit_info)

        # Trigger callback if set
        if self.on_exit_signal:
            try:
                await self.on_exit_signal(target_position, 'MANUAL_EXIT')
            except Exception as e:
                logger.error(f"Manual exit callback error: {e}")

        return True

    def get_open_positions(self) -> List[Dict]:
        """
        Get list of open positions with current values.

        Returns:
            List of position dicts with current valuation.
        """
        open_positions = []
        for pos in self.positions:
            if pos.get('status') != 'EXECUTED':
                continue

            yes_price, no_price = self._get_current_prices(pos)
            shares = pos.get('shares', 0)
            entry_cost = pos.get('entry_cost', 0)

            if yes_price is not None and no_price is not None:
                current_value = shares * (yes_price + no_price)
                unrealized_pnl = current_value - entry_cost
                pnl_pct = (unrealized_pnl / entry_cost * 100) if entry_cost > 0 else 0
            else:
                current_value = None
                unrealized_pnl = None
                pnl_pct = None

            open_positions.append({
                'market_id': pos.get('market_id'),
                'id': pos.get('id'),
                'shares': shares,
                'entry_cost': entry_cost,
                'current_value': current_value,
                'unrealized_pnl': unrealized_pnl,
                'pnl_pct': pnl_pct,
                'yes_token': pos.get('yes_token'),
                'no_token': pos.get('no_token'),
                'timestamp': pos.get('timestamp')
            })

        return open_positions


class ExitExecutor:
    """
    Executes position exits (sells) when triggered by PositionMonitor.
    """

    def __init__(self, client, rate_limiter):
        """
        Initialize exit executor.

        Args:
            client: ClobClient for order execution.
            rate_limiter: APIRateLimiter for throttling.
        """
        self.client = client
        self.rate_limiter = rate_limiter

    async def execute_exit(
        self,
        position: Dict,
        reason: str,
        current_yes_price: float,
        current_no_price: float
    ) -> Dict:
        """
        Execute an exit (sell both YES and NO tokens).

        For arbitrage positions, we hold both YES and NO.
        At exit, we can either:
        1. Sell both at market price (immediate exit)
        2. Wait for resolution ($1.00 guaranteed)

        This method sells at market for immediate exit.

        Args:
            position: Position dict with market_id, shares, etc.
            reason: Exit reason (STOP_LOSS, TAKE_PROFIT).
            current_yes_price: Current YES bid price.
            current_no_price: Current NO bid price.

        Returns:
            Exit result dict with success status and details.
        """
        from py_clob_client.clob_types import OrderArgs, OrderType
        from py_clob_client.order_builder.constants import SELL

        market_id = position.get('market_id')
        shares = position.get('shares', 0)

        if not market_id or shares <= 0:
            return {'success': False, 'error': 'Invalid position'}

        logger.info(
            f"Executing {reason} exit for {market_id}: "
            f"{shares} shares @ YES={current_yes_price:.4f}, NO={current_no_price:.4f}"
        )

        try:
            # Rate limit
            await self.rate_limiter.acquire('orders')
            await self.rate_limiter.acquire('orders')

            loop = asyncio.get_running_loop()

            # Get token IDs from position or market details
            yes_token = position.get('yes_token')
            no_token = position.get('no_token')

            if not yes_token or not no_token:
                return {'success': False, 'error': 'Missing token IDs'}

            # Execute sell orders in parallel
            # Using limit orders at current bid price for better fills
            t1 = loop.run_in_executor(
                None,
                lambda: self._place_sell_order(yes_token, shares, current_yes_price)
            )
            t2 = loop.run_in_executor(
                None,
                lambda: self._place_sell_order(no_token, shares, current_no_price)
            )

            results = await asyncio.gather(t1, t2, return_exceptions=True)

            success = all(
                not isinstance(r, Exception) and r is not None
                for r in results
            )

            if success:
                exit_value = shares * (current_yes_price + current_no_price)
                entry_cost = position.get('entry_cost', 0)
                realized_pnl = exit_value - entry_cost

                logger.info(
                    f"Exit executed successfully: "
                    f"Value=${exit_value:.2f}, P&L=${realized_pnl:.2f}"
                )

                return {
                    'success': True,
                    'reason': reason,
                    'market_id': market_id,
                    'shares': shares,
                    'exit_value': exit_value,
                    'entry_cost': entry_cost,
                    'realized_pnl': realized_pnl,
                    'timestamp': datetime.now()
                }
            else:
                logger.error(f"Exit execution failed: {results}")
                return {
                    'success': False,
                    'error': str(results),
                    'market_id': market_id
                }

        except Exception as e:
            logger.error(f"Exit execution error: {e}")
            return {'success': False, 'error': str(e)}

    def _place_sell_order(self, token_id: str, amount: float, price: float):
        """Place a sell order (synchronous, for run_in_executor)."""
        from py_clob_client.clob_types import OrderArgs, OrderType
        from py_clob_client.order_builder.constants import SELL

        if self.client is None:
            raise RuntimeError("Client not initialized")

        try:
            resp = self.client.create_and_post_order(
                OrderArgs(
                    price=price,
                    size=amount,
                    side=SELL,
                    token_id=token_id,
                    order_type=OrderType.GTC  # Good-til-canceled for sells
                )
            )
            logger.debug(f"Sell order placed: {resp}")
            return resp
        except Exception as e:
            logger.error(f"Sell order failed for {token_id}: {e}")
            raise


class BalanceManager:
    """
    Manages balance verification before trades.
    """

    def __init__(self, client, fallback_balance: float = 1000.0):
        """
        Initialize balance manager.

        Args:
            client: ClobClient for balance queries.
            fallback_balance: Balance to use if API fails.
        """
        self.client = client
        self.fallback_balance = fallback_balance
        self._cached_balance: Optional[float] = None
        self._last_check: Optional[datetime] = None
        self._cache_ttl: float = 30.0  # Cache balance for 30 seconds

    async def get_balance(self, force_refresh: bool = False) -> float:
        """
        Get current USDC balance.

        Args:
            force_refresh: Bypass cache and fetch fresh balance.

        Returns:
            Current USDC balance.
        """
        now = datetime.now()

        # Check cache
        if (
            not force_refresh
            and self._cached_balance is not None
            and self._last_check is not None
        ):
            elapsed = (now - self._last_check).total_seconds()
            if elapsed < self._cache_ttl:
                return self._cached_balance

        # Fetch fresh balance
        try:
            loop = asyncio.get_running_loop()
            balance = await loop.run_in_executor(
                None,
                self._fetch_balance
            )
            self._cached_balance = balance
            self._last_check = now
            return balance
        except Exception as e:
            logger.error(f"Failed to fetch balance: {e}")
            return self._cached_balance or self.fallback_balance

    def _fetch_balance(self) -> float:
        """Fetch balance from API (synchronous)."""
        if self.client is None:
            return self.fallback_balance

        try:
            # Get collateral balance (USDC)
            balance_info = self.client.get_balance()
            if isinstance(balance_info, dict):
                return float(balance_info.get('balance', self.fallback_balance))
            return float(balance_info) if balance_info else self.fallback_balance
        except Exception as e:
            logger.error(f"Balance fetch error: {e}")
            return self.fallback_balance

    async def can_trade(
        self,
        required_amount: float,
        levels_yes: int = 1,
        levels_no: int = 1
    ) -> tuple:
        """
        Check if we have sufficient balance for a trade.
        PHASE 5: Uses dynamic buffer based on order book depth.

        Args:
            required_amount: USDC amount needed for the trade.
            levels_yes: Number of YES order book levels consumed.
            levels_no: Number of NO order book levels consumed.

        Returns:
            Tuple of (can_trade: bool, current_balance: float, message: str).
        """
        balance = await self.get_balance()

        # PHASE 5: Dynamic buffer based on order book depth
        buffer = self.calculate_dynamic_buffer(levels_yes, levels_no)
        required_with_buffer = required_amount * buffer

        if balance >= required_with_buffer:
            return True, balance, f"Sufficient balance (buffer: {buffer:.1%})"
        else:
            return (
                False,
                balance,
                f"Insufficient balance: ${balance:.2f} < ${required_with_buffer:.2f} (buffer: {buffer:.1%})"
            )

    def calculate_dynamic_buffer(self, levels_yes: int = 1, levels_no: int = 1) -> float:
        """
        Calculate dynamic buffer based on order book depth consumed.
        PHASE 5: Higher depth = more slippage risk = larger buffer needed.

        Args:
            levels_yes: Number of YES order book levels consumed.
            levels_no: Number of NO order book levels consumed.

        Returns:
            Buffer multiplier (1.02 to 1.10).
        """
        base_buffer = 1.02  # 2% minimum buffer
        depth_penalty = 0.005  # 0.5% per level beyond first

        total_levels = levels_yes + levels_no
        extra_levels = max(0, total_levels - 2)  # First level of each is "free"

        depth_buffer = extra_levels * depth_penalty

        # Cap at 10% max buffer
        final_buffer = min(base_buffer + depth_buffer, 1.10)

        return final_buffer

    def invalidate_cache(self):
        """Invalidate the balance cache (call after trades)."""
        self._cached_balance = None
        self._last_check = None
