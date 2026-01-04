"""
Time Pattern Analyzer - Trading quality adjustment based on market hours.

Adjusts trading behavior based on:
- Time of day (US market hours have higher liquidity)
- Day of week (weekends may have different patterns)
- Market event timing (e.g., around resolution times)
"""

from datetime import datetime, timezone
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class TimePatternAnalyzer:
    """
    Analyzes time patterns to optimize trading quality.

    Polymarket is primarily US-focused, so US trading hours typically
    have better liquidity and tighter spreads.
    """

    # US Market Hours (approximate, in UTC)
    # US markets: 9:30 AM - 4:00 PM ET = 14:30 - 21:00 UTC (standard time)
    # Extended hours: 8:00 AM - 8:00 PM ET = 13:00 - 01:00 UTC
    PEAK_HOURS_START = 13  # 1 PM UTC (8 AM ET)
    PEAK_HOURS_END = 22    # 10 PM UTC (5 PM ET)

    # Low activity hours (night in US)
    LOW_HOURS_START = 4    # 4 AM UTC (11 PM ET)
    LOW_HOURS_END = 11     # 11 AM UTC (6 AM ET)

    # Quality score adjustments
    PEAK_QUALITY_BONUS = 10      # Add to min quality during peak
    LOW_QUALITY_PENALTY = 20     # Add to min quality during low hours

    # Allocation multipliers
    PEAK_ALLOCATION_MULT = 1.0   # Full allocation during peak
    NORMAL_ALLOCATION_MULT = 0.9 # 90% during normal hours
    LOW_ALLOCATION_MULT = 0.75   # 75% during low hours

    @classmethod
    def get_current_period(cls) -> str:
        """
        Get current trading period.

        Returns:
            'PEAK', 'NORMAL', or 'LOW'
        """
        hour = datetime.now(timezone.utc).hour

        if cls.PEAK_HOURS_START <= hour < cls.PEAK_HOURS_END:
            return 'PEAK'
        elif cls.LOW_HOURS_START <= hour < cls.LOW_HOURS_END:
            return 'LOW'
        else:
            return 'NORMAL'

    @classmethod
    def get_time_multiplier(cls) -> float:
        """
        Get allocation multiplier based on current time.

        Returns:
            Float multiplier (0.75 to 1.0)
        """
        period = cls.get_current_period()

        if period == 'PEAK':
            return cls.PEAK_ALLOCATION_MULT
        elif period == 'LOW':
            return cls.LOW_ALLOCATION_MULT
        else:
            return cls.NORMAL_ALLOCATION_MULT

    @classmethod
    def get_min_quality_score(cls, base_score: float = 50.0) -> float:
        """
        Get minimum market quality score for current time.

        During low hours, require higher quality to compensate
        for potentially worse execution.

        Args:
            base_score: Base minimum quality score from config

        Returns:
            Adjusted minimum quality score
        """
        period = cls.get_current_period()

        if period == 'PEAK':
            # During peak, can accept slightly lower quality
            return max(base_score - cls.PEAK_QUALITY_BONUS, 30.0)
        elif period == 'LOW':
            # During low hours, require higher quality
            return min(base_score + cls.LOW_QUALITY_PENALTY, 90.0)
        else:
            return base_score

    @classmethod
    def get_max_slippage(cls, base_slippage: float = 0.005) -> float:
        """
        Get maximum acceptable slippage for current time.

        During low hours, expect more slippage so be more lenient
        but also more cautious about position size.

        Args:
            base_slippage: Base max slippage from config

        Returns:
            Adjusted max slippage
        """
        period = cls.get_current_period()

        if period == 'PEAK':
            return base_slippage  # Normal slippage tolerance
        elif period == 'LOW':
            return base_slippage * 1.5  # Accept 50% more slippage
        else:
            return base_slippage * 1.2  # Accept 20% more slippage

    @classmethod
    def should_trade(cls, roi_percent: float, market_score: float) -> Tuple[bool, str]:
        """
        Determine if current conditions are suitable for trading.

        Args:
            roi_percent: Expected ROI of opportunity
            market_score: Market quality score

        Returns:
            Tuple of (should_trade, reason)
        """
        period = cls.get_current_period()
        min_quality = cls.get_min_quality_score()

        # Check market quality
        if market_score < min_quality:
            return False, f"Quality {market_score:.0f} below min {min_quality:.0f} for {period} hours"

        # During low hours, require higher ROI to compensate for risk
        if period == 'LOW':
            min_roi = 3.0  # Require 3% ROI during low hours
            if roi_percent < min_roi:
                return False, f"ROI {roi_percent:.1f}% below min {min_roi}% for LOW hours"

        return True, f"OK for {period} hours"

    @classmethod
    def get_trading_summary(cls) -> dict:
        """
        Get summary of current trading conditions.

        Returns:
            Dict with current time-based parameters
        """
        now = datetime.now(timezone.utc)
        period = cls.get_current_period()

        return {
            'current_time_utc': now.strftime('%Y-%m-%d %H:%M:%S'),
            'current_hour_utc': now.hour,
            'period': period,
            'allocation_multiplier': cls.get_time_multiplier(),
            'min_quality_score': cls.get_min_quality_score(),
            'max_slippage': cls.get_max_slippage(),
            'peak_hours': f"{cls.PEAK_HOURS_START}:00 - {cls.PEAK_HOURS_END}:00 UTC",
            'low_hours': f"{cls.LOW_HOURS_START}:00 - {cls.LOW_HOURS_END}:00 UTC"
        }


