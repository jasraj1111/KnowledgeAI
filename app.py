"""
Flask REST API for the Personal AI Knowledge Assistant.

Endpoints
---------
POST   /api/upload          – Upload and ingest a PDF
GET    /api/stats           – Vector store statistics
POST   /api/query           – Ask a question (RAG pipeline, supports streaming)
DELETE /api/source/<src>    – Remove all chunks from a source
GET    /api/health          – Health check
GET    /api/gmail/status    – Gmail auth status
POST   /api/gmail/auth      – Start Gmail OAuth flow
POST   /api/gmail/sync      – Sync emails into knowledge base
"""
import json
import logging
import os
import threading
import uuid
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

# ── Load env ──────────────────────────────────────────────────────────────────
load_dotenv()

UPLOAD_FOLDER    = os.getenv("UPLOAD_FOLDER", "data/uploads")
FAISS_INDEX_PATH = os.getenv("FAISS_INDEX_PATH", "data/faiss_index")
CHUNK_SIZE       = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP    = int(os.getenv("CHUNK_OVERLAP", "50"))
TOP_K            = int(os.getenv("TOP_K_RESULTS", "5"))

# ── Gmail config ──────────────────────────────────────────────────────────────
GMAIL_CREDENTIALS = os.getenv("GMAIL_CREDENTIALS_PATH", "credentials.json")
GMAIL_TOKEN       = os.getenv("GMAIL_TOKEN_PATH", "data/gmail_token.json")
GMAIL_MAX_RESULTS = int(os.getenv("GMAIL_MAX_RESULTS", "50"))

# ── LLM Provider config ──────────────────────────────────────────────────────
LLM_PROVIDER    = os.getenv("LLM_PROVIDER", "openai")          # "ollama" or "openai"

# Ollama settings (used when LLM_PROVIDER=ollama)
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# OpenAI-compatible settings (used when LLM_PROVIDER=openai)
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "openai/gpt-oss-20b")

Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
logger.info("LLM Provider: %s", LLM_PROVIDER)

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


def _get_llm_functions():
    """Return (generate_answer, stream_answer, format_citations) for the active provider."""
    if LLM_PROVIDER == "ollama":
        from llm.ollama_client import generate_answer, stream_answer, format_citations
        return generate_answer, stream_answer, format_citations
    else:
        from llm.openai_client import generate_answer, stream_answer, format_citations
        return generate_answer, stream_answer, format_citations


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("frontend", "index.html")


