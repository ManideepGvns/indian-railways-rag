from __future__ import annotations
import uuid
import hashlib
import threading
from datetime import datetime, timezone
from typing import Optional
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FilterSelector, FieldCondition, MatchValue, MatchText,
    TextIndexParams, TokenizerType, PayloadSchemaType,
)
from ..core.config import get_settings

_client: Optional[AsyncQdrantClient] = None
_collection_lock = threading.Lock()   # threading.Lock is event-loop-agnostic
_collection_ready: bool = False


def get_client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
        )
    return _client


async def ensure_collection(vector_size: int) -> None:
    """Idempotent collection creation — safe under concurrent uploads."""
    global _collection_ready
    if _collection_ready:
        return
    settings = get_settings()
    client = get_client()
    # threading.Lock used (not asyncio) so it works across different event loops
    with _collection_lock:
        if _collection_ready:
            return
        exists = await client.collection_exists(settings.qdrant_collection)
        if not exists:
            await client.create_collection(
                collection_name=settings.qdrant_collection,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
        # Full-text index on the `text` payload field — enables keyword search
        # for names, acronyms and codes that semantic search can miss.
        try:
            await client.create_payload_index(
                collection_name=settings.qdrant_collection,
                field_name="text",
                field_schema=TextIndexParams(
                    type=PayloadSchemaType.TEXT,
                    tokenizer=TokenizerType.WORD,
                    min_token_len=2,
                    lowercase=True,
                ),
            )
        except Exception:
            pass  # Index may already exist; safe to ignore
        _collection_ready = True


def content_hash(data: bytes) -> str:
    """SHA-256 hex digest of file bytes — used for deduplication."""
    return hashlib.sha256(data).hexdigest()


def _chunk_point_id(file_id: str, chunk_index: int) -> str:
    raw = f"{file_id}:{chunk_index}"
    return str(uuid.UUID(hashlib.md5(raw.encode()).hexdigest()))


async def file_already_indexed(user_id: int, content_sha256: str) -> bool:
    """Return True if an identical file (same hash, same user) exists in the collection."""
    settings = get_settings()
    client = get_client()
    try:
        results = await client.scroll(
            collection_name=settings.qdrant_collection,
            scroll_filter=Filter(must=[
                FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                FieldCondition(key="content_hash", match=MatchValue(value=content_sha256)),
            ]),
            limit=1,
            with_payload=False,
            with_vectors=False,
        )
        return len(results[0]) > 0
    except Exception:
        return False


_UPSERT_BATCH = 200  # points per HTTP request — keeps payloads well under Qdrant's limits


async def upsert_chunks(
    file_id: str,
    filename: str,
    user_id: int,
    chunks: list[str],
    embeddings: list[list[float]],
    file_content_hash: str = "",
) -> None:
    settings = get_settings()
    client = get_client()
    upload_date = datetime.now(timezone.utc).isoformat()
    points = [
        PointStruct(
            id=_chunk_point_id(file_id, i),
            vector=emb,
            payload={
                "user_id": user_id,
                "file_id": file_id,
                "filename": filename,
                "chunk_index": i,
                "text": chunk,
                "content_hash": file_content_hash,
                "upload_date": upload_date,
            },
        )
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ]
    # Upsert in batches to avoid oversized HTTP requests and Qdrant timeouts.
    # A single request with thousands of 768-dim vectors + text payloads can
    # easily exceed 20 MB and trigger a 5 s client_request_timeout on the server.
    for start in range(0, len(points), _UPSERT_BATCH):
        await client.upsert(
            collection_name=settings.qdrant_collection,
            points=points[start : start + _UPSERT_BATCH],
        )


import re as _re

_STOP_WORDS = {
    "the", "and", "for", "are", "was", "were", "is", "in", "of", "to",
    "a", "an", "who", "what", "when", "where", "how", "tell", "about",
    "me", "give", "list", "show", "find", "which", "from", "with", "has",
    "had", "did", "do", "does", "can", "could", "would", "should", "have",
}


def _meaningful_tokens(text: str) -> list[str]:
    """
    Extract tokens ≥ 3 chars that are not common stop words.
    Proper names, acronyms and codes are the primary targets.
    """
    tokens = _re.findall(r"[A-Za-z][A-Za-z0-9]*", text)
    return [t for t in tokens if len(t) >= 3 and t.lower() not in _STOP_WORDS]


async def search(
    query_vector: list[float],
    user_id: int,
    top_k: int,
    query_text: str = "",
) -> list[dict]:
    """
    Hybrid search: vector similarity + keyword supplement.

    1. Vector search  — captures semantic / paraphrase similarity.
    2. Keyword filter — scrolls the collection for chunks that contain
       every meaningful word from the query.  This rescues proper names,
       acronyms and numeric codes that the embedding model under-ranks.

    Keyword hits not already present in the vector results are appended
    so the LLM sees the relevant chunk even when the cosine score is low.
    """
    settings = get_settings()
    client = get_client()

    # ── 1. Vector search ──────────────────────────────────────────────────
    vec_results = await client.search(
        collection_name=settings.qdrant_collection,
        query_vector=query_vector,
        limit=top_k,
        with_payload=True,
    )
    seen_ids = {r.id for r in vec_results}
    hits: list[dict] = [
        {
            "text": r.payload.get("text", ""),
            "filename": r.payload.get("filename", ""),
            "score": r.score,
            "upload_date": r.payload.get("upload_date", ""),
        }
        for r in vec_results
    ]

    # ── 2. Keyword supplement ─────────────────────────────────────────────
    if query_text:
        tokens = _meaningful_tokens(query_text)
        if tokens:
            try:
                # Use Qdrant full-text MatchText per token (OR semantics);
                # collect union of results, then keep only those that match ALL tokens.
                candidate_ids: dict[str, dict] = {}  # point_id -> payload
                for token in tokens:
                    kw_results, _ = await client.scroll(
                        collection_name=settings.qdrant_collection,
                        scroll_filter=Filter(
                            must=[
                                FieldCondition(
                                    key="text",
                                    match=MatchText(text=token),
                                )
                            ]
                        ),
                        limit=50,
                        with_payload=True,
                        with_vectors=False,
                    )
                    for point in kw_results:
                        pid = str(point.id)
                        if pid not in candidate_ids:
                            candidate_ids[pid] = point.payload

                # Keep candidates that contain ALL tokens (case-insensitive)
                tokens_lower = [t.lower() for t in tokens]
                for pid, payload in candidate_ids.items():
                    chunk_text_lower = payload.get("text", "").lower()
                    if all(t in chunk_text_lower for t in tokens_lower):
                        # Only add if not already returned by vector search
                        raw_id = pid
                        # IDs may be UUID strings or ints depending on Qdrant version
                        if raw_id not in {str(i) for i in seen_ids}:
                            hits.append({
                                "text": payload.get("text", ""),
                                "filename": payload.get("filename", ""),
                                "score": 1.0,  # keyword-exact match — treat as top evidence
                                "upload_date": payload.get("upload_date", ""),
                            })
                            seen_ids.add(raw_id)
            except Exception:
                pass  # Keyword search is a best-effort supplement; never block

    return hits


async def delete_file_chunks(file_id: str) -> None:
    """Delete all Qdrant vectors for a file. No-ops gracefully if the collection
    does not exist (e.g. the upload failed before any vectors were stored)."""
    settings = get_settings()
    client = get_client()
    try:
        exists = await client.collection_exists(settings.qdrant_collection)
        if not exists:
            return
        await client.delete(
            collection_name=settings.qdrant_collection,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="file_id", match=MatchValue(value=file_id))]
                )
            ),
        )
    except Exception:
        pass  # Best-effort — always allow the SQLite record to be removed
