"""
Tests for RiskManager.

These tests verify the risk management system including:
- Stop-loss triggers
- Take-profit triggers
- Daily loss limits
"""
import pytest
import sys
import os
from datetime import date

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.risk_manager import RiskManager


class TestRiskManager:
    """Test cases for RiskManager."""

    # ========================================
    # Tests for stop-loss
    # ========================================

    def test_stop_loss_triggered(self):
        """Should trigger stop loss when position drops below threshold."""
        rm = RiskManager(stop_loss=0.05)  # 5% stop loss

        should_exit, reason = rm.should_exit_position(
            entry_cost=100.0,
            current_value=94.0  # -6% loss
        )

        assert should_exit is True
        assert reason == "STOP_LOSS"

    def test_stop_loss_not_triggered(self):
        """Should not trigger stop loss when loss is within threshold."""
        rm = RiskManager(stop_loss=0.05)  # 5% stop loss

        should_exit, reason = rm.should_exit_position(
            entry_cost=100.0,
            current_value=96.0  # -4% loss
        )

        assert should_exit is False
        assert reason == ""

    def test_stop_loss_at_threshold(self):
        """Should trigger stop loss at exact threshold."""
        rm = RiskManager(stop_loss=0.05)  # 5% stop loss

        should_exit, reason = rm.should_exit_position(
            entry_cost=100.0,
            current_value=95.0  # -5% exactly
        )

        assert should_exit is True
        assert reason == "STOP_LOSS"

    def test_stop_loss_disabled(self):
        """Should not trigger when stop loss is not configured."""
        rm = RiskManager(stop_loss=None)

        should_exit, reason = rm.should_exit_position(
            entry_cost=100.0,
            current_value=50.0  # -50% loss
        )

        assert should_exit is False

    # ========================================
    # Tests for take-profit
    # ========================================

    def test_take_profit_triggered(self):
        """Should trigger take profit when position exceeds threshold."""
        rm = RiskManager(take_profit=0.10)  # 10% take profit

        should_exit, reason = rm.should_exit_position(
            entry_cost=100.0,
            current_value=112.0  # +12% profit
        )

        assert should_exit is True
        assert reason == "TAKE_PROFIT"

    def test_take_profit_not_triggered(self):
        """Should not trigger take profit when gain is below threshold."""
        rm = RiskManager(take_profit=0.10)  # 10% take profit

        should_exit, reason = rm.should_exit_position(
            entry_cost=100.0,
            current_value=108.0  # +8% profit
        )

        assert should_exit is False
        assert reason == ""

    def test_take_profit_at_threshold(self):
        """Should trigger take profit at exact threshold."""
        rm = RiskManager(take_profit=0.10)  # 10% take profit

        should_exit, reason = rm.should_exit_position(
            entry_cost=100.0,
            current_value=110.0  # +10% exactly
        )

        assert should_exit is True
        assert reason == "TAKE_PROFIT"

    def test_take_profit_disabled(self):
        """Should not trigger when take profit is not configured."""
        rm = RiskManager(take_profit=None)

        should_exit, reason = rm.should_exit_position(
            entry_cost=100.0,
            current_value=200.0  # +100% gain
        )

        assert should_exit is False

    # ========================================
    # Tests for combined stop-loss and take-profit
    # ========================================

    def test_stop_loss_priority(self):
        """Stop loss should take priority over take profit."""
        rm = RiskManager(stop_loss=0.05, take_profit=0.10)

        # Loss position
        should_exit, reason = rm.should_exit_position(
            entry_cost=100.0,
            current_value=94.0
        )

        assert should_exit is True
        assert reason == "STOP_LOSS"

    def test_both_thresholds_profit(self):
        """Take profit should trigger in profitable position."""
        rm = RiskManager(stop_loss=0.05, take_profit=0.10)

        should_exit, reason = rm.should_exit_position(
            entry_cost=100.0,
            current_value=112.0
        )

        assert should_exit is True
        assert reason == "TAKE_PROFIT"

    # ========================================
    # Tests for daily loss limit
    # ========================================

    def test_daily_limit_not_reached(self):
        """Should allow trading when daily limit not reached."""
        rm = RiskManager(max_daily_loss=50.0)

        rm.record_pnl(-30.0)  # $30 loss

        assert rm.check_daily_limit() is True

    def test_daily_limit_reached(self):
        """Should halt trading when daily limit reached."""
        rm = RiskManager(max_daily_loss=50.0)

        rm.record_pnl(-50.0)  # $50 loss

        assert rm.check_daily_limit() is False
        assert rm.is_trading_halted is True

    def test_daily_limit_exceeded(self):
        """Should halt trading when daily limit exceeded."""
        rm = RiskManager(max_daily_loss=50.0)

        rm.record_pnl(-60.0)  # $60 loss

        assert rm.check_daily_limit() is False

    def test_daily_limit_disabled(self):
        """Should allow trading when no daily limit configured."""
        rm = RiskManager(max_daily_loss=None)

        rm.record_pnl(-1000.0)  # Large loss

        assert rm.check_daily_limit() is True

    def test_daily_pnl_accumulates(self):
        """Should accumulate P&L across multiple trades."""
        rm = RiskManager(max_daily_loss=50.0)

        rm.record_pnl(-20.0)
        rm.record_pnl(-20.0)
        rm.record_pnl(-15.0)  # Total: -$55

        assert rm.check_daily_limit() is False

    def test_profits_offset_losses(self):
        """Profits should offset losses in daily tracking."""
        rm = RiskManager(max_daily_loss=50.0)

        rm.record_pnl(-40.0)
        rm.record_pnl(30.0)  # Total: -$10

        assert rm.check_daily_limit() is True
        assert rm.daily_pnl == -10.0

    # ========================================
    # Tests for check_position
    # ========================================

    def test_check_position_stop_loss(self):
        """Should detect stop loss for arbitrage position."""
        rm = RiskManager(stop_loss=0.05)

        position = {
            'shares': 100,
            'entry_cost': 95.0,  # Cost $0.95 per share
            'yes_price': 0.45,
            'no_price': 0.50
        }

        # Current value: 100 * (0.40 + 0.50) = 90 (loss of 5.26%)
        should_exit, reason = rm.check_position(
            position,
            current_yes_price=0.40,
            current_no_price=0.50
        )

        assert should_exit is True
        assert reason == "STOP_LOSS"

    def test_check_position_take_profit(self):
        """Should detect take profit for arbitrage position."""
        rm = RiskManager(take_profit=0.05)

        position = {
            'shares': 100,
            'entry_cost': 95.0,
            'yes_price': 0.45,
            'no_price': 0.50
        }

        # Current value: 100 * (0.50 + 0.55) = 105 (profit)
        should_exit, reason = rm.check_position(
            position,
            current_yes_price=0.50,
            current_no_price=0.55
        )

        assert should_exit is True
        assert reason == "TAKE_PROFIT"

    # ========================================
    # Tests for status and reset
    # ========================================

    def test_get_status(self):
        """Should return correct status information."""
        rm = RiskManager(
            stop_loss=0.05,
            take_profit=0.10,
            max_daily_loss=50.0
        )
        rm.record_pnl(-20.0)

        status = rm.get_status()

        assert status['daily_pnl'] == -20.0
        assert status['max_daily_loss'] == 50.0
        assert status['stop_loss'] == 0.05
        assert status['take_profit'] == 0.10
        assert status['is_trading_halted'] is False
        assert status['remaining_daily_budget'] == 30.0

    def test_reset(self):
        """Should reset all tracking values."""
        rm = RiskManager(max_daily_loss=50.0)
        rm.record_pnl(-60.0)

        assert rm.is_trading_halted is True

        rm.reset()

        assert rm.daily_pnl == 0.0
        assert rm.is_trading_halted is False

    # ========================================
    # Tests for edge cases
    # ========================================

    def test_zero_entry_cost(self):
        """Should handle zero entry cost gracefully."""
        rm = RiskManager(stop_loss=0.05)

        should_exit, reason = rm.should_exit_position(
            entry_cost=0.0,
            current_value=100.0
        )

        assert should_exit is False
        assert reason == ""

    def test_negative_entry_cost(self):
        """Should handle negative entry cost gracefully."""
        rm = RiskManager(stop_loss=0.05)

        should_exit, reason = rm.should_exit_position(
            entry_cost=-10.0,
            current_value=100.0
        )

        assert should_exit is False

    def test_empty_position(self):
        """Should handle empty position dict."""
        rm = RiskManager(stop_loss=0.05)

        should_exit, reason = rm.check_position({}, 0.5, 0.5)

        assert should_exit is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
