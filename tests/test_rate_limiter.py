"""
Tests for RateLimiter.

These tests verify the rate limiting system that prevents API bans.
"""
import pytest
import asyncio
import time
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.rate_limiter import RateLimiter, APIRateLimiter, SyncRateLimiter


class TestRateLimiter:
    """Test cases for async RateLimiter."""

    @pytest.mark.asyncio
    async def test_allows_requests_under_limit(self):
        """Should allow requests when under the limit."""
        limiter = RateLimiter(max_requests=5, time_window=1.0)

        for _ in range(5):
            waited = await limiter.acquire()
            assert waited == 0.0

    @pytest.mark.asyncio
    async def test_can_proceed_true(self):
        """Should return True when under limit."""
        limiter = RateLimiter(max_requests=5, time_window=1.0)

        assert limiter.can_proceed() is True

    @pytest.mark.asyncio
    async def test_can_proceed_false_at_limit(self):
        """Should return False when at limit."""
        limiter = RateLimiter(max_requests=2, time_window=10.0)

        await limiter.acquire()
        await limiter.acquire()

        assert limiter.can_proceed() is False

    @pytest.mark.asyncio
    async def test_time_until_available(self):
        """Should return time until next slot is available."""
        limiter = RateLimiter(max_requests=1, time_window=1.0)

        await limiter.acquire()
        time_remaining = limiter.time_until_available()

        assert 0 < time_remaining <= 1.0

    @pytest.mark.asyncio
    async def test_time_until_available_immediate(self):
        """Should return 0 when slot is immediately available."""
        limiter = RateLimiter(max_requests=5, time_window=1.0)

        assert limiter.time_until_available() == 0.0

    @pytest.mark.asyncio
    async def test_current_usage(self):
        """Should track current usage correctly."""
        limiter = RateLimiter(max_requests=5, time_window=10.0)

        assert limiter.current_usage == 0

        await limiter.acquire()
        await limiter.acquire()

        assert limiter.current_usage == 2

    @pytest.mark.asyncio
    async def test_reset_clears_requests(self):
        """Should clear all tracked requests on reset."""
        limiter = RateLimiter(max_requests=2, time_window=10.0)

        await limiter.acquire()
        await limiter.acquire()

        assert limiter.can_proceed() is False

        limiter.reset()

        assert limiter.can_proceed() is True
        assert limiter.current_usage == 0

    @pytest.mark.asyncio
    async def test_cleanup_old_requests(self):
        """Should clean up requests outside the time window."""
        limiter = RateLimiter(max_requests=2, time_window=0.1)

        await limiter.acquire()
        await limiter.acquire()

        # Wait for window to expire
        await asyncio.sleep(0.15)

        assert limiter.can_proceed() is True

    @pytest.mark.asyncio
    async def test_waits_when_at_limit(self):
        """Should wait when at rate limit."""
        limiter = RateLimiter(max_requests=1, time_window=0.1)

        await limiter.acquire()
        start = time.time()
        waited = await limiter.acquire()
        elapsed = time.time() - start

        assert waited > 0
        assert elapsed >= 0.05  # Should have waited


class TestAPIRateLimiter:
    """Test cases for multi-endpoint API rate limiter."""

    @pytest.mark.asyncio
    async def test_default_limiters_exist(self):
        """Should have default limiters for orders, markets, and default."""
        limiter = APIRateLimiter()

        assert 'orders' in limiter.limiters
        assert 'markets' in limiter.limiters
        assert 'default' in limiter.limiters

    @pytest.mark.asyncio
    async def test_orders_limiter_more_restrictive(self):
        """Orders endpoint should have lower limit than markets."""
        limiter = APIRateLimiter()

        orders_max = limiter.limiters['orders'].max_requests
        markets_max = limiter.limiters['markets'].max_requests

        assert orders_max < markets_max

    @pytest.mark.asyncio
    async def test_acquire_uses_correct_limiter(self):
        """Should use endpoint-specific limiter."""
        limiter = APIRateLimiter()

        await limiter.acquire('orders')

        assert limiter.limiters['orders'].current_usage == 1
        assert limiter.limiters['markets'].current_usage == 0

    @pytest.mark.asyncio
    async def test_acquire_unknown_endpoint(self):
        """Should use default limiter for unknown endpoints."""
        limiter = APIRateLimiter()

        await limiter.acquire('unknown_endpoint')

        # Should use default limiter
        assert limiter.limiters['default'].current_usage == 1

    @pytest.mark.asyncio
    async def test_can_proceed_checks_both_limiters(self):
        """Should check both endpoint and global limiters."""
        limiter = APIRateLimiter()

        # Fill up the global limiter (20 requests)
        for _ in range(20):
            # This consumes both endpoint and global slots
            limiter._global_limiter.requests.append(time.time())

        # Even if endpoint limiter has space, global is full
        assert limiter.can_proceed('orders') is False

    @pytest.mark.asyncio
    async def test_get_status(self):
        """Should return status for all endpoints."""
        limiter = APIRateLimiter()

        await limiter.acquire('orders')
        await limiter.acquire('markets')

        status = limiter.get_status()

        assert 'orders' in status
        assert 'markets' in status
        assert status['orders']['usage'] == 1
        assert status['markets']['usage'] == 1

    @pytest.mark.asyncio
    async def test_reset_all(self):
        """Should reset all limiters."""
        limiter = APIRateLimiter()

        await limiter.acquire('orders')
        await limiter.acquire('markets')

        limiter.reset_all()

        assert limiter.limiters['orders'].current_usage == 0
        assert limiter.limiters['markets'].current_usage == 0


class TestSyncRateLimiter:
    """Test cases for synchronous rate limiter."""

    def test_allows_requests_under_limit(self):
        """Should allow requests when under the limit."""
        limiter = SyncRateLimiter(max_requests=5, time_window=1.0)

        for _ in range(5):
            waited = limiter.acquire()
            assert waited == 0.0

    def test_can_proceed_true(self):
        """Should return True when under limit."""
        limiter = SyncRateLimiter(max_requests=5, time_window=1.0)

        assert limiter.can_proceed() is True

    def test_can_proceed_false_at_limit(self):
        """Should return False when at limit."""
        limiter = SyncRateLimiter(max_requests=2, time_window=10.0)

        limiter.acquire()
        limiter.acquire()

        assert limiter.can_proceed() is False

    def test_cleanup_old_requests(self):
        """Should clean up requests outside the time window."""
        limiter = SyncRateLimiter(max_requests=2, time_window=0.1)

        limiter.acquire()
        limiter.acquire()

        # Wait for window to expire
        time.sleep(0.15)

        assert limiter.can_proceed() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
