"""Telegram out. Text/image/file. Split auto si > 4096."""

import requests

from shared import config

API_BASE = "https://api.telegram.org/bot{token}/{method}"

def send_text(text: str, parse_mode: str = "Markdown"):
    token = config.telegram_token()
    chat_id = config.telegram_chat_id()
    if not token or not chat_id:
        print("[notify] Telegram non configuré, dump local:")
        print(text)
        return
    url = API_BASE.format(token=token, method="sendMessage")
    chunks = [text[i:i+3800] for i in range(0, len(text), 3800)]
    for chunk in chunks:
        r = requests.post(url, data={
            "chat_id": chat_id, "text": chunk,
            "parse_mode": parse_mode, "disable_web_page_preview": True,
        })
        if not r.ok:
            requests.post(url, data={"chat_id": chat_id, "text": chunk})

def send_image(path, caption=None):
    token = config.telegram_token()
    chat_id = config.telegram_chat_id()
    url = API_BASE.format(token=token, method="sendPhoto")
    with open(path, "rb") as f:
        requests.post(url, data={"chat_id": chat_id, "caption": caption or ""},
                      files={"photo": f})

def send_document(path, caption=None):
    token = config.telegram_token()
    chat_id = config.telegram_chat_id()
    url = API_BASE.format(token=token, method="sendDocument")
    with open(path, "rb") as f:
        requests.post(url, data={"chat_id": chat_id, "caption": caption or ""},
                      files={"document": f})
