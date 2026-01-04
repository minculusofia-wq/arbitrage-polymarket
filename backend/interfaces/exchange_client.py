"""
Exchange Client Interface - Abstract base class for all exchange clients.

This module defines the unified interfaces that all platform-specific clients
must implement, enabling platform-agnostic arbitrage detection and execution.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from enum import Enum
import time


class OrderSide(Enum):
    """Order side enumeration."""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """Order type enumeration."""
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    FOK = "FOK"  # Fill-or-Kill
    GTC = "GTC"  # Good-til-Cancelled


class OrderStatus(Enum):
    """Order status enumeration."""
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass
class UnifiedMarket:
    """
    Normalized market representation across all platforms.

    This dataclass provides a consistent structure for markets
    regardless of the underlying platform's API format.
    """
    platform: str  # "polymarket" | "kalshi"
    market_id: str  # Unique identifier (condition_id for Poly, ticker for Kalshi)
    question: str  # Human-readable market question
    outcomes: List[str]  # ["Yes", "No"] for binary markets
    volume: float  # 24h or total volume in USD
    end_date: Optional[str] = None  # ISO format end date
    tokens: Dict[str, str] = field(default_factory=dict)  # outcome -> token_id mapping
    active: bool = True
    category: Optional[str] = None

    @property
    def is_binary(self) -> bool:
        """Check if market is binary (Yes/No)."""
        return len(self.outcomes) == 2 and "Yes" in self.outcomes and "No" in self.outcomes

    def get_token_id(self, outcome: str) -> Optional[str]:
        """Get token ID for a specific outcome."""
        return self.tokens.get(outcome)


@dataclass
class UnifiedOrderBook:
    """
    Normalized order book representation.

    Bids and asks are lists of (price, size) tuples,
    sorted by price (bids descending, asks ascending).
    """
    platform: str
    market_id: str
    outcome: str  # "Yes" or "No"
    bids: List[Tuple[float, float]]  # [(price, size), ...] - buyers
    asks: List[Tuple[float, float]]  # [(price, size), ...] - sellers
    timestamp: float = field(default_factory=time.time)

    @property
    def best_bid(self) -> Optional[float]:
        """Get best bid price."""
        return self.bids[0][0] if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        """Get best ask price."""
        return self.asks[0][0] if self.asks else None

    @property
    def spread(self) -> Optional[float]:
        """Calculate bid-ask spread."""
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return None

    @property
    def mid_price(self) -> Optional[float]:
        """Calculate mid price."""
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2
        return None

    def get_total_liquidity(self, side: str, depth: int = 10) -> float:
        """Get total liquidity on a side up to given depth."""
        orders = self.bids if side == "bid" else self.asks
        return sum(size for _, size in orders[:depth])

    def calculate_effective_price(self, side: str, size: float) -> Optional[Tuple[float, int]]:
        """
        Calculate effective price for a given size.

        Returns (effective_price, levels_consumed) or None if insufficient liquidity.
        """
        orders = self.asks if side == "buy" else self.bids

        remaining = size
        total_cost = 0.0
        levels = 0

        for price, available in orders:
            levels += 1
            if remaining <= available:
                total_cost += remaining * price
                remaining = 0
                break
            else:
                total_cost += available * price
                remaining -= available

        if remaining > 0:
            return None  # Insufficient liquidity

        return (total_cost / size, levels)


@dataclass
class OrderResult:
    """Result of an order placement."""
    success: bool
    order_id: Optional[str] = None
    filled_size: float = 0.0
    filled_price: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    error_message: Optional[str] = None
    platform: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class Position:
    """Represents an open position."""
    platform: str
    market_id: str
    outcome: str
    size: float
    entry_price: float
    current_price: Optional[float] = None
    unrealized_pnl: float = 0.0
    timestamp: float = field(default_factory=time.time)

    @property
    def market_value(self) -> float:
        """Calculate current market value."""
        price = self.current_price or self.entry_price
        return self.size * price


class IExchangeClient(ABC):
    """
    Abstract base class for exchange clients.

    All platform-specific clients must implement this interface
    to enable unified arbitrage detection and execution.
    """

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return the platform name (e.g., 'polymarket', 'kalshi')."""
        pass

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if client is connected and authenticated."""
        pass

    @abstractmethod
    async def connect(self) -> bool:
        """
        Connect and authenticate to the exchange.

        Returns:
            True if connection successful, False otherwise.
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the exchange."""
        pass

    @abstractmethod
    async def fetch_markets(
        self,
        min_volume: float = 0,
        active_only: bool = True
    ) -> List[UnifiedMarket]:
        """
        Fetch available markets from the exchange.

        Args:
            min_volume: Minimum volume filter
            active_only: Only return active markets

        Returns:
            List of UnifiedMarket objects
        """
        pass

    @abstractmethod
    async def get_order_book(
        self,
        market_id: str,
        outcome: str
    ) -> UnifiedOrderBook:
        """
        Get order book for a specific market outcome.

        Args:
            market_id: Market identifier
            outcome: "Yes" or "No"

        Returns:
            UnifiedOrderBook object
        """
        pass

    @abstractmethod
    async def place_order(
        self,
        market_id: str,
        outcome: str,
        side: OrderSide,
        price: float,
        size: float,
        order_type: OrderType = OrderType.FOK
    ) -> OrderResult:
        """
        Place an order on the exchange.

        Args:
            market_id: Market identifier
            outcome: "Yes" or "No"
            side: BUY or SELL
            price: Limit price
            size: Number of shares/contracts
            order_type: Order type (default FOK)

        Returns:
            OrderResult with execution details
        """
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an open order.

        Args:
            order_id: Order identifier

        Returns:
            True if cancellation successful
        """
        pass

    @abstractmethod
    async def get_balance(self) -> float:
        """
        Get available balance in USD(C).

        Returns:
            Available balance
        """
        pass

    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """
        Get all open positions.

        Returns:
            List of Position objects
        """
        pass

    async def get_market_by_id(
        self,
        market_id: str
    ) -> Optional[UnifiedMarket]:
        """
        Get a specific market by ID.

        Default implementation fetches all markets and filters.
        Override for more efficient platform-specific implementation.
        """
        markets = await self.fetch_markets()
        for market in markets:
            if market.market_id == market_id:
                return market
        return None

    async def get_both_order_books(
        self,
        market_id: str
    ) -> Tuple[Optional[UnifiedOrderBook], Optional[UnifiedOrderBook]]:
        """
        Get order books for both Yes and No outcomes.

        Returns:
            Tuple of (yes_orderbook, no_orderbook)
        """
        try:
            yes_ob = await self.get_order_book(market_id, "Yes")
            no_ob = await self.get_order_book(market_id, "No")
            return (yes_ob, no_ob)
        except Exception:
            return (None, None)
