"""Interfaces module for multi-platform arbitrage."""

from backend.interfaces.exchange_client import (
    IExchangeClient,
    UnifiedMarket,
    UnifiedOrderBook,
    OrderResult,
    Position
)
from backend.interfaces.credentials import (
    IPlatformCredentials,
    PolymarketCredentials,
    KalshiCredentials
)

__all__ = [
    'IExchangeClient',
    'UnifiedMarket',
    'UnifiedOrderBook',
    'OrderResult',
    'Position',
    'IPlatformCredentials',
    'PolymarketCredentials',
    'KalshiCredentials'
]
