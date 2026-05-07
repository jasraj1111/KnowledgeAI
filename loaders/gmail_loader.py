"""
Gmail ingestion module.

Authenticates via OAuth 2.0, fetches emails from the user's inbox,
extracts body text, chunks it, and returns KnowledgeChunks ready
for embedding – mirroring the pdf_loader interface.
"""
import base64
import logging
import os
import re
import uuid
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from core.chunker import chunk_text
from core.models import KnowledgeChunk

logger = logging.getLogger(__name__)

# Read-only access to Gmail
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


# ---------------------------------------------------------------------------
# HTML → plain-text helper
# ---------------------------------------------------------------------------

class _HTMLStripper(HTMLParser):
    """Minimal HTML-to-text converter."""

    def __init__(self):
        super().__init__()
        self._text = StringIO()
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True
        elif tag in ("br", "p", "div", "li", "tr"):
            self._text.write("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self._text.write(data)

    def get_text(self) -> str:
        return self._text.getvalue()


def _html_to_text(html: str) -> str:
    """Strip HTML tags and return plain text."""
    stripper = _HTMLStripper()
    stripper.feed(html)
    text = stripper.get_text()
    # Collapse excessive whitespace / blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# OAuth helpers
# ---------------------------------------------------------------------------

def get_gmail_credentials(
    credentials_path: str = "credentials.json",
    token_path: str = "data/gmail_token.json",
) -> Credentials:
    """
    Load or create OAuth2 credentials for Gmail.

    On first run, opens a browser for user authorisation and saves
    the resulting refresh token to *token_path*.
    """
    creds: Optional[Credentials] = None

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired Gmail token.")
            creds.refresh(Request())
        else:
            logger.info("Starting Gmail OAuth flow (browser will open).")
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_path, SCOPES
            )
            creds = flow.run_local_server(
                port=0,            # auto-pick port to match redirect_uris
                prompt="consent",
                access_type="offline",
            )

        # Persist the token for next time
        Path(token_path).parent.mkdir(parents=True, exist_ok=True)
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        logger.info("Gmail token saved to %s", token_path)

    return creds


def get_gmail_service(
    credentials_path: str = "credentials.json",
    token_path: str = "data/gmail_token.json",
):
    """Build and return a Gmail API service resource."""
    creds = get_gmail_credentials(credentials_path, token_path)
    return build("gmail", "v1", credentials=creds)


def is_authenticated(token_path: str = "data/gmail_token.json") -> bool:
    """Return True if a valid (or refreshable) Gmail token exists."""
    if not os.path.exists(token_path):
        return False
    try:
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        if creds.valid:
            return True
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            return True
    except Exception:
        return False
    return False


# ---------------------------------------------------------------------------
# Email fetching & parsing
# ---------------------------------------------------------------------------

