"""
Capital Allocator Service - Dynamic capital allocation based on opportunity quality.

This service calculates optimal capital allocation for each trade based on:
- ROI potential (higher ROI = larger allocation)
- Market quality score (better markets = larger allocation)
- Daily P&L performance (winning = increase, losing = decrease)
- Risk parameters from configuration
"""

from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class AllocationResult:
    """Result of capital allocation calculation."""
    allocated_capital: float
    roi_multiplier: float
    quality_multiplier: float
    pnl_multiplier: float
    reason: str


class CapitalAllocator:
    """
    Dynamic capital allocation based on opportunity quality.

    Adjusts trade size based on multiple factors to maximize returns
    while managing risk appropriately.
    """

    # ROI thresholds for allocation tiers
    MIN_ROI_FOR_BOOST = 2.0  # Start boosting at 2% ROI
    MAX_ROI_BOOST = 1.5      # Maximum 50% boost for high ROI
    MIN_ROI_REDUCTION = 0.8  # Minimum 80% for low ROI

    # P&L adjustment limits
    MAX_PNL_BOOST = 1.2      # Maximum 20% boost when profitable
    MIN_PNL_REDUCTION = 0.5  # Minimum 50% when losing

    # Quality thresholds
    MIN_QUALITY_FOR_FULL = 80.0  # Full allocation above this score

    def __init__(
        self,
        base_capital: float,
        max_daily_loss: Optional[float] = None,
        min_allocation_percent: float = 0.5,
        max_allocation_percent: float = 1.5
    ):
        """
        Initialize the capital allocator.

        Args:
            base_capital: Default capital per trade from config
            max_daily_loss: Maximum daily loss limit (for P&L adjustment)
            min_allocation_percent: Minimum allocation as % of base (0.5 = 50%)
            max_allocation_percent: Maximum allocation as % of base (1.5 = 150%)
        """
        self.base_capital = base_capital
        self.max_daily_loss = max_daily_loss or base_capital * 5  # Default 5x base
        self.min_allocation_percent = min_allocation_percent
        self.max_allocation_percent = max_allocation_percent

        # Track daily P&L
        self._daily_pnl = 0.0
        self._trades_today = 0

    def calculate_allocation(
        self,
        roi_percent: float,
        market_score: Optional[float] = None,
        daily_pnl: Optional[float] = None,
        levels_consumed: int = 1
    ) -> AllocationResult:
        """
        Calculate optimal capital allocation for a trade.

        Args:
            roi_percent: Expected ROI of the opportunity (e.g., 5.0 for 5%)
            market_score: Market quality score 0-100 (optional)
            daily_pnl: Current daily P&L in dollars (optional, uses internal tracker)
            levels_consumed: Number of order book levels needed (higher = more risk)

        Returns:
            AllocationResult with calculated allocation and multipliers
        """
        # Use provided daily_pnl or internal tracker
        current_pnl = daily_pnl if daily_pnl is not None else self._daily_pnl

        # 1. ROI Multiplier
        roi_mult = self._calculate_roi_multiplier(roi_percent)

        # 2. Quality Multiplier
        quality_mult = self._calculate_quality_multiplier(market_score)

        # 3. P&L Multiplier
        pnl_mult = self._calculate_pnl_multiplier(current_pnl)

        # 4. Depth Risk Adjustment
        depth_mult = self._calculate_depth_multiplier(levels_consumed)

        # Calculate final allocation
        combined_mult = roi_mult * quality_mult * pnl_mult * depth_mult

        # Apply min/max bounds
        bounded_mult = max(
            self.min_allocation_percent,
            min(combined_mult, self.max_allocation_percent)
        )

        allocated = self.base_capital * bounded_mult

        # Build reason string
        reason_parts = []
        if roi_mult != 1.0:
            reason_parts.append(f"ROI:{roi_mult:.2f}x")
        if quality_mult != 1.0:
            reason_parts.append(f"Quality:{quality_mult:.2f}x")
        if pnl_mult != 1.0:
            reason_parts.append(f"P&L:{pnl_mult:.2f}x")
        if depth_mult != 1.0:
            reason_parts.append(f"Depth:{depth_mult:.2f}x")

        reason = " | ".join(reason_parts) if reason_parts else "Standard allocation"

        logger.debug(
            f"Capital allocation: ${allocated:.2f} "
            f"(base=${self.base_capital:.2f}, mult={bounded_mult:.2f}) - {reason}"
        )

        return AllocationResult(
            allocated_capital=allocated,
            roi_multiplier=roi_mult,
            quality_multiplier=quality_mult,
            pnl_multiplier=pnl_mult,
            reason=reason
        )

    def _calculate_roi_multiplier(self, roi_percent: float) -> float:
        """
        Calculate ROI-based multiplier.

        Higher ROI = larger allocation (up to MAX_ROI_BOOST)
        Lower ROI = smaller allocation (down to MIN_ROI_REDUCTION)
        """
        if roi_percent >= self.MIN_ROI_FOR_BOOST:
            # Linear scaling from 1.0 at 2% to MAX_ROI_BOOST at 12%
            boost = (roi_percent - self.MIN_ROI_FOR_BOOST) / 10.0
            return min(1.0 + boost, self.MAX_ROI_BOOST)
        else:
            # Below threshold, reduce allocation
            return max(
                self.MIN_ROI_REDUCTION,
                0.8 + (roi_percent / self.MIN_ROI_FOR_BOOST) * 0.2
            )

    def _calculate_quality_multiplier(self, market_score: Optional[float]) -> float:
        """
        Calculate market quality multiplier.

        Higher quality score = larger allocation
        """
        if market_score is None:
            return 1.0  # No adjustment if score not available

        if market_score >= self.MIN_QUALITY_FOR_FULL:
            return 1.0  # Full allocation for high-quality markets
        elif market_score >= 50:
            # Scale from 0.8 at 50 to 1.0 at 80
            return 0.8 + (market_score - 50) / 150
        else:
            # Low quality, reduce significantly
            return max(0.5, market_score / 100)

    def _calculate_pnl_multiplier(self, daily_pnl: float) -> float:
        """
        Calculate P&L-based multiplier.

        Profitable day = slightly increase allocation
        Losing day = reduce allocation proportionally
        """
        # Handle edge case of zero max_daily_loss
        if self.max_daily_loss <= 0:
            return 1.0

        if daily_pnl >= 0:
            # In profit: increase slightly (up to MAX_PNL_BOOST)
            boost = min(daily_pnl / self.max_daily_loss, 0.2)
            return min(1.0 + boost, self.MAX_PNL_BOOST)
        else:
            # In loss: reduce proportionally (down to MIN_PNL_REDUCTION)
            reduction = daily_pnl / self.max_daily_loss  # Negative
            return max(1.0 + reduction, self.MIN_PNL_REDUCTION)

    def _calculate_depth_multiplier(self, levels_consumed: int) -> float:
        """
        Calculate depth risk multiplier.

        More levels consumed = higher slippage risk = smaller allocation
        """
        if levels_consumed <= 1:
            return 1.0  # No adjustment for single level
        elif levels_consumed <= 3:
            return 0.95  # 5% reduction for 2-3 levels
        elif levels_consumed <= 5:
            return 0.9   # 10% reduction for 4-5 levels
        else:
            return 0.85  # 15% reduction for deep fills

    def update_daily_pnl(self, pnl_change: float) -> None:
        """Update internal daily P&L tracker after a trade."""
        self._daily_pnl += pnl_change
        self._trades_today += 1
        logger.debug(f"Daily P&L updated: ${self._daily_pnl:.2f} ({self._trades_today} trades)")

    def reset_daily_stats(self) -> None:
        """Reset daily statistics (call at start of each trading day)."""
        self._daily_pnl = 0.0
        self._trades_today = 0
        logger.info("Daily statistics reset")

    def get_daily_stats(self) -> dict:
        """Get current daily statistics."""
        return {
            'daily_pnl': self._daily_pnl,
            'trades_today': self._trades_today,
            'base_capital': self.base_capital,
            'max_daily_loss': self.max_daily_loss
        }

    def should_stop_trading(self) -> bool:
        """Check if daily loss limit has been reached."""
        if self._daily_pnl < 0 and abs(self._daily_pnl) >= self.max_daily_loss:
            logger.warning(
                f"Daily loss limit reached: ${self._daily_pnl:.2f} >= ${self.max_daily_loss:.2f}"
            )
            return True
        return False


