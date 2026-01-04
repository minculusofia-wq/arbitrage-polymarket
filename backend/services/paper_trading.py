"""
Paper Trading Service for Polymarket Arbitrage Bot.

Provides simulated trade execution for backtesting and paper trading modes.
Uses Strategy Pattern to allow seamless switching between live and paper modes.
"""

import asyncio
import json
import random
import sqlite3
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class PaperTrade:
    """Simulated trade record."""
    id: int
    market_id: str
    yes_token: str
    no_token: str
    shares: float
    yes_price: float
    no_price: float
    entry_cost: float
    expected_pnl: float
    roi: float
    timestamp: datetime
    status: str = "SIMULATED"
    levels_yes: int = 0
    levels_no: int = 0

    def to_dict(self) -> Dict:
        """Convert to dictionary for storage/display."""
        return {
            'id': self.id,
            'market_id': self.market_id,
            'yes_token': self.yes_token,
            'no_token': self.no_token,
            'shares': self.shares,
            'yes_price': self.yes_price,
            'no_price': self.no_price,
            'entry_cost': self.entry_cost,
            'expected_pnl': self.expected_pnl,
            'roi': self.roi,
            'timestamp': self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp,
            'status': self.status,
            'levels_yes': self.levels_yes,
            'levels_no': self.levels_no
        }


class ITradeExecutor(ABC):
    """
    Interface for trade execution - enables paper/live switching.

    Implementations:
    - LiveTradeExecutor: Real trades via Polymarket API
    - PaperTradeExecutor: Simulated trades for backtesting
    """

    @abstractmethod
    async def execute_trade(
        self,
        market_id: str,
        yes_token: str,
        no_token: str,
        shares: float,
        price_yes: float,
        price_no: float,
        levels_yes: int = 0,
        levels_no: int = 0
    ) -> Dict[str, Any]:
        """
        Execute a trade and return result.

        Returns:
            Dict with keys:
            - success: bool
            - trade: trade record (if success)
            - reason: failure reason (if failed)
            - mode: "LIVE" or "PAPER"
        """
        pass

    @abstractmethod
    def get_mode(self) -> str:
        """Return 'LIVE' or 'PAPER'."""
        pass

    @abstractmethod
    def get_balance(self) -> float:
        """Return current balance (virtual for paper, real for live)."""
        pass


class LiveTradeExecutor(ITradeExecutor):
    """
    Real trade execution - wraps existing order placement logic.

    This is a thin wrapper that delegates to the actual ClobClient.
    """

    def __init__(self, client, rate_limiter, place_order_func):
        """
        Initialize live executor.

        Args:
            client: ClobClient instance
            rate_limiter: APIRateLimiter instance
            place_order_func: Reference to ArbitrageBot._place_order method
        """
        self.client = client
        self.rate_limiter = rate_limiter
        self._place_order = place_order_func
        self._balance: float = 0.0

    async def execute_trade(
        self,
        market_id: str,
        yes_token: str,
        no_token: str,
        shares: float,
        price_yes: float,
        price_no: float,
        levels_yes: int = 0,
        levels_no: int = 0
    ) -> Dict[str, Any]:
        """Execute real trade via Polymarket API."""
        try:
            # Place both orders in parallel
            yes_task = self._place_order(yes_token, shares, price_yes)
            no_task = self._place_order(no_token, shares, price_no)

            yes_result, no_result = await asyncio.gather(yes_task, no_task, return_exceptions=True)

            # Check for exceptions
            if isinstance(yes_result, Exception):
                return {"success": False, "reason": f"YES order failed: {yes_result}", "mode": "LIVE"}
            if isinstance(no_result, Exception):
                return {"success": False, "reason": f"NO order failed: {no_result}", "mode": "LIVE"}

            # Check results
            if not yes_result or not no_result:
                return {"success": False, "reason": "Order placement returned None", "mode": "LIVE"}

            entry_cost = shares * (price_yes + price_no)
            expected_pnl = shares * 1.0 - entry_cost
            roi = (expected_pnl / entry_cost * 100) if entry_cost > 0 else 0

            return {
                "success": True,
                "mode": "LIVE",
                "trade": {
                    "market_id": market_id,
                    "yes_token": yes_token,
                    "no_token": no_token,
                    "shares": shares,
                    "yes_price": price_yes,
                    "no_price": price_no,
                    "entry_cost": entry_cost,
                    "expected_pnl": expected_pnl,
                    "roi": roi,
                    "timestamp": datetime.now(),
                    "status": "EXECUTED",
                    "levels_yes": levels_yes,
                    "levels_no": levels_no
                }
            }
        except Exception as e:
            logger.error(f"Live trade execution failed: {e}")
            return {"success": False, "reason": str(e), "mode": "LIVE"}

    def get_mode(self) -> str:
        return "LIVE"

    def get_balance(self) -> float:
        return self._balance

    def set_balance(self, balance: float):
        """Update cached balance from external source."""
        self._balance = balance


