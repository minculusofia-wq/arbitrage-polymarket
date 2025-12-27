# Polymarket Arbitrage Bot

A professional-grade arbitrage trading bot for Polymarket prediction markets. Automatically detects and executes profitable opportunities when YES + NO prices fall below 1.0.

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![PySide6](https://img.shields.io/badge/GUI-PySide6-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## Features

- **Real-time Market Monitoring** - WebSocket connection to Polymarket order books
- **Automatic Arbitrage Detection** - Finds opportunities where YES + NO < 1.0
- **Parallel Order Execution** - Simultaneous BUY orders for both legs
- **Fill-or-Kill Orders** - Minimizes partial fill risk
- **Modern Dark UI** - Professional Qt-based interface
- **Live Logging** - Real-time logs in console and file
- **Configurable Parameters** - Capital, margin, volume thresholds

## Screenshots

The application features a modern dark-themed interface with:
- Live market feed showing arbitrage opportunities
- Real-time system logs
- Configuration panel for API credentials and trading parameters

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
│   ├── arbitrage.py      # Main bot engine
│   ├── config.py         # Configuration management
│   ├── logger.py         # Logging setup
│   ├── services/         # Modular services
│   │   ├── market_service.py
│   │   ├── websocket_service.py
│   │   └── order_service.py
│   └── models/           # Data models
│       ├── order_book.py
│       └── trade.py
│
├── frontend/              # User interface
│   ├── main_window.py    # Main application window
│   ├── styles.py         # Dark theme styling
│   └── components/
│       ├── config_widget.py    # Configuration form
│       └── market_monitor.py   # Live market table
│
└── logs/                  # Trading logs
    └── bot.log
```

## How It Works

1. **Market Fetching** - Retrieves active binary markets filtered by volume
2. **WebSocket Connection** - Subscribes to level 2 order book updates
3. **Price Monitoring** - Tracks best ask prices for YES and NO tokens
4. **Arbitrage Detection** - Triggers when `YES_price + NO_price < 1.0 - margin`
5. **Trade Execution** - Places parallel FOK orders for both outcomes
6. **Position Tracking** - Logs executed trades and monitors positions

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

## License

MIT License - See LICENSE file for details.

## Disclaimer

This software is provided for educational purposes. Trading involves significant risk of loss. The authors are not responsible for any financial losses incurred from using this software. Always do your own research and understand the risks before trading.
