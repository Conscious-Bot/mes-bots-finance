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


def canonical_ticker_aliases(ticker: str) -> list[str]:
    """Génère les aliases canoniques pour un ticker — méthode de classification.

    Doctrine 26/06 : toute nouvelle note thèse / hub / sentinelle référençant
    un ticker DOIT inclure ces aliases pour être searchable dans Cerebro.

    Récupère longName + shortName via yfinance, dérive version sans suffixes
    corporate (Inc/Corp/Corporation/Ltd/N.V./S.A./etc).

    Returns: liste d'aliases dédupliquée [ticker, longName, longName_clean,
        shortName, shortName_clean] — vides filtrés.

    Fail-soft : si yfinance HS, retourne juste [ticker].

    Exemple :
        canonical_ticker_aliases("AVGO")
        # ['AVGO', 'Broadcom Inc.', 'Broadcom']

        canonical_ticker_aliases("000660.KS")
        # ['000660.KS', 'SK hynix Inc.', 'SK hynix']

        canonical_ticker_aliases("TSM")
        # ['TSM', 'Taiwan Semiconductor Manufacturing Company Limited',
        #  'Taiwan Semiconductor Manufacturing Company', 'TSMC']
    """
    import re as _re

    def _clean(name: str) -> str:
        if not name:
            return ""
        n = name
        # Strip corporate suffixes (ordered longest first to avoid partial match)
        for suf in [
            ", Inc.", " Inc.", " Inc", ", Corp.", " Corp.", " Corporation",
            " N.V.", " Limited", " Ltd.", " Ltd", " S.A.", " S.E.", " SE",
            " Co., Ltd.", ", Ltd.", " Holding", " Holdings", " Group",
        ]:
            n = _re.sub(_re.escape(suf) + r"$", "", n)
        return n.strip().rstrip(".").strip()

    aliases = [ticker]
    try:
        import yfinance as _yf
        info = _yf.Ticker(ticker).info or {}
        longName = (info.get("longName") or "").strip()
        shortName = (info.get("shortName") or "").strip()
        for raw in [longName, _clean(longName), shortName, _clean(shortName)]:
            if raw and raw not in aliases:
                aliases.append(raw)
    except Exception:
        pass
    return aliases


def thesis_frontmatter(
    *,
    ticker: str,
    conviction: int | str,
    cap_pct: float,
    cluster: str = "AI-compute",
    sector_thesis_id: str | None = None,
    extra_aliases: list[str] | None = None,
    status: str = "active",
) -> str:
    """Frontmatter canonique pour TOUTE nouvelle note thèse — méthode de
    classification au moment de la création.

    Aliases auto-générés via canonical_ticker_aliases() + extra_aliases user.
    Garantit que la note est searchable dans Cerebro par : ticker, longName,
    company name nettoyé, tout alias user-supplied.

    Doctrine 26/06 cf [[manual-exec-must-create-cf]] (helper canonique) et
    cette nouvelle [[canonical-thesis-aliases-at-creation]].
    """
    aliases = canonical_ticker_aliases(ticker)
    if extra_aliases:
        for a in extra_aliases:
            if a and a not in aliases:
                aliases.append(a)
    lines = [
        "---",
        "type: these",
        "domain: patrimoine",
        "strate: synthese",
        f"ticker: {ticker}",
        f"conviction: {conviction}",
        f"cap_pct: {cap_pct}",
        "taille_actuelle:    # % du book aujourd'hui",
        f"cluster: {cluster}",
        f"status: {status}     # active | concluded | invalidated",
        f"created: {date.today().isoformat()}",
        f"aliases: [{', '.join(f'\"{a}\"' for a in aliases)}]",
        f"tickers: [\"{ticker}\"]",
        "sentinelle: []     # conditions d'invalidation datées",
        "gouverne_par: \"[[Presage]]\"",
        "teste_ma_discipline: \"[[Biais 1 vendre les gagnants trop tot]]\"",
    ]
    if sector_thesis_id:
        lines.append(f"sector_thesis_id: {sector_thesis_id}")
    lines.append("---")
    return "\n".join(lines) + "\n"


# ─── Bootstrap session ─────────────────────────────────────────────────────

# Hubs canoniques lus au demarrage de chaque session non-triviale.
# Cf memory [[project-obsidian-vault-primary-substrate]] doctrine 25/06/2026.
BOOTSTRAP_HUBS = [
    "CLAUDE.md",  # doctrine vault (prime sur toute autre instruction)
    "Grille de Conviction.md",
    "World Model — le modèle causal (apex).md",
    "Concentration — grappe AI-compute.md",
]


def vault_bootstrap(*, include_latest_snapshot: bool = True) -> dict:
    """Lecture des hubs canoniques au demarrage de session.

    Retourne dict {note_path: content_markdown}. Le caller (typiquement Claude
    en debut de session) lit les hubs pour aligner sur contexte courant
    Olivier en vigueur (Grille de Conviction, World Model, doctrine vault).

    Si include_latest_snapshot=True (defaut), ajoute aussi la note "Snapshot
    patrimoine — YYYY-MM-DD.md" la plus recente trouvee a la racine.

    Returns : dict[path -> content]. Cles absentes pour notes inexistantes.
    """
    out: dict[str, str] = {}
    for note in BOOTSTRAP_HUBS:
        try:
            out[note] = read_note(note)
        except ObsidianError as e:
            # Note inexistante = on skip (peut etre nouvelle session ou doctrine pas encore migree)
            if "404" in str(e):
                continue
            raise
    if include_latest_snapshot:
        try:
            entries = list_notes()
            # Prefere les snapshots DATES (format "Snapshot patrimoine — YYYY-MM-DD.md")
            # vs le canonical sans date qui peut etre un index vide.
            import re
            dated_pattern = re.compile(r"Snapshot patrimoine — (\d{4}-\d{2}-\d{2})\.md$")
            dated_snaps = []
            for e in entries:
                m = dated_pattern.match(e)
                if m:
                    dated_snaps.append((m.group(1), e))
            if dated_snaps:
                dated_snaps.sort(reverse=True)  # most recent first
                latest_path = dated_snaps[0][1]
                out[latest_path] = read_note(latest_path)
            else:
                # Fallback canonical sans date
                if "Snapshot patrimoine.md" in entries:
                    out["Snapshot patrimoine.md"] = read_note("Snapshot patrimoine.md")
        except ObsidianError:
            pass
    return out


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
