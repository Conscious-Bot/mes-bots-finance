"""Client Obsidian Local REST API pour vault PRESAGE.

Doctrine (cf CLAUDE.md du vault PRESAGE, livré 25/06/2026) :
- Le vault = raffinerie (lent/sélectif/cumulatif), PAS un entrepôt
- FIREWALL FAIT / JUGEMENT :
  - FAIT (daté/sourcé/falsifiable) : on remplit
  - JUGEMENT (conviction/cran/cible/sizing) : JAMAIS sans dictée explicite O.
- Multi-voix dans archive de dialogue : 🟦 Olivier vs ⬜ LLM séparés
- Anti-fantôme : [[liens]] vers notes EXISTANTES uniquement
- Anti-confirmation : extraire ce qui CASSE la thèse d'abord
- Schema commun frontmatter : type / date / aliases / tickers / theses_touchees /
  noms_propres / hubs / status

3 workflows :
  A : archive conversation copilot -> journal/dialogues/DIALOGUE_<sujet>_<date>.md
  B : ingest source externe -> 00_ingestion/STUB_<sujet>_<date>.md
  C : digest bot -> journal/digests/DIGEST_<date>.md

Sécurité : OBSIDIAN_API_URL + OBSIDIAN_API_KEY en .env non-commité.
"""
from __future__ import annotations

import json
import os
import ssl
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

# Lazy load env (compatibilite avec dashboard/render qui peut tourner sans dotenv)
_API_URL = os.environ.get("OBSIDIAN_API_URL", "")
_API_KEY = os.environ.get("OBSIDIAN_API_KEY", "")
if not _API_URL or not _API_KEY:
    # Try loading from .env file directly
    _env_path = Path(__file__).parent.parent / ".env"
    if _env_path.exists():
        for line in _env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("OBSIDIAN_API_URL="):
                _API_URL = line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("OBSIDIAN_API_KEY="):
                _API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")

# SSL context : Obsidian Local REST API utilise cert self-signed sur HTTPS
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


class ObsidianError(Exception):
    """Erreur appel API Obsidian."""


def _request(method: str, path: str, body: str | None = None, content_type: str = "application/json") -> str:
    """Appel HTTPS authentifie via Bearer token. Returns raw response body."""
    if not _API_URL or not _API_KEY:
        raise ObsidianError("OBSIDIAN_API_URL / OBSIDIAN_API_KEY manquants en .env")
    # URL-encode path segments (espace, accents, parentheses dans noms de notes)
    parts = path.split("/")
    encoded = "/".join(urllib.parse.quote(p, safe="") for p in parts)
    url = f"{_API_URL}/{encoded.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {_API_KEY}",
        "Accept": "application/json",
    }
    if body is not None:
        headers["Content-Type"] = content_type
    data = body.encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=_CTX, timeout=10) as r:
            return r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise ObsidianError(f"HTTP {e.code} {method} {path}: {e.read().decode('utf-8', 'replace')[:200]}") from e
    except Exception as e:
        raise ObsidianError(f"{method} {path}: {e}") from e


# ─── Vault listing ─────────────────────────────────────────────────────────

def list_notes(folder: str = "") -> list[str]:
    """List entries dans un folder du vault (root si folder='').

    Retour : list de filenames (ne distingue pas notes/folders dans l'output
    Obsidian REST API ; les folders peuvent etre suffixes par '/').
    """
    path = f"vault/{folder.strip('/')}/" if folder else "vault/"
    raw = _request("GET", path)
    return json.loads(raw).get("files", [])


def note_exists(note_path: str) -> bool:
    """Retourne True si la note existe (HEAD-like via GET, swallowed 404)."""
    try:
        _request("GET", f"vault/{note_path}")
        return True
    except ObsidianError as e:
        if "404" in str(e):
            return False
        raise


# ─── Read ──────────────────────────────────────────────────────────────────

def read_note(note_path: str) -> str:
    """Lit le contenu Markdown brut d'une note."""
    return _request("GET", f"vault/{note_path}")


# ─── Write ─────────────────────────────────────────────────────────────────

def write_note(note_path: str, content: str, *, overwrite: bool = False) -> None:
    """Cree ou ecrase une note Markdown.

    Si overwrite=False (defaut) ET note existe -> raise (anti-clobber).
    Folders parents auto-created par l'API.
    """
    if not overwrite and note_exists(note_path):
        raise ObsidianError(f"Note '{note_path}' existe deja (overwrite=False)")
    _request("PUT", f"vault/{note_path}", body=content, content_type="text/markdown")


def append_to_note(note_path: str, content: str) -> None:
    """Append text a une note existante."""
    _request("POST", f"vault/{note_path}", body=content, content_type="text/markdown")


# ─── Helpers schema commun ──────────────────────────────────────────────────

def frontmatter(
    type_: str,
    *,
    date_iso: str | None = None,
    aliases: list[str] | None = None,
    tickers: list[str] | None = None,
    theses_touchees: list[str] | None = None,
    noms_propres: list[str] | None = None,
    hubs: list[str] | None = None,
    status: str = "archive",
) -> str:
    """Frontmatter YAML conforme schema commun vault PRESAGE.

    Regle anti-fantome : theses_touchees + hubs DOIVENT etre des [[liens]] vers
    notes EXISTANTES. Le caller verifie via note_exists() AVANT d'inclure.
    Les tickers + noms_propres sans note restent VALEURS nues (pas de [[lien]]).
    """
    def _yaml_list(items: list[str] | None) -> str:
        if not items:
            return "[]"
        # Quote chaque item pour gerer espaces/accents
        return "[" + ", ".join(f'"{it}"' for it in items) + "]"

    lines = [
        "---",
        f"type: {type_}",
        f"date: {date_iso or date.today().isoformat()}",
        f"aliases: {_yaml_list(aliases)}",
        f"tickers: {_yaml_list(tickers)}",
        f"theses_touchees: {_yaml_list(theses_touchees)}",
        f"noms_propres: {_yaml_list(noms_propres)}",
        f"hubs: {_yaml_list(hubs)}",
        f"status: {status}",
        "---",
    ]
    return "\n".join(lines) + "\n"


# ─── Anti-fantome check ────────────────────────────────────────────────────

def filter_existing_links(candidate_links: list[str]) -> tuple[list[str], list[str]]:
    """Pour une liste de noms de notes candidats, retourne (existantes, fantomes).

    Doctrine vault PRESAGE : never link to non-existent note. Wrapper qui
    teste chaque candidate via list_notes() puis matche case-insensitive
    partielle (le nom du vault peut differer du label court).

    Retour : (existantes_brutes, fantomes_brutes). Les existantes_brutes
    sont les filenames vault EXACT pour les links [[exact_name]].
    """
    root_entries = list_notes()  # filenames at root (no folders for now)
    existing: list[str] = []
    ghosts: list[str] = []
    for cand in candidate_links:
        # Match exact filename minus .md
        cand_lower = cand.lower()
        match = None
        for entry in root_entries:
            entry_stripped = entry.rstrip("/").replace(".md", "")
            if entry_stripped.lower() == cand_lower:
                match = entry_stripped
                break
            # Partial : candidate ticker matches start of entry (ex "ASML" -> "ASML.md")
            if entry_stripped.lower().startswith(cand_lower + " ") or entry_stripped.lower() == cand_lower:
                match = entry_stripped
                break
        if match:
            existing.append(match)
        else:
            ghosts.append(cand)
    return existing, ghosts
