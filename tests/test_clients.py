"""Tests for Exchange Clients (Polymarket, Kalshi)."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from backend.clients.kalshi_client import KalshiClient
from backend.interfaces.credentials import KalshiCredentials, PolymarketCredentials
from backend.interfaces.exchange_client import (
    UnifiedMarket, UnifiedOrderBook, OrderSide, OrderType, OrderStatus
)


# Sample RSA private key for testing (DO NOT USE IN PRODUCTION)
TEST_RSA_PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEArIygrikSF2rjREcDowOs6H4+yZhHwK9penm+a3jSgFZpBXtJ
p/8RVNqMlfwWtitFE5Vsj5c/4dNVjBBcuLf81FrsjCEiipRfbWZj9+Okwq+M9Aam
skDdP1qdEUaZA3vc5d2yZx4PpMx9fqf4xWlhtd2Ju1UAazqERDt7TQo646Chm1Bl
OaLpdcdt+Rt/tE3Wz9BR7FTs5eWRnRktvkrlaV23Y2VW+2PwQU62apJ9BDufRMhg
FS9cwNhX1e0Vs5lrmbsRYpZ+MkKcTQk9dJq51JDiGUJ239v6eDqPdK8cOFo+dV5z
wrhMvPQummwbCR710YTRj592twM1UEQ6jw0WVwIDAQABAoIBADlN1ssgPq7iQ6nY
P7/yp4jq7GU9Go9GcixHpFLC5H3UtLoqULLnRdU9Y7Un7E8BncY8OLqTS5bu/Zkv
keuSxverXqXHF1aYofyOJaMcygoSDSi50MCgRBoXONSU8poyl5ELiIUweZeMhhz7
IeZF8jpY4bYCK8pwu56BdpiGTjpsAR7G88c3mj9q1x9Z+hzQtIXtXCOGYqYQDnme
BplF4obL/7A6NE0G71numMLon//yklXN1QWvj/VIZPdyDvmt9qZmPdJQHQTo9NaR
CZkkihsAxzA3RXEHROLMsAKliM82jipivNKpm6oM368o4j0/cTc7//mXmzw/oG+S
/ByG3jkCgYEA54U2Mx57zzKNSsCciY54T0XaMdXUhthrFa/8gMM+9sMpoVYllYhV
/Hq+OK2Imfpx5IOaFLXvMxM8jhOgDb6xCXt7jLigzJ2LO+PI3Pq7FUE1g9Glhwb6
BNSkuNzlb4Y1IzHo+NUoh8rCb6WrofBq3c3tp7L/O8n+zWLO4L1knE0CgYEAvssw
dGUMhtlkPTxpWWjnNyxoZ3kMmYSVfr29k85zf7/BkMkc7xVSALQiS+uflTzUEKLn
Sgxzdgn1q6BqDgRmJocPg89+OR08+O9E6kEJuXJgq7KDMaPr+FHnOMc3sOXbsgSO
jeg6dKag/nt0lHQQDjJRgaiAan47hsPi8/E3PzMCgYBQ+OUo4ct5fvutnknhTkPD
rfGPJnMrKjvhnOhZ/G9kDIPd2mxQrRstr5wh5Id3GwGEY4abIbpkCaFPK4v54qy2
XUqrv9L1XVBaBOO2bbbKy0C1NriGzijZUam+wfs4kx64jXcmuB5xx7dTJwUtIRGv
O5uX4GGl/pKwMJOcRIEQrQKBgQCHb8Fzvo+H4iXv+kRmfbs0RUfPu/QfvihJEfPT
SohetQZ4+uqZJS9S5Iw8DIT58XYwYROCUxhbQHKuZG8kiCbjTpjK3q4haQnxRBhN
meGHTRQmjc/nmw9U9P8IJRL5dhHgaq+vOJzWVbqPK5/0CfejvEBzo+OUtQsYfVFM
DX1EVQKBgEWilB3f7AwI/i96sMQC/MNufRCuGKsxNfBK5iPFUo6H+E8apjHvdpQ7
Wp7mz1ACSAyZAybqjzXk28uW4ELZYW0N823R+a4nK02tDoJHrJOTcOeGx+92rgDO
XVB9s/g/X4t5/hD9JQALylqGDKpHg0s/GhUxJ3NNG9WKAZFVozon
-----END RSA PRIVATE KEY-----"""


