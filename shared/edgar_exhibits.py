"""SEC EDGAR exhibit extractor — resolve filing URL to material content.

Bug origine (audit 30/05 iter 5) : `filings_8k_log.filing_url` pointe vers la
cover page du filing (ex: nvda-20260520.htm = 26KB de boilerplate). Le contenu
material (earnings tables, press release, CFO commentary) vit dans des exhibits
attaches dans le meme folder, typiquement les fichiers .htm les plus gros
(ex: q1fy27pr.htm = 275KB).

V2 sur la cover page sort 100% watch ev=none ("boilerplate header"). V2 sur
l'exhibit principal sort prob=0.750 strong sur une vraie earnings 8-K (NVDA).

Cette fonction resout : filing_url -> [exhibit text] via SEC EDGAR folder index.json.
"""

import logging
import re

import requests

log = logging.getLogger(__name__)

# Header SEC obligatoire (rejette les calls sans User-Agent reel)
EDGAR_HEADERS = {
    "User-Agent": "Olivier Legendre olegendre@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}

# Limites raisonnables -- on extrait les 2 plus gros exhibits HTML > 30KB.
# Press release + CFO commentary = couverture earnings complete. Plus = overflow.
MIN_EXHIBIT_SIZE = 30_000
MAX_EXHIBITS_PER_FILING = 2
MAX_CHARS_PER_EXHIBIT = 6_000
MAX_TOTAL_CHARS = 12_000


def _list_filing_documents(folder_url: str) -> list[dict]:
    """Fetch index.json du filing folder, retourne liste docs.

    Format SEC : `{folder}/index.json` -> {"directory": {"item": [{"name":..., "size":..., "type":...}]}}.
    """
    if not folder_url.endswith("/"):
        folder_url = folder_url + "/"
    try:
        r = requests.get(folder_url + "index.json", headers=EDGAR_HEADERS, timeout=10)
        if r.status_code != 200:
            log.warning(f"edgar_exhibits: index.json HTTP {r.status_code} for {folder_url}")
            return []
        j = r.json()
        return list(j.get("directory", {}).get("item", []))
    except Exception as e:
        log.warning(f"edgar_exhibits: list_documents failed for {folder_url}: {e}")
        return []


def _fetch_and_strip_html(url: str, max_chars: int = MAX_CHARS_PER_EXHIBIT) -> str:
    """Fetch URL, strip HTML tags + entities, retourne texte propre tronque."""
    try:
        r = requests.get(url, headers=EDGAR_HEADERS, timeout=15)
        if r.status_code != 200:
            return ""
        html = r.text
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", html)
        # Entites HTML communes
        for src, dst in (
            ("&nbsp;", " "), ("&amp;", "&"), ("&#160;", " "), ("&#8217;", "'"),
            ("&#8212;", "--"), ("&#8213;", "--"), ("&#x201c;", '"'), ("&#x201d;", '"'),
            ("&yen;", "Y"), ("&pound;", "GBP"), ("&euro;", "EUR"), ("&lt;", "<"), ("&gt;", ">"),
        ):
            text = text.replace(src, dst)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]
    except Exception as e:
        log.warning(f"edgar_exhibits: fetch_strip_html failed for {url}: {e}")
        return ""


def extract_filing_content(filing_url: str) -> str:
    """Resolve filing URL -> contenu material des exhibits attaches.

    Strategy : list folder index.json, exclure le main filing (cover page),
    exclure R*.htm (XBRL reports) et fichiers < 30KB, fetcher top 2 par taille.

    Returns : str concatenant les exhibits formates ou "" si echec.
    """
    folder = filing_url.rsplit("/", 1)[0]
    main_filename = filing_url.rsplit("/", 1)[-1]

    docs = _list_filing_documents(folder)
    if not docs:
        return ""

    exhibits = []
    for d in docs:
        name = d.get("name", "")
        size_str = d.get("size", "0") or "0"
        try:
            size = int(size_str)
        except (ValueError, TypeError):
            size = 0
        if name == main_filename:
            continue  # le main filing = cover page
        if not name.endswith(".htm"):
            continue  # on ne lit que HTML
        if name.startswith("R") and len(name) <= 8:
            continue  # R1.htm, R2.htm = XBRL viewer reports
        if "index" in name.lower():
            continue
        if size < MIN_EXHIBIT_SIZE:
            continue  # trop petit pour etre un exhibit material
        exhibits.append((name, size))

    exhibits.sort(key=lambda x: -x[1])

    chunks = []
    for name, _ in exhibits[:MAX_EXHIBITS_PER_FILING]:
        url = f"{folder}/{name}"
        text = _fetch_and_strip_html(url)
        if text:
            chunks.append(f"[{name}]: {text}")

    return " | ".join(chunks)[:MAX_TOTAL_CHARS]
