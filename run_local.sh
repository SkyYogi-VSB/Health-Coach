#!/bin/bash

# run_local.sh
# A convenience script to run the AI Health Coach continuously in the background on your local machine.

echo "========================================="
echo "🏋️‍♀️ Starting AI Health Coach Locally..."
echo "========================================="

# 1. Provide absolute paths assuming script is run from project root
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# 2. Check for .env file
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found."
    echo "Please copy .env.example to .env and fill in your API keys before running."
    exit 1
fi

# 3. Check for Virtual Environment
if [ ! -d "venv" ]; then
    echo "⚠️ Virtual environment not found. Creating one now..."
    python3 -m venv venv
    echo "📦 Installing requirements..."
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# 4. Stop any existing bot instances
echo "🛑 Stopping any existing bot processes..."
pkill -f "bot.py" || true
sleep 2

# 5. Start the bot via nohup so it survives terminal closing
echo "🚀 Igniting the AI Brain..."
nohup python bot.py > bot_local.log 2>&1 &
BOT_PID=$!

echo "========================================="
echo "✅ Bot is now running in the background! (PID: $BOT_PID)"
echo "📜 Logs are being written to bot_local.log"
echo "To view live logs, run: tail -f bot_local.log"
echo "To stop the bot, run: pkill -f bot.py"
echo "========================================="
