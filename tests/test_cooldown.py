"""
Tests for CooldownManager.
"""
import time
import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.arbitrage import CooldownManager


class TestCooldownManager:
    """Test cases for CooldownManager."""

    def test_can_trade_initially(self):
        """Should allow trading on a market that hasn't been traded yet."""
        manager = CooldownManager(cooldown_seconds=30)
        assert manager.can_trade("market_1") is True

    def test_cooldown_blocks_immediate_retrade(self):
        """Should block immediate retrade after recording a trade."""
        manager = CooldownManager(cooldown_seconds=30)
        manager.record_trade("market_1")
        assert manager.can_trade("market_1") is False

    def test_cooldown_allows_after_expiry(self):
        """Should allow trading after cooldown expires."""
        manager = CooldownManager(cooldown_seconds=0.1)
        manager.record_trade("market_1")
        assert manager.can_trade("market_1") is False
        time.sleep(0.15)
        assert manager.can_trade("market_1") is True

    def test_different_markets_independent(self):
        """Cooldown on one market shouldn't affect others."""
        manager = CooldownManager(cooldown_seconds=30)
        manager.record_trade("market_1")
        assert manager.can_trade("market_1") is False
        assert manager.can_trade("market_2") is True

    def test_time_remaining(self):
        """Should correctly report remaining cooldown time."""
        manager = CooldownManager(cooldown_seconds=30)
        manager.record_trade("market_1")
        remaining = manager.time_remaining("market_1")
        assert 29 < remaining <= 30

    def test_time_remaining_zero_when_expired(self):
        """Should return 0 when cooldown has expired."""
        manager = CooldownManager(cooldown_seconds=0.1)
        manager.record_trade("market_1")
        time.sleep(0.15)
        assert manager.time_remaining("market_1") == 0

    def test_time_remaining_zero_for_new_market(self):
        """Should return 0 for a market that hasn't been traded."""
        manager = CooldownManager(cooldown_seconds=30)
        assert manager.time_remaining("new_market") == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
