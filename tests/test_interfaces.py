"""Tests for Exchange Client and Credentials Interfaces."""

import pytest
from backend.interfaces.exchange_client import (
    IExchangeClient, UnifiedMarket, UnifiedOrderBook, OrderResult,
    Position, OrderSide, OrderType, OrderStatus
)
from backend.interfaces.credentials import (
    IPlatformCredentials, PolymarketCredentials, KalshiCredentials,
    CredentialsManager
)


class TestUnifiedMarket:
    """Tests for UnifiedMarket dataclass."""

    def test_create_binary_market(self):
        market = UnifiedMarket(
            platform="polymarket",
            market_id="0x123",
            question="Will it rain tomorrow?",
            outcomes=["Yes", "No"],
            volume=10000.0,
            tokens={"Yes": "token_yes", "No": "token_no"}
        )
        assert market.platform == "polymarket"
        assert market.is_binary is True
        assert market.get_token_id("Yes") == "token_yes"

    def test_non_binary_market(self):
        market = UnifiedMarket(
            platform="kalshi",
            market_id="TEMP-23",
            question="What will the temperature be?",
            outcomes=["Under 70", "70-80", "Over 80"],
            volume=5000.0
        )
        assert market.is_binary is False

    def test_market_with_no_tokens(self):
        market = UnifiedMarket(
            platform="kalshi",
            market_id="TEST",
            question="Test market",
            outcomes=["Yes", "No"],
            volume=1000.0
        )
        assert market.get_token_id("Yes") is None
        assert market.tokens == {}


class TestUnifiedOrderBook:
    """Tests for UnifiedOrderBook dataclass."""

    def test_order_book_properties(self):
        ob = UnifiedOrderBook(
            platform="polymarket",
            market_id="0x123",
            outcome="Yes",
            bids=[(0.45, 100), (0.44, 200)],
            asks=[(0.47, 150), (0.48, 250)]
        )
        assert ob.best_bid == 0.45
        assert ob.best_ask == 0.47
        assert abs(ob.spread - 0.02) < 0.001  # Float comparison
        assert abs(ob.mid_price - 0.46) < 0.001

    def test_empty_order_book(self):
        ob = UnifiedOrderBook(
            platform="polymarket",
            market_id="0x123",
            outcome="Yes",
            bids=[],
            asks=[]
        )
        assert ob.best_bid is None
        assert ob.best_ask is None
        assert ob.spread is None
        assert ob.mid_price is None

    def test_total_liquidity(self):
        ob = UnifiedOrderBook(
            platform="polymarket",
            market_id="0x123",
            outcome="Yes",
            bids=[(0.45, 100), (0.44, 200), (0.43, 300)],
            asks=[(0.47, 150), (0.48, 250)]
        )
        assert ob.get_total_liquidity("bid", depth=2) == 300
        assert ob.get_total_liquidity("ask", depth=10) == 400

    def test_calculate_effective_price(self):
        ob = UnifiedOrderBook(
            platform="polymarket",
            market_id="0x123",
            outcome="Yes",
            bids=[(0.45, 100), (0.44, 200)],
            asks=[(0.47, 100), (0.48, 200)]
        )
        # Buy 50 shares at first level only
        result = ob.calculate_effective_price("buy", 50)
        assert result is not None
        assert result[0] == 0.47  # All from first level
        assert result[1] == 1

        # Buy 150 shares across two levels
        result = ob.calculate_effective_price("buy", 150)
        assert result is not None
        expected_price = (100 * 0.47 + 50 * 0.48) / 150
        assert abs(result[0] - expected_price) < 0.001
        assert result[1] == 2

    def test_calculate_effective_price_insufficient_liquidity(self):
        ob = UnifiedOrderBook(
            platform="polymarket",
            market_id="0x123",
            outcome="Yes",
            bids=[(0.45, 100)],
            asks=[(0.47, 100)]
        )
        result = ob.calculate_effective_price("buy", 500)
        assert result is None


class TestOrderResult:
    """Tests for OrderResult dataclass."""

    def test_successful_order(self):
        result = OrderResult(
            success=True,
            order_id="order_123",
            filled_size=100,
            filled_price=0.47,
            status=OrderStatus.FILLED,
            platform="polymarket"
        )
        assert result.success is True
        assert result.status == OrderStatus.FILLED

    def test_failed_order(self):
        result = OrderResult(
            success=False,
            status=OrderStatus.REJECTED,
            error_message="Insufficient balance",
            platform="polymarket"
        )
        assert result.success is False
        assert result.error_message == "Insufficient balance"


