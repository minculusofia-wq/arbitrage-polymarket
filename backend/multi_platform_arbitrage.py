"""
Multi-Platform Arbitrage Bot - Cross-platform arbitrage detection and execution.

This module provides the main bot class that coordinates arbitrage detection
across multiple prediction market platforms (Polymarket, Kalshi).
"""

import asyncio
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set
from difflib import SequenceMatcher

from backend.config import Config
from backend.interfaces.exchange_client import (
    IExchangeClient,
    UnifiedMarket,
    UnifiedOrderBook,
    OrderSide,
    OrderType
)
from backend.interfaces.credentials import (
    PolymarketCredentials,
    KalshiCredentials
)
from backend.clients.polymarket_client import PolymarketClient
from backend.clients.kalshi_client import KalshiClient
from backend.services.rate_limiter import APIRateLimiter
from backend.services.risk_manager import RiskManager
from backend.services.capital_allocator import CapitalAllocator
from backend.services.trade_storage import TradeStorage
from backend.services.data_collector import DataCollector

logger = logging.getLogger(__name__)


@dataclass
class ArbitrageOpportunity:
    """Represents a detected arbitrage opportunity."""
    opportunity_type: str  # "intra_platform" or "cross_platform"
    platform: str  # Primary platform for intra, or "cross" for cross-platform
    market_id: str
    question: str
    yes_price: float
    no_price: float
    total_cost: float
    roi_percent: float
    timestamp: float = field(default_factory=time.time)

    # Cross-platform specific fields
    platform_1: Optional[str] = None
    market_id_1: Optional[str] = None
    platform_2: Optional[str] = None
    market_id_2: Optional[str] = None

    @property
    def is_profitable(self) -> bool:
        return self.total_cost < 1.0 and self.roi_percent > 0


@dataclass
class MarketMatch:
    """Represents a matched market across platforms."""
    question: str
    similarity: float
    polymarket: Optional[UnifiedMarket] = None
    kalshi: Optional[UnifiedMarket] = None

    @property
    def is_valid(self) -> bool:
        return self.polymarket is not None and self.kalshi is not None


