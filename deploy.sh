#!/bin/bash
set -e

# Configuration
SERVICE_NAME="lentor-concierge"
REGION="asia-southeast1" # Singapore region

echo "🚀 Deploying ${SERVICE_NAME} to Google Cloud Run in ${REGION}..."

# Ensure gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ Error: gcloud CLI is not installed or not in PATH."
    exit 1
fi

# Load variables from .env if present
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

if [ -z "$GCP_PROJECT_ID" ]; then
    echo "❌ Error: GCP_PROJECT_ID is not set in .env"
    exit 1
fi

gcloud config set project "$GCP_PROJECT_ID"

# Build and deploy directly to Cloud Run
gcloud run deploy "$SERVICE_NAME" \
    --source . \
    --region "$REGION" \
    --platform managed \
    --allow-unauthenticated \
    --min-instances 0 \
    --max-instances 3 \
    --memory 512Mi \
    --cpu 1 \
    --set-env-vars "ENVIRONMENT=production,GEMINI_MODEL=gemini-3.8-flash,GCP_PROJECT_ID=${GCP_PROJECT_ID},TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN},ADMIN_TELEGRAM_ID=${ADMIN_TELEGRAM_ID},GEMINI_API_KEY=${GEMINI_API_KEY}"

echo "✅ Deployment complete! Check the Cloud Run service URL in the output above."
