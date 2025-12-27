"""
Market fetching service.
"""
import asyncio
from typing import Dict, List, Optional
from backend.config import Config
from backend.logger import logger


class MarketService:
    """
    Service for fetching and managing market data from Polymarket.
    """

    def __init__(self, client, config: Config):
        self.client = client
        self.config = config
        self.market_details: Dict[str, dict] = {}
        self.token_to_market: Dict[str, str] = {}  # token_id -> market_id mapping

    async def fetch_markets(self) -> List[str]:
        """
        Fetches active binary markets filtered by volume.
        Returns list of condition_ids (market IDs).
        """
        logger.info("Fetching markets...")
        markets_whitelist = []

        try:
            loop = asyncio.get_running_loop()
            markets = await loop.run_in_executor(
                None,
                lambda: self.client.get_markets(
                    limit=50,
                    active=True,
                    volume_min=self.config.MIN_MARKET_VOLUME
                )
            )

            for m in markets:
                # Filter for Binary Yes/No markets
                if len(m.get('tokens', [])) == 2:
                    condition_id = m['condition_id']
                    markets_whitelist.append(condition_id)
                    self.market_details[condition_id] = m

                    # Build token to market index for fast lookup
                    for token in m['tokens']:
                        self.token_to_market[token['token_id']] = condition_id

            logger.info(f"Monitoring {len(markets_whitelist)} markets with significant volume.")

        except Exception as e:
            logger.error(f"Error fetching markets: {e}")

        return markets_whitelist

    def get_market_tokens(self, market_id: str) -> Optional[tuple]:
        """
        Get YES and NO token IDs for a market.
        Returns (yes_token_id, no_token_id) or None.
        """
        market = self.market_details.get(market_id)
        if market and 'tokens' in market and len(market['tokens']) >= 2:
            return (market['tokens'][0]['token_id'], market['tokens'][1]['token_id'])
        return None

    def get_market_for_token(self, token_id: str) -> Optional[str]:
        """
        Fast O(1) lookup of market ID for a token.
        """
        return self.token_to_market.get(token_id)

    def get_token_ids(self) -> List[str]:
        """
        Get all token IDs for subscription.
        Respects MAX_TOKENS_MONITOR limit.
        """
        token_ids = []
        for cid in list(self.market_details.keys()):
            m = self.market_details[cid]
            if 'tokens' in m:
                token_ids.append(m['tokens'][0]['token_id'])
                token_ids.append(m['tokens'][1]['token_id'])

        # Limit tokens for reliability
        return token_ids[:self.config.MAX_TOKENS_MONITOR]
