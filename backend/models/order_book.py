"""
Order Book data model.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional


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
