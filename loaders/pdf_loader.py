"""
PDF ingestion module.

Extracts text page-by-page using pdfplumber, chunks each page,
and returns a list of KnowledgeChunks ready for embedding.
"""
import logging
import uuid
from pathlib import Path
from typing import List

import pdfplumber

from core.chunker import chunk_text
from core.models import KnowledgeChunk

logger = logging.getLogger(__name__)


def load_pdf(
    file_path: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> List[KnowledgeChunk]:
    """
    Extract and chunk text from a PDF file.

    Parameters
    ----------
    file_path    : Absolute path to the PDF file.
    chunk_size   : Target chunk word-count.
    chunk_overlap: Word overlap between consecutive chunks.

    Returns
    -------
    List of KnowledgeChunks with source='pdf' and metadata:
        file_name, page (1-indexed), total_pages.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")

    chunks: List[KnowledgeChunk] = []

    with pdfplumber.open(file_path) as pdf:
        total_pages = len(pdf.pages)
        logger.info("Processing PDF: %s (%d pages)", path.name, total_pages)

        for page_num, page in enumerate(pdf.pages, start=1):
            raw_text = page.extract_text() or ""
            raw_text = raw_text.strip()

            if not raw_text:
                logger.debug("Page %d is empty, skipping.", page_num)
                continue

            page_chunks = chunk_text(raw_text, chunk_size, chunk_overlap)

            for i, text in enumerate(page_chunks):
                chunk = KnowledgeChunk(
                    text=text,
                    source="pdf",
                    chunk_id=str(uuid.uuid4()),
                    metadata={
                        "file_name": path.name,
                        "page": page_num,
                        "total_pages": total_pages,
                        "chunk_index": i,
                    },
                )
                chunks.append(chunk)

    logger.info(
        "PDF '%s' produced %d chunks across %d pages.",
        path.name, len(chunks), total_pages,
    )
    return chunks
