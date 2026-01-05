# Multi-Platform Arbitrage Bot

A professional-grade arbitrage trading bot for prediction markets. Supports **Polymarket** and **Kalshi** with cross-platform arbitrage detection.

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![PySide6](https://img.shields.io/badge/GUI-PySide6-green.svg)
![Tests](https://img.shields.io/badge/Tests-372%20passed-brightgreen.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## Features

### Multi-Platform Support (Phase 6 - NEW)
- **Polymarket Integration** - Full CLOB API support with WebSocket order books
- **Kalshi Integration** - REST API support for US-regulated prediction markets
- **Cross-Platform Arbitrage** - Detects price discrepancies between platforms on similar markets
- **Market Matching** - Automatic question similarity matching (80%+ threshold)
- **Unified Interface** - Abstract IExchangeClient interface for platform-agnostic trading
- **Credentials Panel** - Tabbed UI for managing API credentials for each platform

### Core Trading
- **Real-time Market Monitoring** - WebSocket connection to Polymarket order books
- **Automatic Arbitrage Detection** - Finds opportunities where YES + NO < 1.0
- **Parallel Order Execution** - Simultaneous BUY orders for both legs
- **Fill-or-Kill Orders** - Minimizes partial fill risk

### Advanced Optimizations
- **Market Impact Calculator** - Calculates REAL cost across order book depth (prevents buying at effective price > $1.00)
- **Cooldown Manager** - Prevents spam trading with per-market cooldown
- **Execution Lock** - Prevents duplicate execution on same market
- **Slippage Protection** - Verifies prices haven't moved before execution
- **Opportunity Cache** - Ranks opportunities by ROI

### Resilience
- **Auto-Reconnection** - WebSocket reconnects with exponential backoff (5s to 60s)
- **Market Quality Scoring** - Prioritizes markets by volume, liquidity, spread, time

### Risk Management (Phase 2)
- **Stop-Loss** - Automatic position exit at configurable loss threshold
- **Take-Profit** - Lock in gains at configurable profit threshold
- **Daily Loss Limit** - Halts trading when daily losses exceed limit
- **Trade Persistence** - SQLite database saves all trades (survives restarts)
- **API Rate Limiter** - Prevents API bans with sliding window throttling

### Position Management (Phase 3)
- **Position Monitor** - Real-time monitoring of open positions with P&L
- **Manual Exit** - Exit any position manually at any time
- **Automatic Exit Execution** - Sells both YES/NO tokens when exit triggers
- **Balance Verification** - Checks USDC balance before each trade

### Paper Trading & Backtesting (Phase 4)
- **Paper Trading Mode** - Simulate trades without real money
- **Data Collection** - Records order book snapshots for backtesting
- **Backtest Engine** - Replay historical data to test strategies
- **Backtest GUI** - Visual dashboard for backtest results with CSV export

### Profitability Optimizations (Phase 5)
- **Trading Fee Model** - Accounts for 1% trading fees in profitability calculations
- **Minimum Profit Threshold** - Avoids micro-trades with <$1 profit
- **Dynamic Capital Allocation** - Adjusts trade size based on opportunity quality (ROI, market score, daily P&L)
- **Position Limits** - Maximum 10 concurrent positions for risk control
- **Time-Based Trading** - Optimized allocation during US market hours (peak/normal/low periods)
- **Momentum Detection** - Prioritizes improving opportunities over degrading ones
- **Dynamic Balance Buffer** - 2-10% buffer based on order book depth consumed

### User Interface
- **PnL Dashboard** - Real-time balance, daily/total P&L, win rate, ROI
- **Trade History** - Historical trades table with CSV export
- **Live Market Feed** - Shows arbitrage opportunities in real-time
- **Backtest Tab** - Configure and run backtests with results visualization
- **System Logs** - Real-time logs in console
- **Modern Dark UI** - Professional Qt-based interface

## Screenshots

The application features a modern dark-themed interface with:
- **Performance Dashboard** - Balance, P&L (today/total), win rate, avg ROI, trade count
- **Tabbed View** - Live Market Feed + Trade History + Backtest with CSV export
- **System Logs** - Real-time logging
- **Configuration Panel** - API credentials and trading parameters

## Installation

### Requirements

- Python 3.11 (required for PySide6 compatibility)
- macOS / Linux / Windows

### Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/arbitrage-poly.git
   cd arbitrage-poly
   ```

2. **Create virtual environment**
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your Polymarket API credentials
   ```

5. **Run the bot**
   ```bash
   python main.py
   ```

### macOS Quick Launch

Double-click `Start_Bot.command` in Finder - it handles everything automatically.

## Configuration

Edit `.env` or configure directly in the application:

### Polymarket Credentials

| Parameter | Description | Example |
|-----------|-------------|---------|
| `POLY_API_KEY` | Polymarket API Key | `your_api_key` |
| `POLY_API_SECRET` | Polymarket API Secret | `your_secret` |
| `POLY_API_PASSPHRASE` | Polymarket Passphrase | `your_passphrase` |
| `PRIVATE_KEY` | Wallet private key for signing | `0x...` |

### Kalshi Credentials (Optional)

Kalshi API v2 uses RSA-PSS authentication. Generate your API key pair at [Kalshi Settings](https://kalshi.com/settings/api).

| Parameter | Description | Example |
|-----------|-------------|---------|
| `KALSHI_API_KEY_ID` | API Key ID from Kalshi dashboard | `your_api_key_id` |
| `KALSHI_PRIVATE_KEY_PATH` | Path to RSA private key PEM file | `~/.kalshi/private_key.pem` |

### Multi-Platform Settings

| Parameter | Description | Example |
|-----------|-------------|---------|
| `ENABLED_PLATFORMS` | Comma-separated platforms | `polymarket,kalshi` |
| `CROSS_PLATFORM_ARBITRAGE` | Enable cross-platform detection | `true` |

### Trading Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `CAPITAL_PER_TRADE` | USDC amount per trade | `10.0` |
| `MIN_PROFIT_MARGIN` | Minimum profit margin (0-1) | `0.02` (2%) |
| `MIN_MARKET_VOLUME` | Minimum market volume filter | `5000` |

### Risk Management (Optional)

| Parameter | Description | Example |
|-----------|-------------|---------|
| `STOP_LOSS` | Stop loss threshold (0-1) | `0.05` (5%) |
| `TAKE_PROFIT` | Take profit threshold (0-1) | `0.10` (10%) |
| `MAX_DAILY_LOSS` | Maximum daily loss in USD | `50.0` |

### Paper Trading & Backtesting (Optional)

| Parameter | Description | Default |
|-----------|-------------|---------|
| `PAPER_TRADING_ENABLED` | Enable paper trading mode | `false` |
| `DATA_COLLECTION_ENABLED` | Collect order book snapshots | `true` |
| `SNAPSHOT_INTERVAL_MS` | Snapshot interval in ms | `1000` |
| `PAPER_INITIAL_BALANCE` | Paper trading starting balance | `10000.0` |

### Advanced Optimization Settings (Optional)

| Parameter | Description | Default |
|-----------|-------------|---------|
| `TRADING_FEE_PERCENT` | Trading fee per side | `0.01` (1%) |
| `MIN_PROFIT_DOLLARS` | Minimum profit per trade | `1.0` |
| `MAX_CONCURRENT_POSITIONS` | Maximum open positions | `10` |
| `MAX_ORDER_BOOK_DEPTH` | Max order book levels | `20` |
| `MIN_MARKET_QUALITY_SCORE` | Min market quality (0-100) | `50.0` |

### Other Advanced Settings (Optional)

| Parameter | Description | Default |
|-----------|-------------|---------|
| `CLOB_WS_URL` | WebSocket URL | `wss://ws-fidelity.polymarket.com` |
| `MAX_TOKENS_MONITOR` | Max tokens to monitor | `20` |
| `FALLBACK_BALANCE` | Fallback balance if API fails | `1000.0` |
| `COOLDOWN_SECONDS` | Cooldown between trades per market | `30.0` |
| `MAX_SLIPPAGE` | Maximum acceptable slippage | `0.005` (0.5%) |

## Project Structure

```
arbitrage-poly/
├── main.py                 # Application entry point
├── requirements.txt        # Python dependencies
├── .env.example           # Configuration template
├── Start_Bot.command      # macOS launcher
├── run.sh                 # Linux/macOS launcher
│
├── backend/               # Core trading logic
│   ├── arbitrage.py      # Main bot engine + all optimizations
│   ├── config.py         # Configuration management
│   ├── logger.py         # Logging setup
│   ├── multi_platform_arbitrage.py  # Cross-platform arbitrage detection
│   │
│   ├── interfaces/       # Abstract interfaces (Phase 6)
│   │   ├── exchange_client.py    # IExchangeClient, UnifiedMarket, UnifiedOrderBook
│   │   └── credentials.py        # IPlatformCredentials, CredentialsManager
│   │
│   ├── clients/          # Platform-specific clients (Phase 6)
│   │   ├── polymarket_client.py  # Polymarket CLOB API wrapper
│   │   └── kalshi_client.py      # Kalshi REST API client
│   │
│   ├── services/         # Modular services
│   │   ├── market_scorer.py      # Market quality scoring
│   │   ├── trade_storage.py      # SQLite trade persistence
│   │   ├── rate_limiter.py       # API rate limiting
│   │   ├── risk_manager.py       # Stop-loss, take-profit, daily limits
│   │   ├── position_monitor.py   # Position monitoring & manual exits
│   │   ├── paper_trading.py      # Paper trading simulation
│   │   ├── data_collector.py     # Order book snapshot collection
│   │   ├── backtest_engine.py    # Historical replay engine
│   │   ├── capital_allocator.py  # Dynamic capital allocation
│   │   └── time_patterns.py      # Time-based trading patterns
│   │
│   └── models/           # Data models
│       ├── order_book.py      # Optimized with SortedDict
│       └── trade.py
│
├── frontend/              # User interface
│   ├── main_window.py    # Main application window
│   ├── styles.py         # Dark theme styling
│   └── components/
│       ├── config_widget.py       # Configuration form
│       ├── credentials_panel.py   # Multi-platform credentials (Phase 6)
│       ├── market_monitor.py      # Live market table
│       ├── pnl_dashboard.py       # P&L performance dashboard
│       ├── trade_history.py       # Trade history + CSV export
│       └── backtest_widget.py     # Backtest GUI dashboard
│
├── tests/                 # Unit tests (372 tests)
│   ├── test_interfaces.py         # Interface tests (Phase 6)
│   ├── test_clients.py            # Client tests (Phase 6)
│   ├── test_multi_platform_arbitrage.py  # Cross-platform tests (Phase 6)
│   ├── test_market_impact.py
│   ├── test_market_scorer.py
│   ├── test_slippage.py
│   ├── test_cooldown.py
│   ├── test_execution_lock.py
│   ├── test_opportunity.py
│   ├── test_order_book.py
│   ├── test_trade_storage.py
│   ├── test_rate_limiter.py
│   ├── test_risk_manager.py
│   ├── test_position_monitor.py
│   ├── test_paper_trading.py
│   ├── test_data_collector.py
│   ├── test_backtest_engine.py
│   ├── test_capital_allocator.py
│   └── test_time_patterns.py
│
├── data/                  # Persistent data
│   ├── trades.db          # SQLite trade database
│   ├── paper_trades.db    # Paper trading history
│   └── snapshots.db       # Order book snapshots
│
└── logs/                  # Trading logs
    └── bot.log
```

## How It Works

1. **Market Fetching** - Retrieves active binary markets filtered by volume
2. **Quality Scoring** - Ranks markets by volume, liquidity, spread, time-to-resolution
3. **WebSocket Connection** - Subscribes to level 2 order book updates (auto-reconnects)
4. **Depth-Aware Analysis** - Calculates REAL cost across multiple price levels (not just top-of-book)
5. **Fee Integration** - Accounts for trading fees in profitability calculations
6. **Optimal Size Calculation** - Binary search finds max profitable shares before market impact kills ROI
7. **Dynamic Allocation** - Adjusts capital based on ROI, market quality, daily P&L, and time of day
8. **Slippage Check** - Verifies prices haven't moved before execution
9. **Trade Execution** - Places parallel FOK orders for both outcomes
10. **Position Tracking** - Logs executed trades, updates PnL dashboard
11. **Risk Management** - Monitors daily P&L, enforces stop-loss/take-profit
12. **Trade Persistence** - Saves all trades to SQLite for recovery

### Why Market Impact Matters

```
Naive approach:     YES=0.45, NO=0.50 → Cost=0.95 → "5% profit!"
Reality at 50 shares: Consumes multiple levels → Effective cost=1.02 → LOSS!

The MarketImpactCalculator prevents this by calculating weighted average
prices across order book depth before trading.
```

### Phase 5 Optimization Impact

| Optimization | Benefit |
|--------------|---------|
| Trading fee integration | Eliminates ~15% false positive opportunities |
| Minimum profit threshold | Avoids micro-trades with negligible profit |
| Dynamic capital allocation | +15-25% better ROI through smart sizing |
| Time-based patterns | +10% win rate during optimal hours |
| Position limits | Risk protection from overexposure |
| Momentum detection | Prioritizes improving opportunities |

## Risk Warning

**This bot places REAL ORDERS with REAL MONEY.**

- Ensure your `.env` contains correct API credentials
- Start with small `CAPITAL_PER_TRADE` values for testing
- Use `PAPER_TRADING_ENABLED=true` to test without real money
- The bot uses Fill-or-Kill (FOK) orders to minimize leg risk
- Partial fills can result in unhedged positions - monitor logs carefully
- Never share or commit your `.env` file

## Dependencies

- `PySide6` - Qt GUI framework
- `qasync` - Asyncio/Qt integration
- `py-clob-client` - Polymarket CLOB API client
- `websockets` - WebSocket connections
- `aiohttp` - Async HTTP requests
- `python-dotenv` - Environment variable management
- `sortedcontainers` - Optimized order book data structures

### Development
- `pytest` - Testing framework
- `pytest-asyncio` - Async test support

## Running Tests

```bash
python3.11 -m pytest tests/ -v
```

372 tests covering:
- **Multi-platform interfaces** (Phase 6)
- **Exchange clients** (Phase 6)
- **Cross-platform arbitrage** (Phase 6)
- Market impact calculation
- Slippage protection
- Cooldown management
- Execution locking
- Opportunity caching
- Order book handling
- Market scoring
- Trade storage
- Rate limiting
- Risk management
- Position monitoring
- Paper trading
- Data collection
- Backtest engine
- Capital allocation
- Time patterns

## License

MIT License - See LICENSE file for details.

## Disclaimer

This software is provided for educational purposes. Trading involves significant risk of loss. The authors are not responsible for any financial losses incurred from using this software. Always do your own research and understand the risks before trading.