class AllocationOptimizer:
    """
    Advanced allocation optimizer using historical performance.

    Tracks trade outcomes to optimize allocation strategy over time.
    """

    def __init__(self, allocator: CapitalAllocator, lookback_trades: int = 100):
        """
        Initialize optimizer with reference to allocator.

        Args:
            allocator: CapitalAllocator instance to optimize
            lookback_trades: Number of recent trades to consider
        """
        self.allocator = allocator
        self.lookback_trades = lookback_trades
        self._trade_history: list = []

    def record_trade(
        self,
        roi_expected: float,
        roi_actual: float,
        market_score: Optional[float],
        levels_consumed: int,
        allocation_used: float
    ) -> None:
        """
        Record trade outcome for optimization.

        Args:
            roi_expected: Expected ROI when trade was made
            roi_actual: Actual ROI after resolution
            market_score: Market quality score used
            levels_consumed: Order book depth consumed
            allocation_used: Capital allocated to trade
        """
        self._trade_history.append({
            'roi_expected': roi_expected,
            'roi_actual': roi_actual,
            'market_score': market_score,
            'levels_consumed': levels_consumed,
            'allocation_used': allocation_used,
            'accuracy': roi_actual / roi_expected if roi_expected > 0 else 0
        })

        # Keep only recent trades
        if len(self._trade_history) > self.lookback_trades:
            self._trade_history.pop(0)

    def get_performance_by_roi_tier(self) -> dict:
        """Analyze performance by ROI tier."""
        tiers = {
            'low_roi': [],    # < 3%
            'medium_roi': [], # 3-5%
            'high_roi': []    # > 5%
        }

        for trade in self._trade_history:
            roi = trade['roi_expected']
            if roi < 3:
                tiers['low_roi'].append(trade['accuracy'])
            elif roi < 5:
                tiers['medium_roi'].append(trade['accuracy'])
            else:
                tiers['high_roi'].append(trade['accuracy'])

        return {
            tier: {
                'count': len(trades),
                'avg_accuracy': sum(trades) / len(trades) if trades else 0
            }
            for tier, trades in tiers.items()
        }

    def suggest_adjustments(self) -> dict:
        """
        Suggest allocation adjustments based on historical performance.

        Returns dict with suggested parameter changes.
        """
        if len(self._trade_history) < 20:
            return {'status': 'insufficient_data', 'trades_needed': 20 - len(self._trade_history)}

        perf = self.get_performance_by_roi_tier()
        suggestions = {}

        # If high ROI trades underperform, reduce MAX_ROI_BOOST
        if perf['high_roi']['count'] > 5 and perf['high_roi']['avg_accuracy'] < 0.9:
            suggestions['reduce_roi_boost'] = True

        # If low quality trades underperform, increase MIN_QUALITY_FOR_FULL
        quality_trades = [t for t in self._trade_history if t['market_score'] and t['market_score'] < 70]
        if quality_trades:
            avg_quality_accuracy = sum(t['accuracy'] for t in quality_trades) / len(quality_trades)
            if avg_quality_accuracy < 0.85:
                suggestions['increase_quality_threshold'] = True

        return suggestions
