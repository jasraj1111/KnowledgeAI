"""
OpenAI-compatible LLM connector.

Works with any provider that exposes an OpenAI-compatible chat API:
  - OpenRouter  (https://openrouter.ai/api/v1)
  - Azure AI
  - Self-hosted vLLM / llama.cpp servers
  - OpenAI itself

Mirrors the interface of ollama_client so app.py can swap freely.
"""
import logging
from typing import Iterator, List, Tuple

from openai import OpenAI

from core.models import KnowledgeChunk

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt construction (shared with ollama_client)
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
f"[{i}] {source_label}\n{chunk.text}"
        )

    context_str = "\n\n---\n\n".join(context_parts) if context_parts else "No context found."

    prompt = (
        "You are a precise AI assistant.\n\n"

        "Rules:\n"
        "- Output ONLY the final answer.\n"
        "- Do NOT include reasoning, thinking, or planning text.\n"
        "- Do NOT include phrases like 'we need to answer'.\n"
        "- Use only the provided context.\n"
        "- Include citations like [1], [2].\n\n"

        "Format:\n"
        "<Answer>\n\n"
        "Sources: [numbers]\n\n"

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
# LLM calls
# ---------------------------------------------------------------------------

def generate_answer(
    query: str,
    context_chunks: List[Tuple[KnowledgeChunk, float]],
    model: str = "openai/gpt-oss-20b",
    base_url: str = "https://integrate.api.nvidia.com/v1",
    api_key: str = "",
) -> str:
    """
    Call the OpenAI-compatible API synchronously and return a clean answer.
    """
    prompt = _build_prompt(query, context_chunks)
    client = OpenAI(base_url=base_url, api_key=api_key)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,  # lower = more deterministic, cleaner output
            max_tokens=4096,
            top_p=1,
        )

        response_text = response.choices[0].message.content.strip()

        # ✅ Extract only final answer (remove reasoning / meta text)
        if "ANSWER:" in response_text:
            response_text = response_text.split("ANSWER:")[-1].strip()

        # ✅ Optional: remove unwanted meta phrases (extra safety)
        banned_phrases = [
            "we need to answer",
            "the question asks",
            "based on the context",
            "let us",
        ]

        cleaned_lines = []
        for line in response_text.split("\n"):
            if not any(p in line.lower() for p in banned_phrases):
                cleaned_lines.append(line)

        final_answer = "\n".join(cleaned_lines).strip()

        return final_answer

    except Exception as exc:
        logger.error("OpenAI API error: %s", exc)
        raise

def stream_answer(
    query: str,
    context_chunks: List[Tuple[KnowledgeChunk, float]],
    model: str = "openai/gpt-oss-20b",
    base_url: str = "https://integrate.api.nvidia.com/v1",
    api_key: str = "",
) -> Iterator[str]:
    """
    Call the OpenAI-compatible API with streaming and yield tokens one by one.

    Handles NVIDIA NIM's ``reasoning_content`` field alongside regular
    ``content`` so both reasoning and answer tokens are surfaced.
    """
    prompt = _build_prompt(query, context_chunks)
    client = OpenAI(base_url=base_url, api_key=api_key)

    try:
        stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=4096,
            top_p=1,
            stream=True,
        )
        for chunk in stream:
            if not getattr(chunk, "choices", None):
                continue

            delta = chunk.choices[0].delta

            if delta and delta.content:
                yield delta.content
    except Exception as exc:
        logger.error("OpenAI streaming error: %s", exc)
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
