# ── Stage 1: Build frontend ──────────────────────────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci --silent
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python runtime ───────────────────────────────────────────────────
FROM python:3.11-slim

# PyMuPDF bundles its own MuPDF — no system libmupdf needed.
# Only standard build tools are required.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Install Python deps
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ ./

# Copy built frontend into a location the FastAPI app will serve
COPY --from=frontend-build /build/frontend/dist ./frontend_dist

# Create persistent data directory and set ownership
RUN mkdir -p /data/sqlite && chown -R appuser:appuser /data /app

USER appuser

EXPOSE 8000

ENV DATABASE_URL=sqlite:////data/sqlite/ir_rag.db

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