class TestKalshiClient:
    """Tests for KalshiClient."""

    @pytest.fixture
    def credentials(self):
        """Create test credentials with RSA key."""
        return KalshiCredentials(
            api_key_id="test_api_key_id",
            private_key_pem=TEST_RSA_PRIVATE_KEY
        )

    @pytest.fixture
    def client(self, credentials):
        """Create client with test credentials."""
        return KalshiClient(credentials, use_demo=True)

    def test_client_initialization(self, client):
        assert client.platform_name == "kalshi"
        assert client.is_connected is False
        assert "demo" in client.base_url

    def test_production_url(self, credentials):
        client = KalshiClient(credentials, use_demo=False)
        assert "demo" not in client.base_url
        assert "api.elections.kalshi.com" in client.base_url

    @pytest.mark.asyncio
    async def test_connect_invalid_credentials(self):
        """Test connection with invalid credentials."""
        creds = KalshiCredentials(api_key_id="", private_key_pem="")
        client = KalshiClient(creds, use_demo=True)
        result = await client.connect()
        assert result is False
        assert client.is_connected is False

    @pytest.mark.asyncio
    async def test_connect_mock_success(self, client):
        """Test successful connection with mocked response."""
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend

        # Load the private key
        private_key = serialization.load_pem_private_key(
            TEST_RSA_PRIVATE_KEY.encode(),
            password=None,
            backend=default_backend()
        )

        # Simulate successful auth by setting internal state
        client._private_key = private_key
        client._api_key_id = "test_api_key_id"
        client._session = AsyncMock()
        client._connected = True

        assert client.is_connected is True

    @pytest.mark.asyncio
    async def test_disconnect(self, client):
        """Test disconnection."""
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend

        private_key = serialization.load_pem_private_key(
            TEST_RSA_PRIVATE_KEY.encode(),
            password=None,
            backend=default_backend()
        )

        client._connected = True
        client._private_key = private_key
        client._api_key_id = "test_key"
        client._session = AsyncMock()
        client._session.close = AsyncMock()

        await client.disconnect()

        assert client.is_connected is False
        assert client._private_key is None

    def test_get_headers_with_key(self, client):
        """Test header generation with RSA key."""
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend

        private_key = serialization.load_pem_private_key(
            TEST_RSA_PRIVATE_KEY.encode(),
            password=None,
            backend=default_backend()
        )

        client._private_key = private_key
        client._api_key_id = "test_api_key"
        headers = client._get_headers("GET", "/trade-api/v2/markets")

        assert headers["Content-Type"] == "application/json"
        assert "KALSHI-ACCESS-KEY" in headers
        assert "KALSHI-ACCESS-SIGNATURE" in headers
        assert "KALSHI-ACCESS-TIMESTAMP" in headers

    def test_get_headers_without_key(self, client):
        """Test header generation without key."""
        headers = client._get_headers()
        assert "KALSHI-ACCESS-KEY" not in headers

    @pytest.mark.asyncio
    async def test_fetch_markets_not_connected(self, client):
        """Test fetching markets when not connected."""
        markets = await client.fetch_markets()
        assert markets == []

    @pytest.mark.asyncio
    async def test_get_order_book_not_connected(self, client):
        """Test getting order book when not connected."""
        with pytest.raises(RuntimeError, match="not connected"):
            await client.get_order_book("TEST-MARKET", "Yes")

    @pytest.mark.asyncio
    async def test_place_order_not_connected(self, client):
        """Test placing order when not connected."""
        result = await client.place_order(
            market_id="TEST",
            outcome="Yes",
            side=OrderSide.BUY,
            price=0.50,
            size=10
        )
        assert result.success is False
        assert "Not connected" in result.error_message

    @pytest.mark.asyncio
    async def test_cancel_order_not_connected(self, client):
        """Test canceling order when not connected."""
        result = await client.cancel_order("order_123")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_balance_not_connected(self, client):
        """Test getting balance when not connected."""
        balance = await client.get_balance()
        assert balance == 0.0

    @pytest.mark.asyncio
    async def test_get_positions_not_connected(self, client):
        """Test getting positions when not connected."""
        positions = await client.get_positions()
        assert positions == []


