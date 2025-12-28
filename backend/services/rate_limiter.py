"""
API Rate Limiter - Prevents API bans by throttling requests.

Uses a sliding window algorithm to enforce rate limits:
- 10 requests/second for general endpoints
- 5 requests/second for order endpoints (more conservative)
"""
import asyncio
import time
from collections import deque
from typing import Optional
from backend.logger import logger


class RateLimiter:
    """
    Sliding window rate limiter using token bucket algorithm.

    Thread-safe for async operations.
    """

    def __init__(self, max_requests: int = 10, time_window: float = 1.0):
        """
        Initialize rate limiter.

        Args:
            max_requests: Maximum requests allowed in time window.
            time_window: Time window in seconds.
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests: deque = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> float:
        """
        Acquire a rate limit slot, waiting if necessary.

        Returns:
            Time waited in seconds (0 if no wait was needed).
        """
        async with self._lock:
            now = time.time()
            waited = 0.0

            # Clean up old requests outside the window
            self._cleanup(now)

            # If at capacity, wait for oldest request to expire
            if len(self.requests) >= self.max_requests:
                wait_time = self.requests[0] + self.time_window - now
                if wait_time > 0:
                    waited = wait_time
                    await asyncio.sleep(wait_time)
                    # Refresh time and cleanup after waiting
                    now = time.time()
                    self._cleanup(now)

            # Record this request
            self.requests.append(time.time())
            return waited

    def _cleanup(self, now: float):
        """Remove requests outside the time window."""
        while self.requests and self.requests[0] < now - self.time_window:
            self.requests.popleft()

    def can_proceed(self) -> bool:
        """
        Check if a request can proceed without waiting.

        Returns:
            True if under rate limit, False if would need to wait.
        """
        now = time.time()
        self._cleanup(now)
        return len(self.requests) < self.max_requests

    def time_until_available(self) -> float:
        """
        Get time until next available slot.

        Returns:
            Seconds until a slot is available (0 if available now).
        """
        now = time.time()
        self._cleanup(now)

        if len(self.requests) < self.max_requests:
            return 0.0

        return max(0.0, self.requests[0] + self.time_window - now)

    @property
    def current_usage(self) -> int:
        """Get current number of requests in the window."""
        self._cleanup(time.time())
        return len(self.requests)

    def reset(self):
        """Clear all tracked requests."""
        self.requests.clear()


class APIRateLimiter:
    """
    Multi-endpoint rate limiter with different limits per endpoint type.

    Default limits:
    - orders: 5 req/sec (conservative for trading)
    - markets: 10 req/sec
    - default: 10 req/sec
    """

    def __init__(self):
        """Initialize with default rate limits per endpoint."""
        self.limiters = {
            'orders': RateLimiter(max_requests=5, time_window=1.0),
            'markets': RateLimiter(max_requests=10, time_window=1.0),
            'default': RateLimiter(max_requests=10, time_window=1.0)
        }
        self._global_limiter = RateLimiter(max_requests=20, time_window=1.0)

    async def acquire(self, endpoint: str = 'default') -> float:
        """
        Acquire rate limit slot for an endpoint.

        Args:
            endpoint: Endpoint type ('orders', 'markets', or 'default').

        Returns:
            Time waited in seconds.
        """
        # Check both endpoint-specific and global limits
        limiter = self.limiters.get(endpoint, self.limiters['default'])

        # Acquire endpoint limit
        endpoint_wait = await limiter.acquire()

        # Acquire global limit
        global_wait = await self._global_limiter.acquire()

        total_wait = endpoint_wait + global_wait
        if total_wait > 0:
            logger.debug(f"Rate limited: waited {total_wait:.3f}s for {endpoint}")

        return total_wait

    def can_proceed(self, endpoint: str = 'default') -> bool:
        """Check if request can proceed without waiting."""
        limiter = self.limiters.get(endpoint, self.limiters['default'])
        return limiter.can_proceed() and self._global_limiter.can_proceed()

    def get_status(self) -> dict:
        """Get current rate limit status for all endpoints."""
        return {
            name: {
                'usage': limiter.current_usage,
                'max': limiter.max_requests,
                'available_in': limiter.time_until_available()
            }
            for name, limiter in self.limiters.items()
        }

    def reset_all(self):
        """Reset all rate limiters."""
        for limiter in self.limiters.values():
            limiter.reset()
        self._global_limiter.reset()


class SyncRateLimiter:
    """
    Synchronous rate limiter for use in blocking code.

    Use this when you can't use async/await (e.g., in run_in_executor).
    """

    def __init__(self, max_requests: int = 10, time_window: float = 1.0):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests: deque = deque()
        import threading
        self._lock = threading.Lock()

    def acquire(self) -> float:
        """
        Acquire a rate limit slot, blocking if necessary.

        Returns:
            Time waited in seconds.
        """
        with self._lock:
            now = time.time()
            waited = 0.0

            # Cleanup old requests
            while self.requests and self.requests[0] < now - self.time_window:
                self.requests.popleft()

            # Wait if at capacity
            if len(self.requests) >= self.max_requests:
                wait_time = self.requests[0] + self.time_window - now
                if wait_time > 0:
                    waited = wait_time
                    time.sleep(wait_time)
                    now = time.time()
                    while self.requests and self.requests[0] < now - self.time_window:
                        self.requests.popleft()

            self.requests.append(time.time())
            return waited

    def can_proceed(self) -> bool:
        """Check if request can proceed without waiting."""
        now = time.time()
        while self.requests and self.requests[0] < now - self.time_window:
            self.requests.popleft()
        return len(self.requests) < self.max_requests
