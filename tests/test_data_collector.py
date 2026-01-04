"""Tests for Data Collector Service."""

import pytest
import asyncio
import time
import os
from backend.services.data_collector import DataCollector, Snapshot, OpportunityLog


class TestSnapshot:
    """Tests for Snapshot dataclass."""

    def test_snapshot_creation(self):
        snap = Snapshot(
            timestamp=1704067200000,
            token_id="token_123",
            market_id="market_456",
            asks_json='[{"price": 0.45, "size": 100}]',
            bids_json='[{"price": 0.44, "size": 50}]',
            best_ask=0.45,
            best_bid=0.44,
            spread=0.01
        )
        assert snap.token_id == "token_123"
        assert snap.market_id == "market_456"
        assert snap.best_ask == 0.45


class TestOpportunityLog:
    """Tests for OpportunityLog dataclass."""

    def test_opportunity_log_creation(self):
        opp = OpportunityLog(
            timestamp=1704067200000,
            market_id="market_123",
            yes_price=0.45,
            no_price=0.50,
            combined_cost=0.95,
            roi=5.26,
            optimal_shares=100.0,
            was_executed=True
        )
        assert opp.market_id == "market_123"
        assert opp.roi == 5.26


class TestDataCollector:
    """Tests for DataCollector."""

    @pytest.fixture
    def collector(self, tmp_path):
        """Create collector with temp database."""
        db_path = str(tmp_path / "test_snapshots.db")
        return DataCollector(
            db_path=db_path,
            snapshot_interval_ms=100,  # Fast interval for tests
            batch_size=5,
            max_buffer_size=1000
        )

    def test_initialization(self, collector):
        assert collector.is_running is False
        assert collector.snapshot_interval_ms == 100

    def test_capture_snapshot_not_running(self, collector):
        """Snapshots should not be captured when collector is stopped."""
        result = collector.capture_snapshot(
            token_id="token_123",
            market_id="market_456",
            order_book={'asks': [{'price': 0.45, 'size': 100}], 'bids': []}
        )
        assert result is False

    def test_capture_snapshot_running(self, collector):
        """Snapshots should be captured when collector is running."""
        collector._running = True

        result = collector.capture_snapshot(
            token_id="token_123",
            market_id="market_456",
            order_book={'asks': [{'price': 0.45, 'size': 100}], 'bids': []}
        )
        assert result is True
        assert collector.stats['snapshots_captured'] == 1

    def test_capture_snapshot_respects_interval(self, collector):
        """Snapshots should respect interval."""
        collector._running = True

        # First capture should succeed
        result1 = collector.capture_snapshot(
            token_id="token_123",
            market_id="market_456",
            order_book={'asks': [], 'bids': []}
        )
        assert result1 is True

        # Immediate second capture should fail
        result2 = collector.capture_snapshot(
            token_id="token_123",
            market_id="market_456",
            order_book={'asks': [], 'bids': []}
        )
        assert result2 is False

    def test_capture_snapshot_force(self, collector):
        """Force flag should bypass interval."""
        collector._running = True

        result1 = collector.capture_snapshot(
            token_id="token_123",
            market_id="market_456",
            order_book={'asks': [], 'bids': []},
            force=True
        )
        assert result1 is True

        result2 = collector.capture_snapshot(
            token_id="token_123",
            market_id="market_456",
            order_book={'asks': [], 'bids': []},
            force=True
        )
        assert result2 is True

    def test_log_opportunity_not_running(self, collector):
        """Opportunities should not be logged when collector is stopped."""
        initial_count = collector.stats['opportunities_logged']
        collector.log_opportunity(
            market_id="market_123",
            yes_price=0.45,
            no_price=0.50,
            optimal_shares=100.0,
            was_executed=False
        )
        assert collector.stats['opportunities_logged'] == initial_count

    def test_log_opportunity_running(self, collector):
        """Opportunities should be logged when collector is running."""
        collector._running = True

        collector.log_opportunity(
            market_id="market_123",
            yes_price=0.45,
            no_price=0.50,
            optimal_shares=100.0,
            was_executed=False
        )
        assert collector.stats['opportunities_logged'] == 1

    def test_get_stats(self, collector):
        stats = collector.get_stats()
        assert 'snapshots_captured' in stats
        assert 'snapshots_flushed' in stats
        assert 'buffer_size' in stats
        assert 'db_size_mb' in stats

    @pytest.mark.asyncio
    async def test_start_stop(self, collector):
        collector.start()
        assert collector.is_running is True

        await collector.stop()
        assert collector.is_running is False

    @pytest.mark.asyncio
    async def test_flush_on_stop(self, collector):
        """Buffered data should be flushed when stopping."""
        collector._running = True

        # Capture some snapshots
        for i in range(3):
            collector.capture_snapshot(
                token_id=f"token_{i}",
                market_id=f"market_{i}",
                order_book={'asks': [], 'bids': []},
                force=True
            )

        assert len(collector._snapshot_buffer) == 3

        await collector.stop()

        # Buffer should be empty after stop
        assert len(collector._snapshot_buffer) == 0

    def test_get_available_date_range_empty(self, collector):
        min_ts, max_ts = collector.get_available_date_range()
        assert min_ts is None
        assert max_ts is None

    def test_get_markets_with_data_empty(self, collector):
        markets = collector.get_markets_with_data()
        assert len(markets) == 0

    def test_get_snapshot_count_empty(self, collector):
        count = collector.get_snapshot_count()
        assert count == 0

    def test_get_opportunity_count_empty(self, collector):
        count = collector.get_opportunity_count()
        assert count == 0


