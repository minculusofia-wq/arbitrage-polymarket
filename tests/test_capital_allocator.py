"""Tests for Capital Allocator Service."""

import pytest
from backend.services.capital_allocator import CapitalAllocator, AllocationResult


class TestCapitalAllocator:
    """Tests for CapitalAllocator."""

    @pytest.fixture
    def allocator(self):
        """Create allocator with default settings."""
        return CapitalAllocator(
            base_capital=100.0,
            max_daily_loss=500.0
        )

    def test_base_allocation(self, allocator):
        """Should return base capital for standard opportunity."""
        result = allocator.calculate_allocation(roi_percent=2.0)
        # At exactly MIN_ROI_FOR_BOOST, multiplier is 1.0
        assert result.allocated_capital == 100.0
        assert result.roi_multiplier == 1.0

    def test_high_roi_boost(self, allocator):
        """Should boost allocation for high ROI opportunities."""
        result = allocator.calculate_allocation(roi_percent=7.0)
        # ROI 7% = 1.0 + (7-2)/10 = 1.5
        assert result.roi_multiplier == 1.5
        assert result.allocated_capital == 150.0

    def test_roi_boost_cap(self, allocator):
        """ROI boost should be capped at MAX_ROI_BOOST."""
        result = allocator.calculate_allocation(roi_percent=20.0)
        # Even at 20% ROI, cap at 1.5
        assert result.roi_multiplier == 1.5

    def test_low_roi_reduction(self, allocator):
        """Should reduce allocation for low ROI opportunities."""
        result = allocator.calculate_allocation(roi_percent=1.0)
        # Below threshold, reduced allocation
        assert result.roi_multiplier < 1.0
        assert result.allocated_capital < 100.0

    def test_quality_multiplier_high_score(self, allocator):
        """High quality score should not reduce allocation."""
        result = allocator.calculate_allocation(
            roi_percent=2.0,
            market_score=85.0
        )
        assert result.quality_multiplier == 1.0

    def test_quality_multiplier_medium_score(self, allocator):
        """Medium quality score should slightly reduce allocation."""
        result = allocator.calculate_allocation(
            roi_percent=2.0,
            market_score=60.0
        )
        # 0.8 + (60-50)/150 = 0.867
        assert 0.8 < result.quality_multiplier < 1.0

    def test_quality_multiplier_low_score(self, allocator):
        """Low quality score should significantly reduce allocation."""
        result = allocator.calculate_allocation(
            roi_percent=2.0,
            market_score=30.0
        )
        assert result.quality_multiplier == 0.5  # Min 0.5

    def test_quality_multiplier_none(self, allocator):
        """No quality score should result in no adjustment."""
        result = allocator.calculate_allocation(
            roi_percent=2.0,
            market_score=None
        )
        assert result.quality_multiplier == 1.0

    def test_positive_pnl_boost(self, allocator):
        """Positive daily P&L should slightly boost allocation."""
        result = allocator.calculate_allocation(
            roi_percent=2.0,
            daily_pnl=50.0
        )
        # Positive P&L gives boost up to 1.2
        assert result.pnl_multiplier > 1.0
        assert result.pnl_multiplier <= 1.2

    def test_negative_pnl_reduction(self, allocator):
        """Negative daily P&L should reduce allocation."""
        result = allocator.calculate_allocation(
            roi_percent=2.0,
            daily_pnl=-100.0
        )
        # Negative P&L reduces, min 0.5
        assert result.pnl_multiplier < 1.0
        assert result.pnl_multiplier >= 0.5

    def test_pnl_multiplier_cap(self, allocator):
        """P&L multiplier should be capped."""
        # Large negative P&L
        result = allocator.calculate_allocation(
            roi_percent=2.0,
            daily_pnl=-1000.0
        )
        assert result.pnl_multiplier == 0.5

    def test_min_allocation_bound(self, allocator):
        """Allocation should not go below min_allocation_percent."""
        result = allocator.calculate_allocation(
            roi_percent=0.5,  # Very low ROI
            market_score=20.0,  # Low quality
            daily_pnl=-400.0  # Heavy losses
        )
        # All multipliers are low, but bounded at 50%
        assert result.allocated_capital >= 50.0

    def test_max_allocation_bound(self, allocator):
        """Allocation should not exceed max_allocation_percent."""
        result = allocator.calculate_allocation(
            roi_percent=15.0,  # Very high ROI
            market_score=100.0,  # Perfect quality
            daily_pnl=400.0  # Big profits
        )
        # All multipliers are high, but capped at 150%
        assert result.allocated_capital <= 150.0

    def test_update_daily_pnl(self, allocator):
        """Should track daily P&L."""
        allocator.update_daily_pnl(10.0)
        allocator.update_daily_pnl(5.0)

        stats = allocator.get_daily_stats()
        assert stats['daily_pnl'] == 15.0
        assert stats['trades_today'] == 2

    def test_reset_daily_stats(self, allocator):
        """Should reset daily statistics."""
        allocator.update_daily_pnl(100.0)
        allocator.reset_daily_stats()

        stats = allocator.get_daily_stats()
        assert stats['daily_pnl'] == 0.0
        assert stats['trades_today'] == 0

    def test_should_stop_trading_not_reached(self, allocator):
        """Should not stop if daily loss limit not reached."""
        allocator.update_daily_pnl(-100.0)
        assert allocator.should_stop_trading() is False

    def test_should_stop_trading_reached(self, allocator):
        """Should stop when daily loss limit reached."""
        allocator.update_daily_pnl(-500.0)
        assert allocator.should_stop_trading() is True

    def test_should_stop_trading_exceeded(self, allocator):
        """Should stop when daily loss limit exceeded."""
        allocator.update_daily_pnl(-600.0)
        assert allocator.should_stop_trading() is True

    def test_depth_multiplier_single_level(self, allocator):
        """Single level should have no depth penalty."""
        result = allocator.calculate_allocation(
            roi_percent=2.0,
            levels_consumed=1
        )
        # No reduction for single level
        assert 0.95 <= result.allocated_capital / 100.0 <= 1.05

    def test_depth_multiplier_deep_fill(self, allocator):
        """Deep fills should have depth penalty."""
        result = allocator.calculate_allocation(
            roi_percent=2.0,
            levels_consumed=10
        )
        # 15% reduction for deep fills
        assert result.allocated_capital < 95.0

    def test_allocation_result_has_reason(self, allocator):
        """Result should include explanation."""
        result = allocator.calculate_allocation(
            roi_percent=5.0,
            market_score=60.0
        )
        assert result.reason != ""
        assert "ROI" in result.reason or "Quality" in result.reason


class TestCapitalAllocatorEdgeCases:
    """Edge case tests for CapitalAllocator."""

    def test_zero_base_capital(self):
        """Should handle zero base capital."""
        allocator = CapitalAllocator(base_capital=0.0)
        result = allocator.calculate_allocation(roi_percent=5.0)
        assert result.allocated_capital == 0.0

    def test_negative_roi(self):
        """Should handle negative ROI (shouldn't happen in practice)."""
        allocator = CapitalAllocator(base_capital=100.0)
        result = allocator.calculate_allocation(roi_percent=-5.0)
        # Should still return valid allocation (reduced)
        assert result.allocated_capital >= 50.0

    def test_zero_max_daily_loss(self):
        """Should handle when max_daily_loss is not set."""
        allocator = CapitalAllocator(
            base_capital=100.0,
            max_daily_loss=None
        )
        # Should use default (5x base)
        result = allocator.calculate_allocation(roi_percent=2.0)
        assert result.allocated_capital > 0
