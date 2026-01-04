"""
Data Collector Service for Polymarket Arbitrage Bot.

Captures order book snapshots at configurable intervals for historical replay.
Optimized for high-throughput with async batch writes.
"""

import asyncio
import json
import sqlite3
import time
import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class Snapshot:
    """Order book snapshot record."""
    timestamp: int  # Unix timestamp in milliseconds
    token_id: str
    market_id: str
    asks_json: str
    bids_json: str
    best_ask: Optional[float]
    best_bid: Optional[float]
    spread: Optional[float]


@dataclass
class OpportunityLog:
    """Detected arbitrage opportunity record."""
    timestamp: int
    market_id: str
    yes_price: float
    no_price: float
    combined_cost: float
    roi: float
    optimal_shares: float
    was_executed: bool


class DataCollector:
    """
    High-performance order book snapshot collector.

    Design goals:
    - Minimal latency impact on main trading loop
    - Efficient batch writes to SQLite
    - Configurable snapshot frequency
    - Memory-bounded buffer with async flush
    """

    def __init__(
        self,
        db_path: str = "data/snapshots.db",
        snapshot_interval_ms: int = 1000,
        batch_size: int = 100,
        max_buffer_size: int = 10000
    ):
        """
        Initialize data collector.

        Args:
            db_path: Path to SQLite database for snapshots
            snapshot_interval_ms: Minimum interval between snapshots per token
            batch_size: Number of snapshots to batch before writing
            max_buffer_size: Maximum buffer size (memory safety)
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.snapshot_interval_ms = snapshot_interval_ms
        self.batch_size = batch_size
        self.max_buffer_size = max_buffer_size

        self._snapshot_buffer: deque = deque(maxlen=max_buffer_size)
        self._opportunity_buffer: deque = deque(maxlen=max_buffer_size)
        self._last_snapshot: Dict[str, int] = {}  # token_id -> last timestamp

        self._running = False
        self._flush_task: Optional[asyncio.Task] = None

        # Statistics
        self.stats = {
            'snapshots_captured': 0,
            'snapshots_flushed': 0,
            'opportunities_logged': 0,
            'bytes_written': 0,
            'flush_errors': 0
        }

        self._init_db()

    def _init_db(self):
        """Initialize database with optimized settings."""
        with sqlite3.connect(self.db_path) as conn:
            # Enable WAL mode for better concurrent access
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-64000")  # 64MB cache

            # Order book snapshots table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS order_book_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER NOT NULL,
                    token_id TEXT NOT NULL,
                    market_id TEXT NOT NULL,
                    asks_json TEXT NOT NULL,
                    bids_json TEXT NOT NULL,
                    best_ask REAL,
                    best_bid REAL,
                    spread REAL
                )
            """)

            # Indexes for efficient querying
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp
                ON order_book_snapshots(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_snapshots_market
                ON order_book_snapshots(market_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_snapshots_token_time
                ON order_book_snapshots(token_id, timestamp)
            """)

            # Market metadata table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS markets_metadata (
                    condition_id TEXT PRIMARY KEY,
                    question TEXT,
                    yes_token_id TEXT,
                    no_token_id TEXT,
                    first_seen INTEGER,
                    last_updated INTEGER,
                    total_snapshots INTEGER DEFAULT 0
                )
            """)

            # Arbitrage opportunities log
            conn.execute("""
                CREATE TABLE IF NOT EXISTS opportunities_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER NOT NULL,
                    market_id TEXT NOT NULL,
                    yes_price REAL,
                    no_price REAL,
                    combined_cost REAL,
                    roi REAL,
                    optimal_shares REAL,
                    was_executed INTEGER DEFAULT 0
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_opportunities_timestamp
                ON opportunities_log(timestamp)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_opportunities_market
                ON opportunities_log(market_id)
            """)

        logger.info(f"Data collector initialized: {self.db_path}")

    def capture_snapshot(
        self,
        token_id: str,
        market_id: str,
        order_book: Dict,
        force: bool = False
    ) -> bool:
        """
        Capture an order book snapshot if interval has elapsed.

        Non-blocking - adds to buffer for async flush.

        Args:
            token_id: Token identifier
            market_id: Market identifier
            order_book: Dict with 'asks' and 'bids' lists
            force: Force capture regardless of interval

        Returns:
            True if snapshot was captured
        """
        if not self._running:
            return False

        now = int(time.time() * 1000)
        last = self._last_snapshot.get(token_id, 0)

        if not force and (now - last) < self.snapshot_interval_ms:
            return False

        asks = order_book.get('asks', [])
        bids = order_book.get('bids', [])

        # Calculate best prices
        best_ask = None
        best_bid = None
        spread = None

        if asks:
            try:
                best_ask = float(asks[0].get('price', asks[0]) if isinstance(asks[0], dict) else asks[0])
            except (ValueError, TypeError, IndexError):
                pass

        if bids:
            try:
                best_bid = float(bids[0].get('price', bids[0]) if isinstance(bids[0], dict) else bids[0])
            except (ValueError, TypeError, IndexError):
                pass

        if best_ask is not None and best_bid is not None:
            spread = best_ask - best_bid

        snapshot = Snapshot(
            timestamp=now,
            token_id=token_id,
            market_id=market_id,
            asks_json=json.dumps(asks),
            bids_json=json.dumps(bids),
            best_ask=best_ask,
            best_bid=best_bid,
            spread=spread
        )

        self._snapshot_buffer.append(snapshot)
        self._last_snapshot[token_id] = now
        self.stats['snapshots_captured'] += 1

        return True

    def log_opportunity(
        self,
        market_id: str,
        yes_price: float,
        no_price: float,
        optimal_shares: float,
        was_executed: bool
    ):
        """
        Log detected arbitrage opportunity for analysis.

        Args:
            market_id: Market identifier
            yes_price: YES token effective price
            no_price: NO token effective price
            optimal_shares: Calculated optimal share size
            was_executed: Whether the opportunity was traded
        """
        if not self._running:
            return

        combined = yes_price + no_price
        roi = ((1.0 - combined) / combined * 100) if combined > 0 else 0

        opp = OpportunityLog(
            timestamp=int(time.time() * 1000),
            market_id=market_id,
            yes_price=yes_price,
            no_price=no_price,
            combined_cost=combined,
            roi=roi,
            optimal_shares=optimal_shares,
            was_executed=was_executed
        )

        self._opportunity_buffer.append(opp)
        self.stats['opportunities_logged'] += 1

    def save_market_metadata(
        self,
        condition_id: str,
        question: str,
        yes_token_id: str,
        no_token_id: str
    ):
        """Save or update market metadata."""
        now = int(time.time() * 1000)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO markets_metadata
                (condition_id, question, yes_token_id, no_token_id, first_seen, last_updated)
                VALUES (?, ?, ?, ?, COALESCE(
                    (SELECT first_seen FROM markets_metadata WHERE condition_id = ?),
                    ?
                ), ?)
            """, (condition_id, question, yes_token_id, no_token_id, condition_id, now, now))

    async def _flush_loop(self):
        """Background task to periodically flush buffers to DB."""
        while self._running:
            await asyncio.sleep(1.0)  # Flush every second

            try:
                await self._flush_buffers()
            except Exception as e:
                logger.error(f"Error flushing data collector buffers: {e}")
                self.stats['flush_errors'] += 1

    async def _flush_buffers(self):
        """Batch write buffered data to database."""
        # Flush snapshots
        if len(self._snapshot_buffer) >= self.batch_size or (
            self._snapshot_buffer and len(self._snapshot_buffer) > 0
        ):
            batch = []
            while self._snapshot_buffer and len(batch) < self.batch_size:
                batch.append(self._snapshot_buffer.popleft())

            if batch:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self._write_snapshot_batch, batch)
                self.stats['snapshots_flushed'] += len(batch)

        # Flush opportunities
        if self._opportunity_buffer:
            opp_batch = []
            while self._opportunity_buffer:
                opp_batch.append(self._opportunity_buffer.popleft())

            if opp_batch:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self._write_opportunity_batch, opp_batch)

    def _write_snapshot_batch(self, batch: List[Snapshot]):
        """Synchronous batch write for snapshots (runs in executor)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany("""
                INSERT INTO order_book_snapshots
                (timestamp, token_id, market_id, asks_json, bids_json,
                 best_ask, best_bid, spread)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, [(
                s.timestamp, s.token_id, s.market_id,
                s.asks_json, s.bids_json,
                s.best_ask, s.best_bid, s.spread
            ) for s in batch])

    def _write_opportunity_batch(self, batch: List[OpportunityLog]):
        """Synchronous batch write for opportunities (runs in executor)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany("""
                INSERT INTO opportunities_log
                (timestamp, market_id, yes_price, no_price,
                 combined_cost, roi, optimal_shares, was_executed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, [(
                o.timestamp, o.market_id, o.yes_price, o.no_price,
                o.combined_cost, o.roi, o.optimal_shares, 1 if o.was_executed else 0
            ) for o in batch])

    def start(self):
        """Start the background flush task."""
        if self._running:
            return

        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info("Data collector started")

    async def stop(self):
        """Stop collector and flush remaining data."""
        self._running = False

        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Final synchronous flush
        if self._snapshot_buffer:
            self._write_snapshot_batch(list(self._snapshot_buffer))
            self._snapshot_buffer.clear()

        if self._opportunity_buffer:
            self._write_opportunity_batch(list(self._opportunity_buffer))
            self._opportunity_buffer.clear()

        logger.info(f"Data collector stopped. Stats: {self.stats}")

    @property
    def is_running(self) -> bool:
        return self._running

    def get_stats(self) -> Dict:
        """Return collection statistics."""
        db_size = 0
        if self.db_path.exists():
            db_size = self.db_path.stat().st_size / (1024 * 1024)

        return {
            **self.stats,
            'buffer_size': len(self._snapshot_buffer),
            'opportunity_buffer_size': len(self._opportunity_buffer),
            'db_size_mb': round(db_size, 2),
            'tokens_tracked': len(self._last_snapshot)
        }

    # ============================================
    # QUERY METHODS FOR BACKTEST ENGINE
    # ============================================

    def get_snapshots_for_period(
        self,
        start_ts: int,
        end_ts: int,
        market_id: Optional[str] = None,
        limit: int = 100000
    ) -> List[Dict]:
        """
        Retrieve snapshots for a time period.

        Args:
            start_ts: Start timestamp (ms)
            end_ts: End timestamp (ms)
            market_id: Optional market filter
            limit: Maximum records to return

        Returns:
            List of snapshot dictionaries
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            if market_id:
                cursor = conn.execute("""
                    SELECT * FROM order_book_snapshots
                    WHERE timestamp >= ? AND timestamp <= ? AND market_id = ?
                    ORDER BY timestamp ASC
                    LIMIT ?
                """, (start_ts, end_ts, market_id, limit))
            else:
                cursor = conn.execute("""
                    SELECT * FROM order_book_snapshots
                    WHERE timestamp >= ? AND timestamp <= ?
                    ORDER BY timestamp ASC
                    LIMIT ?
                """, (start_ts, end_ts, limit))

            return [dict(row) for row in cursor.fetchall()]

    def get_opportunities_for_period(
        self,
        start_ts: int,
        end_ts: int,
        market_id: Optional[str] = None
    ) -> List[Dict]:
        """Retrieve opportunities for a time period."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            if market_id:
                cursor = conn.execute("""
                    SELECT * FROM opportunities_log
                    WHERE timestamp >= ? AND timestamp <= ? AND market_id = ?
                    ORDER BY timestamp ASC
                """, (start_ts, end_ts, market_id))
            else:
                cursor = conn.execute("""
                    SELECT * FROM opportunities_log
                    WHERE timestamp >= ? AND timestamp <= ?
                    ORDER BY timestamp ASC
                """, (start_ts, end_ts))

            return [dict(row) for row in cursor.fetchall()]

    def get_available_date_range(self) -> Tuple[Optional[int], Optional[int]]:
        """Return (min_timestamp, max_timestamp) of available data."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT MIN(timestamp), MAX(timestamp) FROM order_book_snapshots
            """)
            row = cursor.fetchone()
            return (row[0], row[1]) if row else (None, None)

    def get_markets_with_data(self) -> List[Dict]:
        """Return list of markets with snapshot data."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT
                    market_id,
                    COUNT(*) as snapshot_count,
                    MIN(timestamp) as first_snapshot,
                    MAX(timestamp) as last_snapshot
                FROM order_book_snapshots
                GROUP BY market_id
                ORDER BY snapshot_count DESC
            """)
            return [dict(row) for row in cursor.fetchall()]

    def get_snapshot_count(self) -> int:
        """Return total number of snapshots in database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM order_book_snapshots")
            return cursor.fetchone()[0]

    def get_opportunity_count(self) -> int:
        """Return total number of opportunities logged."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM opportunities_log")
            return cursor.fetchone()[0]

    def export_snapshots_to_csv(self, filepath: str, start_ts: int, end_ts: int) -> str:
        """Export snapshots to CSV file."""
        import csv

        snapshots = self.get_snapshots_for_period(start_ts, end_ts)

        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "Timestamp", "Token ID", "Market ID",
                "Best Ask", "Best Bid", "Spread",
                "Asks JSON", "Bids JSON"
            ])

            for snap in snapshots:
                writer.writerow([
                    snap['timestamp'],
                    snap['token_id'],
                    snap['market_id'],
                    snap['best_ask'],
                    snap['best_bid'],
                    snap['spread'],
                    snap['asks_json'],
                    snap['bids_json']
                ])

        return filepath

    def export_opportunities_to_csv(self, filepath: str, start_ts: int, end_ts: int) -> str:
        """Export opportunities to CSV file."""
        import csv

        opportunities = self.get_opportunities_for_period(start_ts, end_ts)

        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "Timestamp", "Market ID", "YES Price", "NO Price",
                "Combined Cost", "ROI %", "Optimal Shares", "Executed"
            ])

            for opp in opportunities:
                writer.writerow([
                    opp['timestamp'],
                    opp['market_id'],
                    f"{opp['yes_price']:.4f}",
                    f"{opp['no_price']:.4f}",
                    f"{opp['combined_cost']:.4f}",
                    f"{opp['roi']:.2f}",
                    f"{opp['optimal_shares']:.2f}",
                    "Yes" if opp['was_executed'] else "No"
                ])

        return filepath

    def clear_data(self, before_timestamp: Optional[int] = None):
        """
        Clear data from database.

        Args:
            before_timestamp: If provided, only clear data before this timestamp.
                            If None, clear all data.
        """
        with sqlite3.connect(self.db_path) as conn:
            if before_timestamp:
                conn.execute(
                    "DELETE FROM order_book_snapshots WHERE timestamp < ?",
                    (before_timestamp,)
                )
                conn.execute(
                    "DELETE FROM opportunities_log WHERE timestamp < ?",
                    (before_timestamp,)
                )
                logger.info(f"Cleared data before timestamp {before_timestamp}")
            else:
                conn.execute("DELETE FROM order_book_snapshots")
                conn.execute("DELETE FROM opportunities_log")
                logger.info("Cleared all data from collector database")

        # VACUUM must be run outside of transaction
        with sqlite3.connect(self.db_path, isolation_level=None) as conn:
            conn.execute("VACUUM")
