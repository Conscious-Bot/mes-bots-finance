"""Gmail data source. Reads emails from 'Newsletters' label and stores raw signals.

First run: OAuth flow opens browser, user authorizes, token.json is saved.
Subsequent runs: token.json reused (auto-refreshed when needed).
"""

import base64
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from shared import storage

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
TOKEN_PATH = Path("token.json")
CREDS_PATH = Path("credentials.json")
LABEL_NAME = "Newsletters"
MAX_BODY_CHARS = 50000


def get_service() -> Any:  # googleapiclient resource
    if not CREDS_PATH.exists():
        raise FileNotFoundError(f"{CREDS_PATH} not found. Place credentials.json at project root.")
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def get_label_id(service: Any, label_name: str = LABEL_NAME) -> str | None:
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    for label in labels:
        if label["name"].lower() == label_name.lower():
            return cast(str | None, label["id"])
    raise ValueError(f"Label '{label_name}' not found in Gmail")


def _extract_body(payload: dict[str, Any]) -> str:
    if "parts" in payload:
        for part in payload["parts"]:
            mime = part.get("mimeType", "")
            data = part.get("body", {}).get("data", "")
            if mime == "text/plain" and data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        for part in payload["parts"]:
            mime = part.get("mimeType", "")
            data = part.get("body", {}).get("data", "")
            if mime == "text/html" and data:
                html = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                return _strip_html(html)
            if "parts" in part:
                nested = _extract_body(part)
                if nested:
                    return nested
    data = payload.get("body", {}).get("data", "")
    if data:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    return ""


def _strip_html(html: str) -> str:
    text = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_email(msg: dict[str, Any]) -> dict[str, Any]:
    headers = msg["payload"].get("headers", [])
    h = {hdr["name"].lower(): hdr["value"] for hdr in headers}
    body = _extract_body(msg["payload"])
    return {
        "gmail_id": msg["id"],
        "subject": h.get("subject", ""),
        "from": h.get("from", ""),
        "date": h.get("date", ""),
        "body": body[:MAX_BODY_CHARS],
    }


def fetch_emails(label_name: str = LABEL_NAME, max_results: int = 50) -> list[dict[str, Any]]:
    service = get_service()
    label_id = get_label_id(service, label_name)
    results = service.users().messages().list(userId="me", labelIds=[label_id], maxResults=max_results).execute()
    messages = results.get("messages", [])
    emails = []
    for m in messages:
        full = service.users().messages().get(userId="me", id=m["id"], format="full").execute()
        emails.append(_parse_email(full))
    return emails


_ONBOARDING_PATTERNS = (
    "welcome to",
    "welcome ",
    "hello from",
    "hi there",
    "hi friends",
    "hey there",
    "you're on the list",
    "you are on the list",
    "you're in",
    "thanks for subscribing",
    "thanks for signing",
    "thanks for joining",
    "confirm your email",
    "confirm your subscription",
    "verify your email",
    "verify your account",
    "activate your account",
    "set up your account",
    "please verify",
    "please confirm",
    "bienvenue ",
    "bienvenue dans",
    "bienvenue à",
    "bienvenu ",
    "merci de vous être inscrit",
    "confirmez votre email",
    "vérifiez votre email",
    "bienvenido a",
    "bienvenida a",
    "gracias por suscribir",
    "willkommen bei",
    "willkommen zu",
    "benvenuto",
    "benvenuta",
)


def _is_onboarding_noise(subject: str) -> bool:
    """Phase A3 — Drop welcome/onboarding emails before persistence."""
    if not subject:
        return False
    s = subject.lower().strip()
    return any(p in s for p in _ONBOARDING_PATTERNS)


def ingest_new_emails(label_name: str = LABEL_NAME, max_results: int = 50) -> dict[str, Any]:
    emails = fetch_emails(label_name, max_results)
    new_count = 0
    skipped_count = 0
    noise_count = 0
    for e in emails:
        if storage.signal_exists_by_gmail_id(e["gmail_id"]):
            skipped_count += 1
            continue
        if _is_onboarding_noise(e.get("subject", "")):
            noise_count += 1
            continue
        source_id = storage.get_or_create_source(e["from"])
        # Phase Solidification — accurate count: only increment if INSERT actually succeeded
        inserted_id = storage.insert_raw_signal(
            source_id=source_id,
            gmail_id=e["gmail_id"],
            timestamp=datetime.now(UTC).isoformat(),
            subject=e["subject"],
            content=e["body"],
        )
        if inserted_id is not None:
            new_count += 1
        else:
            noise_count += 1
    return {
        "total_fetched": len(emails),
        "new_ingested": new_count,
        "skipped_duplicates": skipped_count,
        "skipped_onboarding_noise": noise_count,
    }


if __name__ == "__main__":
    print("=== Test Gmail connection ===")
    try:
        service = get_service()
        print("OK Gmail authenticated")
        label_id = get_label_id(service)
        print(f"OK Label '{LABEL_NAME}' found: {label_id}")
        print("\nFetching last 5 emails...")
        emails = fetch_emails(max_results=5)
        print(f"OK Fetched {len(emails)} emails")
        for i, e in enumerate(emails, 1):
            print(f"\n--- Email {i} ---")
            print(f"  From    : {e['from'][:80]}")
            print(f"  Subject : {e['subject'][:80]}")
            print(f"  Date    : {e['date']}")
            print(f"  Body    : {len(e['body'])} chars")
        print("\n=== Test ingestion in DB ===")
        stats = ingest_new_emails(max_results=10)
        print(f"Total fetched   : {stats['total_fetched']}")
        print(f"New ingested    : {stats['new_ingested']}")
        print(f"Skipped (dup)   : {stats['skipped_duplicates']}")
    except Exception as e:
        print(f"ERREUR : {type(e).__name__}: {e}")
