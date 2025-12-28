"""
Tests for PositionMonitor and BalanceManager.

These tests verify the position monitoring and balance verification systems.
"""
import pytest
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.position_monitor import PositionMonitor, BalanceManager
from backend.services.risk_manager import RiskManager


class TestPositionMonitor:
    """Test cases for PositionMonitor."""

    @pytest.fixture
    def risk_manager(self):
        """Create risk manager with stop-loss and take-profit."""
        return RiskManager(stop_loss=0.05, take_profit=0.10)

    @pytest.fixture
    def monitor(self, risk_manager):
        """Create position monitor instance."""
        return PositionMonitor(
            risk_manager=risk_manager,
            check_interval=0.1  # Fast for testing
        )

    def test_init(self, monitor):
        """Should initialize with correct defaults."""
        assert monitor._running is False
        assert monitor.positions == []
        assert monitor.order_books == {}

    def test_update_positions(self, monitor):
        """Should update positions list."""
        positions = [
            {'market_id': 'm1', 'shares': 100, 'entry_cost': 95},
            {'market_id': 'm2', 'shares': 50, 'entry_cost': 47}
        ]

        monitor.update_positions(positions)

        assert len(monitor.positions) == 2

    def test_update_order_books(self, monitor):
        """Should update order books."""
        order_books = {
            'token1': {'asks': [{'price': '0.50', 'size': '100'}], 'bids': []},
            'token2': {'asks': [], 'bids': [{'price': '0.48', 'size': '100'}]}
        }

        monitor.update_order_books(order_books)

        assert 'token1' in monitor.order_books
        assert 'token2' in monitor.order_books

    def test_update_market_data(self, monitor):
        """Should update market mapping data."""
        token_to_market = {'t1': 'm1', 't2': 'm1'}
        market_details = {'m1': {'tokens': [{'token_id': 't1'}, {'token_id': 't2'}]}}

        monitor.update_market_data(token_to_market, market_details)

        assert monitor.token_to_market == token_to_market
        assert monitor.market_details == market_details

    def test_get_status_stopped(self, monitor):
        """Should return correct status when stopped."""
        status = monitor.get_status()

        assert status['running'] is False
        assert status['positions_monitored'] == 0

    @pytest.mark.asyncio
    async def test_start_stop(self, monitor):
        """Should start and stop correctly."""
        monitor.start()
        assert monitor._running is True

        # Give it a moment to start
        await asyncio.sleep(0.05)

        monitor.stop()
        assert monitor._running is False

    @pytest.mark.asyncio
    async def test_get_current_prices(self, monitor):
        """Should get current prices from order books."""
        monitor.market_details = {
            'market-1': {
                'tokens': [
                    {'token_id': 'yes-token'},
                    {'token_id': 'no-token'}
                ]
            }
        }
        monitor.order_books = {
            'yes-token': {
                'asks': [{'price': '0.50', 'size': '100'}],
                'bids': [{'price': '0.48', 'size': '100'}]
            },
            'no-token': {
                'asks': [{'price': '0.45', 'size': '100'}],
                'bids': [{'price': '0.43', 'size': '100'}]
            }
        }

        position = {'market_id': 'market-1'}
        yes_price, no_price = monitor._get_current_prices(position)

        assert yes_price == 0.48  # Best bid
        assert no_price == 0.43  # Best bid

    @pytest.mark.asyncio
    async def test_get_current_prices_missing_market(self, monitor):
        """Should return None for missing market."""
        position = {'market_id': 'unknown-market'}
        yes_price, no_price = monitor._get_current_prices(position)

        assert yes_price is None
        assert no_price is None

    @pytest.mark.asyncio
    async def test_check_positions_triggers_stop_loss(self, monitor):
        """Should detect stop loss condition."""
        monitor.market_details = {
            'market-1': {
                'tokens': [
                    {'token_id': 'yes-token'},
                    {'token_id': 'no-token'}
                ]
            }
        }
        monitor.order_books = {
            'yes-token': {'bids': [{'price': '0.40', 'size': '100'}], 'asks': []},
            'no-token': {'bids': [{'price': '0.50', 'size': '100'}], 'asks': []}
        }
        monitor.positions = [{
            'market_id': 'market-1',
            'shares': 100,
            'entry_cost': 95.0,
            'status': 'EXECUTED'
        }]

        exits = await monitor._check_positions()

        assert len(exits) == 1
        assert exits[0]['reason'] == 'STOP_LOSS'

    @pytest.mark.asyncio
    async def test_check_positions_triggers_take_profit(self, monitor):
        """Should detect take profit condition."""
        monitor.market_details = {
            'market-1': {
                'tokens': [
                    {'token_id': 'yes-token'},
                    {'token_id': 'no-token'}
                ]
            }
        }
        # Current value = 100 * (0.55 + 0.55) = 110 (+15.8%)
        monitor.order_books = {
            'yes-token': {'bids': [{'price': '0.55', 'size': '100'}], 'asks': []},
            'no-token': {'bids': [{'price': '0.55', 'size': '100'}], 'asks': []}
        }
        monitor.positions = [{
            'market_id': 'market-1',
            'shares': 100,
            'entry_cost': 95.0,
            'status': 'EXECUTED'
        }]

        exits = await monitor._check_positions()

        assert len(exits) == 1
        assert exits[0]['reason'] == 'TAKE_PROFIT'

    @pytest.mark.asyncio
    async def test_check_positions_no_exit(self, monitor):
        """Should not trigger exit within thresholds."""
        monitor.market_details = {
            'market-1': {
                'tokens': [
                    {'token_id': 'yes-token'},
                    {'token_id': 'no-token'}
                ]
            }
        }
        # Current value = 100 * (0.48 + 0.50) = 98 (+3.2%)
        monitor.order_books = {
            'yes-token': {'bids': [{'price': '0.48', 'size': '100'}], 'asks': []},
            'no-token': {'bids': [{'price': '0.50', 'size': '100'}], 'asks': []}
        }
        monitor.positions = [{
            'market_id': 'market-1',
            'shares': 100,
            'entry_cost': 95.0,
            'status': 'EXECUTED'
        }]

        exits = await monitor._check_positions()

        assert len(exits) == 0

    @pytest.mark.asyncio
    async def test_check_positions_skips_closed(self, monitor):
        """Should skip closed positions."""
        monitor.market_details = {
            'market-1': {
                'tokens': [
                    {'token_id': 'yes-token'},
                    {'token_id': 'no-token'}
                ]
            }
        }
        monitor.order_books = {
            'yes-token': {'bids': [{'price': '0.30', 'size': '100'}], 'asks': []},
            'no-token': {'bids': [{'price': '0.30', 'size': '100'}], 'asks': []}
        }
        monitor.positions = [{
            'market_id': 'market-1',
            'shares': 100,
            'entry_cost': 95.0,
            'status': 'CLOSED'  # Already closed
        }]

        exits = await monitor._check_positions()

        assert len(exits) == 0

    # ========================================
    # Tests for manual exit
    # ========================================

    @pytest.mark.asyncio
    async def test_manual_exit_by_market_id(self, monitor):
        """Should queue manual exit by market ID."""
        monitor.market_details = {
            'market-1': {
                'tokens': [
                    {'token_id': 'yes-token'},
                    {'token_id': 'no-token'}
                ]
            }
        }
        monitor.order_books = {
            'yes-token': {'bids': [{'price': '0.50', 'size': '100'}], 'asks': []},
            'no-token': {'bids': [{'price': '0.48', 'size': '100'}], 'asks': []}
        }
        monitor.positions = [{
            'market_id': 'market-1',
            'shares': 100,
            'entry_cost': 95.0,
            'status': 'EXECUTED'
        }]

        result = await monitor.manual_exit('market-1')

        assert result is True
        assert monitor._exit_queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_manual_exit_not_found(self, monitor):
        """Should return False for unknown position."""
        result = await monitor.manual_exit('unknown-market')

        assert result is False

    @pytest.mark.asyncio
    async def test_manual_exit_already_closed(self, monitor):
        """Should not exit already closed position."""
        monitor.positions = [{
            'market_id': 'market-1',
            'shares': 100,
            'entry_cost': 95.0,
            'status': 'CLOSED'
        }]

        result = await monitor.manual_exit('market-1')

        assert result is False

    # ========================================
    # Tests for get_open_positions
    # ========================================

    def test_get_open_positions_empty(self, monitor):
        """Should return empty list when no positions."""
        positions = monitor.get_open_positions()
        assert positions == []

    def test_get_open_positions_with_values(self, monitor):
        """Should return positions with current values."""
        monitor.market_details = {
            'market-1': {
                'tokens': [
                    {'token_id': 'yes-token'},
                    {'token_id': 'no-token'}
                ]
            }
        }
        monitor.order_books = {
            'yes-token': {'bids': [{'price': '0.52', 'size': '100'}], 'asks': []},
            'no-token': {'bids': [{'price': '0.50', 'size': '100'}], 'asks': []}
        }
        monitor.positions = [{
            'market_id': 'market-1',
            'shares': 100,
            'entry_cost': 95.0,
            'status': 'EXECUTED'
        }]

        positions = monitor.get_open_positions()

        assert len(positions) == 1
        assert positions[0]['current_value'] == 102.0  # 100 * (0.52 + 0.50)
        assert positions[0]['unrealized_pnl'] == 7.0   # 102 - 95


