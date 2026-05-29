from __future__ import annotations
import httpx
from typing import AsyncIterator
from ..core.config import get_settings


async def embed(text: str) -> list[float]:
    """
    Call Ollama's embedding API.

    Tries the newer /api/embed endpoint first (Ollama ≥ 0.1.33).
    Falls back to the legacy /api/embeddings endpoint for older builds.

    Input is hard-truncated at 8000 chars (~2000 tokens) as a last-resort
    safety net against 400 errors from models with limited context windows.
    """
    # Safety truncation: nomic-embed-text context limit is 8192 tokens (~32k chars);
    # practical safe limit is ~8000 chars to leave headroom for tokenization overhead.
    MAX_EMBED_CHARS = 8000
    if len(text) > MAX_EMBED_CHARS:
        text = text[:MAX_EMBED_CHARS]

    settings = get_settings()
    async with httpx.AsyncClient(timeout=120.0) as client:
        # ── Try modern endpoint (/api/embed) ────────────────────────
        resp = await client.post(
            f"{settings.ollama_base_url}/api/embed",
            json={"model": settings.ollama_embed_model, "input": text},
        )
        if resp.status_code == 404:
            # ── Fall back to legacy endpoint (/api/embeddings) ──────
            resp = await client.post(
                f"{settings.ollama_base_url}/api/embeddings",
                json={"model": settings.ollama_embed_model, "prompt": text},
            )
            resp.raise_for_status()
            return resp.json()["embedding"]  # legacy shape: {"embedding": [...]}

        resp.raise_for_status()
        data = resp.json()
        # Modern shape: {"embeddings": [[...]], "model": ...}
        return data["embeddings"][0]


async def chat_stream(messages: list[dict]) -> AsyncIterator[str]:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=300.0) as client:
        async with client.stream(
            "POST",
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_chat_model,
                "messages": messages,
                "stream": True,
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                import json
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                content = chunk.get("message", {}).get("content", "")
                if content:
                    yield content
                if chunk.get("done"):
                    break


async def chat_complete(messages: list[dict]) -> str:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_chat_model,
                "messages": messages,
                "stream": False,
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]


async def classify_chunk_boundary(current_chunk: str, next_paragraph: str) -> bool:
    """
    Ask Ollama whether `next_paragraph` starts a new logical topic or continues
    the current chunk.

    Returns True  → start a NEW chunk (boundary detected).
    Returns False → CONTINUE accumulating into the current chunk.

    On any error the safe default is False (keep accumulating).
    """
    settings = get_settings()
    # Use the tail of the current chunk so the prompt stays small.
    chunk_preview = current_chunk[-600:] if len(current_chunk) > 600 else current_chunk
    prompt = (
        "You are a document chunking assistant for Indian Railways documents.\n"
        "Decide if the NEXT PARAGRAPH belongs to the same topic/section as the CURRENT CHUNK "
        "or starts a completely new topic.\n\n"
        f"CURRENT CHUNK:\n{chunk_preview}\n\n"
        f"NEXT PARAGRAPH:\n{next_paragraph}\n\n"
        "Rules:\n"
        "- Numbered steps within the same process are the SAME topic (CONTINUE).\n"
        "- A shift to a different procedure, department, or subject is a NEW topic (NEW).\n"
        "- Consecutive directory/table rows for the same department are CONTINUE.\n\n"
        "Respond with exactly one word: CONTINUE or NEW."
    )
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model": settings.ollama_chat_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {"temperature": 0},
                },
            )
            resp.raise_for_status()
            raw = resp.json()["message"]["content"].strip().upper()
            first_word = raw.split()[0].rstrip(".,;:") if raw.split() else ""
            return first_word == "NEW"
    except Exception:
        return False  # default: CONTINUE — never split on error