class PaperTradeExecutor(ITradeExecutor):
    """
    Simulated trade execution with realistic modeling.

    Features:
    - Virtual balance tracking
    - Configurable fill probability
    - Realistic slippage modeling
    - SQLite persistence for paper trades
    """

    def __init__(
        self,
        db_path: str = "data/paper_trades.db",
        initial_balance: float = 10000.0,
        fill_probability: float = 0.95,
        slippage_bps: float = 5.0
    ):
        """
        Initialize paper trade executor.

        Args:
            db_path: Path to SQLite database for paper trades
            initial_balance: Starting virtual balance
            fill_probability: Probability of fill (0.0 to 1.0)
            slippage_bps: Average slippage in basis points
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.virtual_balance = initial_balance
        self.initial_balance = initial_balance
        self.fill_probability = fill_probability
        self.slippage_bps = slippage_bps

        self.positions: List[PaperTrade] = []
        self._trade_count = 0

        self._init_db()
        self._load_state()

    def _init_db(self):
        """Create paper trades table."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS paper_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    market_id TEXT NOT NULL,
                    yes_token TEXT,
                    no_token TEXT,
                    shares REAL NOT NULL,
                    yes_price REAL NOT NULL,
                    no_price REAL NOT NULL,
                    entry_cost REAL NOT NULL,
                    expected_pnl REAL NOT NULL,
                    roi REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    status TEXT DEFAULT 'SIMULATED',
                    levels_yes INTEGER DEFAULT 0,
                    levels_no INTEGER DEFAULT 0,
                    virtual_balance_after REAL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS paper_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    virtual_balance REAL NOT NULL,
                    trade_count INTEGER NOT NULL,
                    last_updated TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_paper_trades_timestamp
                ON paper_trades(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_paper_trades_market
                ON paper_trades(market_id)
            """)

    def _load_state(self):
        """Load previous state from database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT virtual_balance, trade_count FROM paper_state WHERE id = 1"
                )
                row = cursor.fetchone()
                if row:
                    self.virtual_balance = row[0]
                    self._trade_count = row[1]
                    logger.info(f"Loaded paper trading state: balance=${self.virtual_balance:.2f}, trades={self._trade_count}")
        except Exception as e:
            logger.warning(f"Could not load paper trading state: {e}")

    def _save_state(self):
        """Persist current state to database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO paper_state (id, virtual_balance, trade_count, last_updated)
                VALUES (1, ?, ?, ?)
            """, (self.virtual_balance, self._trade_count, datetime.now().isoformat()))

    async def execute_trade(
        self,
        market_id: str,
        yes_token: str,
        no_token: str,
        shares: float,
        price_yes: float,
        price_no: float,
        levels_yes: int = 0,
        levels_no: int = 0
    ) -> Dict[str, Any]:
        """
        Simulate trade execution with realistic fill modeling.

        1. Apply slippage model to prices
        2. Simulate fill probability
        3. Deduct from virtual balance
        4. Record in database
        5. Return simulated result
        """
        # Simulate fill probability
        if random.random() > self.fill_probability:
            logger.info(f"[PAPER] Simulated no-fill for {market_id}")
            return {
                "success": False,
                "reason": "SIMULATED_NO_FILL",
                "mode": "PAPER"
            }

        # Apply slippage (gaussian distribution around 0)
        slippage = random.gauss(0, self.slippage_bps / 10000)
        adj_yes = price_yes * (1 + abs(slippage))  # Slippage always adverse
        adj_no = price_no * (1 + abs(slippage))

        entry_cost = shares * (adj_yes + adj_no)

        # Check virtual balance
        if entry_cost > self.virtual_balance:
            logger.warning(f"[PAPER] Insufficient virtual balance: need ${entry_cost:.2f}, have ${self.virtual_balance:.2f}")
            return {
                "success": False,
                "reason": "INSUFFICIENT_VIRTUAL_BALANCE",
                "mode": "PAPER",
                "required": entry_cost,
                "available": self.virtual_balance
            }

        # Deduct balance
        self.virtual_balance -= entry_cost

        # Calculate expected P&L (assumes resolution at $1)
        expected_pnl = shares * 1.0 - entry_cost
        roi = (expected_pnl / entry_cost * 100) if entry_cost > 0 else 0

        # Create trade record
        self._trade_count += 1
        trade = PaperTrade(
            id=self._trade_count,
            market_id=market_id,
            yes_token=yes_token,
            no_token=no_token,
            shares=shares,
            yes_price=adj_yes,
            no_price=adj_no,
            entry_cost=entry_cost,
            expected_pnl=expected_pnl,
            roi=roi,
            timestamp=datetime.now(),
            status="SIMULATED",
            levels_yes=levels_yes,
            levels_no=levels_no
        )

        # Save to database
        self._save_trade(trade)
        self._save_state()

        self.positions.append(trade)

        logger.info(f"[PAPER] Executed trade: {shares:.1f} shares @ ${entry_cost:.2f}, P&L: ${expected_pnl:.2f} ({roi:.2f}%)")

        return {
            "success": True,
            "trade": trade.to_dict(),
            "mode": "PAPER",
            "virtual_balance": self.virtual_balance
        }

    def _save_trade(self, trade: PaperTrade):
        """Save trade to database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO paper_trades
                (market_id, yes_token, no_token, shares, yes_price, no_price,
                 entry_cost, expected_pnl, roi, timestamp, status,
                 levels_yes, levels_no, virtual_balance_after)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade.market_id,
                trade.yes_token,
                trade.no_token,
                trade.shares,
                trade.yes_price,
                trade.no_price,
                trade.entry_cost,
                trade.expected_pnl,
                trade.roi,
                trade.timestamp.isoformat() if isinstance(trade.timestamp, datetime) else trade.timestamp,
                trade.status,
                trade.levels_yes,
                trade.levels_no,
                self.virtual_balance
            ))

    def get_mode(self) -> str:
        return "PAPER"

    def get_balance(self) -> float:
        return self.virtual_balance

    def get_trades(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        """Get paper trades from database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM paper_trades
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
            return [dict(row) for row in cursor.fetchall()]

    def get_statistics(self) -> Dict:
        """Return paper trading statistics."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT
                    COUNT(*) as total_trades,
                    COALESCE(SUM(expected_pnl), 0) as total_pnl,
                    COALESCE(AVG(roi), 0) as avg_roi,
                    COALESCE(SUM(CASE WHEN expected_pnl > 0 THEN 1 ELSE 0 END), 0) as wins,
                    COALESCE(SUM(CASE WHEN expected_pnl <= 0 THEN 1 ELSE 0 END), 0) as losses,
                    COALESCE(SUM(entry_cost), 0) as total_invested
                FROM paper_trades
            """)
            row = cursor.fetchone()

            total_trades = row[0] or 0
            wins = row[3] or 0

            return {
                "total_trades": total_trades,
                "total_pnl": row[1] or 0,
                "avg_roi": row[2] or 0,
                "wins": wins,
                "losses": row[4] or 0,
                "win_rate": (wins / total_trades * 100) if total_trades > 0 else 0,
                "total_invested": row[5] or 0,
                "current_balance": self.virtual_balance,
                "initial_balance": self.initial_balance,
                "net_return": ((self.virtual_balance - self.initial_balance) / self.initial_balance * 100)
                             if self.initial_balance > 0 else 0
            }

    def reset(self, initial_balance: Optional[float] = None):
        """Reset paper trading state."""
        if initial_balance is not None:
            self.initial_balance = initial_balance

        self.virtual_balance = self.initial_balance
        self.positions = []
        self._trade_count = 0

        # Clear database
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM paper_trades")
            conn.execute("DELETE FROM paper_state")

        self._save_state()
        logger.info(f"[PAPER] Reset paper trading with balance ${self.initial_balance:.2f}")

    def export_to_csv(self, filepath: str) -> str:
        """Export paper trades to CSV file."""
        import csv

        trades = self.get_trades(limit=10000)
        stats = self.get_statistics()

        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)

            # Write summary header
            writer.writerow(["# Paper Trading Summary"])
            writer.writerow(["Initial Balance", f"${self.initial_balance:.2f}"])
            writer.writerow(["Current Balance", f"${self.virtual_balance:.2f}"])
            writer.writerow(["Total P&L", f"${stats['total_pnl']:.2f}"])
            writer.writerow(["Total Trades", stats['total_trades']])
            writer.writerow(["Win Rate", f"{stats['win_rate']:.1f}%"])
            writer.writerow([])

            # Write trades header
            writer.writerow([
                "Timestamp", "Market ID", "Shares", "YES Price", "NO Price",
                "Entry Cost", "Expected P&L", "ROI %", "Status", "Balance After"
            ])

            # Write trades
            for trade in trades:
                writer.writerow([
                    trade['timestamp'],
                    trade['market_id'],
                    f"{trade['shares']:.2f}",
                    f"{trade['yes_price']:.4f}",
                    f"{trade['no_price']:.4f}",
                    f"{trade['entry_cost']:.2f}",
                    f"{trade['expected_pnl']:.2f}",
                    f"{trade['roi']:.2f}",
                    trade['status'],
                    f"{trade['virtual_balance_after']:.2f}"
                ])

        return filepath
