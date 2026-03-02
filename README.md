# Telegram AI Health Coach Bot

A powerful, Python-based Telegram bot that acts as a personal health, nutrition, and fitness coach. For version 2, we have streamlined the architecture to use **Google Gemini (Flash/Pro)** as a unified, all-in-one multimodal backend to seamlessly process text, meal photos, and voice notes. *(Note: For users who prefer the original dual-routing approach, **NVIDIA NIMs** support remains heavily featured and available in the v1 codebase!)*

## 🚀 Features (v2)
- **Unified Multimodal Engine**: Powered by Google Gemini to intelligently process text chats, transcribe audio voice notes, and visually estimate calories from your meal photos in one seamless flow.
- **NLP Onboarding & Timezone Support**: Just tell the bot where you live and when you eat (e.g., "I'm in NY and eat lunch at 1pm"). It uses NLP to automatically configure your internal timezone and schedule.
- **Proactive Engagement**: Automatically sends daily breakfast plans, meal check-ins at your typical eating times, and weekly summary reports if you have pending goals or missed workouts.
- **Nutritional Pushback**: The AI actively protests and keeps you accountable if you try to log a meal that breaks your daily caloric or protein goals.
- **Long-term Memory**: Remembers your fitness goals, past conversations, and preferences using SQLite.
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
- A **Gemini API Key** (from [Google AI Studio](https://aistudio.google.com/))
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
   GEMINI_API_KEY="your-gemini-api-key"
   ALLOWED_TELEGRAM_USER_IDS="[Your Telegram User ID]" 
   ```
4. Start the bot using our automated bash script! This will create the virtual environment, install dependencies, and run the bot in the background.
   ```bash
   ./run_local.sh
   ```
*(To stop the background bot safely, run `pkill -f bot.py`)*

### Option A.2: Manual Systemd Setup (Linux / Cloud VM)
If you pulled the repository manually into a Linux server or cloud VM and want to run it reliably as a system background service, we have included an automated script to handle the systemd service creation.

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
4. Run the automated background service installer script! This script will automatically create the virtual environment, install dependencies, inject your username into the systemd service paths, enable the service, and start it.
   ```bash
   chmod +x install_service.sh
   ./install_service.sh
   ```

*(After running, use `sudo systemctl status health_coach.service` to check its status or `sudo journalctl -u health_coach.service -f` to see the live logs.)*

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

### Option C: Automated CI/CD with GitHub Actions (Optional)
If you want to automate deployments so that any code pushed to the `main` branch automatically updates your GCP VM, you can use the included GitHub Actions workflow (`.github/workflows/deploy.yml`).

**Prerequisites:**
- You must have already completed **Option B** to initially provision the VM and set up your `.env`.
- Ensure your repository is cloned on the GCP VM in the `~/health-coach` directory (if deployed via `deploy.sh`, you may need to SSH into the VM, backup your `.env` and `health_coach.db`, and run `git clone` there).

**Setup Steps:**
1. Go to your GitHub repository -> **Settings** -> **Secrets and variables** -> **Actions** -> **New repository secret**.
2. Add the following three secrets:
   - `GCP_VM_IP`: The external IP address of your GCP cloud instance.
   - `GCP_USERNAME`: The username used for SSH access on the VM.
   - `GCP_SSH_PRIVATE_KEY`: An SSH private key authorized to connect to your VM.
3. Once configured, every push to the `main` branch will seamlessly trigger a Git Pull and service restart on your VM without overwriting your sensitive files!

## 🔒 Security Note
This bot is designed for personal use. The `ALLOWED_TELEGRAM_USER_IDS` environment variable ensures that only authorized users can chat with the bot. Requests from any other Telegram IDs will be ignored.
