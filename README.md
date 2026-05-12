# Personal AI Knowledge Assistant

A single personal assistant for asking questions across the information you already live in: PDFs, Gmail, and notes. Instead of searching one app at a time, this project brings your knowledge sources into one searchable workspace and answers with grounded citations.

The core idea is simple: upload documents, sync email, and ask natural-language questions from one chat interface. The assistant retrieves the most relevant chunks from your private knowledge base, sends that context to an LLM, and returns a focused answer with source references.

## Why This Project Exists

Important information is usually scattered. A useful fact might be inside a class PDF, an old email thread, or a note you wrote weeks ago. This application turns those disconnected sources into one personal knowledge layer.

The USP of this project is the unified assistant experience: one application that can answer from your notes, PDFs, and email at the same time. You do not need to remember where something was stored before asking about it.

## What It Can Do

- Chat with your knowledge base through a clean web interface.
- Upload PDFs and index their content page by page.
- Connect Gmail with OAuth and sync inbox emails into the same vector store.
- Ask questions across all indexed sources, or filter by source.
- Stream AI answers in real time.
- Show citations with source type, filename or email subject, page/date metadata, relevance score, and excerpt.
- Track indexed knowledge counts for PDFs, Gmail, and notes/Notion.
- Switch between OpenAI-compatible providers and local Ollama models.

## Current Source Support

| Source | Status | Details |
| --- | --- | --- |
| PDFs | Implemented | Upload from the UI, extract text with `pdfplumber`, chunk by page, embed, and store in FAISS. |
| Gmail | Implemented | OAuth login, read-only Gmail access, inbox sync, deduplication by message ID, chunking, embedding, and citation metadata. |
| Notes / Notion | Planned foundation | The common data model, stats, filters, and citation formatting already include a `notion` source path. The loader and sync UI are the next implementation step. |

## How It Works

1. Data is ingested from a source such as a PDF or Gmail.
2. Each item is normalized into a common `KnowledgeChunk` format.
3. Text is split into overlapping chunks for better retrieval.
4. Chunks are embedded with `sentence-transformers/all-MiniLM-L6-v2`.
5. Embeddings are stored in a FAISS vector index with JSON metadata.
6. A user asks a question in the frontend.
7. The backend embeds the query, retrieves relevant chunks, and sends them to the configured LLM.
8. The answer is returned with citations so users can trace where the information came from.

## Architecture

```text
frontend/
  index.html        Chat UI, upload controls, Gmail controls, source filters
  app.js            API calls, streaming responses, citations, UI state
  style.css         Application styling

app.py              Flask API and application entry point

core/
  models.py         Shared KnowledgeChunk data model
  chunker.py        Text chunking utility
  embedder.py       SentenceTransformer embedding wrapper
  vector_store.py   FAISS index plus metadata persistence

loaders/
  pdf_loader.py     PDF text extraction and chunk creation
  gmail_loader.py   Gmail OAuth, fetching, parsing, and chunk creation

llm/
  openai_client.py  OpenAI-compatible chat and streaming client
  ollama_client.py  Local Ollama chat and streaming client
```

## API Overview

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Check backend status and active model/provider. |
| `GET` | `/api/stats` | Return total chunks and counts by source. |
| `POST` | `/api/upload` | Upload and ingest a PDF. |
| `POST` | `/api/query` | Ask a question against the knowledge base. Supports streaming and filters. |
| `DELETE` | `/api/source/<source>` | Delete all chunks for `pdf`, `gmail`, or `notion`. |
| `GET` | `/api/gmail/status` | Check whether Gmail is authenticated. |
| `POST` | `/api/gmail/auth` | Start Gmail OAuth flow. |
| `POST` | `/api/gmail/sync` | Fetch and index Gmail messages. |

### Images
![Home Page](<Screenshot 2026-05-12 154650.png>)

![query](<Screenshot 2026-05-12 154812.png>)

![sources](<Screenshot 2026-05-12 154828.png>)




## Setup

### 1. Create and activate a virtual environment

```bash
python -m venv venv
venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file from `.env.example`.

```bash
copy .env.example .env
```

For an OpenAI-compatible provider such as OpenRouter:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=your_api_key
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_MODEL=openai/gpt-oss-20b
```

For local Ollama:

```env
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3
OLLAMA_BASE_URL=http://localhost:11434
```

### 4. Run the app

```bash
python app.py
```

Open:

```text
http://localhost:5000
```

## Gmail Setup

Gmail sync uses read-only OAuth access.

1. Create a Google Cloud project.
2. Enable the Gmail API.
3. Create OAuth client credentials for a desktop app.
4. Download the credentials file as `credentials.json` in the project root.
5. Start the app and click `Connect Gmail`.
6. After authorization, click `Sync Emails`.

The token is saved locally at `data/gmail_token.json`.

## Example Questions

- "What are the main points from my uploaded PDFs?"
- "Summarize the email thread about the project deadline."
- "What did this document say about evaluation metrics?"
- "Find anything in my knowledge base about invoices."
- "Answer only from Gmail."
- "Answer only from PDFs."

## Data Storage

The app stores uploaded PDFs and vector data locally by default:

```text
data/uploads/
data/faiss_index/index.faiss
data/faiss_index/metadata.json
data/gmail_token.json
```

The Gmail integration requests read-only access and stores the OAuth token locally.

## Testing

Run the test suite with:

```bash
pytest
```

The existing tests cover chunking, the shared data model, PDF loader behavior, FAISS vector store operations, filtering, and stats.

## Roadmap

- Add a notes/Notion loader and sync workflow.
- Add richer metadata filters such as sender, date, note title, and document name.
- Persist chat history.
- Add source management tools for deleting individual files or email batches.
- Improve onboarding for provider and Gmail setup.

## Project Vision

This is more than a document chatbot. It is a personal assistance layer over your own knowledge. The long-term goal is for one assistant to understand your PDFs, your emails, and your notes together, then answer with enough context and citations that you can trust where the answer came from.
