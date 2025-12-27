#!/bin/bash

# Polymarket Arbitrage Bot Launcher

cd "$(dirname "$0")"

echo "================================================"
echo "   POLYMARKET ARBITRAGE BOT - Premium Edition   "
echo "================================================"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "❌ ERROR: Virtual environment not found!"
    echo "   Please run Start_Bot.command first, or create it manually:"
    echo "   /usr/local/bin/python3.11 -m venv venv"
    echo "   source venv/bin/activate"
    echo "   pip install -r requirements.txt"
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  No .env file found. Creating empty one..."
    touch .env
fi

# Run the bot
echo "🚀 Launching Bot Interface..."
python main.py
