"""Telegram out. Text/image/file. Split auto si > 4096.

Hook 31/05/2026 : chaque send_text est persiste dans chat_messages (surface='telegram')
pour que le copilot dashboard ait acces a l'historique des pushes Telegram.
Cf shared/copilot_persona + dashboard/chat.py qui inject Telegram pushes 24h dans contexte.
"""

import requests

from shared import config

API_BASE = "https://api.telegram.org/bot{token}/{method}"


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
        r = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
        )
        if not r.ok:
            requests.post(url, data={"chat_id": chat_id, "text": chunk})
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
