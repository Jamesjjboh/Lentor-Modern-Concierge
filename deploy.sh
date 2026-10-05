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
    --no-cpu-throttling \
    --cpu-boost \
    --set-env-vars "ENVIRONMENT=production,WEBHOOK_URL=${SERVICE_URL},GEMINI_MODEL=${GEMINI_MODEL:-gemini-3.5-flash-lite},GCP_PROJECT_ID=${GCP_PROJECT_ID},TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN},ADMIN_TELEGRAM_ID=${ADMIN_TELEGRAM_ID},GEMINI_API_KEY=${GEMINI_API_KEY},WEBHOOK_SECRET_TOKEN=${WEBHOOK_SECRET_TOKEN:-}"

echo "✅ Cloud Run deployment complete!"
echo "🔗 Setting Telegram Webhook directly..."
WEBHOOK_SET_URL="https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook?url=${SERVICE_URL}/${TELEGRAM_BOT_TOKEN}"
if [ -n "$WEBHOOK_SECRET_TOKEN" ]; then
    WEBHOOK_SET_URL="${WEBHOOK_SET_URL}&secret_token=${WEBHOOK_SECRET_TOKEN}"
fi
curl -s "$WEBHOOK_SET_URL" | grep '"ok":true' && echo " ✓ Webhook confirmed active!" || echo " ⚠️ Check webhook status."

echo "🎉 Lentor Modern Digital Concierge is live 24/7 on Google Cloud Run!"
