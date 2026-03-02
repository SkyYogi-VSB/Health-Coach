#!/bin/bash

# Exit on error
set -e

echo "Setting up Telegram AI Health Coach as a background service..."

# Ensure we are in the script's directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# Check for .env file
if [ ! -f .env ]; then
    echo "Error: .env file not found. Please create one (e.g., cp .env.example .env) and fill in your credentials before installing."
    exit 1
fi

# 1. Setup virtual environment and dependencies
echo "Creating virtual environment and installing dependencies..."
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Configure and install systemd service
echo "Configuring systemd service for user $USER..."

# Create a temporary service file with correct paths
cp health_coach.service /tmp/health_coach.service.tmp

# Replace User and Group
sed -i "s/User=<your-username>/User=$USER/g" /tmp/health_coach.service.tmp
sed -i "s/Group=<your-username>/Group=$USER/g" /tmp/health_coach.service.tmp

# Replace Paths to rely on the actual directory instead of assumptions
sed -i "s|WorkingDirectory=/home/<your-username>/health-coach|WorkingDirectory=$DIR|g" /tmp/health_coach.service.tmp
sed -i "s|ExecStart=/home/<your-username>/health-coach/venv/bin/python3 /home/<your-username>/health-coach/bot.py|ExecStart=$DIR/venv/bin/python3 $DIR/bot.py|g" /tmp/health_coach.service.tmp
sed -i "s|Environment=\"PATH=/home/<your-username>/health-coach/venv/bin:\$PATH\"|Environment=\"PATH=$DIR/venv/bin:\$PATH\"|g" /tmp/health_coach.service.tmp

# Move the file to systemd directory
sudo mv /tmp/health_coach.service.tmp /etc/systemd/system/health_coach.service

# 3. Enable and start the service
echo "Reloading systemd, enabling and starting the service..."
sudo systemctl daemon-reload
sudo systemctl enable health_coach.service
sudo systemctl restart health_coach.service

echo ""
echo "========================================================="
echo "✅ Done! The Health Coach bot is now running in the background."
echo "========================================================="
echo "Check its status with:   sudo systemctl status health_coach.service"
echo "View the live logs with: sudo journalctl -u health_coach.service -f"
echo "Stop the service with:   sudo systemctl stop health_coach.service"
echo "========================================================="
