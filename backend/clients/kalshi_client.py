"""
Kalshi Client - Implementation of IExchangeClient for Kalshi.

This client provides async access to the Kalshi Trading API v2
for prediction market trading.
"""

import asyncio
import aiohttp
import time
import logging
from typing import List, Optional, Dict

from backend.interfaces.exchange_client import (
    IExchangeClient,
    UnifiedMarket,
    UnifiedOrderBook,
    OrderResult,
    Position,
    OrderSide,
    OrderType,
    OrderStatus
)
from backend.interfaces.credentials import KalshiCredentials
from backend.utils.ssl_patch import get_ssl_context

logger = logging.getLogger(__name__)


class KalshiClient(IExchangeClient):
    """
    Kalshi exchange client implementing IExchangeClient interface.

    Uses the Kalshi Trading API v2 for market data and order execution.
    """

    BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
    DEMO_URL = "https://demo-api.kalshi.co/trade-api/v2"

    def __init__(self, credentials: KalshiCredentials, use_demo: bool = False):
        """
        Initialize Kalshi client.

        Args:
            credentials: KalshiCredentials object with email/password
            use_demo: If True, use demo environment
        """
        self.credentials = credentials
        self.base_url = self.DEMO_URL if use_demo else self.BASE_URL
        self._session: Optional[aiohttp.ClientSession] = None
        self._token: Optional[str] = None
        self._member_id: Optional[str] = None
        self._connected = False
        self._markets_cache: Dict[str, UnifiedMarket] = {}
        self._last_markets_fetch: float = 0
        self._cache_ttl: float = 60.0

    @property
    def platform_name(self) -> str:
        return "kalshi"

    @property
    def is_connected(self) -> bool:
        return self._connected and self._session is not None and self._token is not None

    async def connect(self) -> bool:
        """Connect and authenticate to Kalshi API."""
        try:
            # Validate credentials first
            is_valid, error = self.credentials.validate()
            if not is_valid:
                logger.error(f"Invalid Kalshi credentials: {error}")
                return False

            # Create aiohttp session with custom SSL context
            connector = aiohttp.TCPConnector(ssl=get_ssl_context())
            self._session = aiohttp.ClientSession(connector=connector)

            # Authenticate
            auth_data = {
                "email": self.credentials.email,
                "password": self.credentials.password
            }

            # Try to authenticate with multiple possible endpoints for the new API
            login_endpoints = [
                f"{self.base_url}/login",
                "https://api.elections.kalshi.com/v2/login",
                "https://api.elections.kalshi.com/trade-api/v2/log_in"
            ]
            
            last_error = ""
            for auth_url in login_endpoints:
                try:
                    logger.info(f"Attempting Kalshi login at {auth_url}...")
                    async with self._session.post(auth_url, json=auth_data) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            self._token = data.get("token")
                            self._member_id = data.get("member_id")
                            self._connected = True
                            logger.info(f"Kalshi client connected successfully via {auth_url}")
                            return True
                        elif resp.status == 404:
                            logger.warning(f"Kalshi login at {auth_url} returned 404, trying next...")
                            continue
                        else:
                            error_text = await resp.text()
                            last_error = f"{resp.status} - {error_text}"
                            logger.error(f"Kalshi authentication failed at {auth_url}: {last_error}")
                except Exception as e:
                    logger.error(f"Error during Kalshi login attempt at {auth_url}: {e}")
                    last_error = str(e)

            logger.error(f"Failed to connect to Kalshi after trying all endpoints. Last error: {last_error}")
            await self.disconnect()
            return False

        except Exception as e:
            logger.error(f"Unexpected error connecting to Kalshi: {e}")
            await self.disconnect()
            return False

    async def disconnect(self) -> None:
        """Disconnect from Kalshi and cleanup session."""
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None
        self._token = None
        self._member_id = None
        self._connected = False
        self._markets_cache.clear()
        logger.info("Kalshi client disconnected")

    def _get_headers(self) -> Dict[str, str]:
        """Get authentication headers."""
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def fetch_markets(
        self,
        min_volume: float = 0,
        active_only: bool = True
    ) -> List[UnifiedMarket]:
        """Fetch available markets from Kalshi."""
        if not self.is_connected:
            logger.error("Cannot fetch markets: not connected")
            return []

        try:
            # Fetch markets from Kalshi API
            url = f"{self.base_url}/markets"
            params = {"limit": 200}
            if active_only:
                params["status"] = "active"

            unified_markets = []
            cursor = None

            while True:
                if cursor:
                    params["cursor"] = cursor

                async with self._session.get(
                    url,
                    headers=self._get_headers(),
                    params=params
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"Error fetching Kalshi markets: {resp.status} - {error_text}")
                        break

                    data = await resp.json()
                    markets = data.get("markets", [])

                    for m in markets:
                        # Filter by volume if specified
                        volume = float(m.get("volume", 0) or 0)
                        if volume < min_volume:
                            continue

                        # Kalshi markets are binary (Yes/No)
                        ticker = m.get("ticker", "")

                        unified_market = UnifiedMarket(
                            platform="kalshi",
                            market_id=ticker,
                            question=m.get("title", ""),
                            outcomes=["Yes", "No"],
                            volume=volume,
                            end_date=m.get("close_time"),
                            tokens={"Yes": ticker, "No": ticker},  # Kalshi uses same ticker for both
                            active=m.get("status") == "active",
                            category=m.get("category")
                        )

                        unified_markets.append(unified_market)
                        self._markets_cache[unified_market.market_id] = unified_market

                    # Check for pagination
                    cursor = data.get("cursor")
                    if not cursor or not markets:
                        break

            self._last_markets_fetch = time.time()
            logger.info(f"Fetched {len(unified_markets)} markets from Kalshi")
            return unified_markets

        except Exception as e:
            logger.error(f"Error fetching Kalshi markets: {e}")
            return []

    async def get_order_book(
        self,
        market_id: str,
        outcome: str
    ) -> UnifiedOrderBook:
        """Get order book for a specific market outcome."""
        if not self.is_connected:
            raise RuntimeError("Cannot get order book: not connected")

        try:
            url = f"{self.base_url}/markets/{market_id}/orderbook"

            async with self._session.get(
                url,
                headers=self._get_headers()
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(f"Error getting order book: {resp.status} - {error_text}")

                data = await resp.json()
                orderbook = data.get("orderbook", {})

                # Kalshi order book format:
                # yes: [[price_cents, quantity], ...] - people buying YES
                # no: [[price_cents, quantity], ...] - people buying NO

                bids = []
                asks = []

                if outcome == "Yes":
                    # For YES outcome:
                    # Bids = people wanting to buy YES (yes list)
                    # Asks = people wanting to sell YES = buying NO at inverse price
                    for entry in orderbook.get("yes", []):
                        price_cents = float(entry[0])
                        quantity = int(entry[1])
                        price = price_cents / 100.0
                        if price > 0 and quantity > 0:
                            bids.append((price, quantity))

                    for entry in orderbook.get("no", []):
                        price_cents = float(entry[0])
                        quantity = int(entry[1])
                        # If someone buys NO at X cents, they're selling YES at (100-X) cents
                        ask_price = (100 - price_cents) / 100.0
                        if ask_price > 0 and quantity > 0:
                            asks.append((ask_price, quantity))
                else:
                    # For NO outcome:
                    # Bids = people wanting to buy NO (no list)
                    # Asks = people wanting to sell NO = buying YES at inverse price
                    for entry in orderbook.get("no", []):
                        price_cents = float(entry[0])
                        quantity = int(entry[1])
                        price = price_cents / 100.0
                        if price > 0 and quantity > 0:
                            bids.append((price, quantity))

                    for entry in orderbook.get("yes", []):
                        price_cents = float(entry[0])
                        quantity = int(entry[1])
                        ask_price = (100 - price_cents) / 100.0
                        if ask_price > 0 and quantity > 0:
                            asks.append((ask_price, quantity))

                # Sort: bids descending, asks ascending
                bids.sort(key=lambda x: x[0], reverse=True)
                asks.sort(key=lambda x: x[0])

                return UnifiedOrderBook(
                    platform="kalshi",
                    market_id=market_id,
                    outcome=outcome,
                    bids=bids,
                    asks=asks,
                    timestamp=time.time()
                )

        except Exception as e:
            logger.error(f"Error getting order book for {market_id}/{outcome}: {e}")
            raise

    async def place_order(
        self,
        market_id: str,
        outcome: str,
        side: OrderSide,
        price: float,
        size: float,
        order_type: OrderType = OrderType.FOK
    ) -> OrderResult:
        """Place an order on Kalshi."""
        if not self.is_connected:
            return OrderResult(
                success=False,
                error_message="Not connected to Kalshi",
                platform="kalshi"
            )

        try:
            url = f"{self.base_url}/portfolio/orders"

            # Convert price to cents
            price_cents = int(price * 100)

            # Kalshi order format
            order_data = {
                "ticker": market_id,
                "action": "buy" if side == OrderSide.BUY else "sell",
                "side": "yes" if outcome == "Yes" else "no",
                "count": int(size),
                "type": "limit"
            }

            # Set price based on outcome
            if outcome == "Yes":
                order_data["yes_price"] = price_cents
            else:
                order_data["no_price"] = price_cents

            # Order type handling
            if order_type == OrderType.FOK:
                order_data["expiration_ts"] = int(time.time()) + 60  # 1 minute expiry
                order_data["sell_position_floor"] = 0
                order_data["buy_max_cost"] = int(size * price * 100)

            async with self._session.post(
                url,
                headers=self._get_headers(),
                json=order_data
            ) as resp:
                if resp.status in [200, 201]:
                    data = await resp.json()
                    order = data.get("order", {})
                    return OrderResult(
                        success=True,
                        order_id=order.get("order_id", ""),
                        filled_size=float(order.get("filled_count", 0)),
                        filled_price=price,
                        status=OrderStatus.FILLED if order.get("status") == "filled" else OrderStatus.PENDING,
                        platform="kalshi"
                    )
                else:
                    error_text = await resp.text()
                    return OrderResult(
                        success=False,
                        error_message=f"Order failed: {resp.status} - {error_text}",
                        status=OrderStatus.REJECTED,
                        platform="kalshi"
                    )

        except Exception as e:
            logger.error(f"Error placing Kalshi order: {e}")
            return OrderResult(
                success=False,
                error_message=str(e),
                status=OrderStatus.REJECTED,
                platform="kalshi"
            )

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        if not self.is_connected:
            return False

        try:
            url = f"{self.base_url}/portfolio/orders/{order_id}"

            async with self._session.delete(
                url,
                headers=self._get_headers()
            ) as resp:
                return resp.status in [200, 204]

        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False

    async def get_balance(self) -> float:
        """Get available USD balance."""
        if not self.is_connected:
            return 0.0

        try:
            url = f"{self.base_url}/portfolio/balance"

            async with self._session.get(
                url,
                headers=self._get_headers()
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Balance is in cents, convert to dollars
                    balance_cents = float(data.get("balance", 0))
                    return balance_cents / 100.0
                return 0.0

        except Exception as e:
            logger.error(f"Error getting Kalshi balance: {e}")
            return 0.0

    async def get_positions(self) -> List[Position]:
        """Get all open positions."""
        if not self.is_connected:
            return []

        try:
            url = f"{self.base_url}/portfolio/positions"

            async with self._session.get(
                url,
                headers=self._get_headers()
            ) as resp:
                if resp.status != 200:
                    return []

                data = await resp.json()
                positions = []

                for p in data.get("market_positions", []):
                    ticker = p.get("ticker")

                    # Kalshi positions have yes_count and no_count
                    yes_count = int(p.get("position", 0))

                    if yes_count > 0:
                        positions.append(Position(
                            platform="kalshi",
                            market_id=ticker,
                            outcome="Yes",
                            size=yes_count,
                            entry_price=float(p.get("total_cost", 0)) / (yes_count * 100) if yes_count else 0,
                            current_price=float(p.get("market_exposure", 0)) / (yes_count * 100) if yes_count else None
                        ))
                    elif yes_count < 0:
                        # Negative means NO position
                        no_count = abs(yes_count)
                        positions.append(Position(
                            platform="kalshi",
                            market_id=ticker,
                            outcome="No",
                            size=no_count,
                            entry_price=float(p.get("total_cost", 0)) / (no_count * 100) if no_count else 0
                        ))

                return positions

        except Exception as e:
            logger.error(f"Error getting Kalshi positions: {e}")
            return []

    async def get_market_by_id(
        self,
        market_id: str
    ) -> Optional[UnifiedMarket]:
        """Get a specific market by ID (ticker)."""
        # Check cache first
        if market_id in self._markets_cache:
            return self._markets_cache[market_id]

        if not self.is_connected:
            return None

        try:
            url = f"{self.base_url}/markets/{market_id}"

            async with self._session.get(
                url,
                headers=self._get_headers()
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    m = data.get("market", {})

                    unified_market = UnifiedMarket(
                        platform="kalshi",
                        market_id=m.get("ticker", market_id),
                        question=m.get("title", ""),
                        outcomes=["Yes", "No"],
                        volume=float(m.get("volume", 0) or 0),
                        end_date=m.get("close_time"),
                        tokens={"Yes": market_id, "No": market_id},
                        active=m.get("status") == "active",
                        category=m.get("category")
                    )

                    self._markets_cache[market_id] = unified_market
                    return unified_market

        except Exception as e:
            logger.error(f"Error getting Kalshi market {market_id}: {e}")

        return None

    async def get_event_markets(self, event_ticker: str) -> List[UnifiedMarket]:
        """Get all markets for a specific event."""
        if not self.is_connected:
            return []

        try:
            url = f"{self.base_url}/events/{event_ticker}/markets"

            async with self._session.get(
                url,
                headers=self._get_headers()
            ) as resp:
                if resp.status != 200:
                    return []

                data = await resp.json()
                markets = []

                for m in data.get("markets", []):
                    unified_market = UnifiedMarket(
                        platform="kalshi",
                        market_id=m.get("ticker", ""),
                        question=m.get("title", ""),
                        outcomes=["Yes", "No"],
                        volume=float(m.get("volume", 0) or 0),
                        end_date=m.get("close_time"),
                        tokens={"Yes": m.get("ticker"), "No": m.get("ticker")},
                        active=m.get("status") == "active",
                        category=m.get("category")
                    )
                    markets.append(unified_market)
                    self._markets_cache[unified_market.market_id] = unified_market

                return markets

        except Exception as e:
            logger.error(f"Error getting event markets: {e}")
            return []
