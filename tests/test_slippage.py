"""
Tests for slippage check utility.
"""
import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.arbitrage import check_slippage


class TestSlippageCheck:
    """Test cases for check_slippage function."""

    def test_slippage_accepts_identical(self):
        """Should accept when prices are identical."""
        result = check_slippage(0.95, 0.95, max_slippage=0.005)
        assert result is True

    def test_slippage_accepts_low_deviation(self):
        """Should accept when slippage is below threshold."""
        # 0.1% slippage < 0.5%
        result = check_slippage(0.95, 0.951, max_slippage=0.005)
        assert result is True

    def test_slippage_rejects_high_deviation(self):
        """Should reject when slippage exceeds threshold."""
        # ~3.15% slippage > 0.5%
        result = check_slippage(0.95, 0.98, max_slippage=0.005)
        assert result is False

    def test_slippage_accepts_exact_threshold(self):
        """Should accept when slippage equals threshold exactly."""
        # 0.5% slippage == 0.5%
        expected = 1.0
        current = 1.005
        result = check_slippage(expected, current, max_slippage=0.005)
        assert result is True

    def test_slippage_rejects_just_above_threshold(self):
        """Should reject when slippage is just above threshold."""
        expected = 1.0
        current = 1.006
        result = check_slippage(expected, current, max_slippage=0.005)
        assert result is False

    def test_slippage_handles_negative_change(self):
        """Should handle price decrease correctly (absolute slippage)."""
        # Price went down, but still within threshold
        result = check_slippage(1.0, 0.996, max_slippage=0.005)
        assert result is True

    def test_slippage_rejects_zero_expected(self):
        """Should reject when expected cost is zero (division protection)."""
        result = check_slippage(0, 0.95, max_slippage=0.005)
        assert result is False

    def test_slippage_rejects_negative_expected(self):
        """Should reject when expected cost is negative."""
        result = check_slippage(-0.5, 0.95, max_slippage=0.005)
        assert result is False

    def test_slippage_with_different_thresholds(self):
        """Should respect different slippage thresholds."""
        # 1% slippage - use slightly higher threshold for float precision
        assert check_slippage(1.0, 1.01, max_slippage=0.0101) is True
        assert check_slippage(1.0, 1.01, max_slippage=0.005) is False

    def test_slippage_real_world_scenario(self):
        """Test with realistic arbitrage values."""
        # YES=0.45, NO=0.50, expected cost=0.95
        # Current: YES=0.452, NO=0.501, current cost=0.953
        # Slippage = |0.953 - 0.95| / 0.95 = 0.316%
        expected_cost = 0.45 + 0.50
        current_cost = 0.452 + 0.501
        result = check_slippage(expected_cost, current_cost, max_slippage=0.005)
        assert result is True  # 0.316% < 0.5%


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
