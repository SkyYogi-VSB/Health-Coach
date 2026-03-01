# Telegram AI Health Coach Bot

A powerful, Python-based Telegram bot that acts as a personal health, nutrition, and fitness coach. It dynamically supports **both NVIDIA NIMs (Nemotron/Llama Vision)** and **Google Gemini (Flash/Pro)** via a simple configuration toggle to automatically track your meals, workouts, and provide personalized advice in a friendly, conversational manner. No more complicated apps—just send a message, voice note, or photo!

## 🚀 Features
- **Multi-Model AI Coaching**: Powered by your choice of NVIDIA NIMs (Nemotron, Llama Vision, Whisper) or Google's Gemini models for fast, intelligent, and context-aware responses!
- **Multi-Modal Understanding**: Send text or photos! Snap a picture of your meal, and the bot will estimate calories and macros.
- **Long-term Memory**: Remembers your fitness goals, past conversations, and preferences using SQLite.
- **Proactive Engagement**: Automatically sends daily reminders and weekly summary reports if you have pending goals or missed workouts.
- **GCP Automated Deployment**: Comes with a built-in bash script for completely automated deployment to Google Cloud Platform.

## 📂 Project Structure
```text
health-coach/
├── .env.example           # Template for environment variables
├── .gitignore             # Ignored files for git
├── ai_coach.py            # AI integration (Dual routing for Gemini and NVIDIA NIMs)
├── bot.py                 # Core telegram bot logic and handlers
├── deploy.sh              # Automated script for 24/7 Google Cloud deployment
├── run_local.sh           # Automated script for continuous local execution
├── health_coach.service   # Systemd service configuration
├── memory.py              # SQLite database manager
└── requirements.txt       # Python dependencies
```

## 🛠 Installation & Deployment
This bot can be run either locally on your own machine (Mac, Windows, Linux, Raspberry Pi) or deployed to the cloud for 24/7 free uptime.

### 1. Prerequisites (For Both Options)
- A Telegram Bot Token (from [@BotFather](https://t.me/botfather) on Telegram)
- An **NVIDIA API Key** (from [NVIDIA API Catalog](https://build.nvidia.com/)) OR a **Gemini API Key** (from [Google AI Studio](https://aistudio.google.com/))
- Your Telegram User ID (to restrict access so only *you* can use the bot)

### Option A: Run Locally (Desktop / Home Server)
Want to run the bot on your own laptop or Raspberry Pi? We included a handy execution script.

1. Clone the repository and navigate to the directory:
   ```bash
   git clone https://github.com/yourusername/health-coach.git
   cd health-coach
   ```
2. Create your environment file:
   ```bash
   cp .env.example .env
   ```
3. Open `.env` and fill in your actual credentials.
   ```env
   TELEGRAM_BOT_TOKEN="your-telegram-bot-token"
   AI_PROVIDER="nvidia"  # Options: 'nvidia' or 'gemini'
   NVIDIA_API_KEY="your-nvidia-api-key"
   GEMINI_API_KEY="your-gemini-api-key"
   ALLOWED_TELEGRAM_USER_IDS="[Your Telegram User ID]" 
   ```
4. Start the bot using our automated bash script! This will create the virtual environment, install dependencies, and run the bot in the background.
   ```bash
   ./run_local.sh
   ```
*(To stop the background bot safely, run `pkill -f bot.py`)*

---

### Option B: Deploy to Cloud (24/7 Free GCP)
Want the bot to run 24/7 without keeping your computer on? We have included an automated deployment script `deploy.sh` that spins up a completely free *e2-micro* VM on Google Cloud Platform, installs all dependencies, configures the `.env`, and sets it up as a background `systemd` service that auto-restarts on reboot!

**Additional Prerequisite:**
- [gcloud CLI](https://cloud.google.com/sdk/docs/install) installed and authenticated (`gcloud auth login`).

**Deployment Steps:**
1. Open `.env` locally and ensure your API keys and User ID are permanently set (the script will securely copy this to the cloud).
2. Open `deploy.sh` and update `PROJECT_ID="<your-gcp-project-id>"` on line 8 with your actual Google Cloud project ID.
3. Run the automated deployment script:
   ```bash
   chmod +x deploy.sh
   ./deploy.sh
   ```
4. Grab a coffee. The script will automatically configure the firewall, SSH into the new VM, clone this secure setup, and start the systemd service!

*Note: The deployment script dynamically replaces placeholder usernames in `health_coach.service` with your actual GCP VM username during the setup phase.*

## 🔒 Security Note
This bot is designed for personal use. The `ALLOWED_TELEGRAM_USER_IDS` environment variable ensures that only authorized users can chat with the bot. Requests from any other Telegram IDs will be ignored.
