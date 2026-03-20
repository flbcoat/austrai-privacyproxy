#!/usr/bin/env bash
set -e

# ──────────────────────────────────────────────
# AUSTR.AI PrivacyProxy — Deploy Script
# Run from local Mac, deploys to Hetzner VPS
# ──────────────────────────────────────────────

SERVER="178.104.37.171"
PORT="2222"
USER="florian"
REMOTE_DIR="/var/www/austrai"
SSH_OPTS="-p ${PORT}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()    { echo -e "${BLUE}[INFO]${NC}  $1"; }
success() { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  AUSTR.AI PrivacyProxy — Deployment${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# ── Step 1: Build frontend ───────────────────
info "Step 1/5: Building frontend..."
cd "${PROJECT_DIR}/frontend"
npm run build || error "Frontend build failed"
success "Frontend built successfully"

# ── Step 2: Deploy frontend dist ─────────────
info "Step 2/5: Uploading frontend to server..."
rsync -avz --delete \
    -e "ssh ${SSH_OPTS}" \
    "${PROJECT_DIR}/frontend/dist/" \
    "${USER}@${SERVER}:${REMOTE_DIR}/dist/" \
    || error "Frontend upload failed"
success "Frontend deployed to ${REMOTE_DIR}/dist/"

# ── Step 3: Deploy backend + docker-compose ──
info "Step 3/5: Uploading backend to server..."
rsync -avz --delete \
    --exclude '__pycache__' \
    --exclude '.venv' \
    --exclude '*.pyc' \
    -e "ssh ${SSH_OPTS}" \
    "${PROJECT_DIR}/backend/" \
    "${USER}@${SERVER}:${REMOTE_DIR}/backend/" \
    || error "Backend upload failed"

rsync -avz \
    -e "ssh ${SSH_OPTS}" \
    "${PROJECT_DIR}/docker-compose.yml" \
    "${USER}@${SERVER}:${REMOTE_DIR}/docker-compose.yml" \
    || error "docker-compose.yml upload failed"
success "Backend and docker-compose.yml deployed"

# ── Step 4: Build & start containers ─────────
info "Step 4/5: Building and starting Docker containers..."
ssh ${SSH_OPTS} "${USER}@${SERVER}" \
    "cd ${REMOTE_DIR} && docker compose up -d --build" \
    || error "Docker build/start failed"
success "Docker containers are running"

# ── Step 5: Health check ─────────────────────
info "Step 5/5: Checking health endpoint..."
sleep 5
HEALTH=$(ssh ${SSH_OPTS} "${USER}@${SERVER}" \
    "curl -sf http://localhost:8000/api/health" 2>&1) \
    || error "Health check failed — backend may not be ready"
success "Health check passed: ${HEALTH}"

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Deployment complete!${NC}"
echo -e "${GREEN}  https://austr.ai${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
