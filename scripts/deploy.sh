#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────────
# deploy.sh — Build and deploy the IR RAG app on the VM.
#
# Usage:
#   chmod +x scripts/deploy.sh
#   ./scripts/deploy.sh
#
# Prerequisites on the VM:
#   - Docker + docker compose v2
#   - .env file in the repo root (copy from env.example and edit)
#   - Qdrant running on the host at QDRANT_URL (default port 6333)
#   - Ollama running on the host at OLLAMA_BASE_URL (default port 11434)
#   - Required Ollama models pulled:
#       ollama pull nomic-embed-text
#       ollama pull llama3.2
# ────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

# ── Helpers ──────────────────────────────────────────────────────────
info()  { echo -e "\033[1;34m[INFO]\033[0m  $*"; }
ok()    { echo -e "\033[1;32m[OK]\033[0m    $*"; }
warn()  { echo -e "\033[1;33m[WARN]\033[0m  $*"; }
error() { echo -e "\033[1;31m[ERROR]\033[0m $*" >&2; exit 1; }

# ── Pre-flight checks ─────────────────────────────────────────────────
command -v docker    &>/dev/null || error "Docker is not installed."
docker compose version &>/dev/null || error "docker compose v2 is not available."

[ -f .env ] || error ".env file not found. Copy env.example to .env and configure it."

# Source .env for validation
set -o allexport
# shellcheck disable=SC1091
source .env
set +o allexport

[ -z "${JWT_SECRET:-}" ] && warn "JWT_SECRET is not set in .env — using default is insecure for production."

info "Repo : $REPO_DIR"
info "Qdrant URL  : ${QDRANT_URL:-http://172.17.0.1:6333}"
info "Ollama URL  : ${OLLAMA_BASE_URL:-http://172.17.0.1:11434}"
info "API port    : ${API_PORT:-8000}"

# ── Build & start ─────────────────────────────────────────────────────
info "Building Docker image …"
docker compose build

info "Starting services (detached) …"
docker compose up -d

# ── Wait for health ───────────────────────────────────────────────────
info "Waiting for API to be healthy …"
MAX_WAIT=60
ELAPSED=0
until docker compose ps api | grep -q "healthy" 2>/dev/null || [ $ELAPSED -ge $MAX_WAIT ]; do
  sleep 3
  ELAPSED=$((ELAPSED + 3))
  echo -n "."
done
echo ""

if [ $ELAPSED -ge $MAX_WAIT ]; then
  warn "API health check timed out — check logs: docker compose logs api"
else
  ok "API is healthy."
fi

# ── Volume info ───────────────────────────────────────────────────────
ok "SQLite chat database is persisted in Docker volume: ir_rag_sqlite_data"
echo "   To inspect: docker volume inspect ir_rag_sqlite_data"
echo "   To backup:  docker run --rm -v ir_rag_sqlite_data:/data -v \$(pwd):/out alpine tar czf /out/ir_rag_backup_\$(date +%Y%m%d).tar.gz /data"

# ── URLs ──────────────────────────────────────────────────────────────
PORT="${API_PORT:-8000}"
echo ""
ok "Deployment complete!"
echo "   App URL  : http://$(hostname -I | awk '{print $1}'):${PORT}"
echo "   API docs : http://$(hostname -I | awk '{print $1}'):${PORT}/docs"
echo ""
echo "   Logs     : docker compose logs -f api"
echo "   Stop     : docker compose down"
