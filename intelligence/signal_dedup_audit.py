"""#77 LOOP -- Dedup audit signals table (vrais doublons + dedup_key robuste).

Mesure empirique des doublons potentiels qui ont passe le dedup gmail_id.
Strategie : groupby fingerprint approximatif (title normalise + ticker +
jour), report les groupes avec n>1.

Pourquoi : gmail_id est unique par construction (SQL UNIQUE INDEX). Mais
si la meme nouvelle 8-K arrive via 2 emails differents (newsletter
syndiquee), elle aura 2 gmail_id distincts et donc 2 lignes en signals
-- ce qui inflate materiality_boost (n_sources +1 artificiel).

Helpers :
- compute_dedup_quality(cx, days_back=90) -> {n_total, n_distinct_gmail_id,
  n_suspected_duplicates, collision_rate, by_source}
- list_suspected_duplicates(cx, days_back=90, min_group_size=2) -> groupes
  [{fingerprint, n, signal_ids, titles, gmail_ids}]
- compute_dedup_by_source(cx, days_back=90) -> par source : {n, n_unique,
  collision_rate}

Le fingerprint normalisation : title.lower() premieres 60 chars +
ticker_canonical + date_iso (YYYY-MM-DD). Volontairement approximatif --
on cible les vrais doublons pas les nuances stylistiques.
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def _normalize_title(title: str | None) -> str:
    """Lowercase + strip punct + collapse whitespace + premier 60 chars."""
    if not title:
        return ""
    t = title.lower().strip()
    t = _PUNCT_RE.sub("", t)
    t = _WS_RE.sub(" ", t).strip()
    return t[:60]


def _parse_first_ticker(entities_json: str | None) -> str:
    """Extract le premier ticker du JSON entities. Heuristique : 1 signal
    -> 1 ticker primaire (les multi-ticker sont rare et OK a multi-compter)."""
    if not entities_json:
        return ""
    try:
        ents = json.loads(entities_json)
        if isinstance(ents, list) and ents:
            return str(ents[0]).upper()
    except (json.JSONDecodeError, TypeError):
        pass
    return ""


def _fingerprint(title: str | None, entities_json: str | None,
                 timestamp: str | None) -> str:
    """Cle de groupby pour suspected duplicates."""
    return "|".join([
        _normalize_title(title),
        _parse_first_ticker(entities_json),
        (timestamp or "")[:10],  # YYYY-MM-DD
    ])


def list_suspected_duplicates(
    cx: sqlite3.Connection,
    days_back: int = 90,
    min_group_size: int = 2,
) -> list[dict[str, Any]]:
    """Returns groups of suspected duplicates (n >= min_group_size).

    Group by fingerprint = (title_normalise, first_ticker, jour).
    Pour chaque groupe : {fingerprint, n, signal_ids, titles, gmail_ids,
    source_ids}. Trie par n DESC.
    """
    cutoff = f"-{days_back} days"
    rows = cx.execute(
        "SELECT id, title, entities, timestamp, gmail_id, source_id "
        "FROM signals "
        "WHERE timestamp >= datetime('now', ?)",
        (cutoff,),
    ).fetchall()

    groups: dict[str, dict[str, Any]] = {}
    for r in rows:
        sid = r[0] if not isinstance(r, dict) else r.get("id")
        title = r[1] if not isinstance(r, dict) else r.get("title")
        entities = r[2] if not isinstance(r, dict) else r.get("entities")
        ts = r[3] if not isinstance(r, dict) else r.get("timestamp")
        gid = r[4] if not isinstance(r, dict) else r.get("gmail_id")
        src_id = r[5] if not isinstance(r, dict) else r.get("source_id")
        fp = _fingerprint(title, entities, ts)
        if not _normalize_title(title):  # skip rows sans title significatif
            continue
        g = groups.setdefault(fp, {
            "fingerprint": fp,
            "n": 0,
            "signal_ids": [],
            "titles": [],
            "gmail_ids": [],
            "source_ids": [],
        })
        g["n"] += 1
        g["signal_ids"].append(sid)
        g["titles"].append(title)
        g["gmail_ids"].append(gid)
        g["source_ids"].append(src_id)

    out = [g for g in groups.values() if g["n"] >= min_group_size]
    out.sort(key=lambda x: -x["n"])
    return out


def compute_dedup_quality(
    cx: sqlite3.Connection,
    days_back: int = 90,
) -> dict[str, Any]:
    """Vue agregee qualite dedup sur la fenetre.

    Returns:
        n_total: total signals sur fenetre
        n_distinct_gmail_id: count(distinct gmail_id) -- hard dedup
        n_suspected_duplicates: somme des n des groupes >1 (vraies
            duplications qui ont passe gmail_id)
        collision_rate: n_suspected / n_total (0 si rien)
        n_groups_suspected: count des fingerprints avec n>1
        status: OK (<2%) / WARN (<5%) / ALERT (>=5%)
    """
    cutoff = f"-{days_back} days"
    row = cx.execute(
        "SELECT COUNT(*), COUNT(DISTINCT gmail_id) FROM signals "
        "WHERE timestamp >= datetime('now', ?)",
        (cutoff,),
    ).fetchone()
    n_total = int(row[0] or 0)
    n_distinct_gmail = int(row[1] or 0)

    groups = list_suspected_duplicates(cx, days_back=days_back, min_group_size=2)
    n_suspected = sum(g["n"] for g in groups)
    n_groups = len(groups)

    rate = round(n_suspected / n_total * 100, 2) if n_total > 0 else 0.0
    if rate >= 5.0:
        status = "ALERT"
    elif rate >= 2.0:
        status = "WARN"
    else:
        status = "OK"

    return {
        "days_back": days_back,
        "n_total": n_total,
        "n_distinct_gmail_id": n_distinct_gmail,
        "n_suspected_duplicates": n_suspected,
        "n_groups_suspected": n_groups,
        "collision_rate_pct": rate,
        "status": status,
    }


def compute_dedup_by_source(
    cx: sqlite3.Connection,
    days_back: int = 90,
) -> list[dict[str, Any]]:
    """Per source : n_signals + suspected duplicates count. Trie par n DESC."""
    cutoff = f"-{days_back} days"
    rows = cx.execute(
        "SELECT s.id, s.name, COUNT(sig.id) AS n "
        "FROM sources s "
        "LEFT JOIN signals sig ON sig.source_id = s.id "
        "AND sig.timestamp >= datetime('now', ?) "
        "GROUP BY s.id, s.name "
        "ORDER BY n DESC",
        (cutoff,),
    ).fetchall()

    groups = list_suspected_duplicates(cx, days_back=days_back)
    suspect_by_src: dict[int, int] = {}
    for g in groups:
        for src_id in g["source_ids"]:
            if src_id is not None:
                suspect_by_src[src_id] = suspect_by_src.get(src_id, 0) + 1

    out = []
    for r in rows:
        sid_raw = r[0] if not isinstance(r, dict) else r.get("id")
        sid = int(sid_raw) if sid_raw is not None else -1
        name = r[1] if not isinstance(r, dict) else r.get("name")
        n = int(r[2] or 0) if not isinstance(r, dict) else int(r.get("n") or 0)
        n_suspect = suspect_by_src.get(sid, 0)
        rate = round(n_suspect / n * 100, 2) if n > 0 else 0.0
        out.append({
            "source_id": sid,
            "source_name": name,
            "n_signals": n,
            "n_suspected_duplicates": n_suspect,
            "collision_rate_pct": rate,
        })
    return out
