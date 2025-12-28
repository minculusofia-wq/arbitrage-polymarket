# Polymarket Arbitrage Bot

A professional-grade arbitrage trading bot for Polymarket prediction markets. Automatically detects and executes profitable opportunities when YES + NO prices fall below 1.0.

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![PySide6](https://img.shields.io/badge/GUI-PySide6-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## Features

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
- **Auto-Reconnection** - WebSocket reconnects with exponential backoff (5s → 60s)
- **Market Quality Scoring** - Prioritizes markets by volume, liquidity, spread, time

### Risk Management (Phase 2)
- **Stop-Loss** - Automatic position exit at configurable loss threshold
- **Take-Profit** - Lock in gains at configurable profit threshold
- **Daily Loss Limit** - Halts trading when daily losses exceed limit
- **Trade Persistence** - SQLite database saves all trades (survives restarts)
- **API Rate Limiter** - Prevents API bans with sliding window throttling

### User Interface
- **PnL Dashboard** - Real-time balance, daily/total P&L, win rate, ROI
- **Trade History** - Historical trades table with CSV export
- **Live Market Feed** - Shows arbitrage opportunities in real-time
- **System Logs** - Real-time logs in console
- **Modern Dark UI** - Professional Qt-based interface

## Screenshots

The application features a modern dark-themed interface with:
- **Performance Dashboard** - Balance, P&L (today/total), win rate, avg ROI, trade count
- **Tabbed View** - Live Market Feed + Trade History with CSV export
- **System Logs** - Real-time logging
- **Configuration Panel** - API credentials and trading parameters

## Installation

### Requirements

- Python 3.11 (required for PySide6 compatibility)
- macOS / Linux / Windows

### Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/minculusofia-wq/arbitrage-polymarket.git
   cd arbitrage-polymarket
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

| Parameter | Description | Example |
|-----------|-------------|---------|
| `POLY_API_KEY` | Polymarket API Key | `your_api_key` |
| `POLY_API_SECRET` | Polymarket API Secret | `your_secret` |
| `POLY_API_PASSPHRASE` | Polymarket Passphrase | `your_passphrase` |
| `PRIVATE_KEY` | Wallet private key for signing | `0x...` |
| `CAPITAL_PER_TRADE` | USDC amount per trade | `10.0` |
| `MIN_PROFIT_MARGIN` | Minimum profit margin (0-1) | `0.02` (2%) |
| `MIN_MARKET_VOLUME` | Minimum market volume filter | `5000` |

### Risk Management (Optional)

| Parameter | Description | Example |
|-----------|-------------|---------|
| `STOP_LOSS` | Stop loss threshold (0-1) | `0.05` (5%) |
| `TAKE_PROFIT` | Take profit threshold (0-1) | `0.10` (10%) |
| `MAX_DAILY_LOSS` | Maximum daily loss in USD | `50.0` |

### Advanced Settings (Optional)

| Parameter | Description | Default |
|-----------|-------------|---------|
| `CLOB_WS_URL` | WebSocket URL | `wss://ws-fidelity.polymarket.com` |
| `MAX_TOKENS_MONITOR` | Max tokens to monitor | `20` |
| `FALLBACK_BALANCE` | Fallback balance if API fails | `1000.0` |

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
│   ├── arbitrage.py      # Main bot engine + optimizations
│   │                     # (MarketImpactCalculator, CooldownManager,
│   │                     #  ExecutionLock, OpportunityManager)
│   ├── config.py         # Configuration management
│   ├── logger.py         # Logging setup
│   ├── services/         # Modular services
│   │   ├── market_service.py
│   │   ├── websocket_service.py
│   │   ├── order_service.py
│   │   ├── market_scorer.py   # Market quality scoring
│   │   ├── trade_storage.py   # SQLite trade persistence
│   │   ├── rate_limiter.py    # API rate limiting
│   │   └── risk_manager.py    # Stop-loss, take-profit, daily limits
│   └── models/           # Data models
│       ├── order_book.py      # Optimized with SortedDict
│       └── trade.py
│
├── frontend/              # User interface
│   ├── main_window.py    # Main application window
│   ├── styles.py         # Dark theme styling
│   └── components/
│       ├── config_widget.py    # Configuration form
│       ├── market_monitor.py   # Live market table
│       ├── pnl_dashboard.py    # P&L performance dashboard
│       └── trade_history.py    # Trade history + CSV export
│
├── tests/                 # Unit tests (155 tests)
│   ├── test_market_impact.py
│   ├── test_market_scorer.py
│   ├── test_slippage.py
│   ├── test_cooldown.py
│   ├── test_execution_lock.py
│   ├── test_opportunity.py
│   ├── test_order_book.py
│   ├── test_trade_storage.py  # Trade persistence tests
│   ├── test_rate_limiter.py   # Rate limiting tests
│   └── test_risk_manager.py   # Risk management tests
│
├── data/                  # Persistent data
│   └── trades.db          # SQLite trade database
│
└── logs/                  # Trading logs
    └── bot.log
```

## How It Works

1. **Market Fetching** - Retrieves active binary markets filtered by volume
2. **Quality Scoring** - Ranks markets by volume, liquidity, spread, time-to-resolution
3. **WebSocket Connection** - Subscribes to level 2 order book updates (auto-reconnects)
4. **Depth-Aware Analysis** - Calculates REAL cost across multiple price levels (not just top-of-book)
5. **Optimal Size Calculation** - Binary search finds max profitable shares before market impact kills ROI
6. **Slippage Check** - Verifies prices haven't moved before execution
7. **Trade Execution** - Places parallel FOK orders for both outcomes
8. **Position Tracking** - Logs executed trades, updates PnL dashboard
9. **Risk Management** - Monitors daily P&L, enforces stop-loss/take-profit
10. **Trade Persistence** - Saves all trades to SQLite for recovery

### Why Market Impact Matters

```
Naive approach:     YES=0.45, NO=0.50 → Cost=0.95 → "5% profit!"
Reality at 50 shares: Consumes multiple levels → Effective cost=1.02 → LOSS!

The MarketImpactCalculator prevents this by calculating weighted average
prices across order book depth before trading.
```

## Risk Warning

**This bot places REAL ORDERS with REAL MONEY.**

- Ensure your `.env` contains correct API credentials
- Start with small `CAPITAL_PER_TRADE` values for testing
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

155 tests covering market impact, slippage, cooldown, execution lock, opportunity cache, order book, market scoring, trade storage, rate limiting, and risk management.

## License

MIT License - See LICENSE file for details.

## Disclaimer

This software is provided for educational purposes. Trading involves significant risk of loss. The authors are not responsible for any financial losses incurred from using this software. Always do your own research and understand the risks before trading.
