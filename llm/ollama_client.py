"""
Ollama LLM connector.

Builds a RAG prompt from retrieved chunks and streams or synchronously
returns the model's answer.
"""
import logging
from typing import Iterator, List, Tuple

import ollama

from core.models import KnowledgeChunk

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _build_prompt(
    query: str,
    context_chunks: List[Tuple[KnowledgeChunk, float]],
) -> str:
    """
    Assemble a RAG prompt that includes retrieved context and citations.
    """
    context_parts = []
    for i, (chunk, score) in enumerate(context_chunks, start=1):
        source_label = _format_citation(chunk)
        context_parts.append(
            f"[{i}] Source: {source_label}\n"
            f"Relevance: {score:.3f}\n"
            f"Content: {chunk.text}"
        )

    context_str = "\n\n---\n\n".join(context_parts) if context_parts else "No context found."

    prompt = (
        "You are a knowledgeable AI assistant. Use ONLY the provided context "
        "to answer the question. If the context doesn't contain enough "
        "information, say so clearly. Always cite the source number(s) you "
        "used in your answer.\n\n"
        f"CONTEXT:\n{context_str}\n\n"
        f"QUESTION: {query}\n\n"
        "ANSWER:"
    )
    return prompt


def _format_citation(chunk: KnowledgeChunk) -> str:
    """Human-readable citation string for a chunk."""
    meta = chunk.metadata
    if chunk.source == "pdf":
        return f"PDF '{meta.get('file_name', 'unknown')}', page {meta.get('page', '?')}"
    if chunk.source == "gmail":
        return (
            f"Email from {meta.get('sender', '?')} "
            f"re: '{meta.get('subject', '?')}' "
            f"({meta.get('date', '?')})"
        )
    if chunk.source == "notion":
        return f"Notion page '{meta.get('page_title', 'unknown')}'"
    return f"{chunk.source} document"


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def generate_answer(
    query: str,
    context_chunks: List[Tuple[KnowledgeChunk, float]],
    model: str = "llama3",
    base_url: str = "http://localhost:11434",
) -> str:
    """
    Call Ollama synchronously and return the complete answer string.
    """
    prompt = _build_prompt(query, context_chunks)
    client = ollama.Client(host=base_url)

    try:
        response = client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response["message"]["content"]
    except Exception as exc:
        logger.error("Ollama error: %s", exc)
        raise


def stream_answer(
    query: str,
    context_chunks: List[Tuple[KnowledgeChunk, float]],
    model: str = "llama3",
    base_url: str = "http://localhost:11434",
) -> Iterator[str]:
    """
    Call Ollama with streaming and yield text tokens one by one.
    """
    prompt = _build_prompt(query, context_chunks)
    client = ollama.Client(host=base_url)

    try:
        for chunk in client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        ):
            token = chunk.get("message", {}).get("content", "")
            if token:
                yield token
    except Exception as exc:
        logger.error("Ollama streaming error: %s", exc)
        raise


def format_citations(
    context_chunks: List[Tuple[KnowledgeChunk, float]],
) -> List[dict]:
    """Return structured citation objects for the API response."""
    citations = []
    for i, (chunk, score) in enumerate(context_chunks, start=1):
        citations.append({
            "index": i,
            "source": chunk.source,
            "citation": _format_citation(chunk),
            "score": round(float(score), 4),
            "metadata": chunk.metadata,
            "excerpt": chunk.text[:300] + ("..." if len(chunk.text) > 300 else ""),
        })
    return citations
