"""Telegram out. Text/image/file. Split auto si > 4096.

Hook 31/05/2026 : chaque send_text est persiste dans chat_messages (surface='telegram')
pour que le copilot dashboard ait acces a l'historique des pushes Telegram.
Cf shared/copilot_persona + dashboard/chat.py qui inject Telegram pushes 24h dans contexte.

Retry 03/06/2026 (audit Flow 3 P2) : 429 Too Many Requests + 5xx avec backoff
expo court. Avant : un drop silencieux sur rate-limit perdait l'alerte.
Maintenant : 3 tentatives, respect Retry-After header, sinon backoff 2/4/8s.
"""

import logging
import time

import requests

from shared import config

API_BASE = "https://api.telegram.org/bot{token}/{method}"

_log = logging.getLogger(__name__)

# Retry config : Telegram rate limit ~30 msg/s global, 1/s par chat. 429 +
# 5xx -> retry. Autres erreurs (4xx auth) -> fail loud sans retry.
_RETRY_MAX = 3
_RETRY_BASE_BACKOFF = 2.0  # seconds, exponential 2/4/8


def _post_with_retry(url: str, data: dict, timeout: int = 10) -> requests.Response | None:
    """POST avec retry sur 429 + 5xx. Respect Retry-After header.

    Returns la response sur succes (2xx) ou None si tous les retries echouent.
    Loggue chaque retry. Jamais raise -- le caller decide de l'escalade.
    """
    for attempt in range(_RETRY_MAX):
        try:
            r = requests.post(url, data=data, timeout=timeout)
        except requests.exceptions.RequestException as e:
            _log.warning(f"Telegram POST network error (attempt {attempt+1}/{_RETRY_MAX}): {e}")
            time.sleep(_RETRY_BASE_BACKOFF * (2 ** attempt))
            continue
        if r.ok:
            return r
        # 429 = rate limit, 5xx = serveur. Retry.
        if r.status_code == 429 or r.status_code >= 500:
            retry_after = None
            try:
                payload = r.json()
                retry_after = payload.get("parameters", {}).get("retry_after")
            except Exception:
                pass
            wait_s = retry_after if retry_after else _RETRY_BASE_BACKOFF * (2 ** attempt)
            _log.warning(
                f"Telegram {r.status_code} (attempt {attempt+1}/{_RETRY_MAX}), "
                f"retry in {wait_s:.1f}s"
            )
            time.sleep(wait_s)
            continue
        # 4xx autre (auth, malformed) : fail loud sans retry
        _log.error(f"Telegram {r.status_code} (no retry): {r.text[:200]}")
        return None
    _log.error(f"Telegram POST failed after {_RETRY_MAX} attempts")
    return None


def _persist_telegram_push(text: str) -> None:
    """Hook : persist chaque Telegram push dans chat_messages (surface='telegram').

    Permet au copilot dashboard de referencer "le brief de ce matin disait X"
    sans que l'user doive re-coller le contenu. Try/except : ne JAMAIS bloquer le
    send Telegram en cas d'erreur DB.
    """
    try:
        from shared import storage as _stg
        _stg.insert_chat_message(
            surface="telegram",
            role="assistant",
            content=text,
            session_id="telegram",  # session canonique pour tous pushes Telegram
            llm_meta=None,
        )
    except Exception:
        pass  # silent : envoyer le Telegram reste prioritaire sur le log


def send_text(text: str, parse_mode: str = "Markdown"):
    token = config.telegram_token()
    chat_id = config.telegram_chat_id()
    if not token or not chat_id:
        print("[notify] Telegram non configuré, dump local:")
        print(text)
        _persist_telegram_push(text)  # persist meme en mode local-dump
        return
    url = API_BASE.format(token=token, method="sendMessage")
    chunks = [text[i : i + 3800] for i in range(0, len(text), 3800)]
    for chunk in chunks:
        r = _post_with_retry(
            url,
            {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
        )
        # Fallback : si parse_mode echoue (Markdown malformed), retry sans parse_mode.
        # _post_with_retry retourne None sur 4xx -> on tente une fois plus en plain.
        if r is None:
            _post_with_retry(url, {"chat_id": chat_id, "text": chunk})
    _persist_telegram_push(text)  # persist apres send (1 entry par send_text, pas par chunk)


def send_image(path: str, caption: str | None = None) -> None:
    token = config.telegram_token()
    chat_id = config.telegram_chat_id()
    url = API_BASE.format(token=token, method="sendPhoto")
    with open(path, "rb") as f:
        requests.post(url, data={"chat_id": chat_id, "caption": caption or ""}, files={"photo": f})


def send_document(path: str, caption: str | None = None) -> None:
    token = config.telegram_token()
    chat_id = config.telegram_chat_id()
    url = API_BASE.format(token=token, method="sendDocument")
    with open(path, "rb") as f:
        requests.post(url, data={"chat_id": chat_id, "caption": caption or ""}, files={"document": f})
