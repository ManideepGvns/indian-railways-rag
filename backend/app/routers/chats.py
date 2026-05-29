from __future__ import annotations
from datetime import datetime, timezone, date as _date
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import json as _json

from ..models import get_db, SessionLocal, ChatSession, Message
from ..core.security import get_current_user_id
from ..core.config import get_settings
from ..services import ollama_client, qdrant_service

router = APIRouter(prefix="/chats", tags=["chats"])

SYSTEM_PROMPT = (
    "You are an expert assistant for Indian Railways, specifically for IRIFM (Indian Railway Institute "
    "of Financial Management) and related departments.\n\n"

    "ANSWERING RULES:\n"
    "1. Use ONLY the provided context to answer. Present every fact you find — do not withhold "
    "partial information.\n"
    "2. NEVER quote, repeat, or reproduce the raw context text in your reply. Synthesize the "
    "information into a clean, natural answer in your own words.\n"
    "3. If a person, topic, or detail is mentioned in the context, state what IS available "
    "(name, designation, tenure, dates, phone numbers, etc.) clearly and directly. Never say "
    "'I don't have information' about something that IS present in the context.\n"
    "4. Only say information is unavailable when the topic is genuinely absent from all context chunks.\n"
    "5. Dates in the documents follow DD-MM-YYYY format (e.g. 02-11-2020 = 2nd November 2020, "
    "not 14th February). Always interpret and present dates correctly.\n"
    "6. Do not add preambles like 'According to the provided context' or 'Based on the documents'. "
    "Just answer directly.\n"
    "7. When the context contains a directory or list entry for the asked person/role, treat that "
    "entry as the complete, authoritative answer — do not request additional documents.\n"
    "8. In telephone directory entries, column labels mean: 'Rly' = Railway internal extension "
    "(4–5 digit number, only works on the railway IVRS/intercom network), 'BSNL' or 'Phone' = "
    "the external/direct contact phone number (7–8 digits). When asked for a contact number or "
    "phone number, give the BSNL/direct number, not the railway extension.\n"
    "9. RESPONSE FORMAT based on question type:\n"
    "   - Process / procedure / steps / how-to questions: Present ALL steps in numbered format "
    "(Step 1, Step 2 …) with sub-bullets for details. Include EVERY step present in the context — "
    "never truncate or summarise steps. Do NOT add disclaimers like 'these steps may not be "
    "comprehensive' or 'please refer to official sources' when the context already contains the "
    "full information.\n"
    "   - Lookup questions (name, phone, date, designation): Give a short, direct answer.\n"
    "   - Explanatory / comparison questions: Use clear paragraphs or a table as appropriate.\n"
    "10. Never add closing remarks like 'I hope this helps', 'feel free to ask', or 'please note "
    "that this information may be incomplete' when the context contains the full answer.\n"
    "11. RECENCY — when the context contains multiple entries for the same role or topic, "
    "identify the most recent one by comparing start dates (e.g. 'From DD-MM-YYYY') and "
    "present that person/information as current. The word 'Present' inside a document is "
    "relative to when the document was written — always use the start date to determine "
    "who is the latest holder.\n"
    "12. For casual greetings or messages completely unrelated to Indian Railways, respond "
    "briefly and naturally. Do NOT mention documents, DGs, or any railway information unless "
    "the user specifically asks."
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SessionInfo(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    sources: Optional[List[str]] = None   # source filenames for assistant messages
    created_at: datetime

    class Config:
        from_attributes = True


class SessionDetail(BaseModel):
    id: int
    title: str
    messages: List[MessageOut]
    total_messages: int

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[int] = None  # None = create new session


class RenameRequest(BaseModel):
    title: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MAX_HISTORY_TURNS = 20


def _build_ollama_messages(history: list[Message], rag_context: str, user_message: str) -> list[dict]:
    today = _date.today().strftime("%d %B %Y")  # e.g. "29 May 2026"
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if rag_context:
        messages.append({
            "role": "system",
            "content": (
                f"Today's date: {today}\n\n"
                "Relevant context from uploaded documents "
                "(each chunk shows the upload date — use it to judge freshness):\n\n"
                f"{rag_context}"
            ),
        })

    for msg in history[-MAX_HISTORY_TURNS:]:
        messages.append({"role": msg.role, "content": msg.content})

    messages.append({"role": "user", "content": user_message})
    return messages


def _auto_title(text: str) -> str:
    words = text.split()[:8]
    title = " ".join(words)
    return title[:80] if len(title) > 80 else title


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=List[SessionInfo])
def list_sessions(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user_id)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )
    return sessions


