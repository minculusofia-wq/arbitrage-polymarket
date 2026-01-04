"""Tests for Multi-Platform Arbitrage Bot."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from backend.multi_platform_arbitrage import (
    MultiPlatformArbitrageBot,
    ArbitrageOpportunity,
    MarketMatch
)
from backend.interfaces.exchange_client import (
    IExchangeClient, UnifiedMarket, UnifiedOrderBook, OrderSide, OrderType
)


class TestArbitrageOpportunity:
    """Tests for ArbitrageOpportunity dataclass."""

    def test_profitable_opportunity(self):
        opp = ArbitrageOpportunity(
            opportunity_type="intra_platform",
            platform="polymarket",
            market_id="0x123",
            question="Test question?",
            yes_price=0.45,
            no_price=0.50,
            total_cost=0.95,
            roi_percent=5.26
        )
        assert opp.is_profitable is True

    def test_unprofitable_opportunity(self):
        opp = ArbitrageOpportunity(
            opportunity_type="intra_platform",
            platform="polymarket",
            market_id="0x123",
            question="Test question?",
            yes_price=0.55,
            no_price=0.50,
            total_cost=1.05,
            roi_percent=-4.76
        )
        assert opp.is_profitable is False

    def test_cross_platform_opportunity(self):
        opp = ArbitrageOpportunity(
            opportunity_type="cross_platform",
            platform="cross",
            market_id="matched_123",
            question="Test question?",
            yes_price=0.45,
            no_price=0.48,
            total_cost=0.93,
            roi_percent=7.5,
            platform_1="polymarket",
            market_id_1="0x123",
            platform_2="kalshi",
            market_id_2="TEST-24"
        )
        assert opp.platform_1 == "polymarket"
        assert opp.platform_2 == "kalshi"
        assert opp.is_profitable is True


class TestMarketMatch:
    """Tests for MarketMatch dataclass."""

    def test_valid_match(self):
        poly_market = UnifiedMarket(
            platform="polymarket",
            market_id="0x123",
            question="Will event happen?",
            outcomes=["Yes", "No"],
            volume=10000
        )
        kalshi_market = UnifiedMarket(
            platform="kalshi",
            market_id="EVENT-24",
            question="Will event happen?",
            outcomes=["Yes", "No"],
            volume=5000
        )

        match = MarketMatch(
            question="Will event happen?",
            similarity=0.95,
            polymarket=poly_market,
            kalshi=kalshi_market
        )

        assert match.is_valid is True
        assert match.similarity == 0.95

    def test_invalid_match_missing_platform(self):
        poly_market = UnifiedMarket(
            platform="polymarket",
            market_id="0x123",
            question="Will event happen?",
            outcomes=["Yes", "No"],
            volume=10000
        )

        match = MarketMatch(
            question="Will event happen?",
            similarity=0.0,
            polymarket=poly_market,
            kalshi=None
        )

        assert match.is_valid is False


class MockConfig:
    """Mock configuration for tests."""
    ENABLED_PLATFORMS = ["polymarket", "kalshi"]
    CROSS_PLATFORM_ARBITRAGE = True
    MIN_MARKET_VOLUME = 1000
    MIN_PROFIT_MARGIN = 0.02
    TRADING_FEE_PERCENT = 0.001
    CAPITAL_PER_TRADE = 100.0
    POLY_API_KEY = "test_key"
    POLY_API_SECRET = "test_secret"
    POLY_API_PASSPHRASE = "test_pass"
    PRIVATE_KEY = "0x" + "a" * 64
    KALSHI_EMAIL = "test@example.com"
    KALSHI_PASSWORD = "password123"
    KALSHI_API_KEY = None
    STOP_LOSS = None
    TAKE_PROFIT = None
    MAX_DAILY_LOSS = None


class TestMultiPlatformArbitrageBot:
    """Tests for MultiPlatformArbitrageBot."""

    @pytest.fixture
    def mock_config(self):
        return MockConfig()

    @pytest.fixture
    def bot(self, mock_config):
        with patch('backend.multi_platform_arbitrage.RiskManager'):
            with patch('backend.multi_platform_arbitrage.CapitalAllocator'):
                return MultiPlatformArbitrageBot(mock_config)

    def test_initialization(self, bot):
        assert bot.clients == {}
        assert bot.markets == {}
        assert bot.running is False

    def test_callbacks_initialization(self, bot):
        assert bot.on_opportunity is None
        assert bot.on_trade is None

    def test_set_callbacks(self, bot):
        callback = MagicMock()
        bot.on_opportunity = callback
        assert bot.on_opportunity is callback


class TestMultiPlatformArbitrageBotMarketMatching:
    """Tests for market matching functionality."""

    @pytest.fixture
    def mock_config(self):
        return MockConfig()

    @pytest.fixture
    def bot(self, mock_config):
        with patch('backend.multi_platform_arbitrage.RiskManager'):
            with patch('backend.multi_platform_arbitrage.CapitalAllocator'):
                return MultiPlatformArbitrageBot(mock_config)

    def test_match_identical_questions(self, bot):
        """Test matching markets with identical questions."""
        poly_markets = [
            UnifiedMarket(
                platform="polymarket",
                market_id="0x123",
                question="Will Bitcoin reach $100k in 2025?",
                outcomes=["Yes", "No"],
                volume=50000
            )
        ]
        kalshi_markets = [
            UnifiedMarket(
                platform="kalshi",
                market_id="BTC-100K-25",
                question="Will Bitcoin reach $100k in 2025?",
                outcomes=["Yes", "No"],
                volume=30000
            )
        ]

        bot.markets = {
            "polymarket": poly_markets,
            "kalshi": kalshi_markets
        }

        matches = bot._match_markets_across_platforms()

        assert len(matches) == 1
        assert matches[0].similarity == 1.0
        assert matches[0].polymarket.market_id == "0x123"
        assert matches[0].kalshi.market_id == "BTC-100K-25"

    def test_match_similar_questions(self, bot):
        """Test matching markets with similar but not identical questions."""
        poly_markets = [
            UnifiedMarket(
                platform="polymarket",
                market_id="0x123",
                question="Will Democrats win the 2024 presidential election?",
                outcomes=["Yes", "No"],
                volume=50000
            )
        ]
        kalshi_markets = [
            UnifiedMarket(
                platform="kalshi",
                market_id="PRES-24-DEM",
                question="Will Democrats win the 2024 US presidential election?",
                outcomes=["Yes", "No"],
                volume=30000
            )
        ]

        bot.markets = {
            "polymarket": poly_markets,
            "kalshi": kalshi_markets
        }

        matches = bot._match_markets_across_platforms()

        assert len(matches) == 1
        assert matches[0].similarity >= 0.80

    def test_no_match_different_questions(self, bot):
        """Test that very different questions don't match."""
        poly_markets = [
            UnifiedMarket(
                platform="polymarket",
                market_id="0x123",
                question="Will it rain tomorrow in NYC?",
                outcomes=["Yes", "No"],
                volume=5000
            )
        ]
        kalshi_markets = [
            UnifiedMarket(
                platform="kalshi",
                market_id="FED-RATE-25",
                question="Will the Fed raise rates in January 2025?",
                outcomes=["Yes", "No"],
                volume=30000
            )
        ]

        bot.markets = {
            "polymarket": poly_markets,
            "kalshi": kalshi_markets
        }

        matches = bot._match_markets_across_platforms()

        assert len(matches) == 0

    def test_no_match_empty_markets(self, bot):
        """Test matching with no markets."""
        bot.markets = {
            "polymarket": [],
            "kalshi": []
        }

        matches = bot._match_markets_across_platforms()

        assert len(matches) == 0


