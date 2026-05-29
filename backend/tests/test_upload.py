"""Tests for /api/upload endpoints."""
from __future__ import annotations
import io
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LONG_TXT = (
    "Indian Railways passenger rules. "
    "Section 1: Refunds are available within 24 hours of journey. "
    "Section 2: All passengers must carry valid government issued photo identity proof. "
    "Section 3: Luggage beyond 35 kg will attract additional charges as per the tariff. "
    "Section 4: Use of alarm chain without valid reason is a punishable offence under the Railway Act. "
) * 3


def _txt_file(content: str = _LONG_TXT) -> tuple:
    return ("test.txt", io.BytesIO(content.encode()), "text/plain")


def _md_file(content: str = "# IR Guide\n\n" + _LONG_TXT) -> tuple:
    return ("test.md", io.BytesIO(content.encode()), "text/markdown")


def _fake_pdf() -> bytes:
    """Minimal valid-ish PDF bytes. PyMuPDF will reject this but we test extension gating."""
    return b"%PDF-1.4 1 0 obj<</Type/Catalog>>endobj"


# ---------------------------------------------------------------------------
# POST /api/upload
# ---------------------------------------------------------------------------

def test_upload_txt(client, auth_headers):
    name, buf, mime = _txt_file()
    resp = client.post(
        "/api/upload",
        files={"file": (name, buf, mime)},
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Upload failed: {resp.text}"
    data = resp.json()
    assert data["status"] == "ready"
    assert data["chunk_count"] > 0
    assert data["filename"] == name


def test_upload_markdown(client, auth_headers):
    name, buf, mime = _md_file()
    resp = client.post(
        "/api/upload",
        files={"file": (name, buf, mime)},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_upload_unsupported_extension(client, auth_headers):
    resp = client.post(
        "/api/upload",
        files={"file": ("notes.xls", io.BytesIO(b"data"), "application/octet-stream")},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "not supported" in resp.json()["detail"].lower()


def test_upload_too_large(client, auth_headers):
    # 51 MB of zeros
    big = io.BytesIO(b"x" * (51 * 1024 * 1024))
    resp = client.post(
        "/api/upload",
        files={"file": ("big.txt", big, "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 413


def test_upload_duplicate_rejected(client, auth_headers, monkeypatch):
    """Uploading the exact same file twice should return 409."""
    import app.services.qdrant_service as qs
    from unittest.mock import AsyncMock

    content = _LONG_TXT + " UNIQUE_DEDUP_MARKER_98765"
    name, buf, mime = _txt_file(content)

    # First upload: not indexed yet
    monkeypatch.setattr(qs, "file_already_indexed", AsyncMock(return_value=False))
    resp1 = client.post("/api/upload", files={"file": (name, buf, mime)}, headers=auth_headers)
    assert resp1.status_code == 200, f"First upload failed: {resp1.text}"

    # Second upload: now it IS indexed
    monkeypatch.setattr(qs, "file_already_indexed", AsyncMock(return_value=True))
    buf2 = io.BytesIO(content.encode())
    resp2 = client.post("/api/upload", files={"file": (name, buf2, mime)}, headers=auth_headers)
    assert resp2.status_code == 409, f"Expected 409, got {resp2.status_code}: {resp2.text}"


def test_upload_requires_auth(client):
    name, buf, mime = _txt_file()
    resp = client.post("/api/upload", files={"file": (name, buf, mime)})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/upload  — list files
# ---------------------------------------------------------------------------

def test_list_files(client, auth_headers):
    resp = client.get("/api/upload", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "files" in data
    assert isinstance(data["files"], list)


def test_list_files_shows_uploaded(client, auth_headers):
    name, buf, mime = _txt_file(_LONG_TXT + " LISTING_MARKER")
    client.post("/api/upload", files={"file": (name, buf, mime)}, headers=auth_headers)
    resp = client.get("/api/upload", headers=auth_headers)
    assert resp.status_code == 200
    filenames = [f["filename"] for f in resp.json()["files"]]
    assert name in filenames


def test_list_files_requires_auth(client):
    resp = client.get("/api/upload")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/upload/{file_id}
# ---------------------------------------------------------------------------

def test_delete_file(client, auth_headers, mock_qdrant):
    name, buf, mime = _txt_file(_LONG_TXT + " DELETE_MARKER")
    upload = client.post("/api/upload", files={"file": (name, buf, mime)}, headers=auth_headers).json()
    assert "file_id" in upload, f"Upload failed: {upload}"
    file_id = upload["file_id"]

    resp = client.delete(f"/api/upload/{file_id}", headers=auth_headers)
    assert resp.status_code == 200

    # Verify removed from list
    listing = client.get("/api/upload", headers=auth_headers).json()
    assert all(f["file_id"] != file_id for f in listing["files"])


def test_delete_file_not_found(client, auth_headers):
    resp = client.delete("/api/upload/nonexistent-uuid", headers=auth_headers)
    assert resp.status_code == 404


def test_delete_file_requires_auth(client):
    resp = client.delete("/api/upload/some-uuid")
    assert resp.status_code == 401
