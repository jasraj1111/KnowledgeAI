"""
Text chunking utilities shared across all ingestion sources.
"""
from typing import List


def chunk_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> List[str]:
    """
    Split *text* into overlapping token-approximate chunks.

    Uses word-level splitting as a lightweight approximation of token
    count (1 word ≈ 1.3 tokens on average).

    Parameters
    ----------
    text          : Raw text to split.
    chunk_size    : Target chunk length in *words*.
    chunk_overlap : Number of words to repeat across consecutive chunks.

    Returns
    -------
    List of non-empty text strings.
    """
    words = text.split()
    if not words:
        return []

    chunks: List[str] = []
    start = 0

    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])
        if chunk.strip():
            chunks.append(chunk)
        if end == len(words):
            break
        start += chunk_size - chunk_overlap

    return chunks
