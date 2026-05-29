#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────────
# start-local-qdrant.sh
#
# Starts Qdrant on port 6333 for local development.
#
# Strategy (tries in order):
#   1. Use an already-running Qdrant on :6333 → nothing to do
#   2. If a local binary exists in scripts/qdrant-bin/ → start it
#   3. Download the native binary for your OS/arch  → start it
#   4. Fall back to Docker if available
#
# Data is stored in scripts/qdrant-data/ (gitignored) so vectors
# survive restarts without Docker volumes.
# ────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${SCRIPT_DIR}/qdrant-bin"
DATA_DIR="${SCRIPT_DIR}/qdrant-data"
PORT=6333
QDRANT_VERSION="v1.18.1"

mkdir -p "${BIN_DIR}" "${DATA_DIR}"

# ── 1. Already running? ───────────────────────────────────────────────
if lsof -i TCP:"${PORT}" -sTCP:LISTEN -t &>/dev/null 2>&1; then
  echo "✓ Qdrant is already listening on port ${PORT} — nothing to do."
  exit 0
fi

# ── 2 / 3. Native binary ─────────────────────────────────────────────
ARCH="$(uname -m)"
OS="$(uname -s)"

case "${OS}-${ARCH}" in
  Darwin-arm64)   ASSET="qdrant-aarch64-apple-darwin.tar.gz" ;;
  Darwin-x86_64)  ASSET="qdrant-x86_64-apple-darwin.tar.gz" ;;
  Linux-aarch64)  ASSET="qdrant-aarch64-unknown-linux-musl.tar.gz" ;;
  Linux-x86_64)   ASSET="qdrant-x86_64-unknown-linux-musl.tar.gz" ;;
  *)
    echo "Unsupported platform: ${OS}-${ARCH}"
    ASSET=""
    ;;
esac

QDRANT_BIN="${BIN_DIR}/qdrant"

if [ -n "${ASSET}" ]; then
  if [ ! -x "${QDRANT_BIN}" ]; then
    URL="https://github.com/qdrant/qdrant/releases/download/${QDRANT_VERSION}/${ASSET}"
    echo "Downloading Qdrant ${QDRANT_VERSION} for ${OS}-${ARCH} …"
    echo "  → ${URL}"
    curl -fL --progress-bar "${URL}" -o "${BIN_DIR}/${ASSET}"
    tar -xzf "${BIN_DIR}/${ASSET}" -C "${BIN_DIR}"
    chmod +x "${QDRANT_BIN}"
    rm -f "${BIN_DIR}/${ASSET}"
    echo "✓ Binary saved to ${QDRANT_BIN}"

    # macOS Gatekeeper: remove quarantine so it runs without a security prompt
    if [ "${OS}" = "Darwin" ]; then
      xattr -d com.apple.quarantine "${QDRANT_BIN}" 2>/dev/null || true
    fi
  else
    echo "✓ Using existing Qdrant binary: ${QDRANT_BIN}"
  fi

  echo ""
  echo "Starting Qdrant on port ${PORT} …"
  echo "  Data dir : ${DATA_DIR}"
  echo "  REST API : http://127.0.0.1:${PORT}"
  echo "  Dashboard: http://127.0.0.1:${PORT}/dashboard"
  echo ""
  echo "Press Ctrl+C to stop."
  echo ""

  # Qdrant v1.7+ reads configuration from env vars (QDRANT__ prefix)
  # rather than CLI flags for most settings.
  export QDRANT__STORAGE__STORAGE_PATH="${DATA_DIR}"
  export QDRANT__SERVICE__HOST="127.0.0.1"
  export QDRANT__SERVICE__HTTP_PORT="${PORT}"

  # Run in foreground — open a new terminal tab or background with & to keep shell free
  "${QDRANT_BIN}"
  exit 0
fi

# ── 4. Docker fallback ────────────────────────────────────────────────
if command -v docker &>/dev/null; then
  CONTAINER_NAME="ir-rag-qdrant-local"
  VOLUME_NAME="ir_rag_qdrant_storage"

  if docker inspect "${CONTAINER_NAME}" &>/dev/null 2>&1; then
    docker rm "${CONTAINER_NAME}" 2>/dev/null || true
  fi

  echo "Starting Qdrant via Docker on port ${PORT} …"
  docker run -d \
    --name "${CONTAINER_NAME}" \
    -p "${PORT}:6333" \
    -v "${VOLUME_NAME}:/qdrant/storage" \
    "qdrant/qdrant:${QDRANT_VERSION}"

  echo "✓ Qdrant started via Docker."
  echo "  REST API : http://127.0.0.1:${PORT}"
  echo "  Stop     : docker stop ${CONTAINER_NAME}"
  exit 0
fi

# ── Nothing worked ────────────────────────────────────────────────────
echo ""
echo "ERROR: Could not start Qdrant — unsupported platform '${OS}-${ARCH}' and Docker is not available."
echo ""
echo "Options:"
echo "  • Install Homebrew Qdrant: brew install qdrant && qdrant"
echo "  • Install Docker Desktop  : https://docs.docker.com/get-docker/"
echo "  • Download binary manually: https://github.com/qdrant/qdrant/releases/tag/${QDRANT_VERSION}"
exit 1
