"""
Backtest Engine for Polymarket Arbitrage Bot.

Replays historical order book data through the arbitrage detection logic
to simulate trading performance.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Tuple

from backend.services.data_collector import DataCollector

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    """Configuration for backtest run."""
    start_time: datetime
    end_time: datetime
    initial_capital: float = 10000.0
    capital_per_trade: float = 100.0
    min_profit_margin: float = 0.02
    max_slippage: float = 0.005
    cooldown_seconds: float = 30.0
    playback_speed: float = 100.0  # 100 = fast, 1.0 = real-time
    markets_filter: Optional[List[str]] = None  # None = all markets
    platforms_filter: Optional[List[str]] = None  # None = all platforms ('polymarket', 'kalshi')


@dataclass
class BacktestTrade:
    """Record of simulated trade during backtest."""
    timestamp: datetime
    market_id: str
    shares: float
    yes_price: float
    no_price: float
    entry_cost: float
    expected_pnl: float
    roi: float
    levels_yes: int
    levels_no: int
    platform: str = "polymarket"  # Platform where trade was executed

    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp,
            'market_id': self.market_id,
            'shares': self.shares,
            'yes_price': self.yes_price,
            'no_price': self.no_price,
            'entry_cost': self.entry_cost,
            'expected_pnl': self.expected_pnl,
            'roi': self.roi,
            'levels_yes': self.levels_yes,
            'levels_no': self.levels_no,
            'platform': self.platform
        }


@dataclass
class BacktestResult:
    """Complete results from a backtest run."""
    config: BacktestConfig
    trades: List[BacktestTrade] = field(default_factory=list)

    # Performance metrics
    total_trades: int = 0
    winning_trades: int = 0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    avg_roi: float = 0.0

    # Capital tracking
    starting_capital: float = 0.0
    ending_capital: float = 0.0
    peak_capital: float = 0.0

    # Time metrics
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: float = 0.0

    # Opportunity analysis
    opportunities_detected: int = 0
    opportunities_executed: int = 0
    opportunities_skipped_cooldown: int = 0
    opportunities_skipped_capital: int = 0
    opportunities_skipped_unprofitable: int = 0

    # Per-day breakdown
    daily_pnl: Dict[str, float] = field(default_factory=dict)

    def calculate_metrics(self):
        """Calculate derived metrics after backtest completes."""
        if not self.trades:
            return

        self.total_trades = len(self.trades)
        self.winning_trades = sum(1 for t in self.trades if t.expected_pnl > 0)
        self.total_pnl = sum(t.expected_pnl for t in self.trades)

        # Calculate drawdown
        capital = self.starting_capital
        peak = capital
        max_dd = 0.0

        for trade in self.trades:
            capital += trade.expected_pnl
            peak = max(peak, capital)
            dd = (peak - capital) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

            # Track daily P&L
            day_key = trade.timestamp.strftime('%Y-%m-%d') if isinstance(trade.timestamp, datetime) else trade.timestamp[:10]
            self.daily_pnl[day_key] = self.daily_pnl.get(day_key, 0) + trade.expected_pnl

        self.max_drawdown = max_dd
        self.ending_capital = capital
        self.peak_capital = peak

        # Win rate
        self.win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0

        # Average ROI
        self.avg_roi = sum(t.roi for t in self.trades) / len(self.trades) if self.trades else 0

        # Duration
        if self.start_time and self.end_time:
            self.duration_seconds = (self.end_time - self.start_time).total_seconds()

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            'config': {
                'start_time': self.config.start_time.isoformat(),
                'end_time': self.config.end_time.isoformat(),
                'initial_capital': self.config.initial_capital,
                'capital_per_trade': self.config.capital_per_trade,
                'min_profit_margin': self.config.min_profit_margin,
                'cooldown_seconds': self.config.cooldown_seconds
            },
            'metrics': {
                'total_trades': self.total_trades,
                'winning_trades': self.winning_trades,
                'total_pnl': self.total_pnl,
                'max_drawdown': self.max_drawdown,
                'win_rate': self.win_rate,
                'avg_roi': self.avg_roi,
                'starting_capital': self.starting_capital,
                'ending_capital': self.ending_capital,
                'peak_capital': self.peak_capital
            },
            'opportunities': {
                'detected': self.opportunities_detected,
                'executed': self.opportunities_executed,
                'skipped_cooldown': self.opportunities_skipped_cooldown,
                'skipped_capital': self.opportunities_skipped_capital,
                'skipped_unprofitable': self.opportunities_skipped_unprofitable
            },
            'daily_pnl': self.daily_pnl,
            'trades': [t.to_dict() for t in self.trades]
        }

    def export_to_csv(self, filepath: str) -> str:
        """Export backtest results to CSV file."""
        import csv

        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)

            # Summary section
            writer.writerow(["# Backtest Summary"])
            writer.writerow(["Start Date", self.config.start_time.strftime('%Y-%m-%d %H:%M')])
            writer.writerow(["End Date", self.config.end_time.strftime('%Y-%m-%d %H:%M')])
            writer.writerow(["Initial Capital", f"${self.starting_capital:.2f}"])
            writer.writerow(["Final Capital", f"${self.ending_capital:.2f}"])
            writer.writerow(["Total P&L", f"${self.total_pnl:.2f}"])
            writer.writerow(["Total Trades", self.total_trades])
            writer.writerow(["Win Rate", f"{self.win_rate:.1f}%"])
            writer.writerow(["Max Drawdown", f"{self.max_drawdown * 100:.1f}%"])
            writer.writerow(["Avg ROI", f"{self.avg_roi:.2f}%"])
            writer.writerow([])

            # Daily P&L section
            writer.writerow(["# Daily P&L"])
            writer.writerow(["Date", "P&L"])
            for day, pnl in sorted(self.daily_pnl.items()):
                writer.writerow([day, f"${pnl:.2f}"])
            writer.writerow([])

            # Trades section
            writer.writerow(["# Trade Details"])
            writer.writerow([
                "Timestamp", "Platform", "Market ID", "Shares", "YES Price", "NO Price",
                "Entry Cost", "Expected P&L", "ROI %", "Levels YES", "Levels NO"
            ])

            for trade in self.trades:
                ts = trade.timestamp.strftime('%Y-%m-%d %H:%M:%S') if isinstance(trade.timestamp, datetime) else trade.timestamp
                writer.writerow([
                    ts,
                    trade.platform,
                    trade.market_id,
                    f"{trade.shares:.2f}",
                    f"{trade.yes_price:.4f}",
                    f"{trade.no_price:.4f}",
                    f"{trade.entry_cost:.2f}",
                    f"{trade.expected_pnl:.2f}",
                    f"{trade.roi:.2f}",
                    trade.levels_yes,
                    trade.levels_no
                ])

        return filepath


class MarketImpactResult:
    """Result of market impact calculation (mirrors the one in arbitrage.py)."""
    def __init__(self, shares: float, effective_price: float, total_cost: float,
                 levels_consumed: int, has_sufficient_liquidity: bool):
        self.shares = shares
        self.effective_price = effective_price
        self.total_cost = total_cost
        self.levels_consumed = levels_consumed
        self.has_sufficient_liquidity = has_sufficient_liquidity


class BacktestEngine:
    """
    Historical replay engine for backtesting arbitrage strategies.

    Features:
    - Realistic order book replay from DataCollector snapshots
    - Configurable playback speed
    - Market impact simulation using existing calculator logic
    - Progress callbacks for UI updates
    """

    def __init__(self, data_collector: DataCollector):
        """
        Initialize backtest engine.

        Args:
            data_collector: DataCollector instance with historical data
        """
        self.data_collector = data_collector
        self.on_progress: Optional[Callable[[float, str], None]] = None
        self.on_trade: Optional[Callable[[BacktestTrade], None]] = None
        self._cancel_requested = False

    @staticmethod
    def calculate_effective_cost(order_book: List[dict], shares_needed: float) -> MarketImpactResult:
        """
        Calculate the average price to buy X shares across multiple price levels.
        (Replicates MarketImpactCalculator logic for standalone use)
        """
        if not order_book or shares_needed <= 0:
            return MarketImpactResult(0, 0, 0, 0, False)

        total_cost = 0.0
        shares_filled = 0.0
        levels_consumed = 0

        for level in order_book:
            # Handle both dict and already-parsed formats
            if isinstance(level, dict):
                price = float(level.get('price', 0))
                size = float(level.get('size', 0))
            else:
                continue

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
        (Replicates MarketImpactCalculator logic for standalone use)
        """
        low, high = 0.0, max_shares
        best_shares = 0.0
        best_yes_price = 0.0
        best_no_price = 0.0

        # First check if even 1 share is profitable
        yes_result = BacktestEngine.calculate_effective_cost(yes_book, 1.0)
        no_result = BacktestEngine.calculate_effective_cost(no_book, 1.0)

        if not yes_result.has_sufficient_liquidity or not no_result.has_sufficient_liquidity:
            return 0.0, 0.0, 0.0

        if yes_result.effective_price + no_result.effective_price >= max_combined_cost:
            return 0.0, 0.0, 0.0

        # Binary search for optimal size
        iterations = 0
        max_iterations = 50

        while high - low > precision and iterations < max_iterations:
            iterations += 1
            mid = (low + high) / 2

            yes_result = BacktestEngine.calculate_effective_cost(yes_book, mid)
            no_result = BacktestEngine.calculate_effective_cost(no_book, mid)

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

    async def run_backtest(self, config: BacktestConfig) -> BacktestResult:
        """
        Execute backtest with given configuration.

        Args:
            config: BacktestConfig with parameters

        Returns:
            BacktestResult with all trades and metrics
        """
        self._cancel_requested = False
        result = BacktestResult(
            config=config,
            starting_capital=config.initial_capital,
            start_time=config.start_time,
            end_time=config.end_time
        )

        # Load historical data
        start_ts = int(config.start_time.timestamp() * 1000)
        end_ts = int(config.end_time.timestamp() * 1000)

        # Determine platform filter for data loading
        platform_filter = None
        if config.platforms_filter and len(config.platforms_filter) == 1:
            platform_filter = config.platforms_filter[0]

        logger.info(f"Loading snapshots from {config.start_time} to {config.end_time}")
        if config.platforms_filter:
            logger.info(f"Filtering by platforms: {config.platforms_filter}")

        snapshots = self.data_collector.get_snapshots_for_period(
            start_ts, end_ts,
            market_id=config.markets_filter[0] if config.markets_filter and len(config.markets_filter) == 1 else None,
            platform=platform_filter
        )

        if not snapshots:
            logger.warning("No snapshots found for the specified period")
            return result

        logger.info(f"Loaded {len(snapshots)} snapshots for replay")

        # Build market state
        order_books: Dict[str, dict] = {}  # token_id -> {asks, bids}
        token_to_market: Dict[str, str] = {}  # token_id -> market_id
        market_tokens: Dict[str, List[str]] = {}  # market_id -> [token_ids]
        cooldown_tracker: Dict[str, int] = {}  # market_id -> last_trade_ts

        capital = config.initial_capital
        total_snapshots = len(snapshots)

        for i, snapshot in enumerate(snapshots):
            if self._cancel_requested:
                logger.info("Backtest cancelled by user")
                break

            # Progress callback
            if self.on_progress and i % 100 == 0:
                progress = (i / total_snapshots) * 100
                self.on_progress(progress, f"Processing {i}/{total_snapshots} snapshots")

            # Update order book state
            token_id = snapshot['token_id']
            market_id = snapshot['market_id']
            platform = snapshot.get('platform', 'polymarket')  # Default to polymarket for legacy data

            # Filter by platforms if multiple specified (single platform filtering done at query level)
            if config.platforms_filter and len(config.platforms_filter) > 1:
                if platform not in config.platforms_filter:
                    continue

            # Parse order book JSON
            try:
                asks = json.loads(snapshot['asks_json']) if isinstance(snapshot['asks_json'], str) else snapshot['asks_json']
                bids = json.loads(snapshot['bids_json']) if isinstance(snapshot['bids_json'], str) else snapshot['bids_json']
            except json.JSONDecodeError:
                continue

            order_books[token_id] = {'asks': asks, 'bids': bids, 'platform': platform}
            token_to_market[token_id] = market_id

            # Track tokens per market
            if market_id not in market_tokens:
                market_tokens[market_id] = []
            if token_id not in market_tokens[market_id]:
                market_tokens[market_id].append(token_id)

            # Filter markets if specified
            if config.markets_filter and market_id not in config.markets_filter:
                continue

            # Check for arbitrage opportunity
            trade = self._check_and_simulate_trade(
                market_id=market_id,
                order_books=order_books,
                market_tokens=market_tokens,
                config=config,
                current_capital=capital,
                cooldown_tracker=cooldown_tracker,
                current_ts=snapshot['timestamp'],
                result=result,
                platform=platform
            )

            if trade:
                result.trades.append(trade)
                capital -= trade.entry_cost  # Deduct entry cost
                # In reality, capital returns at resolution, but for simulation we track differently
                # Assume profit is realized immediately for simplicity
                capital += trade.entry_cost + trade.expected_pnl
                cooldown_tracker[market_id] = snapshot['timestamp']
                result.opportunities_executed += 1

                if self.on_trade:
                    self.on_trade(trade)

            # Simulate playback speed delay (only for slow playback)
            if config.playback_speed < 10:
                await asyncio.sleep(0.001 / config.playback_speed)

        # Final progress update
        if self.on_progress:
            self.on_progress(100.0, "Backtest complete")

        result.calculate_metrics()
        logger.info(f"Backtest complete: {result.total_trades} trades, P&L: ${result.total_pnl:.2f}")

        return result

    def _check_and_simulate_trade(
        self,
        market_id: str,
        order_books: Dict[str, dict],
        market_tokens: Dict[str, List[str]],
        config: BacktestConfig,
        current_capital: float,
        cooldown_tracker: Dict[str, int],
        current_ts: int,
        result: BacktestResult,
        platform: str = "polymarket"
    ) -> Optional[BacktestTrade]:
        """
        Check for arbitrage opportunity and simulate trade using market metadata.
        """
        # PHASE 4: Use market metadata for accurate token mapping
        metadata = self.data_collector.get_market_metadata(market_id)
        if not metadata or not metadata.get('yes_token_id') or not metadata.get('no_token_id'):
            # Fallback to order in market_tokens if metadata missing
            tokens = market_tokens.get(market_id, [])
            if len(tokens) < 2:
                return None
            yes_token = tokens[0]
            no_token = tokens[1]
        else:
            yes_token = metadata['yes_token_id']
            no_token = metadata['no_token_id']

        # Get order books
        yes_asks = order_books.get(yes_token, {}).get('asks', [])
        no_asks = order_books.get(no_token, {}).get('asks', [])

        if not yes_asks or not no_asks:
            return None

        # Check cooldown
        last_trade = cooldown_tracker.get(market_id, 0)
        if (current_ts - last_trade) < config.cooldown_seconds * 1000:
            result.opportunities_skipped_cooldown += 1
            return None

        # Calculate optimal trade using market impact calculator
        # Sync with MIN_PROFIT_MARGIN from config
        target_cost = 1.0 - config.min_profit_margin
        
        # Use capital_per_trade for max shares calculation
        max_shares = config.capital_per_trade / 0.5  # Approximate max shares

        optimal_shares, eff_yes, eff_no = self.find_optimal_trade_size(
            yes_asks, no_asks,
            max_combined_cost=target_cost,
            max_shares=max_shares
        )

        result.opportunities_detected += 1

        if optimal_shares <= 0:
            result.opportunities_skipped_unprofitable += 1
            return None

        effective_cost = eff_yes + eff_no
        entry_cost = optimal_shares * effective_cost

        # Check capital
        if entry_cost > current_capital:
            result.opportunities_skipped_capital += 1
            return None

        expected_pnl = optimal_shares * (1.0 - effective_cost)
        roi = ((1.0 - effective_cost) / effective_cost * 100) if effective_cost > 0 else 0

        # Calculate levels consumed
        yes_result = self.calculate_effective_cost(yes_asks, optimal_shares)
        no_result = self.calculate_effective_cost(no_asks, optimal_shares)

        return BacktestTrade(
            timestamp=datetime.fromtimestamp(current_ts / 1000),
            market_id=market_id,
            shares=optimal_shares,
            yes_price=eff_yes,
            no_price=eff_no,
            entry_cost=entry_cost,
            expected_pnl=expected_pnl,
            roi=roi,
            levels_yes=yes_result.levels_consumed,
            levels_no=no_result.levels_consumed,
            platform=platform
        )

    def cancel(self):
        """Request cancellation of running backtest."""
        self._cancel_requested = True
        logger.info("Backtest cancellation requested")

    def get_available_data_range(self) -> Tuple[Optional[datetime], Optional[datetime]]:
        """Return available date range for backtesting."""
        min_ts, max_ts = self.data_collector.get_available_date_range()

        if min_ts is None or max_ts is None:
            return None, None

        return (
            datetime.fromtimestamp(min_ts / 1000),
            datetime.fromtimestamp(max_ts / 1000)
        )

    def get_available_markets(self) -> List[Dict]:
        """Return list of markets with available data."""
        return self.data_collector.get_markets_with_data()

    def get_data_stats(self) -> Dict:
        """Return statistics about available data."""
        min_date, max_date = self.get_available_data_range()
        snapshot_count = self.data_collector.get_snapshot_count()
        opportunity_count = self.data_collector.get_opportunity_count()
        markets = self.get_available_markets()

        return {
            'has_data': snapshot_count > 0,
            'snapshot_count': snapshot_count,
            'opportunity_count': opportunity_count,
            'market_count': len(markets),
            'date_range': {
                'start': min_date.isoformat() if min_date else None,
                'end': max_date.isoformat() if max_date else None
            },
            'markets': markets[:10]  # Top 10 markets by snapshot count
        }
