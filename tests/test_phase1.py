"""Unit tests for Phase 1 – PDF Integration."""
import os
import sys
import tempfile
import uuid
import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Chunker tests ──────────────────────────────────────────────────────────────

from core.chunker import chunk_text

def test_chunk_basic():
    text = " ".join([f"word{i}" for i in range(1000)])
    chunks = chunk_text(text, chunk_size=100, chunk_overlap=10)
    assert len(chunks) > 5
    for c in chunks:
        words = c.split()
        assert len(words) <= 110   # allow slight overshoot

def test_chunk_empty():
    assert chunk_text("") == []

def test_chunk_short_text():
    text = "Hello world"
    chunks = chunk_text(text, chunk_size=500)
    assert chunks == ["Hello world"]

def test_chunk_overlap():
    words = [f"w{i}" for i in range(20)]
    text = " ".join(words)
    chunks = chunk_text(text, chunk_size=10, chunk_overlap=3)
    # Second chunk should share last 3 words of first chunk
    first_end   = chunks[0].split()[-3:]
    second_start= chunks[1].split()[:3]
    assert first_end == second_start


# ── Model tests ────────────────────────────────────────────────────────────────

from core.models import KnowledgeChunk

def test_chunk_to_dict():
    chunk = KnowledgeChunk(
        text="Hello",
        source="pdf",
        chunk_id="123",
        metadata={"file_name": "test.pdf", "page": 1},
    )
    d = chunk.to_dict()
    assert d["text"] == "Hello"
    assert d["source"] == "pdf"
    assert d["metadata"]["page"] == 1
    assert "embedding" not in d

def test_chunk_round_trip():
    original = KnowledgeChunk(
        text="Sample text",
        source="gmail",
        chunk_id=str(uuid.uuid4()),
        metadata={"subject": "Test Email"},
    )
    restored = KnowledgeChunk.from_dict(original.to_dict())
    assert restored.text == original.text
    assert restored.source == original.source
    assert restored.metadata == original.metadata


# ── PDF loader tests ───────────────────────────────────────────────────────────

def _create_minimal_pdf(path: str):
    """Create a tiny valid PDF using raw bytes (no external library)."""
    content = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 44>>
stream
BT /F1 12 Tf 72 720 Td (Hello World PDF) Tj ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000266 00000 n 
0000000360 00000 n 
trailer<</Size 6/Root 1 0 R>>
startxref
441
%%EOF"""
    with open(path, "wb") as f:
        f.write(content)


def test_pdf_loader_missing_file():
    from loaders.pdf_loader import load_pdf
    with pytest.raises(FileNotFoundError):
        load_pdf("/nonexistent/path/file.pdf")


def test_pdf_loader_output_shape():
    """Ensure loader returns KnowledgeChunks with correct metadata keys."""
    from loaders.pdf_loader import load_pdf

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        tmp_path = f.name

    try:
        _create_minimal_pdf(tmp_path)
        chunks = load_pdf(tmp_path, chunk_size=50, chunk_overlap=5)
        # pdfplumber may or may not extract text from the raw PDF
        # but the loader must not crash and must return a list
        assert isinstance(chunks, list)
        for chunk in chunks:
            assert chunk.source == "pdf"
            assert "file_name" in chunk.metadata
            assert "page" in chunk.metadata
            assert chunk.text.strip()
    finally:
        os.unlink(tmp_path)


# ── Vector store tests (in-memory) ────────────────────────────────────────────

import numpy as np

def test_vector_store_add_and_search(tmp_path):
    from core.vector_store import VectorStore, EMBEDDING_DIM

    vs = VectorStore(str(tmp_path))
    assert vs.total_chunks == 0

    chunk = KnowledgeChunk(
        text="Artificial intelligence is changing the world.",
        source="pdf",
        chunk_id=str(uuid.uuid4()),
        metadata={"file_name": "ai.pdf", "page": 1},
        embedding=np.random.rand(EMBEDDING_DIM).astype(np.float32),
    )
    vs.add_chunks([chunk])
    assert vs.total_chunks == 1

    # Search with a random vector
    q = np.random.rand(EMBEDDING_DIM).astype(np.float32)
    results = vs.search(q, top_k=1)
    assert len(results) == 1
    assert results[0][0].source == "pdf"


def test_vector_store_filter(tmp_path):
    from core.vector_store import VectorStore, EMBEDDING_DIM

    vs = VectorStore(str(tmp_path))

    for src in ["pdf", "gmail", "notion"]:
        chunk = KnowledgeChunk(
            text=f"Content from {src}",
            source=src,
            chunk_id=str(uuid.uuid4()),
            metadata={},
            embedding=np.random.rand(EMBEDDING_DIM).astype(np.float32),
        )
        vs.add_chunks([chunk])

    q = np.random.rand(EMBEDDING_DIM).astype(np.float32)
    pdf_results = vs.search(q, top_k=5, filters={"source": "pdf"})
    assert all(r[0].source == "pdf" for r in pdf_results)


def test_vector_store_stats(tmp_path):
    from core.vector_store import VectorStore, EMBEDDING_DIM

    vs = VectorStore(str(tmp_path))
    for src in ["pdf", "pdf", "gmail"]:
        chunk = KnowledgeChunk(
            text="text",
            source=src,
            chunk_id=str(uuid.uuid4()),
            metadata={},
            embedding=np.random.rand(EMBEDDING_DIM).astype(np.float32),
        )
        vs.add_chunks([chunk])

    stats = vs.get_stats()
    assert stats["total"] == 3
    assert stats["by_source"]["pdf"] == 2
    assert stats["by_source"]["gmail"] == 1
