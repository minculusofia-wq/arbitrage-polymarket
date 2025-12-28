import os
import sys
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

@dataclass
class Config:
    """
    Centralized configuration for the Arbitrage Bot.
    Validates that all required fields are present and correctly typed.
    """
    POLY_API_KEY: str
    POLY_API_SECRET: str
    POLY_API_PASSPHRASE: str
    PRIVATE_KEY: str
    
    CAPITAL_PER_TRADE: float
    MIN_PROFIT_MARGIN: float
    MIN_MARKET_VOLUME: float

    # Optional risk management
    STOP_LOSS: Optional[float] = None
    TAKE_PROFIT: Optional[float] = None
    MAX_DAILY_LOSS: Optional[float] = None

    # Advanced settings with defaults
    CLOB_WS_URL: str = "wss://ws-fidelity.polymarket.com"
    MAX_TOKENS_MONITOR: int = 20
    FALLBACK_BALANCE: float = 1000.0

    # Optimization parameters
    COOLDOWN_SECONDS: float = 30.0  # Cooldown between trades on same market
    MAX_SLIPPAGE: float = 0.005     # Maximum acceptable slippage (0.5%)
    OPPORTUNITY_CACHE_TTL: float = 60.0  # Opportunity cache expiration

    @classmethod
    def load(cls):
        """
        Loads configuration from environment variables.
        Terminates the program if critical variables are missing.
        """
        try:
            # Critical Credentials
            api_key = os.getenv("POLY_API_KEY")
            api_secret = os.getenv("POLY_API_SECRET")
            passphrase = os.getenv("POLY_API_PASSPHRASE")
            private_key = os.getenv("PRIVATE_KEY")

            if not all([api_key, api_secret, passphrase, private_key]):
                raise ValueError("Missing critical API credentials in .env")

            # Trading Parameters
            capital = os.getenv("CAPITAL_PER_TRADE")
            margin = os.getenv("MIN_PROFIT_MARGIN")
            volume = os.getenv("MIN_MARKET_VOLUME")

            if not all([capital, margin, volume]):
                raise ValueError("Missing trading parameters (Capital, Margin, Volume) in .env")

            # Convert and validate trading parameters
            capital_float = float(capital)
            if capital_float <= 0:
                raise ValueError("CAPITAL_PER_TRADE must be positive")

            margin_float = float(margin)
            if not (0 < margin_float < 1):
                raise ValueError("MIN_PROFIT_MARGIN must be between 0 and 1")

            volume_float = float(volume)
            if volume_float < 0:
                raise ValueError("MIN_MARKET_VOLUME must be non-negative")

            # Risk Management (Optional but validated if present)
            stop_loss = os.getenv("STOP_LOSS")
            take_profit = os.getenv("TAKE_PROFIT")
            max_daily_loss = os.getenv("MAX_DAILY_LOSS")

            # Advanced settings (Optional, use defaults if not set)
            ws_url = os.getenv("CLOB_WS_URL", "wss://ws-fidelity.polymarket.com")
            max_tokens = int(os.getenv("MAX_TOKENS_MONITOR", "20"))
            fallback_balance = float(os.getenv("FALLBACK_BALANCE", "1000.0"))

            # Optimization parameters
            cooldown_seconds = float(os.getenv("COOLDOWN_SECONDS", "30.0"))
            max_slippage = float(os.getenv("MAX_SLIPPAGE", "0.005"))
            opportunity_cache_ttl = float(os.getenv("OPPORTUNITY_CACHE_TTL", "60.0"))

            return cls(
                POLY_API_KEY=api_key,
                POLY_API_SECRET=api_secret,
                POLY_API_PASSPHRASE=passphrase,
                PRIVATE_KEY=private_key,
                CAPITAL_PER_TRADE=capital_float,
                MIN_PROFIT_MARGIN=margin_float,
                MIN_MARKET_VOLUME=volume_float,
                STOP_LOSS=float(stop_loss) if stop_loss else None,
                TAKE_PROFIT=float(take_profit) if take_profit else None,
                MAX_DAILY_LOSS=float(max_daily_loss) if max_daily_loss else None,
                CLOB_WS_URL=ws_url,
                MAX_TOKENS_MONITOR=max_tokens,
                FALLBACK_BALANCE=fallback_balance,
                # Optimization parameters
                COOLDOWN_SECONDS=cooldown_seconds,
                MAX_SLIPPAGE=max_slippage,
                OPPORTUNITY_CACHE_TTL=opportunity_cache_ttl,
            )
        except Exception as e:
            # Re-raise to be handled by caller (UI or Main)
            raise e

# Initialize a global config instance for easy access (lazy loading in main recommended usually, but this works)
# We will load it in main.py to allow for UI error handling if needed.