@app.route("/api/health")
def health():
    model = OPENAI_MODEL if LLM_PROVIDER == "openai" else OLLAMA_MODEL
    return jsonify({"status": "ok", "model": model, "provider": LLM_PROVIDER})


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
        "filters": {"source": "pdf"},  // optional metadata filters
        "stream": true              // optional – use SSE streaming
    }
    """
    body = request.get_json(silent=True) or {}
    user_query = body.get("query", "").strip()
    if not user_query:
        return jsonify({"error": "query field is required"}), 400

    top_k   = int(body.get("top_k", TOP_K))
    filters = body.get("filters") or None
    use_stream = body.get("stream", True)  # default to streaming

    try:
        from core.embedder import embed_query

        generate_answer, stream_answer, format_citations = _get_llm_functions()

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

        citations = format_citations(results)

        # ── Streaming response (SSE) ──────────────────────────────────────
        if use_stream:
            def event_stream():
                try:
                    if LLM_PROVIDER == "ollama":
                        token_gen = stream_answer(
                            user_query, results,
                            model=OLLAMA_MODEL,
                            base_url=OLLAMA_BASE_URL,
                        )
                    else:
                        token_gen = stream_answer(
                            user_query, results,
                            model=OPENAI_MODEL,
                            base_url=OPENAI_BASE_URL,
                            api_key=OPENAI_API_KEY,
                        )

                    for token in token_gen:
                        data = json.dumps({"token": token})
                        yield f"data: {data}\n\n"

                    # Final event with citations
                    done_data = json.dumps({"done": True, "citations": citations})
                    yield f"data: {done_data}\n\n"

                except Exception as exc:
                    logger.exception("Streaming error")
                    err_data = json.dumps({"error": str(exc)})
                    yield f"data: {err_data}\n\n"

            return Response(
                event_stream(),
                mimetype="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )

        # ── Non-streaming response ────────────────────────────────────────
        if LLM_PROVIDER == "ollama":
            answer = generate_answer(
                user_query, results,
                model=OLLAMA_MODEL,
                base_url=OLLAMA_BASE_URL,
            )
        else:
            answer = generate_answer(
                user_query, results,
                model=OPENAI_MODEL,
                base_url=OPENAI_BASE_URL,
                api_key=OPENAI_API_KEY,
            )

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


# ── Gmail routes ──────────────────────────────────────────────────────────────

@app.route("/api/gmail/status")
def gmail_status():
    """Check whether the user has authenticated Gmail."""
    from loaders.gmail_loader import is_authenticated
    return jsonify({"authenticated": is_authenticated(GMAIL_TOKEN)})


@app.route("/api/gmail/auth", methods=["POST"])
def gmail_auth():
    """
    Start the Gmail OAuth2 flow.

    Opens a local browser for user consent. The token is saved
    automatically once the user authorises the app.
    """
    if not os.path.exists(GMAIL_CREDENTIALS):
        return jsonify({
            "error": "credentials.json not found. Please download it from Google Cloud Console."
        }), 400

    try:
        from loaders.gmail_loader import get_gmail_credentials

        # Run the OAuth flow (opens browser automatically)
        def _run_auth():
            try:
                get_gmail_credentials(GMAIL_CREDENTIALS, GMAIL_TOKEN)
                logger.info("Gmail OAuth completed successfully.")
            except Exception as exc:
                logger.exception("Gmail OAuth failed: %s", exc)

        # Run in a thread so the HTTP response returns immediately
        auth_thread = threading.Thread(target=_run_auth, daemon=True)
        auth_thread.start()

        return jsonify({
            "success": True,
            "message": "OAuth flow started – check your browser to authorise.",
        })

    except Exception as exc:
        logger.exception("Gmail auth error")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/gmail/sync", methods=["POST"])
def gmail_sync():
    """
    Fetch emails from Gmail, chunk, embed, and add to the vector store.
    Deduplicates against already-ingested message IDs.
    """
    from loaders.gmail_loader import is_authenticated, load_gmail

    if not is_authenticated(GMAIL_TOKEN):
        return jsonify({"error": "Gmail not authenticated. Connect Gmail first."}), 401

    try:
        from core.embedder import embed_texts

        # Collect existing Gmail message IDs for deduplication
        vs = get_vector_store()
        existing_ids = set()
        for m in vs._metadata:
            if m.get("source") == "gmail":
                mid = m.get("metadata", {}).get("message_id")
                if mid:
                    existing_ids.add(mid)

        chunks = load_gmail(
            credentials_path=GMAIL_CREDENTIALS,
            token_path=GMAIL_TOKEN,
            max_results=GMAIL_MAX_RESULTS,
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            existing_message_ids=existing_ids,
        )

        if not chunks:
            return jsonify({
                "success": True,
                "message": "No new emails to sync.",
                "chunks_added": 0,
                "emails_processed": 0,
            })

        texts = [c.text for c in chunks]
        embeddings = embed_texts(texts)
        for chunk, emb in zip(chunks, embeddings):
            chunk.embedding = emb

        vs.add_chunks(chunks)

        # Count unique emails
        unique_emails = len({c.metadata["message_id"] for c in chunks})

        return jsonify({
            "success": True,
            "emails_processed": unique_emails,
            "chunks_added": len(chunks),
            "total_chunks": vs.total_chunks,
        })

    except Exception as exc:
        logger.exception("Gmail sync error")
        return jsonify({"error": str(exc)}), 500


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Starting Knowledge Assistant API on http://localhost:5000")
    logger.info("Provider: %s | Model: %s", LLM_PROVIDER,
                OPENAI_MODEL if LLM_PROVIDER == "openai" else OLLAMA_MODEL)
    app.run(
        debug=True,
        host="0.0.0.0",
        port=5000,
        use_reloader=False,        # watchdog on Windows restarts when torch loads
    )
