"""
Tests for ExecutionLock.
"""
import asyncio
import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.arbitrage import ExecutionLock


class TestExecutionLock:
    """Test cases for ExecutionLock."""

    @pytest.mark.asyncio
    async def test_acquire_success(self):
        """Should successfully acquire lock on first attempt."""
        lock = ExecutionLock()
        result = await lock.acquire("market_1")
        assert result is True

    @pytest.mark.asyncio
    async def test_acquire_blocks_duplicate(self):
        """Should block duplicate acquisition."""
        lock = ExecutionLock()
        await lock.acquire("market_1")
        result = await lock.acquire("market_1")
        assert result is False

    @pytest.mark.asyncio
    async def test_release_allows_reacquire(self):
        """Should allow re-acquisition after release."""
        lock = ExecutionLock()
        await lock.acquire("market_1")
        await lock.release("market_1")
        result = await lock.acquire("market_1")
        assert result is True

    @pytest.mark.asyncio
    async def test_different_markets_independent(self):
        """Locks on different markets should be independent."""
        lock = ExecutionLock()
        await lock.acquire("market_1")
        result = await lock.acquire("market_2")
        assert result is True

    @pytest.mark.asyncio
    async def test_is_executing(self):
        """Should correctly report if a market is executing."""
        lock = ExecutionLock()
        assert lock.is_executing("market_1") is False
        await lock.acquire("market_1")
        assert lock.is_executing("market_1") is True
        await lock.release("market_1")
        assert lock.is_executing("market_1") is False

    @pytest.mark.asyncio
    async def test_release_nonexistent_safe(self):
        """Should safely handle releasing non-acquired lock."""
        lock = ExecutionLock()
        # Should not raise
        await lock.release("market_1")

    @pytest.mark.asyncio
    async def test_concurrent_acquire(self):
        """Should handle concurrent acquire attempts correctly."""
        lock = ExecutionLock()

        async def try_acquire(market_id):
            return await lock.acquire(market_id)

        # Run multiple acquires concurrently
        results = await asyncio.gather(
            try_acquire("market_1"),
            try_acquire("market_1"),
            try_acquire("market_1")
        )

        # Only one should succeed
        assert sum(results) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
