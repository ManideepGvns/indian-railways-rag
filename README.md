# Indian Railways RAG Assistant

A full-stack Retrieval-Augmented Generation (RAG) application for Indian Railways knowledge management. Upload railway documents (circulars, manuals, timetables, policy PDFs) and get precise, context-aware answers via a beautiful chat interface — all powered by locally-hosted AI through Ollama.

---

## Features

- **Beautiful chat UI** — hero empty state, session sidebar, streaming markdown responses
- **Document upload** — PDF, DOCX, TXT, Markdown with recursive-character chunking
- **RAG pipeline** — Qdrant vector search + Ollama embeddings + LLM chat
- **Session memory** — each chat thread retains full context; resume any past conversation
- **Login** — JWT-based auth; admin user seeded on first start
- **VM-ready** — Docker multi-stage build; SQLite data persisted in a named volume

---

## Architecture

```
Browser ──► FastAPI ──► Ollama (embed + chat)
                   ──► Qdrant  (vector search)
                   ──► SQLite  (users / sessions / messages)
```

---

## Local Development (no Docker for the app)

### 1. Prerequisites


| Tool    | Version | Purpose             |
| ------- | ------- | ------------------- |
| Python  | 3.11+   | Backend             |
| Node.js | 20+     | Frontend            |
| Ollama  | latest  | LLM + embeddings    |
| Qdrant  | latest  | Vector DB           |
| Docker  | latest  | Qdrant only (local) |


### 2. Pull Ollama models

```bash
ollama pull nomic-embed-text   # embedding model
ollama pull llama3.2           # chat model (or another tag you prefer)
```

Ollama listens on **port 11434** by default.

### 3. Start Qdrant on port 6333

**If Qdrant is already running on your machine on port 6333** (natively installed, or an existing Docker container) — skip this step entirely. Your `.env` points to `http://127.0.0.1:6333` and the app will use it directly.

**If you do NOT have Qdrant running** and have Docker installed, the helper script will start it:

```bash
chmod +x scripts/start-local-qdrant.sh
./scripts/start-local-qdrant.sh
```

This runs the official `qdrant/qdrant` image on **port 6333** with a named Docker volume (`ir_rag_qdrant_storage`) so vectors survive restarts. To stop: `docker stop ir-rag-qdrant-local`

**If you do NOT have Docker either**, install Qdrant natively:

```bash
# macOS via Homebrew
brew install qdrant
qdrant   # starts on :6333 by default
```