def _get_header(headers: List[dict], name: str) -> str:
    """Extract a header value by name from the Gmail message headers."""
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _decode_body(data: str) -> str:
    """Base64url-decode a Gmail message body part."""
    padded = data + "=" * (4 - len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def _extract_body(payload: dict) -> str:
    """
    Recursively walk MIME parts to extract body text.
    Prefers text/plain; falls back to text/html → stripped.
    """
    mime_type = payload.get("mimeType", "")

    # Simple single-part message
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        return _decode_body(data) if data else ""

    if mime_type == "text/html":
        data = payload.get("body", {}).get("data", "")
        return _html_to_text(_decode_body(data)) if data else ""

    # Multipart – recurse into parts
    parts = payload.get("parts", [])
    plain_text = ""
    html_text = ""

    for part in parts:
        part_mime = part.get("mimeType", "")
        if part_mime == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                plain_text += _decode_body(data)
        elif part_mime == "text/html":
            data = part.get("body", {}).get("data", "")
            if data:
                html_text += _html_to_text(_decode_body(data))
        elif part_mime.startswith("multipart/"):
            # Nested multipart (e.g. multipart/alternative inside multipart/mixed)
            nested = _extract_body(part)
            if nested:
                plain_text += nested

    return plain_text if plain_text else html_text


def _parse_date(date_str: str) -> str:
    """Parse an RFC 2822 date into ISO format (YYYY-MM-DD)."""
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return date_str[:10] if len(date_str) >= 10 else date_str


def parse_email(message: dict) -> Dict[str, Any]:
    """
    Parse a raw Gmail API message into a clean dict.

    Returns
    -------
    {
        "message_id": str,
        "thread_id": str,
        "subject": str,
        "sender": str,
        "date": str (YYYY-MM-DD),
        "labels": List[str],
        "body": str,
    }
    """
    payload = message.get("payload", {})
    headers = payload.get("headers", [])

    subject = _get_header(headers, "Subject") or "(no subject)"
    sender = _get_header(headers, "From") or "unknown"
    date_raw = _get_header(headers, "Date") or ""

    body = _extract_body(payload).strip()

    return {
        "message_id": message["id"],
        "thread_id": message.get("threadId", ""),
        "subject": subject,
        "sender": sender,
        "date": _parse_date(date_raw),
        "labels": message.get("labelIds", []),
        "body": body,
    }


def fetch_emails(
    service,
    max_results: int = 50,
    label_ids: Optional[List[str]] = None,
) -> List[dict]:
    """
    Fetch up to *max_results* emails from the user's Gmail.

    Returns a list of parsed email dicts.
    """
    if label_ids is None:
        label_ids = ["INBOX"]

    logger.info("Fetching up to %d emails (labels=%s)…", max_results, label_ids)

    # Step 1: Get message IDs
    results = (
        service.users()
        .messages()
        .list(userId="me", labelIds=label_ids, maxResults=max_results)
        .execute()
    )
    message_ids = results.get("messages", [])
    logger.info("Found %d message IDs.", len(message_ids))

    # Step 2: Fetch full message for each ID
    emails: List[dict] = []
    for i, msg_stub in enumerate(message_ids):
        try:
            full_msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_stub["id"], format="full")
                .execute()
            )
            parsed = parse_email(full_msg)
            if parsed["body"]:  # skip empty emails
                emails.append(parsed)
        except Exception as exc:
            logger.warning("Failed to fetch message %s: %s", msg_stub["id"], exc)

    logger.info("Parsed %d emails with body text.", len(emails))
    return emails


# ---------------------------------------------------------------------------
# Main loader (mirrors pdf_loader.load_pdf interface)
# ---------------------------------------------------------------------------

def load_gmail(
    credentials_path: str = "credentials.json",
    token_path: str = "data/gmail_token.json",
    max_results: int = 50,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    existing_message_ids: Optional[set] = None,
) -> List[KnowledgeChunk]:
    """
    Fetch Gmail emails and return chunked KnowledgeChunks.

    Parameters
    ----------
    credentials_path : Path to the OAuth2 client credentials JSON.
    token_path       : Path where the user's refresh token is stored.
    max_results      : Maximum number of emails to fetch.
    chunk_size       : Target chunk word-count.
    chunk_overlap    : Word overlap between consecutive chunks.
    existing_message_ids : Set of message_ids already in the vector store
                           (used for deduplication).

    Returns
    -------
    List of KnowledgeChunks with source='gmail'.
    """
    service = get_gmail_service(credentials_path, token_path)
    emails = fetch_emails(service, max_results=max_results)

    if existing_message_ids is None:
        existing_message_ids = set()

    chunks: List[KnowledgeChunk] = []
    skipped = 0

    for email in emails:
        # Deduplication: skip emails already ingested
        if email["message_id"] in existing_message_ids:
            skipped += 1
            continue

        # Prepend subject to body for better context in search
        full_text = f"Subject: {email['subject']}\n\n{email['body']}"

        page_chunks = chunk_text(full_text, chunk_size, chunk_overlap)

        for i, text in enumerate(page_chunks):
            chunk = KnowledgeChunk(
                text=text,
                source="gmail",
                chunk_id=str(uuid.uuid4()),
                metadata={
                    "subject": email["subject"],
                    "sender": email["sender"],
                    "date": email["date"],
                    "message_id": email["message_id"],
                    "thread_id": email["thread_id"],
                    "chunk_index": i,
                },
            )
            chunks.append(chunk)

    logger.info(
        "Gmail produced %d chunks from %d emails (%d skipped as duplicates).",
        len(chunks), len(emails) - skipped, skipped,
    )
    return chunks