class TestKalshiClientMocked:
    """Tests for KalshiClient with mocked API responses."""

    @pytest.fixture
    def connected_client(self):
        """Create a mocked connected client."""
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend

        creds = KalshiCredentials(
            api_key_id="test_api_key_id",
            private_key_pem=TEST_RSA_PRIVATE_KEY
        )
        client = KalshiClient(creds, use_demo=True)

        # Load the private key for mocking
        private_key = serialization.load_pem_private_key(
            TEST_RSA_PRIVATE_KEY.encode(),
            password=None,
            backend=default_backend()
        )

        client._connected = True
        client._private_key = private_key
        client._api_key_id = "test_api_key_id"
        client._session = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_fetch_markets_success(self, connected_client):
        """Test successful market fetch."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "markets": [
                {
                    "ticker": "PRES-24-DEM",
                    "title": "Will Democrats win the 2024 presidential election?",
                    "volume": 100000,
                    "status": "active",
                    "category": "Politics"
                }
            ],
            "cursor": None
        })

        connected_client._session.get = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))

        markets = await connected_client.fetch_markets()

        assert len(markets) == 1
        assert markets[0].platform == "kalshi"
        assert markets[0].market_id == "PRES-24-DEM"
        assert markets[0].is_binary is True

    @pytest.mark.asyncio
    async def test_get_order_book_success(self, connected_client):
        """Test successful order book fetch."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "orderbook": {
                "yes": [[45, 100], [44, 200]],  # price cents, quantity
                "no": [[55, 150], [56, 250]]
            }
        })

        connected_client._session.get = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))

        ob = await connected_client.get_order_book("TEST", "Yes")

        assert ob.platform == "kalshi"
        assert ob.outcome == "Yes"
        assert len(ob.bids) > 0
        assert len(ob.asks) > 0

    @pytest.mark.asyncio
    async def test_place_order_success(self, connected_client):
        """Test successful order placement."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "order": {
                "order_id": "order_123",
                "filled_count": 10,
                "status": "filled"
            }
        })

        connected_client._session.post = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))

        result = await connected_client.place_order(
            market_id="TEST",
            outcome="Yes",
            side=OrderSide.BUY,
            price=0.50,
            size=10
        )

        assert result.success is True
        assert result.order_id == "order_123"
        assert result.filled_size == 10

    @pytest.mark.asyncio
    async def test_get_balance_success(self, connected_client):
        """Test successful balance fetch."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "balance": 100000  # 1000 dollars in cents
        })

        connected_client._session.get = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))

        balance = await connected_client.get_balance()

        assert balance == 1000.0

    @pytest.mark.asyncio
    async def test_get_positions_success(self, connected_client):
        """Test successful positions fetch."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "market_positions": [
                {
                    "ticker": "TEST",
                    "position": 100,  # Positive = YES
                    "total_cost": 4500  # 45 cents * 100 contracts
                }
            ]
        })

        connected_client._session.get = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))

        positions = await connected_client.get_positions()

        assert len(positions) == 1
        assert positions[0].outcome == "Yes"
        assert positions[0].size == 100


class TestPolymarketCredentialsForClient:
    """Tests for PolymarketCredentials used by client."""

    def test_valid_credentials_for_client(self):
        """Test that valid credentials can be converted to client kwargs."""
        creds = PolymarketCredentials(
            api_key="test_key",
            api_secret="test_secret",
            passphrase="test_pass",
            private_key="0x" + "a" * 64
        )

        kwargs = creds.to_client_kwargs()

        assert kwargs["key"] == "test_key"
        assert kwargs["secret"] == "test_secret"
        assert kwargs["passphrase"] == "test_pass"
        assert kwargs["private_key"] == "a" * 64  # Without 0x
        assert len(kwargs["private_key"]) == 64


class TestClientUnifiedMarketIntegration:
    """Tests for UnifiedMarket used across clients."""

    def test_kalshi_market_tokens(self):
        """Test Kalshi market token handling."""
        market = UnifiedMarket(
            platform="kalshi",
            market_id="PRES-24-DEM",
            question="Will Democrats win?",
            outcomes=["Yes", "No"],
            volume=100000,
            tokens={"Yes": "PRES-24-DEM", "No": "PRES-24-DEM"}
        )

        # Kalshi uses same ticker for both outcomes
        assert market.get_token_id("Yes") == market.get_token_id("No")
        assert market.is_binary is True

    def test_polymarket_market_tokens(self):
        """Test Polymarket market token handling."""
        market = UnifiedMarket(
            platform="polymarket",
            market_id="0x123",
            question="Will event happen?",
            outcomes=["Yes", "No"],
            volume=50000,
            tokens={"Yes": "0xyes123", "No": "0xno456"}
        )

        # Polymarket has different token IDs
        assert market.get_token_id("Yes") != market.get_token_id("No")
        assert market.get_token_id("Yes") == "0xyes123"
