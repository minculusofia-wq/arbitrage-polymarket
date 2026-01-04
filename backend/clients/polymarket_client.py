"""
Polymarket Client - Implementation of IExchangeClient for Polymarket.

This client wraps the py_clob_client library and provides a unified interface
for interacting with the Polymarket CLOB API.
"""

import asyncio
import time
import logging
from typing import List, Optional, Dict, Tuple

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType as ClobOrderType
from py_clob_client.order_builder.constants import BUY, SELL
from py_clob_client.constants import POLYGON

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
from backend.interfaces.credentials import PolymarketCredentials

logger = logging.getLogger(__name__)


class PolymarketClient(IExchangeClient):
    """
    Polymarket exchange client implementing IExchangeClient interface.

    Wraps the py_clob_client library for unified access to Polymarket CLOB API.
    """

    CLOB_HOST = "https://clob.polymarket.com"
    CHAIN_ID = POLYGON  # 137

    def __init__(self, credentials: PolymarketCredentials):
        """
        Initialize Polymarket client.

        Args:
            credentials: PolymarketCredentials object with API keys and private key
        """
        self.credentials = credentials
        self._client: Optional[ClobClient] = None
        self._connected = False
        self._markets_cache: Dict[str, UnifiedMarket] = {}
        self._last_markets_fetch: float = 0
        self._cache_ttl: float = 60.0  # 1 minute cache

    @property
    def platform_name(self) -> str:
        return "polymarket"

    @property
    def is_connected(self) -> bool:
        return self._connected and self._client is not None

    async def connect(self) -> bool:
        """Connect and authenticate to Polymarket CLOB API."""
        try:
            logger.info(f"Connecting to Polymarket (HOST={self.CLOB_HOST}, CHAIN_ID={self.CHAIN_ID})...")
            
            # Diagnostic: Inspect raw credential values before validation
            import re
            def debug_val(name, val):
                if not val:
                    logger.info(f"{name} is empty")
                    return
                # Show first/last chars and total length
                safe_val = val[:2] + "..." + val[-2:] if len(val) > 4 else "..."
                raw_repr = repr(val)
                logger.info(f"{name}: len={len(val)}, safe='{safe_val}', repr={raw_repr}")
                # Check for non-hex in PK
                if name == "PK" and not re.match(r'^[0-9a-fA-F]*$', val):
                    non_hex = set(re.sub(r'[0-9a-fA-F]', '', val))
                    logger.error(f"PRIVATE KEY CONTAINS NON-HEX CHARACTERS: {non_hex}")
                    # Log char codes of problematic characters
                    for char in val:
                        if not re.match(r'[0-9a-fA-F]', char):
                            logger.error(f"  Invalid char found: '{char}' (code: {ord(char)})")

            # Validate credentials first
            is_valid, error = self.credentials.validate()
            if not is_valid:
                logger.error(f"Invalid Polymarket credentials: {error}")
                return False

            kwargs = self.credentials.to_client_kwargs()
            pk = kwargs.get("private_key", "")
            
            debug_val("API_KEY", kwargs.get("key"))
            debug_val("PK", pk)

            # Initialize ClobClient
            logger.info("Instantiating ClobClient...")
            self._client = ClobClient(
                self.CLOB_HOST,
                key=kwargs["key"],
                chain_id=self.CHAIN_ID,
                signature_type=1,  # L2 API Key
                funder=pk
            )

            # Set API credentials for authenticated requests
            self._client.set_api_creds(
                api_key=kwargs["key"],
                api_secret=kwargs["secret"],
                api_passphrase=kwargs["passphrase"]
            )

            self._connected = True
            logger.info("Polymarket client connected successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to Polymarket: {e}")
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from Polymarket."""
        self._client = None
        self._connected = False
        self._markets_cache.clear()
        logger.info("Polymarket client disconnected")

    async def fetch_markets(
        self,
        min_volume: float = 0,
        active_only: bool = True
    ) -> List[UnifiedMarket]:
        """Fetch available markets from Polymarket."""
        if not self.is_connected:
            logger.error("Cannot fetch markets: not connected")
            return []

        try:
            loop = asyncio.get_running_loop()

            # Fetch markets from CLOB API
            markets = await loop.run_in_executor(
                None,
                lambda: self._client.get_markets(
                    limit=100,
                    active=active_only,
                    volume_min=min_volume
                )
            )

            unified_markets = []
            self._markets_cache.clear()

            for m in markets:
                # Only process binary markets (2 tokens)
                tokens = m.get('tokens', [])
                if len(tokens) != 2:
                    continue

                # Build token mapping
                token_map = {}
                for i, token in enumerate(tokens):
                    # First token is typically YES, second is NO
                    outcome = "Yes" if i == 0 else "No"
                    token_map[outcome] = token.get('token_id', '')

                unified_market = UnifiedMarket(
                    platform="polymarket",
                    market_id=m.get('condition_id', ''),
                    question=m.get('question', ''),
                    outcomes=["Yes", "No"],
                    volume=float(m.get('volume', 0) or 0),
                    end_date=m.get('end_date_iso'),
                    tokens=token_map,
                    active=m.get('active', True),
                    category=m.get('category')
                )

                unified_markets.append(unified_market)
                self._markets_cache[unified_market.market_id] = unified_market

            self._last_markets_fetch = time.time()
            logger.info(f"Fetched {len(unified_markets)} binary markets from Polymarket")
            return unified_markets

        except Exception as e:
            logger.error(f"Error fetching Polymarket markets: {e}")
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
            # Get token ID for the outcome
            market = self._markets_cache.get(market_id)
            if not market:
                # Fetch markets if not in cache
                await self.fetch_markets()
                market = self._markets_cache.get(market_id)

            if not market:
                raise ValueError(f"Market {market_id} not found")

            token_id = market.tokens.get(outcome)
            if not token_id:
                raise ValueError(f"No token found for outcome {outcome} in market {market_id}")

            loop = asyncio.get_running_loop()

            # Fetch order book from CLOB API
            order_book = await loop.run_in_executor(
                None,
                lambda: self._client.get_order_book(token_id)
            )

            # Parse bids and asks
            bids = []
            asks = []

            for bid in order_book.get('bids', []):
                price = float(bid.get('price', 0))
                size = float(bid.get('size', 0))
                if price > 0 and size > 0:
                    bids.append((price, size))

            for ask in order_book.get('asks', []):
                price = float(ask.get('price', 0))
                size = float(ask.get('size', 0))
                if price > 0 and size > 0:
                    asks.append((price, size))

            # Sort: bids descending, asks ascending
            bids.sort(key=lambda x: x[0], reverse=True)
            asks.sort(key=lambda x: x[0])

            return UnifiedOrderBook(
                platform="polymarket",
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
        """Place an order on Polymarket."""
        if not self.is_connected:
            return OrderResult(
                success=False,
                error_message="Not connected to Polymarket",
                platform="polymarket"
            )

        try:
            # Get token ID for the outcome
            market = self._markets_cache.get(market_id)
            if not market:
                await self.fetch_markets()
                market = self._markets_cache.get(market_id)

            if not market:
                return OrderResult(
                    success=False,
                    error_message=f"Market {market_id} not found",
                    platform="polymarket"
                )

            token_id = market.tokens.get(outcome)
            if not token_id:
                return OrderResult(
                    success=False,
                    error_message=f"No token for outcome {outcome}",
                    platform="polymarket"
                )

            # Map order type to CLOB order type
            clob_order_type = ClobOrderType.FOK
            if order_type == OrderType.LIMIT:
                clob_order_type = ClobOrderType.GTC
            elif order_type == OrderType.GTC:
                clob_order_type = ClobOrderType.GTC

            # Map side
            clob_side = BUY if side == OrderSide.BUY else SELL

            loop = asyncio.get_running_loop()

            # Place order
            response = await loop.run_in_executor(
                None,
                lambda: self._client.create_and_post_order(
                    OrderArgs(
                        price=price,
                        size=size,
                        side=clob_side,
                        token_id=token_id,
                        order_type=clob_order_type
                    )
                )
            )

            # Parse response
            if response and response.get('success'):
                return OrderResult(
                    success=True,
                    order_id=response.get('order_id', ''),
                    filled_size=float(response.get('filled_size', size)),
                    filled_price=float(response.get('average_price', price)),
                    status=OrderStatus.FILLED,
                    platform="polymarket"
                )
            else:
                return OrderResult(
                    success=False,
                    error_message=response.get('error', 'Order failed'),
                    status=OrderStatus.REJECTED,
                    platform="polymarket"
                )

        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return OrderResult(
                success=False,
                error_message=str(e),
                status=OrderStatus.REJECTED,
                platform="polymarket"
            )

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        if not self.is_connected:
            return False

        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._client.cancel(order_id)
            )
            return response.get('success', False)
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False

    async def get_balance(self) -> float:
        """Get available USDC balance."""
        if not self.is_connected:
            return 0.0

        try:
            loop = asyncio.get_running_loop()
            balance_info = await loop.run_in_executor(
                None,
                lambda: self._client.get_balance()
            )
            # Parse balance (format depends on API response)
            if isinstance(balance_info, dict):
                return float(balance_info.get('balance', 0))
            return float(balance_info or 0)
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return 0.0

    async def get_positions(self) -> List[Position]:
        """Get all open positions."""
        if not self.is_connected:
            return []

        try:
            loop = asyncio.get_running_loop()
            positions_data = await loop.run_in_executor(
                None,
                lambda: self._client.get_positions()
            )

            positions = []
            for p in (positions_data or []):
                # Map token_id back to market_id and outcome
                token_id = p.get('token_id')
                market_id = None
                outcome = None

                for mid, market in self._markets_cache.items():
                    for out, tid in market.tokens.items():
                        if tid == token_id:
                            market_id = mid
                            outcome = out
                            break
                    if market_id:
                        break

                if market_id:
                    positions.append(Position(
                        platform="polymarket",
                        market_id=market_id,
                        outcome=outcome or "Unknown",
                        size=float(p.get('size', 0)),
                        entry_price=float(p.get('avg_price', 0)),
                        current_price=float(p.get('current_price', 0)) if p.get('current_price') else None
                    ))

            return positions

        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []

    async def get_market_by_id(
        self,
        market_id: str
    ) -> Optional[UnifiedMarket]:
        """Get a specific market by ID."""
        # Check cache first
        if market_id in self._markets_cache:
            return self._markets_cache[market_id]

        # Fetch markets if cache is stale
        if time.time() - self._last_markets_fetch > self._cache_ttl:
            await self.fetch_markets()

        return self._markets_cache.get(market_id)

    def get_raw_client(self) -> Optional[ClobClient]:
        """Get the underlying ClobClient for advanced operations."""
        return self._client
