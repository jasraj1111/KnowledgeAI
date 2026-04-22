# Personal AI Knowledge Assistant Development Plan

## Goal Description

Build a modular Personal AI Knowledge Assistant that ingests data from three sources—PDF documents, Gmail, and Notion—into a unified knowledge base. The system will chunk, embed, and store data in a vector database (FAISS) and provide conversational Q&A via a local LLM (Ollama). The architecture emphasizes a **common data format** and **metadata‑driven retrieval** to enable source‑specific filtering and advanced query capabilities.

---

## User Review Required

> [!IMPORTANT]
> Please review the following open questions before we proceed. Your answers will shape key implementation choices.

---

## Proposed Changes

### Phase 1 – PDF Integration (Foundation)
- **Create PDF ingestion module** using `pdfplumber` (preferred) or `PyPDF2`.
- **Implement text extraction**, page‑level metadata, and chunking (e.g., 500‑token chunks).
- **Store chunks** in FAISS with metadata (`source: pdf`, `file_name`, `page`).
- **Expose a simple UI** (HTML/JS) to upload PDFs and trigger processing.
- **Add basic retrieval endpoint** that accepts a user query, performs similarity search, and returns the top‑k chunks with citations.

### Phase 2 – Gmail Integration
- **Set up Google Cloud project** and enable Gmail API.
- **Implement OAuth 2.0 flow** (local server or device code) using `google-auth-oauthlib`.
- **Create email fetcher** that pulls messages (subject, body, sender, date) and threads.
- **Normalize to common format** and chunk email bodies.
- **Push Gmail chunks** into the same FAISS index, preserving metadata (`source: gmail`, `subject`, `sender`, `date`).
- **Add UI controls** to trigger Gmail sync and display sync status.

### Phase 3 – Notion Integration
- **Create Notion integration** using `notion-client`.
- **Authenticate via Notion integration token** (user‑generated secret).
- **Fetch pages/blocks**, extract plain‑text content, and collect metadata (`source: notion`, `page_title`, `created_time`).
- **Chunk and embed** Notion content, add to FAISS.
- **Add UI for Notion sync** (button to start fetch, progress indicator).

### Phase 4 – Unified Retrieval & Advanced Features
- **Enhance retriever** to support metadata filtering (e.g., `source == 'gmail'` and `sender == 'boss@gmail.com'`).
- **Implement time‑based filters** (`date >= ...`).
- **Add source‑specific citation rendering** in the chat UI.
- **Introduce chat history persistence** (local JSON store).
- **Optional UI polish**: dark mode, glass‑morphism cards, smooth micro‑animations.

---

## Open Questions

> [!WARNING]
> - **Vector Store Preference**: Do you want to stick with FAISS or explore an alternative (e.g., Chroma, Milvus)?
> - **LLM Model**: Which Ollama model should we default to (Llama3, Mistral, or a custom one)?
> - **Authentication Method**: For Gmail, would you prefer a local web‑server OAuth flow or a device‑code flow?
> - **UI Stack**: Should the front‑end be a simple static HTML/JS page or a lightweight Vite/React app for richer interactivity?

---

## Verification Plan

### Automated Tests
- Unit tests for each loader (PDF, Gmail, Notion) verifying output shape and metadata.
- Integration test that runs a full ingestion pipeline and confirms that a query returns expected citations.
- CI script to lint Python (`ruff`) and run tests (`pytest`).

### Manual Verification
- Upload a sample PDF, run a query, and confirm answer + source citation.
- Perform Gmail sync, query for a known email subject, verify correct filtering.
- Sync Notion pages, query for a specific page title, check results.
- UI walkthrough: upload, sync, ask questions, view citations.

---

*This plan outlines the step‑by‑step roadmap, key decisions, and validation strategy. Please provide answers to the open questions so we can finalize the implementation details.*
