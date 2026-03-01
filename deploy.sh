#!/bin/bash
set -e

# ==============================================================================
# Telegram Health Coach - GCP Automated Deployment Script
# ==============================================================================

PROJECT_ID="<your-gcp-project-id>" # CHANGE THIS TO YOUR GCP PROJECT ID
ZONE="us-central1-a"
INSTANCE_NAME="health-coach-vm"
MACHINE_TYPE="e2-micro"

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ Error: gcloud CLI is not installed."
    echo "Please install it first: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

echo "🚀 Starting deployment to GCP..."

# 1. Check if VM exists or Create the VM instance
echo "📦 Checking VM instance ($INSTANCE_NAME)..."
if gcloud compute instances describe $INSTANCE_NAME --project=$PROJECT_ID --zone=$ZONE &> /dev/null; then
    echo "✅ VM exists. Stopping the remote bot service before update..."
    gcloud compute ssh $INSTANCE_NAME --project=$PROJECT_ID --zone=$ZONE --command="sudo systemctl stop health_coach.service || true"
else
    echo "📦 Creating VM instance ($INSTANCE_NAME)..."
    gcloud compute instances create $INSTANCE_NAME \
        --project=$PROJECT_ID \
        --zone=$ZONE \
        --machine-type=$MACHINE_TYPE \
        --image-family=debian-11 \
        --image-project=debian-cloud \
        --boot-disk-size=30GB \
        --boot-disk-type=pd-standard \
        --tags=http-server,https-server \
        --quiet
        
    echo "⏳ Waiting for VM to initialize..."
    sleep 15
    
    echo "🛠️ Installing Python and dependencies on the VM..."
    gcloud compute ssh $INSTANCE_NAME --project=$PROJECT_ID --zone=$ZONE --command="
        sudo apt-get update && \
        sudo apt-get install -y python3 python3-pip python3-venv && \
        mkdir -p ~/health-coach
    "
fi

# 3. Copy application files to the VM (We skip health_coach.db to avoid overwriting production data)
echo "📂 Uploading bot files to the VM (excluding database)..."
gcloud compute scp --recurse \
    bot.py ai_coach.py memory.py requirements.txt .env health_coach.service \
    $INSTANCE_NAME:~/health-coach \
    --project=$PROJECT_ID \
    --zone=$ZONE

# 4. Finalize setup and restart the service on the VM
echo "⚙️ Configuring the virtual environment and systemd service..."
gcloud compute ssh $INSTANCE_NAME --project=$PROJECT_ID --zone=$ZONE --command="
    cd ~/health-coach && \
    chmod 600 .env && \
    python3 -m venv venv && \
    source venv/bin/activate && \
    pip install -r requirements.txt && \
    sudo cp health_coach.service /etc/systemd/system/ && \
    sudo sed -i \"s/User=<your-username>/User=\$USER/g\" /etc/systemd/system/health_coach.service && \
    sudo sed -i \"s/Group=<your-username>/Group=\$USER/g\" /etc/systemd/system/health_coach.service && \
    sudo sed -i \"s|/home/<your-username>/|/home/\$USER/|g\" /etc/systemd/system/health_coach.service && \
    sudo systemctl daemon-reload && \
    sudo systemctl enable health_coach.service && \
    sudo systemctl restart health_coach.service
"

echo "✅ Deployment successful! Your bot v2 logic should now be running securely."
echo "To check the logs, run: gcloud compute ssh $INSTANCE_NAME --project=$PROJECT_ID --zone=$ZONE --command='sudo journalctl -u health_coach.service -f'"
