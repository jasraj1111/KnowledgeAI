"""
Flask REST API for the Personal AI Knowledge Assistant.

Endpoints
---------
POST /api/upload          – Upload and ingest a PDF
GET  /api/stats           – Vector store statistics
POST /api/query           – Ask a question (RAG pipeline)
DELETE /api/source/<src>  – Remove all chunks from a source
GET  /api/health          – Health check
"""
import json
import logging
import os
import uuid
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

# ── Load env ──────────────────────────────────────────────────────────────────
load_dotenv()

UPLOAD_FOLDER    = os.getenv("UPLOAD_FOLDER", "data/uploads")
FAISS_INDEX_PATH = os.getenv("FAISS_INDEX_PATH", "data/faiss_index")
OLLAMA_MODEL     = os.getenv("OLLAMA_MODEL", "llama3")
OLLAMA_BASE_URL  = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
CHUNK_SIZE       = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP    = int(os.getenv("CHUNK_OVERLAP", "50"))
TOP_K            = int(os.getenv("TOP_K_RESULTS", "5"))

Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── App & lazy imports (heavy ml libs loaded on first use) ────────────────────
app = Flask(__name__, static_folder="frontend", static_url_path="")
CORS(app)

# Lazy-init singletons
_vector_store = None


def get_vector_store():
    global _vector_store
    if _vector_store is None:
        from core.vector_store import VectorStore
        _vector_store = VectorStore(FAISS_INDEX_PATH)
    return _vector_store


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("frontend", "index.html")


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "model": OLLAMA_MODEL})


@app.route("/api/stats")
def stats():
    vs = get_vector_store()
    return jsonify(vs.get_stats())


@app.route("/api/upload", methods=["POST"])
def upload_pdf():
    """
    Upload a PDF file and ingest it into the vector store.
    Accepts multipart/form-data with field 'file'.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are supported"}), 400

    # Save to upload folder with a unique prefix to avoid collisions
    safe_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    save_path = os.path.join(UPLOAD_FOLDER, safe_name)
    file.save(save_path)
    logger.info("Saved uploaded PDF: %s", save_path)

    try:
        from loaders.pdf_loader import load_pdf
        from core.embedder import embed_texts

        chunks = load_pdf(save_path, CHUNK_SIZE, CHUNK_OVERLAP)
        if not chunks:
            return jsonify({"error": "No text could be extracted from the PDF"}), 422

        texts = [c.text for c in chunks]
        embeddings = embed_texts(texts)
        for chunk, emb in zip(chunks, embeddings):
            chunk.embedding = emb

        vs = get_vector_store()
        vs.add_chunks(chunks)

        return jsonify({
            "success": True,
            "file_name": file.filename,
            "chunks_added": len(chunks),
            "total_chunks": vs.total_chunks,
        })

    except Exception as exc:
        logger.exception("Error processing PDF")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/query", methods=["POST"])
def query():
    """
    Ask a question against the knowledge base.

    Body (JSON)
    -----------
    {
        "query": "What is ...",
        "top_k": 5,                // optional
        "filters": {"source": "pdf"}  // optional metadata filters
    }
    """
    body = request.get_json(silent=True) or {}
    user_query = body.get("query", "").strip()
    if not user_query:
        return jsonify({"error": "query field is required"}), 400

    top_k   = int(body.get("top_k", TOP_K))
    filters = body.get("filters") or None

    try:
        from core.embedder import embed_query
        from llm.ollama_client import generate_answer, format_citations

        vs = get_vector_store()

        if vs.total_chunks == 0:
            return jsonify({
                "answer": "The knowledge base is empty. Please upload some documents first.",
                "citations": [],
            })

        q_vec   = embed_query(user_query)
        results = vs.search(q_vec, top_k=top_k, filters=filters)

        if not results:
            return jsonify({
                "answer": "No relevant documents found for your query.",
                "citations": [],
            })

        answer    = generate_answer(user_query, results, OLLAMA_MODEL, OLLAMA_BASE_URL)
        citations = format_citations(results)

        return jsonify({"answer": answer, "citations": citations})

    except Exception as exc:
        logger.exception("Error during query")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/source/<source>", methods=["DELETE"])
def delete_source(source: str):
    """Remove all chunks belonging to a given source."""
    allowed = {"pdf", "gmail", "notion"}
    if source not in allowed:
        return jsonify({"error": f"Unknown source '{source}'"}), 400

    try:
        vs = get_vector_store()
        removed = vs.delete_by_source(source)
        return jsonify({"success": True, "removed": removed, "source": source})
    except Exception as exc:
        logger.exception("Error deleting source")
        return jsonify({"error": str(exc)}), 500


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Starting Knowledge Assistant API on http://localhost:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)
