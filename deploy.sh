#!/bin/bash
set -e

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

SERVICE_URL="https://${SERVICE_NAME}-523250497459.${REGION}.run.app"
echo "🌐 Cloud Run Service URL target: ${SERVICE_URL}"

# Build container and deploy to Cloud Run with Webhook mode enabled
echo "📦 Building container and deploying to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
    --source . \
    --region "$REGION" \
    --platform managed \
    --allow-unauthenticated \
    --port 8080 \
    --min-instances 1 \
    --max-instances 2 \
    --memory 512Mi \
    --cpu 1 \
    --set-env-vars "ENVIRONMENT=production,WEBHOOK_URL=${SERVICE_URL},GEMINI_MODEL=${GEMINI_MODEL:-gemini-3.8-flash},GCP_PROJECT_ID=${GCP_PROJECT_ID},TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN},ADMIN_TELEGRAM_ID=${ADMIN_TELEGRAM_ID},GEMINI_API_KEY=${GEMINI_API_KEY}"


echo "✅ Cloud Run deployment complete!"
echo "🔗 Setting Telegram Webhook directly..."
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook?url=${SERVICE_URL}/${TELEGRAM_BOT_TOKEN}" | grep '"ok":true' && echo " ✓ Webhook confirmed active!" || echo " ⚠️ Check webhook status."

echo "🎉 Lentor Modern Digital Concierge is live 24/7 on Google Cloud Run!"
