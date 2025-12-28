"""
Risk Manager - Automated exit strategy and daily loss protection.

Implements:
- Stop-loss: Automatically exit positions at specified loss threshold
- Take-profit: Lock in gains at specified profit threshold
- Max daily loss: Stop trading when daily losses exceed limit
"""
from datetime import date
from typing import Tuple, Optional
from backend.logger import logger


class RiskManager:
    """
    Manages risk thresholds and automatic exits.

    Uses configuration parameters:
    - STOP_LOSS: e.g., 0.05 = exit at -5% loss
    - TAKE_PROFIT: e.g., 0.10 = exit at +10% profit
    - MAX_DAILY_LOSS: e.g., 50.0 = stop trading after $50 daily loss
    """

    def __init__(
        self,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        max_daily_loss: Optional[float] = None
    ):
        """
        Initialize risk manager.

        Args:
            stop_loss: Stop loss threshold as decimal (0.05 = 5%).
            take_profit: Take profit threshold as decimal (0.10 = 10%).
            max_daily_loss: Maximum daily loss in dollars.
        """
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.max_daily_loss = max_daily_loss

        self.daily_pnl: float = 0.0
        self.last_reset: date = date.today()
        self.is_trading_halted: bool = False

    def _check_day_reset(self):
        """Reset daily P&L if it's a new day."""
        today = date.today()
        if today != self.last_reset:
            logger.info(f"New day detected. Resetting daily P&L from ${self.daily_pnl:.2f}")
            self.daily_pnl = 0.0
            self.last_reset = today
            self.is_trading_halted = False

    def check_daily_limit(self) -> bool:
        """
        Check if trading should continue based on daily loss limit.

        Returns:
            True if trading can continue, False if daily limit reached.
        """
        self._check_day_reset()

        if self.max_daily_loss is None:
            return True

        if self.daily_pnl <= -self.max_daily_loss:
            if not self.is_trading_halted:
                logger.warning(
                    f"Daily loss limit reached: ${abs(self.daily_pnl):.2f} >= "
                    f"${self.max_daily_loss:.2f}. Trading halted."
                )
                self.is_trading_halted = True
            return False

        return True

    def record_pnl(self, pnl: float):
        """
        Record P&L for daily tracking.

        Args:
            pnl: Profit/loss amount in dollars (positive or negative).
        """
        self._check_day_reset()
        self.daily_pnl += pnl

        if pnl < 0:
            logger.debug(f"Recorded loss: -${abs(pnl):.2f}. Daily P&L: ${self.daily_pnl:.2f}")
        else:
            logger.debug(f"Recorded profit: +${pnl:.2f}. Daily P&L: ${self.daily_pnl:.2f}")

        # Check if this puts us over the limit
        self.check_daily_limit()

    def should_exit_position(
        self,
        entry_cost: float,
        current_value: float
    ) -> Tuple[bool, str]:
        """
        Check if a position should be exited based on risk thresholds.

        Args:
            entry_cost: Original cost to enter the position.
            current_value: Current market value of the position.

        Returns:
            Tuple of (should_exit, reason).
            reason is "STOP_LOSS", "TAKE_PROFIT", or "" if no exit.
        """
        if entry_cost <= 0:
            return False, ""

        pnl_pct = (current_value - entry_cost) / entry_cost

        # Check stop loss
        if self.stop_loss is not None and pnl_pct <= -self.stop_loss:
            logger.warning(
                f"Stop loss triggered: {pnl_pct:.1%} <= -{self.stop_loss:.1%}"
            )
            return True, "STOP_LOSS"

        # Check take profit
        if self.take_profit is not None and pnl_pct >= self.take_profit:
            logger.info(
                f"Take profit triggered: {pnl_pct:.1%} >= {self.take_profit:.1%}"
            )
            return True, "TAKE_PROFIT"

        return False, ""

    def check_position(
        self,
        position: dict,
        current_yes_price: float,
        current_no_price: float
    ) -> Tuple[bool, str]:
        """
        Check if a position should be exited.

        Args:
            position: Position dict with 'shares', 'entry_cost', 'yes_price', 'no_price'.
            current_yes_price: Current YES token price.
            current_no_price: Current NO token price.

        Returns:
            Tuple of (should_exit, reason).
        """
        shares = position.get('shares', 0)
        entry_cost = position.get('entry_cost', 0)

        if shares <= 0 or entry_cost <= 0:
            return False, ""

        # For arbitrage positions, we hold both YES and NO
        # Current value = shares * (current_yes + current_no)
        # At resolution, this will be worth shares * 1.0
        current_value = shares * (current_yes_price + current_no_price)

        return self.should_exit_position(entry_cost, current_value)

    def get_status(self) -> dict:
        """Get current risk manager status."""
        self._check_day_reset()
        return {
            'daily_pnl': self.daily_pnl,
            'max_daily_loss': self.max_daily_loss,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'is_trading_halted': self.is_trading_halted,
            'remaining_daily_budget': (
                self.max_daily_loss + self.daily_pnl
                if self.max_daily_loss else None
            )
        }

    def reset(self):
        """Reset all tracking (for testing or manual reset)."""
        self.daily_pnl = 0.0
        self.last_reset = date.today()
        self.is_trading_halted = False
        logger.info("Risk manager reset")

    @classmethod
    def from_config(cls, config) -> 'RiskManager':
        """
        Create RiskManager from Config object.

        Args:
            config: Config object with STOP_LOSS, TAKE_PROFIT, MAX_DAILY_LOSS.

        Returns:
            Configured RiskManager instance.
        """
        return cls(
            stop_loss=config.STOP_LOSS,
            take_profit=config.TAKE_PROFIT,
            max_daily_loss=config.MAX_DAILY_LOSS
        )
