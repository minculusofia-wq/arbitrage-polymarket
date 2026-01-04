import os
import sys
from dataclasses import dataclass, field
from typing import Optional, List
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

    # Paper Trading / Backtest settings
    PAPER_TRADING_ENABLED: bool = False  # Run in paper trading mode (no real trades)
    DATA_COLLECTION_ENABLED: bool = True  # Collect order book snapshots for backtesting
    SNAPSHOT_INTERVAL_MS: int = 1000  # Interval between snapshots in milliseconds
    PAPER_INITIAL_BALANCE: float = 10000.0  # Starting balance for paper trading

    # Advanced Optimization settings
    TRADING_FEE_PERCENT: float = 0.01  # Trading fee per side (1% = 0.01)
    MIN_PROFIT_DOLLARS: float = 1.0  # Minimum absolute profit per trade in $
    MAX_CONCURRENT_POSITIONS: int = 10  # Maximum simultaneous open positions
    MAX_ORDER_BOOK_DEPTH: int = 20  # Maximum order book levels to analyze
    MIN_MARKET_QUALITY_SCORE: float = 50.0  # Minimum market quality score (0-100)

    # Kalshi credentials (optional)
    KALSHI_EMAIL: str = ""
    KALSHI_PASSWORD: str = ""
    KALSHI_API_KEY: str = ""

    # Multi-platform settings
    ENABLED_PLATFORMS: List[str] = field(default_factory=lambda: ["polymarket"])
    CROSS_PLATFORM_ARBITRAGE: bool = False  # Enable cross-platform arbitrage detection

    @classmethod
    def load(cls):
        """
        Loads configuration from environment variables.
        Terminates the program if critical variables are missing.
        """
        try:
            # Critical Credentials
            # Critical Credentials - Aggressively remove all whitespace/hidden chars
            api_key = os.getenv("POLY_API_KEY", "").strip().replace(" ", "")
            api_secret = os.getenv("POLY_API_SECRET", "").strip().replace(" ", "")
            passphrase = os.getenv("POLY_API_PASSPHRASE", "").strip().replace(" ", "")
            private_key = os.getenv("PRIVATE_KEY", "").strip().replace(" ", "")

            from backend.logger import logger
            logger.info(f"Credential check - KEY len: {len(api_key)}, SECRET len: {len(api_secret)}, PASSPHRASE len: {len(passphrase)}, PK len: {len(private_key)}")

            if private_key.startswith("0x"):
                private_key = private_key[2:]

            # Check which platforms are enabled to validate credentials
            enabled_platforms_check = os.getenv("ENABLED_PLATFORMS", "polymarket")
            poly_enabled = "polymarket" in enabled_platforms_check.lower()
            kalshi_enabled = "kalshi" in enabled_platforms_check.lower()

            # Validate Polymarket credentials only if Polymarket is enabled
            if poly_enabled and not all([api_key, api_secret, passphrase, private_key]):
                raise ValueError("Missing Polymarket API credentials in .env (required when Polymarket is enabled)")

            # Validate Kalshi credentials only if Kalshi is enabled
            kalshi_email_check = os.getenv("KALSHI_EMAIL", "").strip()
            kalshi_password_check = os.getenv("KALSHI_PASSWORD", "").strip()
            if kalshi_enabled and not all([kalshi_email_check, kalshi_password_check]):
                raise ValueError("Missing Kalshi credentials in .env (required when Kalshi is enabled)")

            # At least one platform must be enabled
            if not poly_enabled and not kalshi_enabled:
                raise ValueError("At least one platform must be enabled (polymarket or kalshi)")

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

            # Paper Trading / Backtest settings
            paper_trading = os.getenv("PAPER_TRADING_ENABLED", "false").lower() in ("true", "1", "yes")
            data_collection = os.getenv("DATA_COLLECTION_ENABLED", "true").lower() in ("true", "1", "yes")
            snapshot_interval = int(os.getenv("SNAPSHOT_INTERVAL_MS", "1000"))
            paper_balance = float(os.getenv("PAPER_INITIAL_BALANCE", "10000.0"))

            # Advanced Optimization settings
            trading_fee = float(os.getenv("TRADING_FEE_PERCENT", "0.01"))
            min_profit_dollars = float(os.getenv("MIN_PROFIT_DOLLARS", "1.0"))
            max_positions = int(os.getenv("MAX_CONCURRENT_POSITIONS", "10"))
            max_depth = int(os.getenv("MAX_ORDER_BOOK_DEPTH", "20"))
            min_quality_score = float(os.getenv("MIN_MARKET_QUALITY_SCORE", "50.0"))

            # Kalshi credentials (optional)
            kalshi_email = os.getenv("KALSHI_EMAIL", "").strip()
            kalshi_password = os.getenv("KALSHI_PASSWORD", "").strip()
            kalshi_api_key = os.getenv("KALSHI_API_KEY", "").strip()

            # Multi-platform settings
            enabled_platforms_str = os.getenv("ENABLED_PLATFORMS", "polymarket")
            enabled_platforms = [p.strip() for p in enabled_platforms_str.split(",") if p.strip()]
            cross_platform = os.getenv("CROSS_PLATFORM_ARBITRAGE", "false").lower() in ("true", "1", "yes")

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
                # Paper Trading / Backtest settings
                PAPER_TRADING_ENABLED=paper_trading,
                DATA_COLLECTION_ENABLED=data_collection,
                SNAPSHOT_INTERVAL_MS=snapshot_interval,
                PAPER_INITIAL_BALANCE=paper_balance,
                # Advanced Optimization settings
                TRADING_FEE_PERCENT=trading_fee,
                MIN_PROFIT_DOLLARS=min_profit_dollars,
                MAX_CONCURRENT_POSITIONS=max_positions,
                MAX_ORDER_BOOK_DEPTH=max_depth,
                MIN_MARKET_QUALITY_SCORE=min_quality_score,
                # Kalshi credentials
                KALSHI_EMAIL=kalshi_email,
                KALSHI_PASSWORD=kalshi_password,
                KALSHI_API_KEY=kalshi_api_key,
                # Multi-platform settings
                ENABLED_PLATFORMS=enabled_platforms,
                CROSS_PLATFORM_ARBITRAGE=cross_platform,
            )
        except Exception as e:
            # Re-raise to be handled by caller (UI or Main)
            raise e

# Initialize a global config instance for easy access (lazy loading in main recommended usually, but this works)
# We will load it in main.py to allow for UI error handling if needed.
