"""Tests for /api/chats endpoints."""
from __future__ import annotations
import pytest


# ---------------------------------------------------------------------------
# POST /api/chats  — create session
# ---------------------------------------------------------------------------

def test_create_session(client, auth_headers):
    resp = client.post("/api/chats", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["title"] == "New Chat"


def test_create_session_requires_auth(client):
    resp = client.post("/api/chats")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/chats  — list sessions
# ---------------------------------------------------------------------------

def test_list_sessions_empty(client, auth_headers):
    resp = client.get("/api/chats", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_list_sessions_after_create(client, auth_headers):
    client.post("/api/chats", headers=auth_headers)
    resp = client.get("/api/chats", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


# ---------------------------------------------------------------------------
# GET /api/chats/{id}  — get session detail
# ---------------------------------------------------------------------------

def test_get_session(client, auth_headers):
    create = client.post("/api/chats", headers=auth_headers).json()
    resp = client.get(f"/api/chats/{create['id']}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == create["id"]
    assert "messages" in data
    assert "total_messages" in data
    assert data["total_messages"] == 0


def test_get_session_not_found(client, auth_headers):
    resp = client.get("/api/chats/99999", headers=auth_headers)
    assert resp.status_code == 404


def test_get_session_pagination(client, auth_headers):
    create = client.post("/api/chats", headers=auth_headers).json()
    resp = client.get(f"/api/chats/{create['id']}?limit=10&offset=0", headers=auth_headers)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# PATCH /api/chats/{id}  — rename
# ---------------------------------------------------------------------------

def test_rename_session(client, auth_headers):
    session = client.post("/api/chats", headers=auth_headers).json()
    resp = client.patch(
        f"/api/chats/{session['id']}",
        json={"title": "My Railway Chat"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "My Railway Chat"


def test_rename_session_not_found(client, auth_headers):
    resp = client.patch("/api/chats/99999", json={"title": "x"}, headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/chats/{id}
# ---------------------------------------------------------------------------

def test_delete_session(client, auth_headers):
    session = client.post("/api/chats", headers=auth_headers).json()
    resp = client.delete(f"/api/chats/{session['id']}", headers=auth_headers)
    assert resp.status_code == 200
    # Confirm it's gone
    resp2 = client.get(f"/api/chats/{session['id']}", headers=auth_headers)
    assert resp2.status_code == 404


def test_delete_session_not_found(client, auth_headers):
    resp = client.delete("/api/chats/99999", headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/chats/{id}/messages  — send message (streaming SSE)
# ---------------------------------------------------------------------------

def test_send_message_streams(client, auth_headers):
    session = client.post("/api/chats", headers=auth_headers).json()
    resp = client.post(
        f"/api/chats/{session['id']}/messages",
        json={"message": "What is the maximum speed of Rajdhani Express?"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    body = resp.text
    assert "data:" in body


def test_send_message_auto_titles_session(client, auth_headers):
    session = client.post("/api/chats", headers=auth_headers).json()
    assert session["title"] == "New Chat"

    client.post(
        f"/api/chats/{session['id']}/messages",
        json={"message": "Tell me about passenger fare rules"},
        headers=auth_headers,
    )
    # After first message, title should be auto-set
    updated = client.get(f"/api/chats/{session['id']}", headers=auth_headers).json()
    assert updated["title"] != "New Chat"


def test_send_message_persists_in_history(client, auth_headers):
    session = client.post("/api/chats", headers=auth_headers).json()
    client.post(
        f"/api/chats/{session['id']}/messages",
        json={"message": "Hello Railways"},
        headers=auth_headers,
    )
    detail = client.get(f"/api/chats/{session['id']}", headers=auth_headers).json()
    # Should have user + assistant messages
    assert detail["total_messages"] >= 2


def test_send_message_not_found_session(client, auth_headers):
    resp = client.post(
        "/api/chats/99999/messages",
        json={"message": "test"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_send_message_requires_auth(client):
    resp = client.post("/api/chats/1/messages", json={"message": "test"})
    assert resp.status_code == 401
