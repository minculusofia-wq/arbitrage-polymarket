"""
Market Quality Scorer - Prioritizes markets based on trading suitability.

Scores markets based on:
- Volume (liquidity indicator)
- Order book depth (execution quality)
- Spread (trading cost)
- Time to resolution (opportunity window)
"""
from dataclasses import dataclass
from typing import List, Dict, Optional
from datetime import datetime, timezone


@dataclass
class MarketScore:
    """Score breakdown for a single market."""
    market_id: str
    volume_score: float      # 0-30 points
    liquidity_score: float   # 0-30 points
    spread_score: float      # 0-20 points
    time_score: float        # 0-20 points
    total_score: float       # 0-100 points

    @property
    def is_tradeable(self) -> bool:
        """Check if market meets minimum quality threshold."""
        return self.total_score >= MarketScorer.MIN_SCORE_THRESHOLD


class MarketScorer:
    """
    Scores markets for prioritization in arbitrage scanning.

    Higher scores = better trading conditions.
    """

    MIN_SCORE_THRESHOLD = 50  # Markets below this are skipped

    # Scoring weights and thresholds
    VOLUME_MAX = 100000  # $100k daily volume = max score
    LIQUIDITY_MAX = 5000  # $5k at best bid/ask = max score
    SPREAD_OPTIMAL = 0.02  # 2% spread = max score
    SPREAD_MAX = 0.10  # 10% spread = zero score

    # Time scoring thresholds (in days)
    TIME_OPTIMAL_MIN = 1    # Markets resolving in 1-30 days are optimal
    TIME_OPTIMAL_MAX = 30
    TIME_MAX = 90  # Markets resolving > 90 days get lower scores

    @classmethod
    def score_market(
        cls,
        market: Dict,
        order_books: Dict[str, Dict]
    ) -> MarketScore:
        """
        Calculate comprehensive score for a market.

        Args:
            market: Market data with volume, tokens, end_date, etc.
            order_books: Dict of token_id -> {bids: [], asks: []}

        Returns:
            MarketScore with breakdown and total
        """
        market_id = market.get('condition_id', market.get('id', 'unknown'))

        # Volume Score (0-30)
        volume = float(market.get('volume', 0))
        volume_score = min(volume / cls.VOLUME_MAX, 1.0) * 30

        # Liquidity Score (0-30)
        liquidity_score = cls._calculate_liquidity_score(market, order_books)

        # Spread Score (0-20)
        spread_score = cls._calculate_spread_score(market, order_books)

        # Time Score (0-20)
        time_score = cls._calculate_time_score(market)

        total = volume_score + liquidity_score + spread_score + time_score

        return MarketScore(
            market_id=market_id,
            volume_score=round(volume_score, 2),
            liquidity_score=round(liquidity_score, 2),
            spread_score=round(spread_score, 2),
            time_score=round(time_score, 2),
            total_score=round(total, 2)
        )

    @classmethod
    def _calculate_liquidity_score(
        cls,
        market: Dict,
        order_books: Dict[str, Dict]
    ) -> float:
        """Calculate liquidity score based on order book depth."""
        tokens = market.get('tokens', [])
        if len(tokens) < 2:
            return 0.0

        total_liquidity = 0.0

        for token in tokens:
            token_id = token.get('token_id', '')
            book = order_books.get(token_id, {})

            # Sum liquidity at best levels (top 3 levels)
            asks = book.get('asks', [])[:3]
            bids = book.get('bids', [])[:3]

            for level in asks:
                price = float(level.get('price', 0))
                size = float(level.get('size', 0))
                total_liquidity += price * size

            for level in bids:
                price = float(level.get('price', 0))
                size = float(level.get('size', 0))
                total_liquidity += price * size

        # Normalize to 0-30 points
        return min(total_liquidity / cls.LIQUIDITY_MAX, 1.0) * 30

    @classmethod
    def _calculate_spread_score(
        cls,
        market: Dict,
        order_books: Dict[str, Dict]
    ) -> float:
        """
        Calculate spread score based on bid-ask spread.

        For arbitrage, we care about YES+NO combined spread.
        """
        tokens = market.get('tokens', [])
        if len(tokens) < 2:
            return 0.0

        yes_token = tokens[0].get('token_id', '')
        no_token = tokens[1].get('token_id', '')

        yes_book = order_books.get(yes_token, {})
        no_book = order_books.get(no_token, {})

        # Get best ask prices
        yes_asks = yes_book.get('asks', [])
        no_asks = no_book.get('asks', [])

        if not yes_asks or not no_asks:
            return 0.0

        yes_best_ask = float(yes_asks[0].get('price', 1.0))
        no_best_ask = float(no_asks[0].get('price', 1.0))

        # Combined spread from theoretical $1
        combined_cost = yes_best_ask + no_best_ask
        spread = abs(combined_cost - 1.0)

        if spread >= cls.SPREAD_MAX:
            return 0.0
        if spread <= cls.SPREAD_OPTIMAL:
            return 20.0

        # Linear interpolation
        spread_ratio = (cls.SPREAD_MAX - spread) / (cls.SPREAD_MAX - cls.SPREAD_OPTIMAL)
        return spread_ratio * 20

    @classmethod
    def _calculate_time_score(cls, market: Dict) -> float:
        """
        Calculate time score based on resolution date.

        Markets resolving too soon (< 1 day) or too far (> 90 days)
        get lower scores.
        """
        end_date_str = market.get('end_date_iso', market.get('end_date', ''))

        if not end_date_str:
            return 10.0  # Default middle score if no date

        try:
            # Parse ISO date
            if isinstance(end_date_str, str):
                end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
            else:
                end_date = end_date_str

            now = datetime.now(timezone.utc)
            days_until = (end_date - now).days

            if days_until < 0:
                return 0.0  # Already expired

            if days_until < cls.TIME_OPTIMAL_MIN:
                # Too close to resolution - risky
                return days_until / cls.TIME_OPTIMAL_MIN * 10

            if days_until <= cls.TIME_OPTIMAL_MAX:
                return 20.0  # Optimal window

            if days_until <= cls.TIME_MAX:
                # Linear decay after optimal window
                decay = (cls.TIME_MAX - days_until) / (cls.TIME_MAX - cls.TIME_OPTIMAL_MAX)
                return 10 + decay * 10

            return 5.0  # Very far out - lower priority

        except Exception:
            return 10.0  # Default on parse error

    @classmethod
    def filter_quality_markets(
        cls,
        markets: List[Dict],
        order_books: Dict[str, Dict],
        min_score: Optional[float] = None
    ) -> List[MarketScore]:
        """
        Filter and rank markets by quality score.

        Args:
            markets: List of market data dicts
            order_books: All order books keyed by token_id
            min_score: Minimum score threshold (default: MIN_SCORE_THRESHOLD)

        Returns:
            List of MarketScore objects, sorted by total_score descending
        """
        threshold = min_score if min_score is not None else cls.MIN_SCORE_THRESHOLD

        scored = []
        for market in markets:
            score = cls.score_market(market, order_books)
            if score.total_score >= threshold:
                scored.append(score)

        # Sort by total score descending
        return sorted(scored, key=lambda x: x.total_score, reverse=True)

    @classmethod
    def get_top_markets(
        cls,
        markets: List[Dict],
        order_books: Dict[str, Dict],
        n: int = 10
    ) -> List[MarketScore]:
        """
        Get the top N markets by quality score.

        Args:
            markets: List of market data dicts
            order_books: All order books keyed by token_id
            n: Number of top markets to return

        Returns:
            List of top N MarketScore objects
        """
        all_scored = cls.filter_quality_markets(markets, order_books, min_score=0)
        return all_scored[:n]