class TestBalanceManager:
    """Test cases for BalanceManager."""

    @pytest.fixture
    def balance_manager(self):
        """Create balance manager with no client."""
        return BalanceManager(client=None, fallback_balance=1000.0)

    @pytest.mark.asyncio
    async def test_get_balance_fallback(self, balance_manager):
        """Should return fallback balance when no client."""
        balance = await balance_manager.get_balance()

        assert balance == 1000.0

    @pytest.mark.asyncio
    async def test_can_trade_sufficient(self, balance_manager):
        """Should allow trade when sufficient balance."""
        can_trade, balance, message = await balance_manager.can_trade(100.0)

        assert can_trade is True
        assert balance == 1000.0
        assert "Sufficient" in message

    @pytest.mark.asyncio
    async def test_can_trade_insufficient(self, balance_manager):
        """Should reject trade when insufficient balance."""
        can_trade, balance, message = await balance_manager.can_trade(2000.0)

        assert can_trade is False
        assert "Insufficient" in message

    @pytest.mark.asyncio
    async def test_can_trade_with_buffer(self, balance_manager):
        """Should account for 5% buffer in balance check."""
        # 950 * 1.05 = 997.5, just under 1000
        can_trade1, _, _ = await balance_manager.can_trade(950.0)
        assert can_trade1 is True

        # 960 * 1.05 = 1008, over 1000
        can_trade2, _, _ = await balance_manager.can_trade(960.0)
        assert can_trade2 is False

    def test_invalidate_cache(self, balance_manager):
        """Should clear cached balance."""
        balance_manager._cached_balance = 500.0
        balance_manager._last_check = "some_time"

        balance_manager.invalidate_cache()

        assert balance_manager._cached_balance is None
        assert balance_manager._last_check is None

    @pytest.mark.asyncio
    async def test_balance_caching(self, balance_manager):
        """Should use cached balance within TTL."""
        # First call
        balance1 = await balance_manager.get_balance()

        # Modify fallback (shouldn't affect cached)
        balance_manager.fallback_balance = 2000.0

        # Second call should use cache
        balance2 = await balance_manager.get_balance()

        assert balance1 == balance2 == 1000.0

    @pytest.mark.asyncio
    async def test_force_refresh(self, balance_manager):
        """Should bypass cache on force refresh."""
        # First call
        await balance_manager.get_balance()

        # Modify fallback
        balance_manager.fallback_balance = 2000.0

        # Force refresh
        balance = await balance_manager.get_balance(force_refresh=True)

        assert balance == 2000.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
