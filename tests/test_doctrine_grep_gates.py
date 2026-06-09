"""Tests P0 Intra-1 (red-team 07/06) : CI grep gates pour 2 doctrines fictives.

Transforme 2 invariants doctrinaux en gates pytest qui bloquent les nouvelles
regressions. Ne fixe PAS les violators existants (out-of-scope today), mais
verrouille l'allowlist pour qu'aucun nouveau fichier ne contourne.

Doctrines verrouillees :
1. **shared/prices.py = single gateway yfinance** (CLAUDE.md "throttle anti-ban
   yfinance via _PX_TTL=1800") -- tout import direct ailleurs casse le throttle
   partage IP avec price_monitor du bot.
2. **shared/storage.py = passerelle DB** (LESSONS doctrine "1 driver canonique
   = 1 passerelle = storage.py") -- imports sqlite3 ailleurs bypassent les
   guards (transaction, DB_PATH override pour tests, lock_in hook post-commit).

Pattern : allowlist legacy fige le tech debt, **gate fail si nouvelle violation
apparait**. C'est l'invariant evolutif : on n'aggrave pas, on peut reduire.

Pour fixer un violator de l'allowlist :
1. Refactor le fichier pour passer par shared/prices.py ou shared/storage.py
2. Retirer le fichier de l'allowlist
3. Tests verts -> commit avec message "[doctrine] retire X de doctrine_allowlist"

Pour ajouter un fichier qui DOIT importer yfinance/sqlite3 directement
(ex: nouveau script ETL standalone) :
1. Justifier dans le commit pourquoi le single-gateway pattern ne s'applique pas
2. Ajouter le fichier a l'allowlist avec note
3. KNOWN-GAP comment dans le code source aussi
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent

# === ALLOWLIST yfinance (vidée 09/06 — HARD mode) ===
# Plus aucun fichier ne contourne shared/prices.py. Toute nouvelle violation
# = build rouge (gate strict, plus de ratchet decroissant).
_YFINANCE_LEGACY_ALLOWLIST: set[str] = set()

# === ALLOWLIST sqlite3 imports (snapshot fige 07/06 nuit) ===
# 48 fichiers hors scripts/ contournent storage.py.
# Note : scripts/ auto-excluded (standalone batches OK).
_SQLITE3_LEGACY_ALLOWLIST: set[str] = {
    "bot/handlers/audit.py",
    "bot/handlers/bias_pattern.py",
    "bot/handlers/bias_status.py",
    "bot/handlers/digest.py",
    "bot/handlers/echo_crypto_macro.py",
    "bot/handlers/find.py",
    "bot/handlers/journal_audit.py",
    "bot/handlers/journal_bias.py",
    "bot/handlers/observability.py",
    "bot/handlers/portfolio_views.py",
    "bot/handlers/positions.py",
    "bot/handlers/review.py",
    "bot/handlers/signal_drilldown.py",
    "bot/handlers/signals_filings.py",
    "bot/handlers/sources_admin.py",
    "bot/handlers/thesis_health.py",
    "bot/handlers/track_record.py",
    "bot/jobs/daily.py",
    "bot/jobs/periodic.py",
    "bot/main.py",
    "dashboard/render.py",
    "intelligence/analyze.py",
    "intelligence/asymmetry.py",
    "intelligence/base_rates.py",
    "intelligence/bias_events.py",
    "intelligence/bias_track_record.py",
    "intelligence/calibration_audit.py",
    "intelligence/digest.py",
    "intelligence/half_life.py",
    "intelligence/learning.py",
    "intelligence/lock_in_detector.py",
    "intelligence/materiality_boost.py",
    "intelligence/materiality_v2.py",
    "intelligence/monthly_track_record.py",
    "intelligence/morning_brief.py",
    "intelligence/outcome_context.py",
    "intelligence/over_cap_monitor.py",
    "intelligence/recalib_map.py",
    "intelligence/signal_dedup_audit.py",
    "intelligence/signal_recall_audit.py",
    "intelligence/thesis_track_record.py",
    "intelligence/track_record_aggregator.py",
    "intelligence/track_record_timeseries.py",
    "shared/degraded_signals.py",
    "shared/llm.py",
    "shared/schema.py",
    "shared/sql_observability.py",
    "shared/ticker_names.py",
}


_YFINANCE_IMPORT_RE = re.compile(r"^\s*(?:import\s+yfinance|from\s+yfinance)", re.MULTILINE)
_SQLITE3_IMPORT_RE = re.compile(r"^\s*(?:import\s+sqlite3|from\s+sqlite3)", re.MULTILINE)


def _scan_violators(import_re: re.Pattern, exclude_paths: set[str]) -> list[str]:
    """Scan tous les .py du repo (hors venv/cache) et liste ceux matchant l'import.

    `exclude_paths` est interprete comme paths absolus repo-rooted (ex 'shared/prices.py').
    Returns liste de paths repo-rooted (str) des violators.
    """
    violators = []
    for py_file in _REPO_ROOT.rglob("*.py"):
        # Skip venv / cache / git
        rel_str = str(py_file.relative_to(_REPO_ROOT)).replace("\\", "/")
        if any(p in rel_str for p in ("venv/", "__pycache__/", ".git/")):
            continue
        # Skip tests/ et alembic/ (legitimate use)
        if rel_str.startswith("tests/") or "/alembic/" in rel_str:
            continue
        # Skip si dans exclude (canonical owner du gateway)
        if rel_str in exclude_paths:
            continue
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if import_re.search(content):
            violators.append(rel_str)
    return sorted(violators)


def test_no_new_yfinance_bypass():
    """Aucun nouveau fichier ne doit importer yfinance hors shared/prices.py.

    Allowlist legacy 07/06 nuit : 20 fichiers. Si la liste retournee diverge,
    soit un nouveau fichier viole, soit un legacy a ete refactor (et il faut
    le retirer de l'allowlist + decrease le tech debt).
    """
    # shared/prices.py = canonical owner
    canonical_owner = {"shared/prices.py"}
    violators = set(_scan_violators(_YFINANCE_IMPORT_RE, canonical_owner))

    new_violators = violators - _YFINANCE_LEGACY_ALLOWLIST
    refactored_legacy = _YFINANCE_LEGACY_ALLOWLIST - violators

    assert not new_violators, (
        f"\n\n❌ NOUVELLE violation doctrine yfinance single-gateway : "
        f"{sorted(new_violators)}\n"
        "Soit refactor pour passer par shared/prices.py (recommande), "
        "soit ajouter explicite a _YFINANCE_LEGACY_ALLOWLIST avec justification "
        "+ KNOWN-GAP comment dans le code source.\n"
    )
    # Si quelqu'un a refactor un legacy, l'allowlist doit etre mise a jour
    assert not refactored_legacy, (
        f"\n\n✓ Legacy yfinance refactor (sortie du tech debt) : "
        f"{sorted(refactored_legacy)}\n"
        "Retire ces fichiers de _YFINANCE_LEGACY_ALLOWLIST dans "
        "tests/test_doctrine_grep_gates.py (decrease tech debt).\n"
    )


def test_no_new_sqlite3_bypass():
    """Aucun nouveau fichier ne doit importer sqlite3 hors shared/storage.py.

    storage.py = passerelle canonique (transaction guards, DB_PATH override,
    post-commit hooks). Legacy allowlist 07/06 nuit fige le tech debt actuel,
    gate empeche regression.
    """
    canonical_owner = {"shared/storage.py"}
    violators = set(_scan_violators(_SQLITE3_IMPORT_RE, canonical_owner))

    # Auto-exclude scripts/ (standalone batches OK)
    violators_filtered = {v for v in violators if not v.startswith("scripts/")}

    new_violators = violators_filtered - _SQLITE3_LEGACY_ALLOWLIST
    refactored_legacy = _SQLITE3_LEGACY_ALLOWLIST - violators_filtered

    assert not new_violators, (
        f"\n\n❌ NOUVELLE violation doctrine storage.py = passerelle DB : "
        f"{sorted(new_violators)}\n"
        "Soit refactor pour utiliser shared/storage.py helpers (recommande, "
        "ex: storage.db() context manager), soit ajouter a "
        "_SQLITE3_LEGACY_ALLOWLIST avec justification + KNOWN-GAP comment.\n"
    )
    assert not refactored_legacy, (
        f"\n\n✓ Legacy sqlite3 refactor (sortie du tech debt) : "
        f"{sorted(refactored_legacy)}\n"
        "Retire ces fichiers de _SQLITE3_LEGACY_ALLOWLIST dans "
        "tests/test_doctrine_grep_gates.py (decrease tech debt).\n"
    )


def test_doctrine_metrics_track():
    """Smoke test : track le size du tech debt pour observability.

    Pas un fail, juste log. Le but est de voir l'evolution session par session :
    si l'allowlist size augmente -> tech debt cresce, mauvais signe doctrine.
    Si size diminue -> sortie progressive du legacy, bon signe doctrine.
    """
    yf_n = len(_YFINANCE_LEGACY_ALLOWLIST)
    sq_n = len(_SQLITE3_LEGACY_ALLOWLIST)
    # Snapshot reference 07/06 nuit pivot : 19 yfinance, 48 sqlite3
    # Update ces numeros quand un refactor sort un fichier de l'allowlist.
    REFERENCE_YF = 19
    REFERENCE_SQ = 48
    print("\nDoctrine tech debt snapshot :")
    print(f"  yfinance allowlist : {yf_n} (reference 07/06 nuit : {REFERENCE_YF})")
    print(f"  sqlite3 allowlist  : {sq_n} (reference 07/06 nuit : {REFERENCE_SQ})")
    # Assert pour catch les insertions silencieuses
    assert yf_n <= REFERENCE_YF, (
        f"yfinance allowlist a augmente ({yf_n} > {REFERENCE_YF}) -- "
        "tech debt cresce. Refactor avant d'ajouter."
    )
    assert sq_n <= REFERENCE_SQ, (
        f"sqlite3 allowlist a augmente ({sq_n} > {REFERENCE_SQ}) -- "
        "tech debt cresce. Refactor avant d'ajouter."
    )
