"""
FAISS-backed vector store with metadata persistence.

The index stores float32 embeddings; metadata (KnowledgeChunk fields
minus embedding) is persisted as a JSON sidecar file.
"""
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import faiss
import numpy as np

from core.models import KnowledgeChunk

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384   # all-MiniLM-L6-v2 output dimension


class VectorStore:
    """
    Manages a FAISS flat (exact) inner-product index alongside a
    JSON metadata store for chunk retrieval.

    Files on disk
    -------------
    <path>/index.faiss   – FAISS binary index
    <path>/metadata.json – List of chunk dicts (parallel to index rows)
    """

    def __init__(self, index_path: str):
        self.index_path = Path(index_path)
        self.index_path.mkdir(parents=True, exist_ok=True)

        self._faiss_file = self.index_path / "index.faiss"
        self._meta_file  = self.index_path / "metadata.json"

        self._index: faiss.IndexFlatIP = self._load_or_create_index()
        self._metadata: List[Dict[str, Any]] = self._load_metadata()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_or_create_index(self) -> faiss.IndexFlatIP:
        if self._faiss_file.exists():
            logger.info("Loading existing FAISS index from %s", self._faiss_file)
            return faiss.read_index(str(self._faiss_file))
        logger.info("Creating new FAISS FlatIP index (dim=%d)", EMBEDDING_DIM)
        return faiss.IndexFlatIP(EMBEDDING_DIM)

    def _load_metadata(self) -> List[Dict[str, Any]]:
        if self._meta_file.exists():
            with open(self._meta_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save(self):
        faiss.write_index(self._index, str(self._faiss_file))
        with open(self._meta_file, "w", encoding="utf-8") as f:
            json.dump(self._metadata, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def total_chunks(self) -> int:
        return self._index.ntotal

    def add_chunks(self, chunks: List[KnowledgeChunk]):
        """
        Embed and add a list of KnowledgeChunks to the index.
        The embeddings must already be set on each chunk.
        """
        if not chunks:
            return

        vectors = np.stack([c.embedding for c in chunks]).astype(np.float32)
        self._index.add(vectors)
        for chunk in chunks:
            self._metadata.append(chunk.to_dict())

        self._save()
        logger.info("Added %d chunks (total: %d)", len(chunks), self.total_chunks)

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[KnowledgeChunk, float]]:
        """
        Retrieve the top-k most similar chunks to *query_vector*.

        Parameters
        ----------
        query_vector : 1-D float32 array of shape (384,).
        top_k        : Number of results to return.
        filters      : Optional metadata equality filters,
                       e.g. {'source': 'gmail', 'sender': 'a@b.com'}.

        Returns
        -------
        List of (KnowledgeChunk, score) sorted by descending score.
        """
        if self._index.ntotal == 0:
            return []

        # Over-fetch when filtering to ensure we can fill top_k after pruning
        fetch_k = min(top_k * 10, self._index.ntotal) if filters else top_k
        query_vector = query_vector.reshape(1, -1).astype(np.float32)

        scores, indices = self._index.search(query_vector, fetch_k)
        scores, indices = scores[0], indices[0]

        results: List[Tuple[KnowledgeChunk, float]] = []
        for idx, score in zip(indices, scores):
            if idx == -1:
                continue
            chunk_dict = self._metadata[idx]
            chunk = KnowledgeChunk.from_dict(chunk_dict)

            # Apply metadata filters
            if filters and not self._matches(chunk.metadata, chunk.source, filters):
                continue

            results.append((chunk, float(score)))
            if len(results) >= top_k:
                break

        return results

    def _matches(
        self,
        metadata: Dict[str, Any],
        source: str,
        filters: Dict[str, Any],
    ) -> bool:
        """Return True if all filters match the chunk's metadata."""
        combined = {"source": source, **metadata}
        for key, value in filters.items():
            if combined.get(key) != value:
                return False
        return True

    def delete_by_source(self, source: str) -> int:
        """
        Remove all chunks from a given source (requires index rebuild).
        Returns number of chunks removed.
        """
        from core.embedder import embed_texts

        keep_indices = [
            i for i, m in enumerate(self._metadata) if m["source"] != source
        ]
        removed = len(self._metadata) - len(keep_indices)
        if removed == 0:
            return 0

        kept_meta = [self._metadata[i] for i in keep_indices]
        kept_texts = [m["text"] for m in kept_meta]

        # Rebuild index
        new_index = faiss.IndexFlatIP(EMBEDDING_DIM)
        if kept_texts:
            vectors = embed_texts(kept_texts)
            new_index.add(vectors)

        self._index = new_index
        self._metadata = kept_meta
        self._save()
        logger.info("Removed %d chunks from source '%s'", removed, source)
        return removed

    def get_stats(self) -> Dict[str, Any]:
        """Return counts grouped by source."""
        counts: Dict[str, int] = {}
        for m in self._metadata:
            counts[m["source"]] = counts.get(m["source"], 0) + 1
        return {"total": self.total_chunks, "by_source": counts}
