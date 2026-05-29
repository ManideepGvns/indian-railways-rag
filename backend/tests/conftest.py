"""
Shared fixtures for the IR-RAG test suite.

All external I/O is mocked:
  - SQLite runs in-memory (no disk, no volume)
  - Ollama embed / chat are mocked with AsyncMock
  - Qdrant client methods are mocked with AsyncMock
"""
from __future__ import annotations
import os
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# Point to an in-memory SQLite DB before the app is imported
os.environ.setdefault("DATABASE_URL", "sqlite:///./tests/test_ir_rag.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-32-chars-minimum!!")
os.environ.setdefault("QDRANT_URL", "http://127.0.0.1:6333")
os.environ.setdefault("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base
from app.models.models import User
from app.core.security import hash_password
from app.main import app
from app.models import get_db

# In-memory SQLite for tests
TEST_DB_URL = "sqlite:///./tests/test_ir_rag.db"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    Base.metadata.create_all(bind=engine)
    # Seed admin user
    db = TestingSessionLocal()
    existing = db.query(User).filter(User.username == "admin").first()
    if not existing:
        db.add(User(username="admin", hashed_password=hash_password("Admin@123")))
        db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def auth_headers(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "Admin@123"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Qdrant mock — patches the global singleton so no real Qdrant is needed
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def mock_qdrant(monkeypatch):
    mock_client = MagicMock()
    mock_client.collection_exists = AsyncMock(return_value=True)
    mock_client.create_collection = AsyncMock()
    mock_client.upsert = AsyncMock()
    mock_client.search = AsyncMock(return_value=[])
    mock_client.delete = AsyncMock()
    mock_client.scroll = AsyncMock(return_value=([], None))

    import app.services.qdrant_service as qs
    monkeypatch.setattr(qs, "_client", mock_client)
    monkeypatch.setattr(qs, "_collection_ready", False)
    return mock_client


# ---------------------------------------------------------------------------
# Ollama mock — patches embed and chat_stream
# ---------------------------------------------------------------------------
FAKE_EMBEDDING = [0.1] * 768   # nomic-embed-text dim


@pytest.fixture(autouse=True)
def mock_ollama(monkeypatch):
    import app.services.ollama_client as oc

    async def fake_embed(text: str):
        return FAKE_EMBEDDING

    async def fake_chat_stream(messages):
        for token in ["Hello", " from", " IR", " assistant"]:
            yield token

    monkeypatch.setattr(oc, "embed", fake_embed)
    monkeypatch.setattr(oc, "chat_stream", fake_chat_stream)
