"""
Common data format for all knowledge sources.
Every ingested document is normalized to a KnowledgeChunk.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class KnowledgeChunk:
    """
    Unified representation of a text chunk from any source.

    Fields
    ------
    text        : The chunk's text content.
    source      : One of 'pdf', 'gmail', 'notion'.
    chunk_id    : Unique identifier for this chunk.
    metadata    : Source-specific metadata dict. Common keys:
                  - pdf   : file_name, page
                  - gmail : subject, sender, date, thread_id
                  - notion: page_title, created_time, page_id
    embedding   : Optional numpy vector (set after encoding).
    """
    text: str
    source: str                        # 'pdf' | 'gmail' | 'notion'
    chunk_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[Any] = None    # numpy ndarray once embedded

    def to_dict(self) -> Dict[str, Any]:
        """Serialize (without embedding) for JSON storage."""
        return {
            "text": self.text,
            "source": self.source,
            "chunk_id": self.chunk_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "KnowledgeChunk":
        return cls(
            text=d["text"],
            source=d["source"],
            chunk_id=d["chunk_id"],
            metadata=d.get("metadata", {}),
        )
