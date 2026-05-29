"""Sprint 6 — Augmentation LLM du grade : narrative grouping + edge identification.

Pourquoi : Sprint 5 utilise des proxies deterministes (secteur >3 = redondant,
lone-wolf sector = decorrelation*) ; c'est grossier. Sprint 6 demande a Opus
de grouper les positions par THESE NARRATIVE (pas secteur) et d'identifier
les positions qui ont un vrai edge independant.

Sortie : un snapshot dans 'portfolio_narrative_clusters' (append-only, hebdo).
Le grade deterministe peut ensuite consommer le dernier snapshot pour raffiner
T2_redondant + decorrelation_star.

Limite : on n'invente pas de signaux. La sortie de l'LLM est purement
classificatoire (regroupement). Le poids reste deterministe (EUR par groupe).
"""

import json
import logging
from datetime import UTC, datetime

from shared import llm, storage

log = logging.getLogger(__name__)


def assemble_narrative_context() -> dict:
    """Snapshot of active positions + theses + key drivers for LLM analysis."""
    with storage.db() as cx:
        pos_rows = cx.execute(
            "SELECT p.ticker, p.qty * p.avg_cost AS weight, t.conviction, t.key_drivers, t.notes "
            "FROM positions p LEFT JOIN theses t ON t.ticker = p.ticker AND t.status='active' "
            "WHERE p.qty > 0 AND p.status='open'"
        ).fetchall()
    positions = [
        {
            "ticker": r[0],
            "weight_eur": float(r[1] or 0),
            "conviction": r[2],
            "key_drivers": (r[3] or "")[:400],
            "notes": (r[4] or "")[:300],
        }
        for r in pos_rows
    ]
    total = sum(p["weight_eur"] for p in positions) or 1
    for p in positions:
        p["weight_pct"] = round(p["weight_eur"] / total * 100, 1)
    return {
        "positions": positions,
        "total_eur": total,
        "n_positions": len(positions),
    }


_NARRATIVE_PROMPT = """Tu es un analyste qui regroupe un portefeuille reel par THESE NARRATIVE.

Contexte : portefeuille de {n} positions, total {total:.0f}€. Voici les positions actives, leur key_drivers et notes (langue : francais melange anglais financier OK).

POSITIONS :
{positions_block}

TACHE :

1. Regroupe les positions en NARRATIVE_CLUSTERS — pas par secteur GICS, par THESE narrative reelle. Exemples : "AI compute backbone", "Industrial reshoring US", "Dividend defensive cash flow", "Crypto BTC pure", "Commodity supercycle", "Specialty chemistry niche", "Defense EU rearmament", etc.

   Une position peut etre dans 0 ou 1 cluster (pas multi-cluster — choisis le plus dominant pour cette these). Si une position n'appartient a aucune these narrative claire (ex. opportuniste, parking cash), mets-la dans "uncategorized".

2. Pour chaque cluster, indique :
   - nom (court, descriptif)
   - tickers (liste)
   - shared_drivers (1-3 phrases : ce qui les fait bouger ENSEMBLE)
   - narrative_overlap_score (0-100 : 100 = clones, 0 = independantes mais meme cluster)

3. EDGE_POSITIONS : identifie les positions qui ont un vrai EDGE INDEPENDANT
   (these unique, pas redondante avec d'autres positions du book, expose un
   risque narratif que aucune autre position ne joue). Liste les tickers + 1
   phrase pourquoi. Conservative : seulement si vraiment independant.

4. REDUNDANT_POSITIONS : positions qui sont redondantes avec une autre du book
   (meme these, meme moteur, peu d'edge marginal). Liste les tickers + le
   ticker_principal de qui ils sont redondants + 1 phrase pourquoi.

EXIGENCES :
- Cite TOUJOURS le ticker exact (pas le nom de societe).
- Si tu n'as pas assez d'info dans les key_drivers, dis-le ("data insuffisante" dans shared_drivers).
- PAS de generalite floue ("tech mega cap" = trop large ; precise le moteur).
- Tu peux trouver 0 redundant ou 0 edge — si c'est le cas, retourne liste vide. Ne force pas.

Reponds UNIQUEMENT en JSON valide selon ce schema :

{{
  "narrative_clusters": [
    {{
      "name": "...",
      "tickers": ["TK1", "TK2"],
      "shared_drivers": "...",
      "narrative_overlap_score": 75
    }}
  ],
  "edge_positions": [
    {{"ticker": "TK", "reason": "..."}}
  ],
  "redundant_positions": [
    {{"ticker": "TK", "redundant_with": "TK_main", "reason": "..."}}
  ],
  "uncategorized_tickers": ["..."]
}}
"""


def _format_positions_block(positions: list[dict]) -> str:
    lines = []
    for p in positions:
        kd = p.get("key_drivers", "") or ""
        notes = p.get("notes", "") or ""
        lines.append(
            f"- {p['ticker']} ({p['weight_pct']}% du book, conv c{p.get('conviction') or '?'})\n"
            f"  drivers: {kd}\n"
            f"  notes: {notes}"
        )
    return "\n".join(lines)


def run_synthesis() -> tuple[dict, int | None]:
    """Call Opus to synthesize narrative clusters. Returns (result, snapshot_id)."""
    ctx = assemble_narrative_context()
    if not ctx["positions"]:
        log.info("portfolio_grade_llm: no positions, skip")
        return {}, None
    prompt = _NARRATIVE_PROMPT.format(
        n=ctx["n_positions"],
        total=ctx["total_eur"],
        positions_block=_format_positions_block(ctx["positions"]),
    )
    try:
        result = llm.call_json(prompt, tier="synthesize", max_tokens=3500)
    except Exception as e:
        log.error(f"portfolio_grade_llm synthesis failed: {e}")
        return {}, None

    snapshot_date = datetime.now(UTC).date().isoformat()
    clusters_json = json.dumps(result.get("narrative_clusters") or [], ensure_ascii=False)
    edges_json = json.dumps(
        {
            "edge_positions": result.get("edge_positions") or [],
            "redundant_positions": result.get("redundant_positions") or [],
            "uncategorized_tickers": result.get("uncategorized_tickers") or [],
        },
        ensure_ascii=False,
    )
    sid = storage.insert_narrative_snapshot(snapshot_date, clusters_json, edges_json)
    log.info(
        f"portfolio_grade_llm: snapshot id={sid} clusters={len(result.get('narrative_clusters') or [])}"
    )
    return result, sid


def get_latest_narrative_snapshot() -> dict | None:
    """Reads back the most recent narrative cluster snapshot."""
    raw = storage.get_latest_narrative_snapshot()
    if not raw:
        return None
    return {
        "id": raw["id"],
        "snapshot_date": raw["snapshot_date"],
        "clusters": json.loads(raw["clusters_json"] or "[]"),
        "edges": json.loads(raw["edges_json"] or "{}"),
    }
