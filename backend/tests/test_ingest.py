"""Unit tests for the ingest service (chunking and extraction)."""
from __future__ import annotations
import pytest
from app.services.ingest_service import chunk_text, extract_and_chunk, _split_text


# ---------------------------------------------------------------------------
# chunk_text
# ---------------------------------------------------------------------------

def test_chunk_text_basic():
    text = ("Indian Railways is one of the largest railway networks in the world. " * 30)
    chunks = chunk_text(text)
    assert len(chunks) >= 1
    for c in chunks:
        assert len(c.strip()) > 0


def test_chunk_text_filters_short_scraps():
    text = "a\n\n" + ("Indian Railways has a very large network spanning the entire country. " * 20)
    chunks = chunk_text(text)
    for c in chunks:
        assert len(c.strip()) > 80


def test_chunk_text_respects_size(monkeypatch):
    from app.core.config import get_settings
    s = get_settings()
    # Ensure no chunk goes more than chunk_size + overlap chars
    long_text = " ".join(["word"] * 5000)
    chunks = chunk_text(long_text)
    for c in chunks:
        assert len(c) <= s.chunk_size + s.chunk_overlap + 10  # +10 for sep chars


def test_chunk_overlap_shares_context():
    """Chunk N+1 should start with text from the end of chunk N (overlap)."""
    from app.core import config as cfg
    text = "AAAA " * 500   # 2500 chars of repeating word
    chunks = chunk_text(text)
    if len(chunks) >= 2:
        # End of chunk 0 should appear at start of chunk 1
        tail = chunks[0][-50:]
        head = chunks[1][:100]
        assert any(w in head for w in tail.split() if w), (
            "No overlap found between consecutive chunks"
        )


# ---------------------------------------------------------------------------
# extract_and_chunk (txt / md)
# ---------------------------------------------------------------------------

def test_extract_txt():
    content = b"Indian Railways freight classification covers many categories.\n" * 40
    chunks = extract_and_chunk("report.txt", content)
    assert len(chunks) >= 1


def test_extract_md():
    content = b"# Section 1\n\nPassenger services information.\n\n" * 20
    chunks = extract_and_chunk("guide.md", content)
    assert len(chunks) >= 1


def test_extract_unsupported_extension():
    with pytest.raises(ValueError, match="Unsupported"):
        extract_and_chunk("file.xlsx", b"data")


def test_empty_file_returns_no_chunks():
    # Very short content won't produce chunks after the 80-char filter
    chunks = extract_and_chunk("empty.txt", b"hi")
    assert chunks == []


# ---------------------------------------------------------------------------
# _split_text internals
# ---------------------------------------------------------------------------

def test_split_text_no_separators():
    text = "A" * 2000
    chunks = _split_text(text, chunk_size=500, chunk_overlap=50, separators=[""])
    for c in chunks:
        assert len(c) <= 500


def test_split_text_single_sep():
    text = "para one\n\npara two\n\npara three\n\n"
    chunks = _split_text(text, chunk_size=100, chunk_overlap=10, separators=["\n\n"])
    assert any("para one" in c for c in chunks)
    assert any("para two" in c for c in chunks)
