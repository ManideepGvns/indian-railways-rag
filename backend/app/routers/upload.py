from __future__ import annotations
import asyncio
import uuid
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List

from ..models import get_db, UploadedFile
from ..models.models import User
from ..core.security import get_current_user_id
from ..core.config import get_settings
from ..services import ingest_service, ollama_client, qdrant_service


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


@router.post("", response_model=FileInfo)
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

    db_file = UploadedFile(
        user_id=user_id,
        filename=file.filename,
        file_id=file_id,
        status="processing",
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)

    async def _ingest() -> None:
        chunks = await ingest_service.extract_and_chunk(file.filename, content)
        if not chunks:
            raise ValueError("No text could be extracted from the file.")

        embeddings = []
        for chunk in chunks:
            emb = await ollama_client.embed(chunk)
            embeddings.append(emb)

        await qdrant_service.ensure_collection(len(embeddings[0]))
        await qdrant_service.upsert_chunks(
            file_id, file.filename, user_id, chunks, embeddings,
            file_content_hash=sha256,
        )
        db_file.chunk_count = len(chunks)
        db_file.status = "ready"

    timeout_s = get_settings().upload_timeout_secs
    try:
        await asyncio.wait_for(_ingest(), timeout=timeout_s)
    except asyncio.TimeoutError:
        db_file.status = "error"
        db.commit()
        raise HTTPException(status_code=504, detail="Embedding timed out. The file may be too large or Ollama is overloaded.")
    except Exception as exc:
        db_file.status = "error"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}")

    db.commit()
    db.refresh(db_file)
    return FileInfo(
        id=db_file.id,
        file_id=db_file.file_id,
        filename=db_file.filename,
        chunk_count=db_file.chunk_count,
        status=db_file.status,
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

    await qdrant_service.delete_file_chunks(file_id)
    db.delete(db_file)
    db.commit()
    return {"message": "File deleted"}
