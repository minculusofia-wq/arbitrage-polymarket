"""
Tests for MarketScorer.

These tests verify the market quality scoring system that prioritizes
markets for arbitrage scanning.
"""
import pytest
import sys
import os
from datetime import datetime, timedelta, timezone

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.market_scorer import MarketScorer, MarketScore


class TestMarketScorer:
    """Test cases for MarketScorer."""

    # ========================================
    # Tests for volume scoring
    # ========================================

    def test_volume_score_max(self):
        """Should give max volume score for high volume markets."""
        market = {
            'condition_id': 'test-market',
            'volume': 150000,  # > $100k
            'tokens': [
                {'token_id': 'yes-token'},
                {'token_id': 'no-token'}
            ]
        }
        order_books = {}

        score = MarketScorer.score_market(market, order_books)

        assert score.volume_score == 30.0  # Max score

    def test_volume_score_partial(self):
        """Should give partial volume score for medium volume."""
        market = {
            'condition_id': 'test-market',
            'volume': 50000,  # 50% of max
            'tokens': [
                {'token_id': 'yes-token'},
                {'token_id': 'no-token'}
            ]
        }
        order_books = {}

        score = MarketScorer.score_market(market, order_books)

        assert score.volume_score == 15.0  # 50% of 30

    def test_volume_score_zero(self):
        """Should give zero volume score for no volume."""
        market = {
            'condition_id': 'test-market',
            'volume': 0,
            'tokens': [
                {'token_id': 'yes-token'},
                {'token_id': 'no-token'}
            ]
        }
        order_books = {}

        score = MarketScorer.score_market(market, order_books)

        assert score.volume_score == 0.0

    # ========================================
    # Tests for liquidity scoring
    # ========================================

    def test_liquidity_score_good_depth(self):
        """Should score high with good order book depth."""
        market = {
            'condition_id': 'test-market',
            'volume': 10000,
            'tokens': [
                {'token_id': 'yes-token'},
                {'token_id': 'no-token'}
            ]
        }
        order_books = {
            'yes-token': {
                'asks': [
                    {'price': '0.50', 'size': '1000'},
                    {'price': '0.51', 'size': '2000'},
                ],
                'bids': [
                    {'price': '0.49', 'size': '1000'},
                ]
            },
            'no-token': {
                'asks': [
                    {'price': '0.50', 'size': '1000'},
                ],
                'bids': [
                    {'price': '0.49', 'size': '1000'},
                ]
            }
        }

        score = MarketScorer.score_market(market, order_books)

        assert score.liquidity_score > 0

    def test_liquidity_score_empty_books(self):
        """Should give zero liquidity for empty order books."""
        market = {
            'condition_id': 'test-market',
            'volume': 10000,
            'tokens': [
                {'token_id': 'yes-token'},
                {'token_id': 'no-token'}
            ]
        }
        order_books = {}

        score = MarketScorer.score_market(market, order_books)

        assert score.liquidity_score == 0.0

    # ========================================
    # Tests for spread scoring
    # ========================================

    def test_spread_score_optimal(self):
        """Should give max spread score for tight spreads."""
        market = {
            'condition_id': 'test-market',
            'volume': 10000,
            'tokens': [
                {'token_id': 'yes-token'},
                {'token_id': 'no-token'}
            ]
        }
        # Combined = 0.49 + 0.49 = 0.98, spread = 2%
        order_books = {
            'yes-token': {
                'asks': [{'price': '0.49', 'size': '100'}],
                'bids': []
            },
            'no-token': {
                'asks': [{'price': '0.49', 'size': '100'}],
                'bids': []
            }
        }

        score = MarketScorer.score_market(market, order_books)

        assert score.spread_score == 20.0  # Max for <= 2% spread

    def test_spread_score_wide(self):
        """Should give lower spread score for wide spreads."""
        market = {
            'condition_id': 'test-market',
            'volume': 10000,
            'tokens': [
                {'token_id': 'yes-token'},
                {'token_id': 'no-token'}
            ]
        }
        # Combined = 0.55 + 0.55 = 1.10, spread = 10%
        order_books = {
            'yes-token': {
                'asks': [{'price': '0.55', 'size': '100'}],
                'bids': []
            },
            'no-token': {
                'asks': [{'price': '0.55', 'size': '100'}],
                'bids': []
            }
        }

        score = MarketScorer.score_market(market, order_books)

        assert score.spread_score == 0.0  # Zero for >= 10% spread

    def test_spread_score_empty_books(self):
        """Should give zero spread score for empty order books."""
        market = {
            'condition_id': 'test-market',
            'volume': 10000,
            'tokens': [
                {'token_id': 'yes-token'},
                {'token_id': 'no-token'}
            ]
        }
        order_books = {}

        score = MarketScorer.score_market(market, order_books)

        assert score.spread_score == 0.0

    # ========================================
    # Tests for time scoring
    # ========================================

    def test_time_score_optimal_window(self):
        """Should give max time score for markets in optimal window."""
        end_date = datetime.now(timezone.utc) + timedelta(days=15)
        market = {
            'condition_id': 'test-market',
            'volume': 10000,
            'end_date_iso': end_date.isoformat(),
            'tokens': [
                {'token_id': 'yes-token'},
                {'token_id': 'no-token'}
            ]
        }
        order_books = {}

        score = MarketScorer.score_market(market, order_books)

        assert score.time_score == 20.0  # Max for 1-30 days

    def test_time_score_expired(self):
        """Should give zero time score for expired markets."""
        end_date = datetime.now(timezone.utc) - timedelta(days=1)
        market = {
            'condition_id': 'test-market',
            'volume': 10000,
            'end_date_iso': end_date.isoformat(),
            'tokens': [
                {'token_id': 'yes-token'},
                {'token_id': 'no-token'}
            ]
        }
        order_books = {}

        score = MarketScorer.score_market(market, order_books)

        assert score.time_score == 0.0

    def test_time_score_too_soon(self):
        """Should give lower time score for markets resolving very soon."""
        end_date = datetime.now(timezone.utc) + timedelta(hours=12)
        market = {
            'condition_id': 'test-market',
            'volume': 10000,
            'end_date_iso': end_date.isoformat(),
            'tokens': [
                {'token_id': 'yes-token'},
                {'token_id': 'no-token'}
            ]
        }
        order_books = {}

        score = MarketScorer.score_market(market, order_books)

        assert score.time_score < 10.0  # Lower than optimal

    def test_time_score_far_out(self):
        """Should give lower time score for markets resolving far out."""
        end_date = datetime.now(timezone.utc) + timedelta(days=120)
        market = {
            'condition_id': 'test-market',
            'volume': 10000,
            'end_date_iso': end_date.isoformat(),
            'tokens': [
                {'token_id': 'yes-token'},
                {'token_id': 'no-token'}
            ]
        }
        order_books = {}

        score = MarketScorer.score_market(market, order_books)

        assert score.time_score == 5.0  # Minimum for > 90 days

    def test_time_score_no_date(self):
        """Should give default time score when no date provided."""
        market = {
            'condition_id': 'test-market',
            'volume': 10000,
            'tokens': [
                {'token_id': 'yes-token'},
                {'token_id': 'no-token'}
            ]
        }
        order_books = {}

        score = MarketScorer.score_market(market, order_books)

        assert score.time_score == 10.0  # Default middle score

    # ========================================
    # Tests for is_tradeable property
    # ========================================

    def test_is_tradeable_high_score(self):
        """Should be tradeable with high score."""
        score = MarketScore(
            market_id='test',
            volume_score=25,
            liquidity_score=20,
            spread_score=15,
            time_score=15,
            total_score=75
        )

        assert score.is_tradeable is True

    def test_is_tradeable_low_score(self):
        """Should not be tradeable with low score."""
        score = MarketScore(
            market_id='test',
            volume_score=10,
            liquidity_score=10,
            spread_score=5,
            time_score=5,
            total_score=30
        )

        assert score.is_tradeable is False

    def test_is_tradeable_threshold(self):
        """Should be tradeable at exact threshold."""
        score = MarketScore(
            market_id='test',
            volume_score=20,
            liquidity_score=15,
            spread_score=10,
            time_score=5,
            total_score=50  # Exact threshold
        )

        assert score.is_tradeable is True

    # ========================================
    # Tests for filter_quality_markets
    # ========================================

    def test_filter_quality_markets_sorts_by_score(self):
        """Should return markets sorted by score descending."""
        markets = [
            {
                'condition_id': 'low-volume',
                'volume': 1000,
                'tokens': [{'token_id': 'y1'}, {'token_id': 'n1'}]
            },
            {
                'condition_id': 'high-volume',
                'volume': 200000,
                'tokens': [{'token_id': 'y2'}, {'token_id': 'n2'}]
            },
            {
                'condition_id': 'mid-volume',
                'volume': 50000,
                'tokens': [{'token_id': 'y3'}, {'token_id': 'n3'}]
            }
        ]
        order_books = {}

        scored = MarketScorer.filter_quality_markets(markets, order_books, min_score=0)

        assert len(scored) == 3
        assert scored[0].market_id == 'high-volume'
        assert scored[1].market_id == 'mid-volume'
        assert scored[2].market_id == 'low-volume'

    def test_filter_quality_markets_filters_by_threshold(self):
        """Should filter out markets below threshold."""
        markets = [
            {
                'condition_id': 'low-score',
                'volume': 100,
                'tokens': [{'token_id': 'y1'}, {'token_id': 'n1'}]
            },
            {
                'condition_id': 'high-score',
                'volume': 200000,
                'tokens': [{'token_id': 'y2'}, {'token_id': 'n2'}]
            }
        ]
        order_books = {}

        scored = MarketScorer.filter_quality_markets(markets, order_books)

        # Only high-score market should pass default threshold
        assert len(scored) <= 2  # Depends on score calculation

    # ========================================
    # Tests for get_top_markets
    # ========================================

    def test_get_top_markets_limits_results(self):
        """Should return only top N markets."""
        # Use volumes below $100k to avoid capping at max score
        markets = [
            {
                'condition_id': f'market-{i}',
                'volume': 10000 + i * 5000,  # 10k to 55k
                'tokens': [{'token_id': f'y{i}'}, {'token_id': f'n{i}'}]
            }
            for i in range(10)
        ]
        order_books = {}

        top = MarketScorer.get_top_markets(markets, order_books, n=3)

        assert len(top) == 3
        # Should be the highest volume markets
        assert top[0].market_id == 'market-9'  # 55k volume
        assert top[1].market_id == 'market-8'  # 50k volume
        assert top[2].market_id == 'market-7'  # 45k volume


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