class MultiPlatformArbitrageBot:
    """
    Bot for detecting and executing arbitrage across multiple platforms.

    Supports:
    - Intra-platform arbitrage (YES + NO < 1 on same platform)
    - Cross-platform arbitrage (same question, different prices across platforms)
    """

    def __init__(self, config: Config):
        self.config = config
        self.clients: Dict[str, IExchangeClient] = {}
        self.markets: Dict[str, List[UnifiedMarket]] = {}
        self.matched_markets: List[MarketMatch] = []
        self.running = False

        # Services
        self.rate_limiter = APIRateLimiter()
        self.risk_manager = RiskManager.from_config(config)
        self.capital_allocator = CapitalAllocator(config.CAPITAL_PER_TRADE)
        self.trade_storage = TradeStorage()
        self.data_collector = DataCollector()

        # Callbacks for UI
        self.on_opportunity: Optional[callable] = None
        self.on_trade: Optional[callable] = None

        # Tracking
        self._opportunity_cache: Dict[str, ArbitrageOpportunity] = {}
        self._last_markets_fetch: float = 0
        self._markets_fetch_interval: float = 300.0  # 5 minutes

    async def initialize_clients(self) -> bool:
        """Initialize clients for all enabled platforms."""
        success = True

        if "polymarket" in self.config.ENABLED_PLATFORMS:
            poly_creds = PolymarketCredentials(
                api_key=self.config.POLY_API_KEY,
                api_secret=self.config.POLY_API_SECRET,
                passphrase=self.config.POLY_API_PASSPHRASE,
                private_key=self.config.PRIVATE_KEY
            )

            if poly_creds.is_complete():
                client = PolymarketClient(poly_creds)
                if await client.connect():
                    self.clients["polymarket"] = client
                    logger.info("Polymarket client initialized")
                else:
                    logger.error("Failed to connect to Polymarket")
                    success = False
            else:
                logger.warning("Polymarket credentials incomplete, skipping")

        if "kalshi" in self.config.ENABLED_PLATFORMS:
            kalshi_creds = KalshiCredentials(
                email=self.config.KALSHI_EMAIL,
                password=self.config.KALSHI_PASSWORD,
                api_key=self.config.KALSHI_API_KEY or None
            )

            if kalshi_creds.is_complete():
                client = KalshiClient(kalshi_creds)
                if await client.connect():
                    self.clients["kalshi"] = client
                    logger.info("Kalshi client initialized")
                else:
                    logger.error("Failed to connect to Kalshi")
                    success = False
            else:
                logger.warning("Kalshi credentials incomplete, skipping")

        if not self.clients:
            logger.error("No platforms initialized successfully")
            return False

        logger.info(f"Initialized {len(self.clients)} platform client(s): {list(self.clients.keys())}")
        return success

    async def fetch_all_markets(self) -> Dict[str, List[UnifiedMarket]]:
        """Fetch markets from all connected platforms."""
        self.markets.clear()

        tasks = []
        for platform, client in self.clients.items():
            tasks.append(self._fetch_platform_markets(platform, client))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, (platform, _) in enumerate(self.clients.items()):
            if isinstance(results[i], Exception):
                logger.error(f"Error fetching {platform} markets: {results[i]}")
            else:
                self.markets[platform] = results[i]
                logger.info(f"Fetched {len(results[i])} markets from {platform}")

        self._last_markets_fetch = time.time()

        # Match markets across platforms if cross-platform enabled
        if self.config.CROSS_PLATFORM_ARBITRAGE and len(self.clients) > 1:
            self._match_markets_across_platforms()

        return self.markets

    async def _fetch_platform_markets(
        self,
        platform: str,
        client: IExchangeClient
    ) -> List[UnifiedMarket]:
        """Fetch markets from a specific platform."""
        return await client.fetch_markets(
            min_volume=self.config.MIN_MARKET_VOLUME,
            active_only=True
        )

    def _match_markets_across_platforms(self) -> List[MarketMatch]:
        """Match similar markets across platforms by question similarity."""
        self.matched_markets.clear()

        poly_markets = self.markets.get("polymarket", [])
        kalshi_markets = self.markets.get("kalshi", [])

        if not poly_markets or not kalshi_markets:
            return []

        for poly in poly_markets:
            best_match: Optional[UnifiedMarket] = None
            best_ratio = 0.0

            poly_question = poly.question.lower().strip()

            for kalshi in kalshi_markets:
                kalshi_question = kalshi.question.lower().strip()

                # Calculate similarity ratio
                ratio = SequenceMatcher(
                    None,
                    poly_question,
                    kalshi_question
                ).ratio()

                if ratio > 0.80 and ratio > best_ratio:  # 80% threshold
                    best_match = kalshi
                    best_ratio = ratio

            if best_match:
                match = MarketMatch(
                    question=poly.question,
                    similarity=best_ratio,
                    polymarket=poly,
                    kalshi=best_match
                )
                self.matched_markets.append(match)
                logger.debug(
                    f"Matched markets ({best_ratio:.0%}): "
                    f"Poly '{poly.question[:50]}...' <-> Kalshi '{best_match.question[:50]}...'"
                )

        logger.info(f"Found {len(self.matched_markets)} matched markets across platforms")
        return self.matched_markets

    async def detect_intra_platform_arbitrage(
        self,
        platform: str
    ) -> List[ArbitrageOpportunity]:
        """
        Detect arbitrage opportunities within a single platform.

        Looking for markets where YES + NO ask prices < 1.0
        """
        opportunities = []
        client = self.clients.get(platform)

        if not client:
            return []

        markets = self.markets.get(platform, [])

        for market in markets:
            if not market.is_binary:
                continue

            try:
                yes_ob, no_ob = await client.get_both_order_books(market.market_id)

                if not yes_ob or not no_ob:
                    continue

                yes_ask = yes_ob.best_ask
                no_ask = no_ob.best_ask

                if yes_ask is None or no_ask is None:
                    continue

                total_cost = yes_ask + no_ask

                # Check if profitable (cost < 1 - fees - min margin)
                target_cost = 1.0 - self.config.MIN_PROFIT_MARGIN
                fee_adjusted_cost = total_cost * (1 + self.config.TRADING_FEE_PERCENT * 2)

                if fee_adjusted_cost < target_cost:
                    roi = ((1.0 - fee_adjusted_cost) / fee_adjusted_cost) * 100

                    opportunity = ArbitrageOpportunity(
                        opportunity_type="intra_platform",
                        platform=platform,
                        market_id=market.market_id,
                        question=market.question,
                        yes_price=yes_ask,
                        no_price=no_ask,
                        total_cost=total_cost,
                        roi_percent=roi
                    )

                    opportunities.append(opportunity)
                    logger.info(
                        f"[{platform.upper()}] Arbitrage found: "
                        f"YES={yes_ask:.3f} + NO={no_ask:.3f} = {total_cost:.3f} "
                        f"(ROI: {roi:.2f}%)"
                    )

                    if self.on_opportunity:
                        self.on_opportunity(market.market_id, yes_ask, no_ask)

                # PHASE 4: Capture snapshots for backtesting
                if self.data_collector:
                    self.data_collector.capture_snapshot(
                        token_id=f"{market.market_id}:Yes",
                        market_id=market.market_id,
                        order_book={'asks': yes_ob.asks, 'bids': yes_ob.bids},
                        platform=platform
                    )
                    self.data_collector.capture_snapshot(
                        token_id=f"{market.market_id}:No",
                        market_id=market.market_id,
                        order_book={'asks': no_ob.asks, 'bids': no_ob.bids},
                        platform=platform
                    )

            except Exception as e:
                logger.debug(f"Error checking {platform} market {market.market_id}: {e}")

        return opportunities

    async def detect_cross_platform_arbitrage(self) -> List[ArbitrageOpportunity]:
        """
        Detect arbitrage opportunities across platforms.

        Looking for matched markets where buying YES on one platform
        and NO on another is profitable.
        """
        if not self.config.CROSS_PLATFORM_ARBITRAGE:
            return []

        if len(self.clients) < 2:
            return []

        opportunities = []

        for match in self.matched_markets:
            if not match.is_valid:
                continue

            try:
                poly_client = self.clients.get("polymarket")
                kalshi_client = self.clients.get("kalshi")

                if not poly_client or not kalshi_client:
                    continue

                # Get order books from both platforms
                poly_yes = await poly_client.get_order_book(
                    match.polymarket.market_id, "Yes"
                )
                kalshi_no = await kalshi_client.get_order_book(
                    match.kalshi.market_id, "No"
                )

                if not poly_yes or not kalshi_no:
                    continue

                # PHASE 4: Capture snapshots
                if self.data_collector:
                    self.data_collector.capture_snapshot(
                        token_id=f"{match.polymarket.market_id}:Yes",
                        market_id=match.polymarket.market_id,
                        order_book={'asks': poly_yes.asks, 'bids': poly_yes.bids},
                        platform="polymarket"
                    )
                    self.data_collector.capture_snapshot(
                        token_id=f"{match.kalshi.market_id}:No",
                        market_id=match.kalshi.market_id,
                        order_book={'asks': kalshi_no.asks, 'bids': kalshi_no.bids},
                        platform="kalshi"
                    )

                poly_yes_ask = poly_yes.best_ask
                kalshi_no_ask = kalshi_no.best_ask

                if poly_yes_ask is None or kalshi_no_ask is None:
                    continue

                # Calculate cross-platform arbitrage
                # Buy YES on Polymarket + Buy NO on Kalshi
                total_cost = poly_yes_ask + kalshi_no_ask
                fee_adjusted_cost = total_cost * (1 + self.config.TRADING_FEE_PERCENT * 2)

                if fee_adjusted_cost < 0.98:  # At least 2% profit
                    roi = ((1.0 - fee_adjusted_cost) / fee_adjusted_cost) * 100

                    opportunity = ArbitrageOpportunity(
                        opportunity_type="cross_platform",
                        platform="cross",
                        market_id=f"{match.polymarket.market_id}|{match.kalshi.market_id}",
                        question=match.question,
                        yes_price=poly_yes_ask,
                        no_price=kalshi_no_ask,
                        total_cost=total_cost,
                        roi_percent=roi,
                        platform_1="polymarket",
                        market_id_1=match.polymarket.market_id,
                        platform_2="kalshi",
                        market_id_2=match.kalshi.market_id
                    )

                    opportunities.append(opportunity)
                    logger.info(
                        f"[CROSS-PLATFORM] Arbitrage found: "
                        f"Poly YES={poly_yes_ask:.3f} + Kalshi NO={kalshi_no_ask:.3f} = {total_cost:.3f} "
                        f"(ROI: {roi:.2f}%)"
                    )

                # Also check reverse: Kalshi YES + Polymarket NO
                kalshi_yes = await kalshi_client.get_order_book(
                    match.kalshi.market_id, "Yes"
                )
                poly_no = await poly_client.get_order_book(
                    match.polymarket.market_id, "No"
                )

                if kalshi_yes and poly_no:
                    # PHASE 4: Capture snapshots
                    if self.data_collector:
                        self.data_collector.capture_snapshot(
                            token_id=f"{match.kalshi.market_id}:Yes",
                            market_id=match.kalshi.market_id,
                            order_book={'asks': kalshi_yes.asks, 'bids': kalshi_yes.bids},
                            platform="kalshi"
                        )
                        self.data_collector.capture_snapshot(
                            token_id=f"{match.polymarket.market_id}:No",
                            market_id=match.polymarket.market_id,
                            order_book={'asks': poly_no.asks, 'bids': poly_no.bids},
                            platform="polymarket"
                        )
                    kalshi_yes_ask = kalshi_yes.best_ask
                    poly_no_ask = poly_no.best_ask

                    if kalshi_yes_ask and poly_no_ask:
                        total_cost_rev = kalshi_yes_ask + poly_no_ask
                        fee_adjusted_rev = total_cost_rev * (1 + self.config.TRADING_FEE_PERCENT * 2)

                        if fee_adjusted_rev < 0.98:
                            roi_rev = ((1.0 - fee_adjusted_rev) / fee_adjusted_rev) * 100

                            opportunity_rev = ArbitrageOpportunity(
                                opportunity_type="cross_platform",
                                platform="cross",
                                market_id=f"{match.kalshi.market_id}|{match.polymarket.market_id}",
                                question=match.question,
                                yes_price=kalshi_yes_ask,
                                no_price=poly_no_ask,
                                total_cost=total_cost_rev,
                                roi_percent=roi_rev,
                                platform_1="kalshi",
                                market_id_1=match.kalshi.market_id,
                                platform_2="polymarket",
                                market_id_2=match.polymarket.market_id
                            )

                            opportunities.append(opportunity_rev)
                            logger.info(
                                f"[CROSS-PLATFORM] Arbitrage found (reverse): "
                                f"Kalshi YES={kalshi_yes_ask:.3f} + Poly NO={poly_no_ask:.3f} = {total_cost_rev:.3f} "
                                f"(ROI: {roi_rev:.2f}%)"
                            )

            except Exception as e:
                logger.debug(f"Error checking cross-platform match: {e}")

        return opportunities

    async def detect_all_opportunities(self) -> List[ArbitrageOpportunity]:
        """Detect all arbitrage opportunities across all platforms."""
        all_opportunities = []

        # Intra-platform detection
        for platform in self.clients.keys():
            opportunities = await self.detect_intra_platform_arbitrage(platform)
            all_opportunities.extend(opportunities)

        # Cross-platform detection
        if self.config.CROSS_PLATFORM_ARBITRAGE:
            cross_opportunities = await self.detect_cross_platform_arbitrage()
            all_opportunities.extend(cross_opportunities)

        # Sort by ROI descending
        all_opportunities.sort(key=lambda x: x.roi_percent, reverse=True)

        return all_opportunities

    async def execute_intra_platform_trade(
        self,
        opportunity: ArbitrageOpportunity
    ) -> bool:
        """Execute an intra-platform arbitrage trade."""
        if opportunity.opportunity_type != "intra_platform":
            return False

        client = self.clients.get(opportunity.platform)
        if not client:
            return False

        # Calculate position size
        allocation = self.capital_allocator.calculate_allocation(
            roi_percent=opportunity.roi_percent,
            market_score=80.0,  # Default score
            daily_pnl=0.0,
            max_daily_loss=self.config.MAX_DAILY_LOSS or 1000.0
        )

        if not allocation.should_trade:
            logger.info(f"Skipping trade: {allocation.reason}")
            return False

        shares = int(allocation.capital / opportunity.total_cost)
        if shares < 1:
            return False

        try:
            # Place YES order
            yes_result = await client.place_order(
                market_id=opportunity.market_id,
                outcome="Yes",
                side=OrderSide.BUY,
                price=opportunity.yes_price,
                size=shares,
                order_type=OrderType.FOK
            )

            if not yes_result.success:
                logger.error(f"YES order failed: {yes_result.error_message}")
                return False

            # Place NO order
            no_result = await client.place_order(
                market_id=opportunity.market_id,
                outcome="No",
                side=OrderSide.BUY,
                price=opportunity.no_price,
                size=shares,
                order_type=OrderType.FOK
            )

            if not no_result.success:
                logger.error(f"NO order failed: {no_result.error_message}")
                # TODO: Handle partial fill - close YES position
                return False

            # Report trade
            trade_info = {
                "type": "intra_platform",
                "platform": opportunity.platform,
                "market_id": opportunity.market_id,
                "question": opportunity.question[:50],
                "yes_price": opportunity.yes_price,
                "no_price": opportunity.no_price,
                "shares": shares,
                "cost": shares * opportunity.total_cost,
                "expected_profit": shares * (1.0 - opportunity.total_cost),
                "timestamp": time.time()
            }

            if self.on_trade:
                self.on_trade(trade_info)

            # Save to storage
            self.trade_storage.save_trade(trade_info)

            logger.info(
                f"Trade executed: {shares} shares @ {opportunity.total_cost:.3f} "
                f"(Expected profit: ${shares * (1.0 - opportunity.total_cost):.2f})"
            )

            return True

        except Exception as e:
            logger.error(f"Trade execution error: {e}")
            return False

    async def execute_cross_platform_trade(
        self,
        opportunity: ArbitrageOpportunity
    ) -> bool:
        """Execute a cross-platform arbitrage trade."""
        if opportunity.opportunity_type != "cross_platform":
            return False

        client_1 = self.clients.get(opportunity.platform_1)
        client_2 = self.clients.get(opportunity.platform_2)

        if not client_1 or not client_2:
            return False

        # Calculate position size
        allocation = self.capital_allocator.calculate_allocation(
            roi_percent=opportunity.roi_percent,
            market_score=90.0,  # Cross-platform gets higher score
            daily_pnl=0.0,
            max_daily_loss=self.config.MAX_DAILY_LOSS or 1000.0
        )

        if not allocation.should_trade:
            logger.info(f"Skipping cross-platform trade: {allocation.reason}")
            return False

        shares = int(allocation.capital / opportunity.total_cost)
        if shares < 1:
            return False

        try:
            # Execute both legs in parallel
            yes_task = client_1.place_order(
                market_id=opportunity.market_id_1,
                outcome="Yes",
                side=OrderSide.BUY,
                price=opportunity.yes_price,
                size=shares,
                order_type=OrderType.FOK
            )

            no_task = client_2.place_order(
                market_id=opportunity.market_id_2,
                outcome="No",
                side=OrderSide.BUY,
                price=opportunity.no_price,
                size=shares,
                order_type=OrderType.FOK
            )

            yes_result, no_result = await asyncio.gather(yes_task, no_task)

            if not yes_result.success or not no_result.success:
                logger.error(
                    f"Cross-platform trade failed: "
                    f"YES={yes_result.success}, NO={no_result.success}"
                )
                # TODO: Handle partial execution
                return False

            # Report trade
            trade_info = {
                "type": "cross_platform",
                "platform_1": opportunity.platform_1,
                "platform_2": opportunity.platform_2,
                "market_id_1": opportunity.market_id_1,
                "market_id_2": opportunity.market_id_2,
                "question": opportunity.question[:50],
                "yes_price": opportunity.yes_price,
                "no_price": opportunity.no_price,
                "shares": shares,
                "cost": shares * opportunity.total_cost,
                "expected_profit": shares * (1.0 - opportunity.total_cost),
                "timestamp": time.time()
            }

            if self.on_trade:
                self.on_trade(trade_info)

            # Save to storage
            self.trade_storage.save_trade(trade_info)

            logger.info(
                f"Cross-platform trade executed: {shares} shares "
                f"(Expected profit: ${shares * (1.0 - opportunity.total_cost):.2f})"
            )

            return True

        except Exception as e:
            logger.error(f"Cross-platform trade error: {e}")
            return False

    async def run(self):
        """Main run loop for multi-platform arbitrage detection."""
        self.running = True
        logger.info("Starting Multi-Platform Arbitrage Bot...")

        # Initialize clients
        if not await self.initialize_clients():
            logger.error("Failed to initialize clients, stopping.")
            return

        # Initial market fetch
        await self.fetch_all_markets()

        # Start data collector
        if self.data_collector:
            await self.data_collector.start()
            logger.info("Data Collector started")

        while self.running:
            try:
                # Refresh markets periodically
                if time.time() - self._last_markets_fetch > self._markets_fetch_interval:
                    await self.fetch_all_markets()

                # Detect opportunities
                opportunities = await self.detect_all_opportunities()

                if opportunities:
                    logger.info(f"Found {len(opportunities)} arbitrage opportunities")

                    # Execute best opportunity (if risk allows)
                    best = opportunities[0]
                    if best.roi_percent >= self.config.MIN_PROFIT_MARGIN * 100:
                        if best.opportunity_type == "intra_platform":
                            await self.execute_intra_platform_trade(best)
                        else:
                            await self.execute_cross_platform_trade(best)

                # Rate limiting
                await asyncio.sleep(1.0)

            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(5.0)

        logger.info("Multi-Platform Arbitrage Bot stopped.")

    def stop(self):
        """Stop the bot."""
        self.running = False
        logger.info("Stopping Multi-Platform Arbitrage Bot...")

    async def cleanup(self):
        """Cleanup resources."""
        for platform, client in self.clients.items():
            try:
                await client.disconnect()
                logger.info(f"Disconnected from {platform}")
            except Exception as e:
                logger.error(f"Error disconnecting from {platform}: {e}")

        if self.data_collector:
            await self.data_collector.stop()
            logger.info("Data Collector stopped")

    def get_status(self) -> dict:
        """Get current bot status."""
        return {
            "running": self.running,
            "platforms": list(self.clients.keys()),
            "markets_count": {p: len(m) for p, m in self.markets.items()},
            "matched_markets": len(self.matched_markets),
            "cross_platform_enabled": self.config.CROSS_PLATFORM_ARBITRAGE
        }