class TestMultiPlatformArbitrageBotOpportunityDetection:
    """Tests for arbitrage opportunity detection."""

    @pytest.fixture
    def mock_config(self):
        return MockConfig()

    @pytest.fixture
    def bot_with_client(self, mock_config):
        with patch('backend.multi_platform_arbitrage.RiskManager'):
            with patch('backend.multi_platform_arbitrage.CapitalAllocator'):
                bot = MultiPlatformArbitrageBot(mock_config)

                # Create mock client
                mock_client = AsyncMock(spec=IExchangeClient)
                mock_client.platform_name = "polymarket"
                mock_client.is_connected = True

                bot.clients["polymarket"] = mock_client
                return bot

    @pytest.mark.asyncio
    async def test_detect_intra_platform_arbitrage_profitable(self, bot_with_client):
        """Test detection of profitable arbitrage."""
        market = UnifiedMarket(
            platform="polymarket",
            market_id="0x123",
            question="Test market?",
            outcomes=["Yes", "No"],
            volume=10000
        )
        bot_with_client.markets["polymarket"] = [market]

        # Mock order books with profitable prices
        yes_ob = UnifiedOrderBook(
            platform="polymarket",
            market_id="0x123",
            outcome="Yes",
            bids=[(0.44, 100)],
            asks=[(0.45, 100)]
        )
        no_ob = UnifiedOrderBook(
            platform="polymarket",
            market_id="0x123",
            outcome="No",
            bids=[(0.49, 100)],
            asks=[(0.50, 100)]
        )

        bot_with_client.clients["polymarket"].get_both_order_books = AsyncMock(
            return_value=(yes_ob, no_ob)
        )

        opportunities = await bot_with_client.detect_intra_platform_arbitrage("polymarket")

        assert len(opportunities) == 1
        assert opportunities[0].yes_price == 0.45
        assert opportunities[0].no_price == 0.50
        assert opportunities[0].total_cost == 0.95
        assert opportunities[0].is_profitable is True

    @pytest.mark.asyncio
    async def test_detect_intra_platform_arbitrage_unprofitable(self, bot_with_client):
        """Test that unprofitable markets are not detected."""
        market = UnifiedMarket(
            platform="polymarket",
            market_id="0x123",
            question="Test market?",
            outcomes=["Yes", "No"],
            volume=10000
        )
        bot_with_client.markets["polymarket"] = [market]

        # Mock order books with unprofitable prices
        yes_ob = UnifiedOrderBook(
            platform="polymarket",
            market_id="0x123",
            outcome="Yes",
            bids=[(0.54, 100)],
            asks=[(0.55, 100)]
        )
        no_ob = UnifiedOrderBook(
            platform="polymarket",
            market_id="0x123",
            outcome="No",
            bids=[(0.49, 100)],
            asks=[(0.50, 100)]
        )

        bot_with_client.clients["polymarket"].get_both_order_books = AsyncMock(
            return_value=(yes_ob, no_ob)
        )

        opportunities = await bot_with_client.detect_intra_platform_arbitrage("polymarket")

        assert len(opportunities) == 0

    @pytest.mark.asyncio
    async def test_detect_intra_platform_no_client(self, bot_with_client):
        """Test detection with no client for platform."""
        opportunities = await bot_with_client.detect_intra_platform_arbitrage("nonexistent")
        assert len(opportunities) == 0

    @pytest.mark.asyncio
    async def test_detect_intra_platform_no_markets(self, bot_with_client):
        """Test detection with no markets."""
        bot_with_client.markets["polymarket"] = []
        opportunities = await bot_with_client.detect_intra_platform_arbitrage("polymarket")
        assert len(opportunities) == 0

    @pytest.mark.asyncio
    async def test_opportunity_callback_triggered(self, bot_with_client):
        """Test that on_opportunity callback is triggered."""
        market = UnifiedMarket(
            platform="polymarket",
            market_id="0x123",
            question="Test market?",
            outcomes=["Yes", "No"],
            volume=10000
        )
        bot_with_client.markets["polymarket"] = [market]

        yes_ob = UnifiedOrderBook(
            platform="polymarket",
            market_id="0x123",
            outcome="Yes",
            bids=[(0.44, 100)],
            asks=[(0.45, 100)]
        )
        no_ob = UnifiedOrderBook(
            platform="polymarket",
            market_id="0x123",
            outcome="No",
            bids=[(0.49, 100)],
            asks=[(0.50, 100)]
        )

        bot_with_client.clients["polymarket"].get_both_order_books = AsyncMock(
            return_value=(yes_ob, no_ob)
        )

        callback = MagicMock()
        bot_with_client.on_opportunity = callback

        await bot_with_client.detect_intra_platform_arbitrage("polymarket")

        callback.assert_called_once_with("0x123", 0.45, 0.50)


