"""
Tests for OpportunityManager.
"""
import time
import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.arbitrage import OpportunityManager, OpportunityCache


class TestOpportunityManager:
    """Test cases for OpportunityManager."""

    def test_opportunity_detected(self):
        """Should detect a profitable opportunity."""
        manager = OpportunityManager(min_profit_margin=0.02)
        # cost = 0.95 < target (1.0 - 0.02 = 0.98)
        opp = manager.update("m1", "yes_token", "no_token", 0.45, 0.50)
        assert opp is not None
        assert opp.market_id == "m1"
        assert opp.cost == 0.95
        assert opp.roi > 0

    def test_opportunity_rejected_too_expensive(self):
        """Should reject when cost exceeds threshold."""
        manager = OpportunityManager(min_profit_margin=0.02)
        # cost = 1.02 > target (0.98)
        opp = manager.update("m1", "yes_token", "no_token", 0.50, 0.52)
        assert opp is None

    def test_opportunity_rejected_at_target(self):
        """Should reject when cost equals target."""
        manager = OpportunityManager(min_profit_margin=0.02)
        # cost = 0.98 == target (not < target)
        opp = manager.update("m1", "yes_token", "no_token", 0.48, 0.50)
        assert opp is None

    def test_opportunity_stores_tokens(self):
        """Should store token IDs correctly."""
        manager = OpportunityManager(min_profit_margin=0.02)
        opp = manager.update("m1", "yes_123", "no_456", 0.45, 0.50)
        assert opp.yes_token == "yes_123"
        assert opp.no_token == "no_456"

    def test_roi_calculation(self):
        """Should calculate ROI correctly."""
        manager = OpportunityManager(min_profit_margin=0.02)
        # cost = 0.90, ROI = (1.0 - 0.90) / 0.90 * 100 = 11.11%
        opp = manager.update("m1", "yes", "no", 0.45, 0.45)
        assert abs(opp.roi - 11.11) < 0.1

    def test_get_best_sorted_by_roi(self):
        """Should return opportunities sorted by ROI (descending)."""
        manager = OpportunityManager(min_profit_margin=0.05)
        # Create opportunities with different ROIs
        manager.update("m1", "y1", "n1", 0.45, 0.45)  # cost=0.90, ROI=11.11%
        manager.update("m2", "y2", "n2", 0.40, 0.40)  # cost=0.80, ROI=25%
        manager.update("m3", "y3", "n3", 0.43, 0.43)  # cost=0.86, ROI=16.28%

        best = manager.get_best(n=3)
        assert len(best) == 3
        assert best[0].market_id == "m2"  # Highest ROI
        assert best[1].market_id == "m3"
        assert best[2].market_id == "m1"  # Lowest ROI

    def test_get_best_limits_results(self):
        """Should limit results to N."""
        manager = OpportunityManager(min_profit_margin=0.1)
        for i in range(10):
            manager.update(f"m{i}", f"y{i}", f"n{i}", 0.40, 0.40)

        best = manager.get_best(n=3)
        assert len(best) == 3

    def test_mark_executed(self):
        """Should mark opportunity as executed."""
        manager = OpportunityManager(min_profit_margin=0.02)
        manager.update("m1", "y1", "n1", 0.45, 0.45)
        manager.mark_executed("m1")

        opp = manager.get("m1")
        assert opp.executed is True

    def test_get_best_excludes_executed(self):
        """Should exclude executed opportunities from get_best."""
        manager = OpportunityManager(min_profit_margin=0.05)
        manager.update("m1", "y1", "n1", 0.40, 0.40)  # Best ROI
        manager.update("m2", "y2", "n2", 0.45, 0.45)

        manager.mark_executed("m1")

        best = manager.get_best(n=5)
        assert len(best) == 1
        assert best[0].market_id == "m2"

    def test_update_removes_unprofitable(self):
        """Should remove opportunity when it becomes unprofitable."""
        manager = OpportunityManager(min_profit_margin=0.02)
        manager.update("m1", "y1", "n1", 0.45, 0.45)  # Profitable
        assert manager.get("m1") is not None

        manager.update("m1", "y1", "n1", 0.50, 0.55)  # No longer profitable
        assert manager.get("m1") is None

    def test_clear_stale(self):
        """Should remove stale opportunities."""
        manager = OpportunityManager(min_profit_margin=0.02)
        manager.update("m1", "y1", "n1", 0.45, 0.45)

        # Manually set timestamp to be old
        manager.opportunities["m1"].timestamp = time.time() - 120

        manager.clear_stale(max_age=60)
        assert manager.get("m1") is None

    def test_zero_cost_rejected(self):
        """Should reject zero cost (division protection)."""
        manager = OpportunityManager(min_profit_margin=0.02)
        opp = manager.update("m1", "y1", "n1", 0, 0)
        assert opp is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
