"""
Trade Storage - SQLite persistence for trades.

Provides persistent storage for trade history, allowing:
- Trade recovery after restart
- Historical P&L analysis
- Daily/total statistics
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional


class TradeStorage:
    """Persistent SQLite storage for trades."""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize trade storage.

        Args:
            db_path: Custom path to database file. Defaults to data/trades.db
        """
        self.db_path = Path(db_path) if db_path else Path("data/trades.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Create tables and indexes if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    market_id TEXT NOT NULL,
                    side TEXT DEFAULT 'BOTH',
                    shares REAL NOT NULL,
                    entry_cost REAL NOT NULL,
                    exit_value REAL,
                    pnl REAL,
                    roi REAL,
                    yes_price REAL,
                    no_price REAL,
                    status TEXT DEFAULT 'EXECUTED',
                    timestamp TEXT NOT NULL,
                    levels_yes INTEGER,
                    levels_no INTEGER,
                    metadata TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_timestamp
                ON trades(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_market
                ON trades(market_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_status
                ON trades(status)
            """)

    def save_trade(self, trade: Dict) -> int:
        """
        Save a trade to the database.

        Args:
            trade: Trade dictionary with market_id, shares, entry_cost, etc.

        Returns:
            The ID of the inserted trade.
        """
        timestamp = trade.get('timestamp')
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()
        elif timestamp is None:
            timestamp = datetime.now().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO trades (
                    market_id, side, shares, entry_cost, exit_value,
                    pnl, roi, yes_price, no_price, status, timestamp,
                    levels_yes, levels_no, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade.get('market_id'),
                trade.get('side', 'BOTH'),
                trade.get('shares'),
                trade.get('entry_cost'),
                trade.get('exit_value'),
                trade.get('pnl'),
                trade.get('roi'),
                trade.get('yes_price'),
                trade.get('no_price'),
                trade.get('status', 'EXECUTED'),
                timestamp,
                trade.get('levels_yes'),
                trade.get('levels_no'),
                json.dumps(trade.get('metadata', {}))
            ))
            return cursor.lastrowid

    def get_trades(
        self,
        limit: int = 100,
        offset: int = 0,
        status: Optional[str] = None
    ) -> List[Dict]:
        """
        Retrieve recent trades.

        Args:
            limit: Maximum number of trades to return.
            offset: Number of trades to skip.
            status: Filter by status (e.g., 'EXECUTED', 'FAILED').

        Returns:
            List of trade dictionaries.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            if status:
                rows = conn.execute("""
                    SELECT * FROM trades
                    WHERE status = ?
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?
                """, (status, limit, offset)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM trades
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?
                """, (limit, offset)).fetchall()

            return [dict(row) for row in rows]

    def get_trade_by_id(self, trade_id: int) -> Optional[Dict]:
        """Get a specific trade by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM trades WHERE id = ?",
                (trade_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_trades_by_market(self, market_id: str) -> List[Dict]:
        """Get all trades for a specific market."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM trades
                WHERE market_id = ?
                ORDER BY timestamp DESC
            """, (market_id,)).fetchall()
            return [dict(row) for row in rows]

    def get_daily_pnl(self, date_str: Optional[str] = None) -> float:
        """
        Calculate P&L for a specific day.

        Args:
            date_str: Date in 'YYYY-MM-DD' format. Defaults to today.

        Returns:
            Total P&L for the day.
        """
        if not date_str:
            date_str = datetime.now().strftime('%Y-%m-%d')

        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute("""
                SELECT COALESCE(SUM(pnl), 0) as daily_pnl
                FROM trades
                WHERE date(timestamp) = date(?)
                AND status = 'EXECUTED'
            """, (date_str,)).fetchone()
            return result[0] if result else 0.0

    def get_total_stats(self) -> Dict:
        """
        Get aggregate statistics for all trades.

        Returns:
            Dictionary with total_trades, total_pnl, avg_roi, win_rate.
        """
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute("""
                SELECT
                    COUNT(*) as total_trades,
                    COALESCE(SUM(pnl), 0) as total_pnl,
                    COALESCE(AVG(roi), 0) as avg_roi,
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses
                FROM trades
                WHERE status = 'EXECUTED'
            """).fetchone()

            total = result[0] or 0
            return {
                'total_trades': total,
                'total_pnl': result[1] or 0.0,
                'avg_roi': result[2] or 0.0,
                'wins': result[3] or 0,
                'losses': result[4] or 0,
                'win_rate': (result[3] / total * 100) if total > 0 else 0.0
            }

    def update_trade_status(self, trade_id: int, status: str) -> bool:
        """
        Update the status of a trade.

        Args:
            trade_id: ID of the trade to update.
            status: New status (e.g., 'CLOSED', 'FAILED').

        Returns:
            True if trade was updated, False otherwise.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE trades SET status = ? WHERE id = ?",
                (status, trade_id)
            )
            return cursor.rowcount > 0

    def get_open_positions(self) -> List[Dict]:
        """Get all trades with EXECUTED status (open positions)."""
        return self.get_trades(limit=1000, status='EXECUTED')

    def count_trades_today(self) -> int:
        """Count the number of trades executed today."""
        date_str = datetime.now().strftime('%Y-%m-%d')
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute("""
                SELECT COUNT(*) FROM trades
                WHERE date(timestamp) = date(?)
            """, (date_str,)).fetchone()
            return result[0] if result else 0

    def clear_all(self) -> int:
        """
        Delete all trades from the database.
        USE WITH CAUTION - for testing only.

        Returns:
            Number of trades deleted.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM trades")
            return cursor.rowcount