@router.post("", response_model=SessionInfo)
def create_session(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    session = ChatSession(user_id=user_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/{session_id}", response_model=SessionDetail)
def get_session(
    session_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    limit: int = Query(default=100, le=200, description="Max messages to return"),
    offset: int = Query(default=0, ge=0, description="Skip N oldest messages"),
):
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id, ChatSession.user_id == user_id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    total = db.query(Message).filter(Message.session_id == session_id).count()
    msgs = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.created_at)
        .offset(offset)
        .limit(limit)
        .all()
    )
    def _msg_out(m: Message) -> MessageOut:
        sources: Optional[List[str]] = None
        if m.sources:
            try:
                sources = _json.loads(m.sources)
            except Exception:
                pass
        return MessageOut(
            id=m.id, role=m.role, content=m.content,
            sources=sources, created_at=m.created_at,
        )

    return SessionDetail(
        id=session.id,
        title=session.title,
        messages=[_msg_out(m) for m in msgs],
        total_messages=total,
    )


@router.patch("/{session_id}", response_model=SessionInfo)
def rename_session(
    session_id: int,
    req: RenameRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id, ChatSession.user_id == user_id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.title = req.title[:200]
    db.commit()
    db.refresh(session)
    return session


@router.delete("/{session_id}")
def delete_session(
    session_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id, ChatSession.user_id == user_id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    db.delete(session)
    db.commit()
    return {"message": "Session deleted"}


@router.post("/{session_id}/messages")
async def send_message(
    session_id: int,
    req: ChatRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    settings = get_settings()

    session = db.query(ChatSession).filter(
        ChatSession.id == session_id, ChatSession.user_id == user_id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Retrieve RAG context
    rag_sources: List[str] = []
    try:
        query_emb = await ollama_client.embed(req.message)
        rag_results = await qdrant_service.search(
            query_emb, user_id, settings.rag_top_k, query_text=req.message
        )
        def _source_label(r: dict) -> str:
            label = r["filename"]
            if r.get("upload_date"):
                label += f" | Uploaded: {r['upload_date'][:10]}"
            return label

        # Only inject RAG context when at least one chunk is genuinely relevant.
        # Keyword-supplement hits have score=1.0 by convention; for vector hits
        # a score below 0.50 means the query likely has nothing to do with the
        # indexed documents (e.g. casual greetings).
        RELEVANCE_THRESHOLD = 0.50
        relevant = [
            r for r in rag_results
            if r["text"] and (r["score"] >= RELEVANCE_THRESHOLD or r["score"] == 1.0)
        ]

        rag_context = "\n\n---\n\n".join(
            f"[{_source_label(r)}]\n{r['text']}" for r in relevant
        )
        # Collect unique source filenames (preserve first-seen order)
        seen: set = set()
        for r in relevant:
            fn = r.get("filename", "")
            if fn and fn not in seen:
                seen.add(fn)
                rag_sources.append(fn)
    except Exception:
        rag_context = ""

    # Capture history BEFORE saving the new user message (used for auto-title check)
    is_first_message = len(session.messages) == 0

    # Build history and Ollama messages
    history = list(session.messages)
    ollama_msgs = _build_ollama_messages(history, rag_context, req.message)

    # Save user message using the request-scoped session
    user_msg = Message(session_id=session_id, role="user", content=req.message)
    db.add(user_msg)
    if is_first_message:
        session.title = _auto_title(req.message)
    db.commit()

    # Stream response — opens its OWN DB session so it runs safely after
    # FastAPI's dependency teardown has closed the request-scoped `db`.
    assistant_chunks: list[str] = []

    async def generate():
        try:
            async for token in ollama_client.chat_stream(ollama_msgs):
                assistant_chunks.append(token)
                yield f"data: {_json.dumps({'token': token})}\n\n"

            full_response = "".join(assistant_chunks)
        except Exception as exc:
            yield f"data: {_json.dumps({'error': str(exc)})}\n\n"
            full_response = "".join(assistant_chunks) or "[Error: response incomplete]"

        sources_json = _json.dumps(rag_sources) if rag_sources else None

        # Use a fresh session — the request-scoped `db` is already closed
        stream_db = SessionLocal()
        try:
            asst_msg = Message(
                session_id=session_id,
                role="assistant",
                content=full_response,
                sources=sources_json,
            )
            stream_db.add(asst_msg)
            stream_sess = stream_db.get(ChatSession, session_id)
            if stream_sess:
                stream_sess.updated_at = datetime.now(timezone.utc)
            stream_db.commit()
            stream_db.refresh(asst_msg)
            yield f"data: {_json.dumps({'done': True, 'message_id': asst_msg.id, 'sources': rag_sources})}\n\n"
        except Exception as exc:
            stream_db.rollback()
            yield f"data: {_json.dumps({'error': f'Persist failed: {exc}'})}\n\n"
        finally:
            stream_db.close()

    return StreamingResponse(generate(), media_type="text/event-stream")
