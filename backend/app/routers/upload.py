from __future__ import annotations
import asyncio
import json
import uuid
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List

from ..models import get_db, UploadedFile
from ..models.models import User
from ..core.security import get_current_user_id
from ..core.config import get_settings
from ..services import ingest_service, ollama_client, qdrant_service


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _require_admin(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> int:
    """Raise 403 if the authenticated user is not an admin."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user_id

router = APIRouter(prefix="/upload", tags=["upload"])

ALLOWED_EXT = {".pdf", ".docx", ".txt", ".md"}
MAX_FILE_BYTES = 50 * 1024 * 1024   # 50 MB hard limit


class FileInfo(BaseModel):
    id: int
    file_id: str
    filename: str
    chunk_count: int
    status: str


class FileListResponse(BaseModel):
    files: List[FileInfo]


@router.post("")
async def upload_file(
    file: UploadFile = File(...),
    user_id: int = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    from pathlib import Path
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"File type not supported. Allowed: {', '.join(ALLOWED_EXT)}")

    content = await file.read()

    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum allowed size is {MAX_FILE_BYTES // (1024*1024)} MB.",
        )

    # Deduplication — skip re-embedding identical files for the same user
    sha256 = qdrant_service.content_hash(content)
    try:
        if await qdrant_service.file_already_indexed(user_id, sha256):
            raise HTTPException(
                status_code=409,
                detail="This exact file has already been uploaded and indexed. Upload a different file or delete the existing one first.",
            )
    except HTTPException:
        raise
    except Exception:
        pass  # If Qdrant is unreachable, proceed and let the embed step fail with a clearer error

    file_id = str(uuid.uuid4())

    # Remove any stale "error" records for the same filename so the user
    # gets a clean slate when retrying a previously failed upload.
    stale = db.query(UploadedFile).filter(
        UploadedFile.user_id == user_id,
        UploadedFile.filename == file.filename,
        UploadedFile.status == "error",
    ).all()
    for s in stale:
        try:
            await qdrant_service.delete_file_chunks(s.file_id)
        except Exception:
            pass
        db.delete(s)
    if stale:
        db.commit()

    db_file = UploadedFile(
        user_id=user_id,
        filename=file.filename,
        file_id=file_id,
        status="processing",
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)

    filename = file.filename  # capture before streaming begins

    # Queue used by the background ingest task to push progress events to the
    # SSE generator.  The generator reads with a short timeout so it can emit
    # SSE keepalive comments even when the ingest is silent (e.g. a CPU-bound
    # Ollama call that takes many seconds), preventing proxy / browser timeouts.
    q: asyncio.Queue[dict] = asyncio.Queue()

    async def _ingest_task() -> None:
        try:
            await q.put({"type": "progress", "phase": "extracting"})
            chunks = await ingest_service.extract_and_chunk(filename, content, q)
            if not chunks:
                raise ValueError("No text could be extracted from the file.")

            total = len(chunks)
            embeddings: list = []
            for i, chunk in enumerate(chunks):
                emb = await ollama_client.embed(chunk)
                embeddings.append(emb)
                await q.put({"type": "progress", "phase": "embedding", "current": i + 1, "total": total})

            await q.put({"type": "progress", "phase": "indexing"})
            await qdrant_service.ensure_collection(len(embeddings[0]))
            await qdrant_service.upsert_chunks(
                file_id, filename, user_id, chunks, embeddings,
                file_content_hash=sha256,
            )
            db_file.chunk_count = len(chunks)
            db_file.status = "ready"
            db.commit()

            await q.put({
                "type": "done",
                "file": {
                    "id": db_file.id,
                    "file_id": db_file.file_id,
                    "filename": db_file.filename,
                    "chunk_count": db_file.chunk_count,
                    "status": db_file.status,
                },
            })
        except Exception as exc:
            db_file.status = "error"
            db.commit()
            await q.put({"type": "error", "detail": str(exc)})

    async def event_stream():
        task = asyncio.create_task(_ingest_task())
        try:
            while True:
                try:
                    # Wait up to 15 s for the next progress event.  If nothing
                    # arrives (Ollama is mid-inference), emit an SSE comment to
                    # keep the connection alive through proxies and browsers.
                    event = await asyncio.wait_for(asyncio.shield(q.get()), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue

                yield _sse(event)
                if event.get("type") in ("done", "error"):
                    break
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("", response_model=FileListResponse)
def list_files(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    files = db.query(UploadedFile).filter(UploadedFile.user_id == user_id).order_by(UploadedFile.created_at.desc()).all()
    return FileListResponse(
        files=[
            FileInfo(id=f.id, file_id=f.file_id, filename=f.filename, chunk_count=f.chunk_count, status=f.status)
            for f in files
        ]
    )


@router.delete("/{file_id}")
async def delete_file(
    file_id: str,
    user_id: int = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    db_file = db.query(UploadedFile).filter(
        UploadedFile.file_id == file_id, UploadedFile.user_id == user_id
    ).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")

    # Best-effort Qdrant cleanup — if the upload previously failed (status="error"),
    # the collection or vectors may not exist; always remove the SQLite record.
    try:
        await qdrant_service.delete_file_chunks(file_id)
    except Exception:
        pass

    db.delete(db_file)
    db.commit()
    return {"message": "File deleted"}