class TestDataCollectorQueries:
    """Tests for DataCollector query methods."""

    @pytest.fixture
    def collector_with_data(self, tmp_path):
        """Create collector and populate with test data."""
        db_path = str(tmp_path / "test_snapshots_data.db")
        collector = DataCollector(
            db_path=db_path,
            snapshot_interval_ms=0,  # No interval for tests
            batch_size=100
        )

        # Manually insert test data
        import sqlite3
        with sqlite3.connect(db_path) as conn:
            # Insert snapshots
            for i in range(10):
                conn.execute("""
                    INSERT INTO order_book_snapshots
                    (timestamp, token_id, market_id, asks_json, bids_json, best_ask, best_bid, spread)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    1704067200000 + i * 1000,  # 1 second apart
                    f"token_{i % 2}",
                    f"market_{i % 3}",
                    '[{"price": 0.45, "size": 100}]',
                    '[{"price": 0.44, "size": 50}]',
                    0.45,
                    0.44,
                    0.01
                ))

            # Insert opportunities
            for i in range(5):
                conn.execute("""
                    INSERT INTO opportunities_log
                    (timestamp, market_id, yes_price, no_price, combined_cost, roi, optimal_shares, was_executed)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    1704067200000 + i * 1000,
                    f"market_{i}",
                    0.45,
                    0.50,
                    0.95,
                    5.26,
                    100.0,
                    i % 2
                ))

        return collector

    def test_get_snapshot_count(self, collector_with_data):
        count = collector_with_data.get_snapshot_count()
        assert count == 10

    def test_get_opportunity_count(self, collector_with_data):
        count = collector_with_data.get_opportunity_count()
        assert count == 5

    def test_get_available_date_range(self, collector_with_data):
        min_ts, max_ts = collector_with_data.get_available_date_range()
        assert min_ts == 1704067200000
        assert max_ts == 1704067200000 + 9000

    def test_get_markets_with_data(self, collector_with_data):
        markets = collector_with_data.get_markets_with_data()
        assert len(markets) == 3  # market_0, market_1, market_2

    def test_get_snapshots_for_period(self, collector_with_data):
        snapshots = collector_with_data.get_snapshots_for_period(
            start_ts=1704067200000,
            end_ts=1704067205000  # First 5 snapshots
        )
        assert len(snapshots) == 6  # Inclusive

    def test_get_snapshots_for_period_with_market_filter(self, collector_with_data):
        snapshots = collector_with_data.get_snapshots_for_period(
            start_ts=1704067200000,
            end_ts=1704067210000,
            market_id="market_0"
        )
        # market_0 appears at positions 0, 3, 6, 9
        assert len(snapshots) == 4

    def test_get_opportunities_for_period(self, collector_with_data):
        opportunities = collector_with_data.get_opportunities_for_period(
            start_ts=1704067200000,
            end_ts=1704067205000
        )
        assert len(opportunities) == 5

    def test_clear_data(self, collector_with_data):
        collector_with_data.clear_data()
        assert collector_with_data.get_snapshot_count() == 0
        assert collector_with_data.get_opportunity_count() == 0

    def test_clear_data_before_timestamp(self, collector_with_data):
        # Clear data before timestamp 1704067205000
        collector_with_data.clear_data(before_timestamp=1704067205000)
        count = collector_with_data.get_snapshot_count()
        assert count == 5  # Only 5 snapshots remain


class TestDataCollectorExport:
    """Tests for CSV export functionality."""

    @pytest.fixture
    def collector_with_data(self, tmp_path):
        """Create collector and populate with test data."""
        db_path = str(tmp_path / "test_export.db")
        collector = DataCollector(db_path=db_path)

        import sqlite3
        with sqlite3.connect(db_path) as conn:
            conn.execute("""
                INSERT INTO order_book_snapshots
                (timestamp, token_id, market_id, asks_json, bids_json, best_ask, best_bid, spread)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (1704067200000, "token_1", "market_1", '[]', '[]', 0.45, 0.44, 0.01))

            conn.execute("""
                INSERT INTO opportunities_log
                (timestamp, market_id, yes_price, no_price, combined_cost, roi, optimal_shares, was_executed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (1704067200000, "market_1", 0.45, 0.50, 0.95, 5.26, 100.0, 1))

        return collector

    def test_export_snapshots_to_csv(self, collector_with_data, tmp_path):
        csv_path = str(tmp_path / "snapshots.csv")
        result = collector_with_data.export_snapshots_to_csv(
            csv_path,
            start_ts=1704067200000,
            end_ts=1704067300000
        )

        assert os.path.exists(result)
        with open(result, 'r') as f:
            content = f.read()
            assert "token_1" in content
            assert "market_1" in content

    def test_export_opportunities_to_csv(self, collector_with_data, tmp_path):
        csv_path = str(tmp_path / "opportunities.csv")
        result = collector_with_data.export_opportunities_to_csv(
            csv_path,
            start_ts=1704067200000,
            end_ts=1704067300000
        )

        assert os.path.exists(result)
        with open(result, 'r') as f:
            content = f.read()
            assert "market_1" in content
            assert "5.26" in content  # ROI
