"""
Trade and Position data models.
"""
from dataclasses import dataclass
from typing import Optional
from enum import Enum
import time


class TradeStatus(Enum):
    """Status of a trade."""
    PENDING = "pending"
    EXECUTING = "executing"
    EXECUTED = "executed"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass
class Trade:
    """
    Represents an arbitrage trade opportunity.
    """
    market_id: str
    yes_token_id: str
    no_token_id: str
    yes_price: float
    no_price: float
    size: float
    status: TradeStatus = TradeStatus.PENDING
    timestamp: float = 0.0
    error: Optional[str] = None

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    @property
    def cost(self) -> float:
        """Total cost to execute the trade."""
        return self.yes_price + self.no_price

    @property
    def profit_margin(self) -> float:
        """Expected profit margin (1.0 - cost)."""
        return 1.0 - self.cost

    @property
    def roi(self) -> float:
        """Expected ROI percentage."""
        if self.cost > 0:
            return (1.0 - self.cost) / self.cost * 100
        return 0.0


@dataclass
class Position:
    """
    Represents an open position from an executed trade.
    """
    market_id: str
    size: float
    entry_cost: float
    timestamp: float
    yes_order_id: Optional[str] = None
    no_order_id: Optional[str] = None

    @property
    def expected_payout(self) -> float:
        """Expected payout (always 1.0 per share for binary markets)."""
        return self.size * 1.0

    @property
    def expected_profit(self) -> float:
        """Expected profit from this position."""
        return self.expected_payout - (self.size * self.entry_cost)
