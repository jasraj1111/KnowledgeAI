"""
Embedding engine – wraps sentence-transformers for encoding text.
Singleton pattern so the model is only loaded once per process.
"""
import logging
from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

_MODEL_NAME = "all-MiniLM-L6-v2"   # Fast, accurate, 384-dim embeddings
_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("Loading embedding model: %s", _MODEL_NAME)
        _model = SentenceTransformer(_MODEL_NAME)
        logger.info("Embedding model loaded.")
    return _model


def embed_texts(texts: List[str], batch_size: int = 64) -> np.ndarray:
    """
    Encode a list of strings into L2-normalised embedding vectors.

    Returns
    -------
    numpy.ndarray of shape (len(texts), 384), dtype float32.
    """
    model = get_model()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=len(texts) > 100,
        normalize_embeddings=True,   # cosine similarity via dot product
        convert_to_numpy=True,
    )
    return embeddings.astype(np.float32)


def embed_query(query: str) -> np.ndarray:
    """Encode a single query string (returns shape (384,))."""
    return embed_texts([query])[0]
