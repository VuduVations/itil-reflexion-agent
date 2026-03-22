#!/bin/bash
set -e

# Configuration — set these for your GCP project
PROJECT_ID="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID environment variable}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="itil-reflexion-agent"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "Building Docker image..."
docker build -t ${IMAGE_NAME} .

echo "Pushing to Container Registry..."
docker push ${IMAGE_NAME}

echo "Deploying to Cloud Run..."
gcloud run deploy ${SERVICE_NAME} \
    --image ${IMAGE_NAME} \
    --platform managed \
    --region ${REGION} \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --timeout 300 \
    --set-env-vars "ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}" \
    --set-env-vars "LLM_MODEL=${LLM_MODEL:-claude-sonnet-4-20250514}" \
    --set-env-vars "MAX_ITERATIONS=${MAX_ITERATIONS:-3}" \
    --set-env-vars "SCORE_THRESHOLD=${SCORE_THRESHOLD:-90}"

# Get service URL
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} \
    --platform managed \
    --region ${REGION} \
    --format 'value(status.url)')

echo ""
echo "Deployed successfully!"
echo "Service URL: ${SERVICE_URL}"
echo "Health check: ${SERVICE_URL}/api/health"
echo "Run reflexion: curl -X POST ${SERVICE_URL}/api/run-reflexion -H 'Content-Type: application/json' -d '{\"scenario_id\": \"db-migration\"}'"
