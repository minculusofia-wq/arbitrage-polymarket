#!/bin/bash
cd "$(dirname "$0")"

echo "================================================"
echo "   POLYMARKET ARBITRAGE BOT - Premium Edition   "
echo "================================================"
echo ""
echo "📂 Working Directory: $(pwd)"

# Check if venv exists, create if not
if [ ! -d "venv" ]; then
    echo "⚙️  Creating virtual environment..."
    /usr/local/bin/python3.11 -m venv venv
    if [ $? -ne 0 ]; then
        echo "❌ ERROR: Failed to create virtual environment"
        echo "   Make sure Python 3.11 is installed"
        read -p "Press [Enter] to close..."
        exit 1
    fi

    # Install dependencies
    echo "📦 Installing dependencies (first time setup)..."
    source venv/bin/activate
    pip install --upgrade pip -q
    pip install -r requirements.txt
else
    echo "✅ Virtual environment found"
    source venv/bin/activate
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "⚠️  No .env file found. Creating empty one..."
    touch .env
    echo "   You can configure credentials in the application."
fi

# Launch the bot
echo ""
echo "🚀 Launching Application..."
echo ""
python main.py

# Exit message
echo ""
echo "❌ Bot process stopped."
read -p "Press [Enter] to close this window..."
