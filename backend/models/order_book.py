"""
Order Book data model with SortedDict optimization.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from sortedcontainers import SortedDict


@dataclass
class OrderBookLevel:
    """Represents a single level in the order book."""
    price: float
    size: float


@dataclass
class OrderBook:
    """
    Order Book for a single token.
    Tracks bids (buy orders) and asks (sell orders).
    """
    token_id: str
    bids: List[OrderBookLevel] = field(default_factory=list)
    asks: List[OrderBookLevel] = field(default_factory=list)

    def update(self, data: dict) -> None:
        """Update the order book with new data from WebSocket."""
        if 'bids' in data:
            self.bids = [
                OrderBookLevel(price=float(b['price']), size=float(b.get('size', 0)))
                for b in data['bids']
            ]
        if 'asks' in data:
            self.asks = [
                OrderBookLevel(price=float(a['price']), size=float(a.get('size', 0)))
                for a in data['asks']
            ]

    @property
    def best_bid(self) -> Optional[float]:
        """Get the best (highest) bid price."""
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        """Get the best (lowest) ask price."""
        return self.asks[0].price if self.asks else None

    def has_liquidity(self) -> bool:
        """Check if the order book has both bids and asks."""
        return bool(self.bids and self.asks)


class OptimizedOrderBook:
    """
    High-performance Order Book using SortedDict.
    Provides O(log n) updates and O(1) best price access.
    """

    def __init__(self, token_id: str):
        self.token_id = token_id
        # Asks: sorted ascending (lowest price = best ask = first)
        self.asks: SortedDict = SortedDict()
        # Bids: sorted descending (highest price = best bid = first)
        self.bids: SortedDict = SortedDict(lambda x: -x)
        self._last_update: float = 0.0

    def update_asks(self, asks: List[dict]) -> None:
        """Update asks from WebSocket data."""
        self.asks.clear()
        for a in asks:
            price = float(a['price'])
            size = float(a.get('size', 0))
            if size > 0:
                self.asks[price] = size

    def update_bids(self, bids: List[dict]) -> None:
        """Update bids from WebSocket data."""
        self.bids.clear()
        for b in bids:
            price = float(b['price'])
            size = float(b.get('size', 0))
            if size > 0:
                self.bids[price] = size

    def update(self, data: dict) -> None:
        """Update from WebSocket message."""
        import time
        if 'asks' in data:
            self.update_asks(data['asks'])
        if 'bids' in data:
            self.update_bids(data['bids'])
        self._last_update = time.time()

    @property
    def best_ask(self) -> Optional[float]:
        """Get the best (lowest) ask price. O(1) access."""
        if self.asks:
            return self.asks.peekitem(0)[0]
        return None

    @property
    def best_bid(self) -> Optional[float]:
        """Get the best (highest) bid price. O(1) access."""
        if self.bids:
            return self.bids.peekitem(0)[0]
        return None

    @property
    def best_ask_with_size(self) -> Optional[Tuple[float, float]]:
        """Get the best ask price and size."""
        if self.asks:
            return self.asks.peekitem(0)
        return None

    @property
    def best_bid_with_size(self) -> Optional[Tuple[float, float]]:
        """Get the best bid price and size."""
        if self.bids:
            return self.bids.peekitem(0)
        return None

    def has_liquidity(self) -> bool:
        """Check if the order book has both bids and asks."""
        return bool(self.asks and self.bids)

    def get_spread(self) -> Optional[float]:
        """Get the bid-ask spread."""
        if self.best_ask is not None and self.best_bid is not None:
            return self.best_ask - self.best_bid
        return None

    def get_mid_price(self) -> Optional[float]:
        """Get the mid-market price."""
        if self.best_ask is not None and self.best_bid is not None:
            return (self.best_ask + self.best_bid) / 2
        return None

    def get_depth(self, levels: int = 5) -> dict:
        """Get top N levels of the order book."""
        ask_levels = list(self.asks.items())[:levels]
        bid_levels = list(self.bids.items())[:levels]
        return {
            'asks': [{'price': p, 'size': s} for p, s in ask_levels],
            'bids': [{'price': p, 'size': s} for p, s in bid_levels]
        }