class TestMultiPlatformArbitrageBotFetchMarkets:
    """Tests for market fetching functionality."""

    @pytest.fixture
    def mock_config(self):
        return MockConfig()

    @pytest.fixture
    def bot_with_clients(self, mock_config):
        with patch('backend.multi_platform_arbitrage.RiskManager'):
            with patch('backend.multi_platform_arbitrage.CapitalAllocator'):
                bot = MultiPlatformArbitrageBot(mock_config)

                # Create mock clients
                poly_client = AsyncMock(spec=IExchangeClient)
                poly_client.platform_name = "polymarket"

                kalshi_client = AsyncMock(spec=IExchangeClient)
                kalshi_client.platform_name = "kalshi"

                bot.clients = {
                    "polymarket": poly_client,
                    "kalshi": kalshi_client
                }
                return bot

    @pytest.mark.asyncio
    async def test_fetch_all_markets(self, bot_with_clients):
        """Test fetching markets from all platforms."""
        poly_markets = [
            UnifiedMarket(
                platform="polymarket",
                market_id="0x123",
                question="Test market?",
                outcomes=["Yes", "No"],
                volume=10000
            )
        ]
        kalshi_markets = [
            UnifiedMarket(
                platform="kalshi",
                market_id="TEST-24",
                question="Test market?",
                outcomes=["Yes", "No"],
                volume=5000
            )
        ]

        bot_with_clients.clients["polymarket"].fetch_markets = AsyncMock(
            return_value=poly_markets
        )
        bot_with_clients.clients["kalshi"].fetch_markets = AsyncMock(
            return_value=kalshi_markets
        )

        result = await bot_with_clients.fetch_all_markets()

        assert "polymarket" in result
        assert "kalshi" in result
        assert len(result["polymarket"]) == 1
        assert len(result["kalshi"]) == 1

    @pytest.mark.asyncio
    async def test_fetch_markets_triggers_matching(self, bot_with_clients):
        """Test that market matching is triggered after fetching."""
        bot_with_clients.clients["polymarket"].fetch_markets = AsyncMock(return_value=[])
        bot_with_clients.clients["kalshi"].fetch_markets = AsyncMock(return_value=[])

        with patch.object(bot_with_clients, '_match_markets_across_platforms') as mock_match:
            await bot_with_clients.fetch_all_markets()
            mock_match.assert_called_once()
