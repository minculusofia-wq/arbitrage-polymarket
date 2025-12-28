"""
Tests for OptimizedOrderBook.
"""
import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.models.order_book import OptimizedOrderBook, OrderBook, OrderBookLevel


class TestOptimizedOrderBook:
    """Test cases for OptimizedOrderBook."""

    def test_empty_book(self):
        """Should handle empty order book."""
        book = OptimizedOrderBook("token_1")
        assert book.best_ask is None
        assert book.best_bid is None
        assert book.has_liquidity() is False

    def test_update_asks(self):
        """Should correctly update asks."""
        book = OptimizedOrderBook("token_1")
        asks = [
            {"price": "0.55", "size": "100"},
            {"price": "0.50", "size": "200"},
            {"price": "0.60", "size": "50"}
        ]
        book.update_asks(asks)

        # Best ask should be lowest price
        assert book.best_ask == 0.50

    def test_update_bids(self):
        """Should correctly update bids."""
        book = OptimizedOrderBook("token_1")
        bids = [
            {"price": "0.45", "size": "100"},
            {"price": "0.50", "size": "200"},
            {"price": "0.40", "size": "50"}
        ]
        book.update_bids(bids)

        # Best bid should be highest price
        assert book.best_bid == 0.50

    def test_update_from_data(self):
        """Should update from WebSocket-style data."""
        book = OptimizedOrderBook("token_1")
        data = {
            "asks": [{"price": "0.55", "size": "100"}],
            "bids": [{"price": "0.45", "size": "100"}]
        }
        book.update(data)

        assert book.best_ask == 0.55
        assert book.best_bid == 0.45
        assert book.has_liquidity() is True

    def test_best_ask_with_size(self):
        """Should return price and size for best ask."""
        book = OptimizedOrderBook("token_1")
        book.update_asks([{"price": "0.50", "size": "100"}])

        result = book.best_ask_with_size
        assert result == (0.50, 100.0)

    def test_best_bid_with_size(self):
        """Should return price and size for best bid."""
        book = OptimizedOrderBook("token_1")
        book.update_bids([{"price": "0.45", "size": "200"}])

        result = book.best_bid_with_size
        assert result == (0.45, 200.0)

    def test_get_spread(self):
        """Should calculate bid-ask spread."""
        book = OptimizedOrderBook("token_1")
        book.update({
            "asks": [{"price": "0.55", "size": "100"}],
            "bids": [{"price": "0.45", "size": "100"}]
        })

        spread = book.get_spread()
        assert abs(spread - 0.10) < 1e-9  # Float precision tolerance

    def test_get_spread_no_liquidity(self):
        """Should return None when no liquidity."""
        book = OptimizedOrderBook("token_1")
        assert book.get_spread() is None

    def test_get_mid_price(self):
        """Should calculate mid-market price."""
        book = OptimizedOrderBook("token_1")
        book.update({
            "asks": [{"price": "0.60", "size": "100"}],
            "bids": [{"price": "0.40", "size": "100"}]
        })

        mid = book.get_mid_price()
        assert mid == 0.50

    def test_get_depth(self):
        """Should return order book depth."""
        book = OptimizedOrderBook("token_1")
        book.update({
            "asks": [
                {"price": "0.50", "size": "100"},
                {"price": "0.55", "size": "200"},
                {"price": "0.60", "size": "300"}
            ],
            "bids": [
                {"price": "0.45", "size": "100"},
                {"price": "0.40", "size": "200"}
            ]
        })

        depth = book.get_depth(levels=2)
        assert len(depth["asks"]) == 2
        assert len(depth["bids"]) == 2
        assert depth["asks"][0]["price"] == 0.50  # Best ask first

    def test_zero_size_ignored(self):
        """Should ignore orders with zero size."""
        book = OptimizedOrderBook("token_1")
        book.update_asks([
            {"price": "0.50", "size": "0"},
            {"price": "0.55", "size": "100"}
        ])

        assert book.best_ask == 0.55


class TestOrderBook:
    """Test cases for basic OrderBook (backward compatibility)."""

    def test_update(self):
        """Should update from data."""
        book = OrderBook(token_id="token_1")
        book.update({
            "asks": [{"price": "0.50", "size": "100"}],
            "bids": [{"price": "0.45", "size": "100"}]
        })

        assert book.best_ask == 0.50
        assert book.best_bid == 0.45

    def test_has_liquidity(self):
        """Should report liquidity correctly."""
        book = OrderBook(token_id="token_1")
        assert book.has_liquidity() is False

        book.bids = [OrderBookLevel(price=0.45, size=100)]
        assert book.has_liquidity() is False

        book.asks = [OrderBookLevel(price=0.55, size=100)]
        assert book.has_liquidity() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