Or download from [https://github.com/qdrant/qdrant/releases](https://github.com/qdrant/qdrant/releases)

### 4. Configure environment

```bash
cp env.example .env
# Edit .env if needed — defaults work for local dev out of the box
```

### 5. Start the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8090
```

On first start, the admin user is created automatically:

- **Username:** `admin`
- **Password:** `Admin@123`

API docs: [http://127.0.0.1:8090/docs](http://127.0.0.1:8090/docs)

### 6. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open **[http://localhost:5173](http://localhost:5173)** — Vite proxies `/api` calls to the FastAPI server on `8090`.

---

## VM Deployment (Docker)

### 1. Prerequisites on the VM

- Docker + `docker compose` v2
- Qdrant already running on port **6333** (external, not managed by this compose)
- Ollama running and models pulled (see step 2 above)

### 2. Configure

```bash
cp env.example .env
# Edit .env:
#   JWT_SECRET  ← generate a long random string
#   QDRANT_URL  ← e.g. http://172.17.0.1:6333  (Linux bridge to host Qdrant)
#                 or    http://host.docker.internal:6333  (Docker Desktop)
#   OLLAMA_BASE_URL ← e.g. http://172.17.0.1:11434
#   CORS_ORIGINS    ← your domain or VM IP
```

> **Linux networking note:** The `docker-compose.yml` adds `extra_hosts: host.docker.internal:host-gateway` so `host.docker.internal` resolves to the host from inside the container. Alternatively, find the Docker bridge IP with `ip route | grep docker` and use that directly in `QDRANT_URL` / `OLLAMA_BASE_URL`.

### 3. Deploy

```bash
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

The script builds the image (multi-stage: Vite build + Python), starts the API container, waits for the health check, and prints the URL.

### 4. SQLite persistence

Chat history and user data live in the **named Docker volume `ir_rag_sqlite_data`** mounted at `/data/sqlite/ir_rag.db` inside the container. The volume survives `docker compose down` and image rebuilds. It is **only** removed if you run `docker compose down -v`.

**Backup:**

```bash
docker run --rm \
  -v ir_rag_sqlite_data:/data \
  -v $(pwd):/out \
  alpine tar czf /out/ir_rag_backup_$(date +%Y%m%d).tar.gz /data
```

---

## Environment Variables

See `[env.example](env.example)` for all variables with comments. Key ones:


| Variable             | Default (local)              | Description                                                   |
| -------------------- | ---------------------------- | ------------------------------------------------------------- |
| `JWT_SECRET`         | *(set in .env)*              | Secret for JWT signing — **change in production**             |
| `DATABASE_URL`       | `sqlite:///./data/ir_rag.db` | SQLite path; use `sqlite:////data/sqlite/ir_rag.db` in Docker |
| `QDRANT_URL`         | `http://127.0.0.1:6333`      | Qdrant REST endpoint                                          |
| `OLLAMA_BASE_URL`    | `http://127.0.0.1:11434`     | Ollama API endpoint                                           |
| `OLLAMA_CHAT_MODEL`  | `llama3.2`                   | Model tag for chat                                            |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text`           | Model tag for embeddings                                      |
| `CHUNK_SIZE`         | `1000`                       | Characters per chunk                                          |
| `CHUNK_OVERLAP`      | `150`                        | Overlap between chunks                                        |
| `RAG_TOP_K`          | `6`                          | Retrieved chunks per query                                    |


---

## Project Layout

```
IR_RAG/
├── backend/
│   ├── app/
│   │   ├── core/         # config, security (JWT + bcrypt)
│   │   ├── models/       # SQLAlchemy models + database setup
│   │   ├── routers/      # auth, chats, upload
│   │   ├── services/     # ollama_client, qdrant_service, ingest_service
│   │   └── main.py       # FastAPI app + lifespan (DB init + admin seed)
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/          # axios client
│   │   ├── components/   # Sidebar, MessageBubble, UploadModal, HeroEmpty
│   │   ├── context/      # AuthContext
│   │   └── pages/        # LoginPage, ChatPage
│   └── vite.config.ts
├── scripts/
│   ├── start-local-qdrant.sh   # local dev: Qdrant in Docker on 6333
│   └── deploy.sh               # VM: build + docker compose up
├── Dockerfile            # multi-stage: frontend build → Python runtime
├── docker-compose.yml    # api service + ir_rag_sqlite_data volume
├── env.example           # all variables documented
└── README.md
```

---

## Default Login


| Field    | Value       |
| -------- | ----------- |
| Username | `admin`     |
| Password | `Admin@123` |


The admin user is created on first startup if it does not already exist.

---

## Chunking Strategy

Documents go through format-specific extraction (PyMuPDF for PDFs, python-docx for DOCX, raw decode for TXT/MD), then a **recursive character text splitter** with separator hierarchy `["\n\n", "\n", ". ", " "]`. This handles mixed-format IR documents (prose + tables + headers) better than naive fixed-window chunking. Chunk size and overlap are configurable via env.

---

## Tech Stack


| Layer       | Technology                                        |
| ----------- | ------------------------------------------------- |
| Backend     | FastAPI, SQLAlchemy, SQLite, python-jose, passlib |
| Vector DB   | Qdrant                                            |
| LLM + Embed | Ollama (`llama3.2` + `nomic-embed-text`)          |
| Frontend    | React 18, Vite, TypeScript, Tailwind CSS v4       |
| Containers  | Docker multi-stage, docker compose v2             |