class DayOfWeekAnalyzer:
    """
    Analyzes day-of-week patterns for trading optimization.

    Weekends may have different liquidity patterns on prediction markets.
    """

    # Day multipliers (0 = Monday, 6 = Sunday)
    DAY_MULTIPLIERS = {
        0: 1.0,   # Monday - normal
        1: 1.0,   # Tuesday - normal
        2: 1.0,   # Wednesday - normal
        3: 1.0,   # Thursday - normal
        4: 0.95,  # Friday - slightly reduced (weekend approaching)
        5: 0.85,  # Saturday - reduced liquidity
        6: 0.85,  # Sunday - reduced liquidity
    }

    @classmethod
    def get_day_multiplier(cls) -> float:
        """
        Get allocation multiplier based on day of week.

        Returns:
            Float multiplier (0.85 to 1.0)
        """
        day = datetime.now(timezone.utc).weekday()
        return cls.DAY_MULTIPLIERS.get(day, 1.0)

    @classmethod
    def is_weekend(cls) -> bool:
        """Check if current day is weekend."""
        return datetime.now(timezone.utc).weekday() >= 5


class MomentumDetector:
    """
    Detects spread momentum to prioritize opportunities.

    Tracks how opportunities are changing over time to decide
    execution priority.
    """

    # Momentum thresholds
    IMPROVING_THRESHOLD = -0.01  # Cost dropping by >1%
    DEGRADING_THRESHOLD = 0.01   # Cost rising by >1%

    def __init__(self, lookback_seconds: int = 60):
        """
        Initialize momentum detector.

        Args:
            lookback_seconds: How far back to look for momentum
        """
        self.lookback_seconds = lookback_seconds
        self._cost_history: dict = {}  # market_id -> [(timestamp, cost), ...]

    def record_cost(self, market_id: str, cost: float) -> None:
        """
        Record a cost observation for a market.

        Args:
            market_id: Market identifier
            cost: Combined cost (YES + NO)
        """
        now = datetime.now(timezone.utc).timestamp()

        if market_id not in self._cost_history:
            self._cost_history[market_id] = []

        self._cost_history[market_id].append((now, cost))

        # Clean old entries
        cutoff = now - self.lookback_seconds
        self._cost_history[market_id] = [
            (ts, c) for ts, c in self._cost_history[market_id]
            if ts >= cutoff
        ]

    def detect_momentum(self, market_id: str, current_cost: float) -> str:
        """
        Detect momentum direction for a market.

        Args:
            market_id: Market identifier
            current_cost: Current combined cost

        Returns:
            'NEW', 'IMPROVING', 'STABLE', or 'DEGRADING'
        """
        if market_id not in self._cost_history or not self._cost_history[market_id]:
            return 'NEW'

        # Get oldest cost in lookback window
        history = self._cost_history[market_id]
        if len(history) < 2:
            return 'NEW'

        oldest_cost = history[0][1]
        cost_change = (current_cost - oldest_cost) / oldest_cost

        if cost_change < self.IMPROVING_THRESHOLD:
            return 'IMPROVING'  # Cost dropping = better opportunity
        elif cost_change > self.DEGRADING_THRESHOLD:
            return 'DEGRADING'  # Cost rising = opportunity fading
        else:
            return 'STABLE'

    def get_priority_score(self, market_id: str, current_cost: float) -> float:
        """
        Get execution priority score based on momentum.

        Higher score = higher priority.

        Args:
            market_id: Market identifier
            current_cost: Current combined cost

        Returns:
            Priority score (0.5 to 1.5)
        """
        momentum = self.detect_momentum(market_id, current_cost)

        if momentum == 'IMPROVING':
            return 1.5  # High priority - opportunity getting better
        elif momentum == 'DEGRADING':
            return 0.5  # Low priority - opportunity fading
        elif momentum == 'NEW':
            return 1.2  # Medium-high - new opportunities are interesting
        else:
            return 1.0  # Normal priority


def get_combined_time_multiplier() -> float:
    """
    Get combined time-based multiplier (hour + day).

    Returns:
        Combined multiplier (0.6 to 1.0)
    """
    hour_mult = TimePatternAnalyzer.get_time_multiplier()
    day_mult = DayOfWeekAnalyzer.get_day_multiplier()

    combined = hour_mult * day_mult

    logger.debug(
        f"Time multiplier: {combined:.2f} "
        f"(hour={hour_mult:.2f}, day={day_mult:.2f})"
    )

    return combined