class TestPosition:
    """Tests for Position dataclass."""

    def test_position_market_value(self):
        pos = Position(
            platform="polymarket",
            market_id="0x123",
            outcome="Yes",
            size=100,
            entry_price=0.45,
            current_price=0.55
        )
        assert abs(pos.market_value - 55.0) < 0.001  # Float comparison

    def test_position_market_value_no_current_price(self):
        pos = Position(
            platform="polymarket",
            market_id="0x123",
            outcome="Yes",
            size=100,
            entry_price=0.45
        )
        assert pos.market_value == 45.0


class TestPolymarketCredentials:
    """Tests for PolymarketCredentials."""

    def test_valid_credentials(self):
        creds = PolymarketCredentials(
            api_key="test_key",
            api_secret="test_secret",
            passphrase="test_pass",
            private_key="0x" + "a" * 64
        )
        assert creds.platform_name == "polymarket"
        is_valid, error = creds.validate()
        assert is_valid is True
        assert error == ""

    def test_missing_api_key(self):
        creds = PolymarketCredentials(
            api_key="",
            api_secret="test_secret",
            passphrase="test_pass",
            private_key="0x" + "a" * 64
        )
        is_valid, error = creds.validate()
        assert is_valid is False
        assert "API Key" in error

    def test_invalid_private_key_length(self):
        creds = PolymarketCredentials(
            api_key="test_key",
            api_secret="test_secret",
            passphrase="test_pass",
            private_key="0x" + "a" * 32  # Too short
        )
        is_valid, error = creds.validate()
        assert is_valid is False
        assert "length" in error.lower()

    def test_invalid_private_key_chars(self):
        creds = PolymarketCredentials(
            api_key="test_key",
            api_secret="test_secret",
            passphrase="test_pass",
            private_key="0xgg" + "a" * 62  # Invalid hex
        )
        is_valid, error = creds.validate()
        assert is_valid is False
        assert "hexadecimal" in error.lower()

    def test_to_client_kwargs(self):
        creds = PolymarketCredentials(
            api_key="test_key",
            api_secret="test_secret",
            passphrase="test_pass",
            private_key="0x" + "a" * 64
        )
        kwargs = creds.to_client_kwargs()
        assert kwargs["key"] == "test_key"
        assert kwargs["private_key"] == "a" * 64  # Without 0x prefix

    def test_to_env_dict(self):
        creds = PolymarketCredentials(
            api_key="test_key",
            api_secret="test_secret",
            passphrase="test_pass",
            private_key="0x" + "a" * 64
        )
        env = creds.to_env_dict()
        assert env["POLY_API_KEY"] == "test_key"
        assert env["PRIVATE_KEY"] == "0x" + "a" * 64

    def test_from_env(self):
        env = {
            "POLY_API_KEY": "key123",
            "POLY_API_SECRET": "secret123",
            "POLY_API_PASSPHRASE": "pass123",
            "PRIVATE_KEY": "0x" + "b" * 64
        }
        creds = PolymarketCredentials.from_env(env)
        assert creds.api_key == "key123"
        assert creds.private_key == "0x" + "b" * 64

    def test_is_complete(self):
        complete = PolymarketCredentials(
            api_key="key",
            api_secret="secret",
            passphrase="pass",
            private_key="0x" + "a" * 64
        )
        assert complete.is_complete() is True

        incomplete = PolymarketCredentials(api_key="key")
        assert incomplete.is_complete() is False


