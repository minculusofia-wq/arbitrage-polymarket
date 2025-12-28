"""
Tests for TradeStorage.

These tests verify the SQLite persistence layer for trades.
"""
import pytest
import sys
import os
import tempfile
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.trade_storage import TradeStorage


class TestTradeStorage:
    """Test cases for TradeStorage."""

    @pytest.fixture
    def storage(self):
        """Create a temporary storage instance for each test."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        storage = TradeStorage(db_path=db_path)
        yield storage
        # Cleanup
        os.unlink(db_path)

    # ========================================
    # Tests for save_trade
    # ========================================

    def test_save_trade_returns_id(self, storage):
        """Should return the trade ID after saving."""
        trade = {
            'market_id': 'test-market-1',
            'shares': 100.0,
            'entry_cost': 95.0,
            'pnl': 5.0,
            'roi': 5.26
        }

        trade_id = storage.save_trade(trade)

        assert trade_id is not None
        assert trade_id > 0

    def test_save_trade_increments_id(self, storage):
        """Should increment trade IDs sequentially."""
        trade = {'market_id': 'test', 'shares': 10, 'entry_cost': 9.5}

        id1 = storage.save_trade(trade)
        id2 = storage.save_trade(trade)
        id3 = storage.save_trade(trade)

        assert id2 == id1 + 1
        assert id3 == id2 + 1

    def test_save_trade_with_datetime_timestamp(self, storage):
        """Should handle datetime timestamp correctly."""
        now = datetime.now()
        trade = {
            'market_id': 'test-market',
            'shares': 50.0,
            'entry_cost': 47.5,
            'timestamp': now
        }

        trade_id = storage.save_trade(trade)
        retrieved = storage.get_trade_by_id(trade_id)

        assert retrieved is not None
        assert now.isoformat() in retrieved['timestamp']

    def test_save_trade_with_string_timestamp(self, storage):
        """Should handle string timestamp correctly."""
        timestamp = '2024-01-15T10:30:00'
        trade = {
            'market_id': 'test-market',
            'shares': 50.0,
            'entry_cost': 47.5,
            'timestamp': timestamp
        }

        trade_id = storage.save_trade(trade)
        retrieved = storage.get_trade_by_id(trade_id)

        assert retrieved['timestamp'] == timestamp

    def test_save_trade_generates_timestamp(self, storage):
        """Should generate timestamp if not provided."""
        trade = {
            'market_id': 'test-market',
            'shares': 50.0,
            'entry_cost': 47.5
        }

        trade_id = storage.save_trade(trade)
        retrieved = storage.get_trade_by_id(trade_id)

        assert retrieved['timestamp'] is not None

    # ========================================
    # Tests for get_trades
    # ========================================

    def test_get_trades_empty(self, storage):
        """Should return empty list when no trades."""
        trades = storage.get_trades()

        assert trades == []

    def test_get_trades_returns_all(self, storage):
        """Should return all trades."""
        for i in range(5):
            storage.save_trade({
                'market_id': f'market-{i}',
                'shares': 10,
                'entry_cost': 9.5
            })

        trades = storage.get_trades()

        assert len(trades) == 5

    def test_get_trades_ordered_by_timestamp_desc(self, storage):
        """Should return trades ordered by timestamp descending."""
        for i in range(3):
            storage.save_trade({
                'market_id': f'market-{i}',
                'shares': 10,
                'entry_cost': 9.5,
                'timestamp': datetime.now() + timedelta(hours=i)
            })

        trades = storage.get_trades()

        # Most recent first
        assert trades[0]['market_id'] == 'market-2'
        assert trades[2]['market_id'] == 'market-0'

    def test_get_trades_with_limit(self, storage):
        """Should respect limit parameter."""
        for i in range(10):
            storage.save_trade({
                'market_id': f'market-{i}',
                'shares': 10,
                'entry_cost': 9.5
            })

        trades = storage.get_trades(limit=5)

        assert len(trades) == 5

    def test_get_trades_with_offset(self, storage):
        """Should respect offset parameter."""
        for i in range(10):
            storage.save_trade({
                'market_id': f'market-{i}',
                'shares': 10,
                'entry_cost': 9.5
            })

        trades = storage.get_trades(limit=5, offset=5)

        assert len(trades) == 5

    def test_get_trades_by_status(self, storage):
        """Should filter by status."""
        storage.save_trade({
            'market_id': 'executed-1',
            'shares': 10,
            'entry_cost': 9.5,
            'status': 'EXECUTED'
        })
        storage.save_trade({
            'market_id': 'failed-1',
            'shares': 10,
            'entry_cost': 9.5,
            'status': 'FAILED'
        })
        storage.save_trade({
            'market_id': 'executed-2',
            'shares': 10,
            'entry_cost': 9.5,
            'status': 'EXECUTED'
        })

        executed = storage.get_trades(status='EXECUTED')
        failed = storage.get_trades(status='FAILED')

        assert len(executed) == 2
        assert len(failed) == 1

    # ========================================
    # Tests for get_trade_by_id
    # ========================================

    def test_get_trade_by_id_exists(self, storage):
        """Should return trade when it exists."""
        trade_id = storage.save_trade({
            'market_id': 'test-market',
            'shares': 100.0,
            'entry_cost': 95.0,
            'pnl': 5.0
        })

        retrieved = storage.get_trade_by_id(trade_id)

        assert retrieved is not None
        assert retrieved['market_id'] == 'test-market'
        assert retrieved['shares'] == 100.0

    def test_get_trade_by_id_not_exists(self, storage):
        """Should return None when trade doesn't exist."""
        retrieved = storage.get_trade_by_id(99999)

        assert retrieved is None

    # ========================================
    # Tests for get_trades_by_market
    # ========================================

    def test_get_trades_by_market(self, storage):
        """Should return all trades for a specific market."""
        storage.save_trade({'market_id': 'market-A', 'shares': 10, 'entry_cost': 9.5})
        storage.save_trade({'market_id': 'market-B', 'shares': 20, 'entry_cost': 19})
        storage.save_trade({'market_id': 'market-A', 'shares': 30, 'entry_cost': 28.5})

        trades = storage.get_trades_by_market('market-A')

        assert len(trades) == 2
        assert all(t['market_id'] == 'market-A' for t in trades)

    def test_get_trades_by_market_empty(self, storage):
        """Should return empty list for unknown market."""
        trades = storage.get_trades_by_market('unknown-market')

        assert trades == []

    # ========================================
    # Tests for get_daily_pnl
    # ========================================

    def test_get_daily_pnl_today(self, storage):
        """Should calculate P&L for today."""
        storage.save_trade({
            'market_id': 'market-1',
            'shares': 100,
            'entry_cost': 95,
            'pnl': 5.0,
            'status': 'EXECUTED',
            'timestamp': datetime.now()
        })
        storage.save_trade({
            'market_id': 'market-2',
            'shares': 100,
            'entry_cost': 95,
            'pnl': 3.0,
            'status': 'EXECUTED',
            'timestamp': datetime.now()
        })

        daily_pnl = storage.get_daily_pnl()

        assert daily_pnl == 8.0

    def test_get_daily_pnl_specific_date(self, storage):
        """Should calculate P&L for a specific date."""
        yesterday = datetime.now() - timedelta(days=1)
        storage.save_trade({
            'market_id': 'market-1',
            'shares': 100,
            'entry_cost': 95,
            'pnl': 10.0,
            'status': 'EXECUTED',
            'timestamp': yesterday
        })

        daily_pnl = storage.get_daily_pnl(yesterday.strftime('%Y-%m-%d'))

        assert daily_pnl == 10.0

    def test_get_daily_pnl_excludes_failed(self, storage):
        """Should exclude failed trades from P&L calculation."""
        storage.save_trade({
            'market_id': 'market-1',
            'shares': 100,
            'entry_cost': 95,
            'pnl': 5.0,
            'status': 'EXECUTED',
            'timestamp': datetime.now()
        })
        storage.save_trade({
            'market_id': 'market-2',
            'shares': 100,
            'entry_cost': 95,
            'pnl': -10.0,
            'status': 'FAILED',
            'timestamp': datetime.now()
        })

        daily_pnl = storage.get_daily_pnl()

        assert daily_pnl == 5.0  # Only executed trade

    def test_get_daily_pnl_no_trades(self, storage):
        """Should return 0 when no trades."""
        daily_pnl = storage.get_daily_pnl()

        assert daily_pnl == 0.0

    # ========================================
    # Tests for get_total_stats
    # ========================================

    def test_get_total_stats_empty(self, storage):
        """Should return zero stats when no trades."""
        stats = storage.get_total_stats()

        assert stats['total_trades'] == 0
        assert stats['total_pnl'] == 0.0
        assert stats['win_rate'] == 0.0

    def test_get_total_stats_with_trades(self, storage):
        """Should calculate correct statistics."""
        # 3 wins, 2 losses
        storage.save_trade({'market_id': 'm1', 'shares': 100, 'entry_cost': 95, 'pnl': 5.0, 'roi': 5.26, 'status': 'EXECUTED'})
        storage.save_trade({'market_id': 'm2', 'shares': 100, 'entry_cost': 95, 'pnl': 3.0, 'roi': 3.16, 'status': 'EXECUTED'})
        storage.save_trade({'market_id': 'm3', 'shares': 100, 'entry_cost': 95, 'pnl': -2.0, 'roi': -2.1, 'status': 'EXECUTED'})
        storage.save_trade({'market_id': 'm4', 'shares': 100, 'entry_cost': 95, 'pnl': 4.0, 'roi': 4.21, 'status': 'EXECUTED'})
        storage.save_trade({'market_id': 'm5', 'shares': 100, 'entry_cost': 95, 'pnl': -1.0, 'roi': -1.05, 'status': 'EXECUTED'})

        stats = storage.get_total_stats()

        assert stats['total_trades'] == 5
        assert stats['total_pnl'] == 9.0  # 5+3-2+4-1
        assert stats['wins'] == 3
        assert stats['losses'] == 2
        assert stats['win_rate'] == 60.0  # 3/5 * 100

    # ========================================
    # Tests for update_trade_status
    # ========================================

    def test_update_trade_status(self, storage):
        """Should update trade status."""
        trade_id = storage.save_trade({
            'market_id': 'test',
            'shares': 100,
            'entry_cost': 95,
            'status': 'EXECUTED'
        })

        result = storage.update_trade_status(trade_id, 'CLOSED')

        assert result is True
        trade = storage.get_trade_by_id(trade_id)
        assert trade['status'] == 'CLOSED'

    def test_update_trade_status_not_found(self, storage):
        """Should return False for non-existent trade."""
        result = storage.update_trade_status(99999, 'CLOSED')

        assert result is False

    # ========================================
    # Tests for get_open_positions
    # ========================================

    def test_get_open_positions(self, storage):
        """Should return only EXECUTED trades."""
        storage.save_trade({'market_id': 'm1', 'shares': 100, 'entry_cost': 95, 'status': 'EXECUTED'})
        storage.save_trade({'market_id': 'm2', 'shares': 100, 'entry_cost': 95, 'status': 'CLOSED'})
        storage.save_trade({'market_id': 'm3', 'shares': 100, 'entry_cost': 95, 'status': 'EXECUTED'})

        positions = storage.get_open_positions()

        assert len(positions) == 2
        assert all(p['status'] == 'EXECUTED' for p in positions)

    # ========================================
    # Tests for count_trades_today
    # ========================================

    def test_count_trades_today(self, storage):
        """Should count trades from today."""
        storage.save_trade({'market_id': 'm1', 'shares': 100, 'entry_cost': 95, 'timestamp': datetime.now()})
        storage.save_trade({'market_id': 'm2', 'shares': 100, 'entry_cost': 95, 'timestamp': datetime.now()})

        count = storage.count_trades_today()

        assert count == 2

    # ========================================
    # Tests for clear_all
    # ========================================

    def test_clear_all(self, storage):
        """Should delete all trades."""
        for i in range(5):
            storage.save_trade({'market_id': f'm{i}', 'shares': 100, 'entry_cost': 95})

        deleted = storage.clear_all()

        assert deleted == 5
        assert storage.get_trades() == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
