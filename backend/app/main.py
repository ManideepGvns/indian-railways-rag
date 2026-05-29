from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from sqlalchemy import text
from .core.config import get_settings
from .core.security import hash_password
from .models.database import Base, engine, SessionLocal
from .models.models import User
from .routers import auth, chats, upload


def _run_migrations():
    """Add new columns to existing tables without breaking existing data."""
    with engine.connect() as conn:
        migrations = [
            "ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0",
            "ALTER TABLE messages ADD COLUMN sources TEXT",
        ]
        for stmt in migrations:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # Column already exists — safe to ignore


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _run_migrations()

    settings = get_settings()
    db = SessionLocal()
    try:
        # Seed / ensure admin user (is_admin=True)
        admin = db.query(User).filter(User.username == settings.admin_seed_username).first()
        if not admin:
            admin = User(
                username=settings.admin_seed_username,
                hashed_password=hash_password(settings.admin_seed_password),
                is_admin=True,
            )
            db.add(admin)
            db.commit()
            print(f"[IR-RAG] Admin user '{settings.admin_seed_username}' created.")
        elif not admin.is_admin:
            admin.is_admin = True
            db.commit()

        # Seed / ensure regular user (is_admin=False)
        regular = db.query(User).filter(User.username == settings.user_seed_username).first()
        if not regular:
            regular = User(
                username=settings.user_seed_username,
                hashed_password=hash_password(settings.user_seed_password),
                is_admin=False,
            )
            db.add(regular)
            db.commit()
            print(f"[IR-RAG] Regular user '{settings.user_seed_username}' created.")
    finally:
        db.close()

    yield


settings = get_settings()

app = FastAPI(
    title="Indian Railways RAG API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    # Wildcard ("*") is forbidden by browsers when credentials=True; list explicitly.
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(chats.router, prefix="/api")
app.include_router(upload.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Serve built frontend (production Docker image)
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "..", "frontend_dist")
if os.path.isdir(frontend_dist):
    from fastapi.responses import FileResponse
    from fastapi import Request

    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str, request: Request):
        return FileResponse(os.path.join(frontend_dist, "index.html"))