class TestKalshiCredentials:
    """Tests for KalshiCredentials."""

    def test_valid_credentials(self):
        creds = KalshiCredentials(
            email="test@example.com",
            password="password123"
        )
        assert creds.platform_name == "kalshi"
        is_valid, error = creds.validate()
        assert is_valid is True
        assert error == ""

    def test_missing_email(self):
        creds = KalshiCredentials(
            email="",
            password="password123"
        )
        is_valid, error = creds.validate()
        assert is_valid is False
        assert "email" in error.lower()

    def test_invalid_email_format(self):
        creds = KalshiCredentials(
            email="not_an_email",
            password="password123"
        )
        is_valid, error = creds.validate()
        assert is_valid is False
        assert "email format" in error.lower()

    def test_password_too_short(self):
        creds = KalshiCredentials(
            email="test@example.com",
            password="12345"
        )
        is_valid, error = creds.validate()
        assert is_valid is False
        assert "6 characters" in error.lower()

    def test_with_api_key(self):
        creds = KalshiCredentials(
            email="test@example.com",
            password="password123",
            api_key="api_key_123"
        )
        kwargs = creds.to_client_kwargs()
        assert kwargs["api_key"] == "api_key_123"

    def test_from_env(self):
        env = {
            "KALSHI_EMAIL": "test@example.com",
            "KALSHI_PASSWORD": "password123",
            "KALSHI_API_KEY": "api_123"
        }
        creds = KalshiCredentials.from_env(env)
        assert creds.email == "test@example.com"
        assert creds.api_key == "api_123"

    def test_from_env_no_api_key(self):
        env = {
            "KALSHI_EMAIL": "test@example.com",
            "KALSHI_PASSWORD": "password123",
            "KALSHI_API_KEY": ""
        }
        creds = KalshiCredentials.from_env(env)
        assert creds.api_key is None

    def test_is_complete(self):
        complete = KalshiCredentials(
            email="test@example.com",
            password="password123"
        )
        assert complete.is_complete() is True

        incomplete = KalshiCredentials(email="test@example.com")
        assert incomplete.is_complete() is False


class TestCredentialsManager:
    """Tests for CredentialsManager."""

    def test_set_and_get_credentials(self):
        manager = CredentialsManager()
        poly_creds = PolymarketCredentials(
            api_key="key",
            api_secret="secret",
            passphrase="pass",
            private_key="0x" + "a" * 64
        )
        manager.set_credentials(poly_creds)

        retrieved = manager.get_credentials("polymarket")
        assert retrieved is not None
        assert retrieved.platform_name == "polymarket"

    def test_get_nonexistent_credentials(self):
        manager = CredentialsManager()
        assert manager.get_credentials("nonexistent") is None

    def test_validate_all(self):
        manager = CredentialsManager()
        poly_creds = PolymarketCredentials(
            api_key="key",
            api_secret="secret",
            passphrase="pass",
            private_key="0x" + "a" * 64
        )
        kalshi_creds = KalshiCredentials(
            email="test@example.com",
            password="password123"
        )
        manager.set_credentials(poly_creds)
        manager.set_credentials(kalshi_creds)

        results = manager.validate_all()
        assert results["polymarket"][0] is True
        assert results["kalshi"][0] is True

    def test_get_enabled_platforms(self):
        manager = CredentialsManager()
        poly_creds = PolymarketCredentials(
            api_key="key",
            api_secret="secret",
            passphrase="pass",
            private_key="0x" + "a" * 64
        )
        kalshi_creds = KalshiCredentials(
            email="test@example.com",
            password=""  # Incomplete
        )
        manager.set_credentials(poly_creds)
        manager.set_credentials(kalshi_creds)

        enabled = manager.get_enabled_platforms()
        assert "polymarket" in enabled
        assert "kalshi" not in enabled

    def test_to_env_dict(self):
        manager = CredentialsManager()
        poly_creds = PolymarketCredentials(
            api_key="poly_key",
            api_secret="poly_secret",
            passphrase="poly_pass",
            private_key="0x" + "a" * 64
        )
        kalshi_creds = KalshiCredentials(
            email="test@example.com",
            password="password123"
        )
        manager.set_credentials(poly_creds)
        manager.set_credentials(kalshi_creds)

        env = manager.to_env_dict()
        assert env["POLY_API_KEY"] == "poly_key"
        assert env["KALSHI_EMAIL"] == "test@example.com"
        assert "ENABLED_PLATFORMS" in env

    def test_from_env(self):
        env = {
            "POLY_API_KEY": "key",
            "POLY_API_SECRET": "secret",
            "POLY_API_PASSPHRASE": "pass",
            "PRIVATE_KEY": "0x" + "a" * 64,
            "KALSHI_EMAIL": "test@example.com",
            "KALSHI_PASSWORD": "password123"
        }
        manager = CredentialsManager.from_env(env)

        assert manager.get_credentials("polymarket") is not None
        assert manager.get_credentials("kalshi") is not None
