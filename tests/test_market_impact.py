"""
Tests for MarketImpactCalculator.

These tests verify the CRITICAL depth-aware calculations that prevent
the bot from buying at effective prices > $1.00.
"""
import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.arbitrage import MarketImpactCalculator, MarketImpactResult


class TestMarketImpactCalculator:
    """Test cases for MarketImpactCalculator."""

    # ========================================
    # Tests for calculate_effective_cost
    # ========================================

    def test_single_level_full_fill(self):
        """Should calculate correctly when single level has enough liquidity."""
        book = [{"price": "0.50", "size": "100"}]
        result = MarketImpactCalculator.calculate_effective_cost(book, 50)

        assert result.effective_price == 0.50
        assert result.shares == 50
        assert result.total_cost == 25.0
        assert result.levels_consumed == 1
        assert result.has_sufficient_liquidity is True

    def test_multi_level_fill(self):
        """Should average price across multiple levels."""
        book = [
            {"price": "0.45", "size": "10"},
            {"price": "0.50", "size": "40"},
        ]
        result = MarketImpactCalculator.calculate_effective_cost(book, 50)

        # (10 * 0.45 + 40 * 0.50) / 50 = (4.5 + 20) / 50 = 0.49
        assert abs(result.effective_price - 0.49) < 0.001
        assert result.shares == 50
        assert result.levels_consumed == 2
        assert result.has_sufficient_liquidity is True

    def test_three_level_fill(self):
        """Should handle three price levels."""
        book = [
            {"price": "0.40", "size": "10"},
            {"price": "0.50", "size": "20"},
            {"price": "0.60", "size": "70"},
        ]
        result = MarketImpactCalculator.calculate_effective_cost(book, 100)

        # (10*0.40 + 20*0.50 + 70*0.60) / 100 = (4 + 10 + 42) / 100 = 0.56
        assert abs(result.effective_price - 0.56) < 0.001
        assert result.levels_consumed == 3

    def test_insufficient_liquidity(self):
        """Should report when not enough liquidity."""
        book = [{"price": "0.50", "size": "10"}]
        result = MarketImpactCalculator.calculate_effective_cost(book, 100)

        assert result.has_sufficient_liquidity is False
        assert result.shares == 10
        assert result.effective_price == 0.50

    def test_empty_book(self):
        """Should handle empty order book."""
        result = MarketImpactCalculator.calculate_effective_cost([], 50)

        assert result.has_sufficient_liquidity is False
        assert result.shares == 0
        assert result.effective_price == 0

    def test_zero_shares(self):
        """Should handle zero shares request."""
        book = [{"price": "0.50", "size": "100"}]
        result = MarketImpactCalculator.calculate_effective_cost(book, 0)

        assert result.has_sufficient_liquidity is False
        assert result.shares == 0

    def test_zero_size_levels_skipped(self):
        """Should skip levels with zero size."""
        book = [
            {"price": "0.45", "size": "0"},
            {"price": "0.50", "size": "100"},
        ]
        result = MarketImpactCalculator.calculate_effective_cost(book, 50)

        assert result.effective_price == 0.50
        assert result.levels_consumed == 1

    def test_exact_fill_at_level_boundary(self):
        """Should handle exact fill at level boundary."""
        book = [
            {"price": "0.45", "size": "50"},
            {"price": "0.55", "size": "50"},
        ]
        result = MarketImpactCalculator.calculate_effective_cost(book, 50)

        assert result.effective_price == 0.45
        assert result.levels_consumed == 1

    # ========================================
    # Tests for find_optimal_trade_size
    # ========================================

    def test_optimal_size_basic(self):
        """Should find profitable size with simple books."""
        yes_book = [{"price": "0.45", "size": "100"}]
        no_book = [{"price": "0.50", "size": "100"}]

        shares, eff_yes, eff_no = MarketImpactCalculator.find_optimal_trade_size(
            yes_book, no_book, max_combined_cost=0.98
        )

        # 0.45 + 0.50 = 0.95 < 0.98, should be profitable
        assert shares > 0
        assert eff_yes == 0.45
        assert eff_no == 0.50
        assert eff_yes + eff_no < 0.98

    def test_optimal_size_with_depth(self):
        """Should find correct size when depth limits profitability."""
        yes_book = [
            {"price": "0.45", "size": "50"},
            {"price": "0.55", "size": "100"},  # Expensive!
        ]
        no_book = [
            {"price": "0.50", "size": "50"},
            {"price": "0.60", "size": "100"},  # Expensive!
        ]

        shares, eff_yes, eff_no = MarketImpactCalculator.find_optimal_trade_size(
            yes_book, no_book, max_combined_cost=0.98
        )

        # At 50 shares: 0.45 + 0.50 = 0.95 (profitable)
        # At higher shares, we start consuming 2nd level
        # The algorithm finds the max profitable size
        assert shares > 0
        assert shares < 100  # Cannot be fully profitable at 100
        assert eff_yes + eff_no < 0.98

        # Verify the cost increases as we consume more levels
        result_at_100 = MarketImpactCalculator.calculate_effective_cost(yes_book, 100)
        result_no_100 = MarketImpactCalculator.calculate_effective_cost(no_book, 100)
        cost_at_100 = result_at_100.effective_price + result_no_100.effective_price
        # At 100 shares: higher than 0.98 (not profitable)
        assert cost_at_100 > 0.98

    def test_no_profitable_size(self):
        """Should return 0 when never profitable."""
        yes_book = [{"price": "0.55", "size": "100"}]
        no_book = [{"price": "0.50", "size": "100"}]

        # 0.55 + 0.50 = 1.05 > 0.98 at any size
        shares, eff_yes, eff_no = MarketImpactCalculator.find_optimal_trade_size(
            yes_book, no_book, max_combined_cost=0.98
        )

        assert shares == 0
        assert eff_yes == 0
        assert eff_no == 0

    def test_insufficient_liquidity_one_side(self):
        """Should return 0 when one side has no liquidity."""
        yes_book = [{"price": "0.45", "size": "100"}]
        no_book = []  # No liquidity

        shares, _, _ = MarketImpactCalculator.find_optimal_trade_size(
            yes_book, no_book, max_combined_cost=0.98
        )

        assert shares == 0

    def test_precision_parameter(self):
        """Should respect precision parameter."""
        yes_book = [{"price": "0.45", "size": "1000"}]
        no_book = [{"price": "0.50", "size": "1000"}]

        # With high precision
        shares1, _, _ = MarketImpactCalculator.find_optimal_trade_size(
            yes_book, no_book, max_combined_cost=0.98, precision=0.1
        )

        # With low precision
        shares2, _, _ = MarketImpactCalculator.find_optimal_trade_size(
            yes_book, no_book, max_combined_cost=0.98, precision=10
        )

        # Both should find profitable trades, but with different precision
        assert shares1 > 0
        assert shares2 > 0

    def test_max_shares_limit(self):
        """Should respect max_shares parameter."""
        yes_book = [{"price": "0.45", "size": "10000"}]
        no_book = [{"price": "0.50", "size": "10000"}]

        shares, _, _ = MarketImpactCalculator.find_optimal_trade_size(
            yes_book, no_book, max_combined_cost=0.98, max_shares=100
        )

        assert shares <= 100

    # ========================================
    # Tests for get_max_profitable_investment
    # ========================================

    def test_max_profitable_investment_basic(self):
        """Should calculate max investment and expected profit."""
        yes_book = [{"price": "0.45", "size": "100"}]
        no_book = [{"price": "0.50", "size": "100"}]

        investment, profit = MarketImpactCalculator.get_max_profitable_investment(
            yes_book, no_book, target_margin=0.02
        )

        assert investment > 0
        assert profit > 0
        # Profit should be positive portion of investment
        assert profit < investment

    def test_max_profitable_investment_not_profitable(self):
        """Should return 0 when not profitable."""
        yes_book = [{"price": "0.60", "size": "100"}]
        no_book = [{"price": "0.50", "size": "100"}]

        investment, profit = MarketImpactCalculator.get_max_profitable_investment(
            yes_book, no_book, target_margin=0.02
        )

        assert investment == 0
        assert profit == 0

    # ========================================
    # Real-world scenario tests
    # ========================================

    def test_realistic_arbitrage_scenario(self):
        """Test with realistic Polymarket order book data."""
        # Realistic YES order book
        yes_book = [
            {"price": "0.45", "size": "50"},
            {"price": "0.46", "size": "100"},
            {"price": "0.48", "size": "200"},
            {"price": "0.52", "size": "500"},
        ]
        # Realistic NO order book
        no_book = [
            {"price": "0.50", "size": "30"},
            {"price": "0.51", "size": "80"},
            {"price": "0.53", "size": "150"},
            {"price": "0.58", "size": "400"},
        ]

        # Top of book: 0.45 + 0.50 = 0.95 (looks profitable)
        # But at 100 shares, we'll consume multiple levels

        shares, eff_yes, eff_no = MarketImpactCalculator.find_optimal_trade_size(
            yes_book, no_book, max_combined_cost=0.98, precision=1.0
        )

        # Should find some profitable size
        if shares > 0:
            assert eff_yes + eff_no < 0.98
            # Verify the effective price is higher than top-of-book
            # if we're consuming multiple levels
            if shares > 30:  # More than first NO level
                assert eff_no > 0.50

    def test_market_impact_demonstration(self):
        """
        Demonstrate why market impact calculation is CRITICAL.

        This test shows the difference between naive top-of-book
        and proper depth-aware calculation.
        """
        yes_book = [
            {"price": "0.45", "size": "10"},
            {"price": "0.55", "size": "90"},
        ]
        no_book = [
            {"price": "0.50", "size": "10"},
            {"price": "0.60", "size": "90"},
        ]

        # NAIVE approach: Just look at top of book
        naive_cost = 0.45 + 0.50  # = 0.95 "Wow, 5% profit!"

        # REALITY at 50 shares:
        result_yes = MarketImpactCalculator.calculate_effective_cost(yes_book, 50)
        result_no = MarketImpactCalculator.calculate_effective_cost(no_book, 50)
        # YES: (10*0.45 + 40*0.55) / 50 = 0.53
        # NO: (10*0.50 + 40*0.60) / 50 = 0.58
        real_cost = result_yes.effective_price + result_no.effective_price
        # = 0.53 + 0.58 = 1.11 -> LOSS!

        assert naive_cost < 1.0  # Naive thinks it's profitable
        assert real_cost > 1.0   # Reality: it's a LOSS!

        # The calculator should NOT find 50 shares as profitable
        shares, _, _ = MarketImpactCalculator.find_optimal_trade_size(
            yes_book, no_book, max_combined_cost=0.98
        )

        # Should only find ~10 shares profitable (first levels only)
        assert shares < 15  # Must be limited to first levels


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
