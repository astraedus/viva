#!/usr/bin/env bash
# Viva — Automated Cloud Run Deployment (IaC)
# Infrastructure-as-Code for the Gemini Live Agent Challenge
#
# Prerequisites:
#   - gcloud CLI authenticated
#   - GOOGLE_API_KEY set in environment or Secret Manager
#
# Usage: ./deploy.sh [PROJECT_ID]

set -euo pipefail

PROJECT_ID="${1:-${GOOGLE_CLOUD_PROJECT:-gemini-project}}"
REGION="us-central1"
SERVICE_NAME="viva-api"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "=== Viva Cloud Run Deployment ==="
echo "Project: ${PROJECT_ID}"
echo "Region:  ${REGION}"
echo "Service: ${SERVICE_NAME}"
echo ""

# Set project
gcloud config set project "${PROJECT_ID}"

# Enable required APIs
echo ">>> Enabling required APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  generativelanguage.googleapis.com \
  --quiet

# Create secret for API key if not exists
if ! gcloud secrets describe google-api-key --quiet 2>/dev/null; then
  echo ">>> Creating secret 'google-api-key'..."
  echo -n "${GOOGLE_API_KEY}" | gcloud secrets create google-api-key \
    --data-file=- \
    --replication-policy="automatic"
fi

# Build container image
echo ">>> Building container image..."
gcloud builds submit ./backend \
  --tag "${IMAGE}" \
  --quiet

# Deploy to Cloud Run
echo ">>> Deploying to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE}" \
  --platform managed \
  --region "${REGION}" \
  --allow-unauthenticated \
  --set-secrets="GOOGLE_API_KEY=google-api-key:latest" \
  --set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=FALSE" \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 3 \
  --timeout 300 \
  --quiet

# Get service URL
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region "${REGION}" \
  --format="value(status.url)")

echo ""
echo "=== Deployment Complete ==="
echo "Backend URL: ${SERVICE_URL}"
echo "Health check: ${SERVICE_URL}/health"
echo ""

# Deploy frontend to Vercel (if vercel CLI available)
if command -v npx &>/dev/null && [ -d "./frontend" ]; then
  echo ">>> Deploying frontend to Vercel..."
  cd frontend
  NEXT_PUBLIC_API_URL="${SERVICE_URL}" \
  BACKEND_URL="${SERVICE_URL}" \
  npx vercel --yes --prod \
    --token "${VERCEL_TOKEN:-}" \
    --scope astraedus-projects \
    --build-env NEXT_PUBLIC_API_URL="${SERVICE_URL}" \
    --build-env BACKEND_URL="${SERVICE_URL}" \
    2>/dev/null || echo "Vercel deploy skipped (no token or CLI)"
  cd ..
fi

echo "Done."
