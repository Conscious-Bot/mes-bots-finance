"""Thesis library : Voyage finance embeddings + Chroma SQLite local pour RAG.

DOCTRINE (memory `business_path_6_acted`) : wedge = discipline mecanisee, pas
alpha predictif. Cet outil mecanise la discipline en miroir : quand tu prepares
une nouvelle thesis, le systeme retrieve les K plus similaires DANS TON track
record + leur outcome. Tu vois ton propre comportement passe sur des setups
ressemblants. Anti-FOMO, anti-lock_in via comparaison historique.

Stack-fit (memory contraintes) :
- Voyage `voyage-finance-2` = embedding specialise finance, ~$0.05/M tokens
- Chroma local backed by SQLite (data/thesis_chroma/) = ZERO nouvelle infra
- Pas de Postgres/Redis/Docker (memory)
- ~300 theses ledger lifetime = ~$0.001 total cost embedding

Setup une fois :
  1. Free Voyage signup https://voyageai.com → API key
  2. .env : VOYAGE_API_KEY=pa-xxx
  3. python3 -c "from shared.thesis_library import bootstrap_from_db ; bootstrap_from_db()"
     Index toutes theses existantes (book + resolved) en une fois.

Discipline fail-soft : sans key → return [] sur queries, no raise. Cron-safe.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("thesis_library")

try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    chromadb = None
    Settings = None

try:
    import voyageai
except ImportError:
    voyageai = None

REPO = Path(__file__).resolve().parent.parent
CHROMA_DIR = REPO / "data" / "thesis_chroma"
COLLECTION_NAME = "thesis_library_v1"
VOYAGE_MODEL = "voyage-finance-2"


def _voyage_client():
    if voyageai is None:
        return None
    key = os.environ.get("VOYAGE_API_KEY")
    if not key:
        return None
    return voyageai.Client(api_key=key)


def _chroma_client():
    if chromadb is None:
        return None
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(CHROMA_DIR),
        settings=Settings(anonymized_telemetry=False),
    )


def _collection():
    c = _chroma_client()
    if c is None:
        return None
    return c.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def _embed(texts: list[str], input_type: str = "document") -> list[list[float]] | None:
    """Embed via Voyage. input_type='document' for store, 'query' for search."""
    vc = _voyage_client()
    if vc is None or not texts:
        return None
    try:
        resp = vc.embed(texts, model=VOYAGE_MODEL, input_type=input_type)
        return resp.embeddings
    except Exception:
        return None


def upsert_thesis(thesis_id: str, text: str, metadata: dict[str, Any]) -> bool:
    """Index ou update une thesis. metadata : ticker, conviction, outcome, etc.

    metadata Chroma constraint : scalar values only (str/int/float/bool).
    Filtre les nested dicts/lists.
    """
    col = _collection()
    if col is None:
        return False
    emb = _embed([text], input_type="document")
    if emb is None:
        return False
    clean_meta = {k: v for k, v in metadata.items() if isinstance(v, (str, int, float, bool))}
    try:
        col.upsert(
            ids=[thesis_id],
            embeddings=emb,
            documents=[text],
            metadatas=[clean_meta],
        )
        return True
    except Exception:
        return False


def find_similar(query_text: str, k: int = 5, filter_meta: dict | None = None) -> list[dict]:
    """Retrieve K plus similaires. filter_meta optionnel pour filtrer (e.g. {ticker:NVDA})."""
    col = _collection()
    if col is None:
        return []
    emb = _embed([query_text], input_type="query")
    if emb is None:
        return []
    try:
        result = col.query(
            query_embeddings=emb,
            n_results=k,
            where=filter_meta,
            include=["documents", "metadatas", "distances"],
        )
        out = []
        ids = result.get("ids", [[]])[0]
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        dists = result.get("distances", [[]])[0]
        for i, doc, meta, dist in zip(ids, docs, metas, dists):
            out.append({
                "thesis_id": i,
                "document": doc[:500],
                "metadata": meta,
                "distance": dist,
                "similarity": 1.0 - dist,
            })
        return out
    except Exception:
        return []


def collection_stats() -> dict:
    """Snapshot health : count, last upsert timestamp si dispo."""
    col = _collection()
    if col is None:
        return {"error": "chromadb / collection unavailable"}
    try:
        return {"count": col.count(), "name": COLLECTION_NAME, "path": str(CHROMA_DIR)}
    except Exception as e:
        return {"error": f"{type(e).__name__} {e}"}


def bootstrap_from_db(batch_size: int = 40, sleep_s: float = 0.0) -> dict:
    """One-shot : index toutes theses existantes du book + resolved.

    batch_size + sleep_s : pace pour le rate-limit. Free tier Voyage sans moyen
    de paiement = 3 RPM + 10K TPM → batch_size=40 (~7-8K tokens) + sleep_s=60
    (1 req/min) reste sous les deux plafonds. Tier payant : sleep_s=0, batch=128.

    Source : table `predictions` (manual + auto). Concat les champs pertinents
    pour text embedding : claim_text si dispo, sinon ticker + direction + horizon.
    metadata : ticker, conviction, claim_type, target_date, outcome, status, created_at.

    Doctrine L17 (test_doctrine_grep_gates) : utilise shared.storage.db()
    context manager au lieu de raw sqlite3 (cure 14/06/2026 post pytest fail).
    """
    if _voyage_client() is None:
        return {"error": "VOYAGE_API_KEY missing"}
    if _collection() is None:
        return {"error": "chromadb unavailable"}

    from shared.storage import db as _storage_db
    with _storage_db() as conn:
        # ADR014-EXEMPT : library bootstrap indexe ALL predictions
        # (methodology_version preserve en metadata, filtrage au retrieval).
        cur = conn.execute("""
            SELECT id, ticker, direction, horizon_days, target_date, outcome,
                   origin, claim_type, methodology_version, created_at,
                   probability_at_creation, scoring_trace_json
            FROM predictions
            ORDER BY created_at DESC
        """)
        rows = cur.fetchall()
    # Compose (id, text, meta) pour toutes les lignes
    items: list[tuple[str, str, dict]] = []
    for row in rows:
        pid, ticker, direction, horizon, td, outcome, origin, ctype, _mv, ca, prob, trace = row
        text_parts = [
            f"ID:{pid}",
            f"Ticker:{ticker or 'macro'}",
            f"Direction:{direction or '?'}",
            f"ClaimType:{ctype or '?'}",
            f"Horizon:{horizon or '?'} days",
            f"TargetDate:{td or '?'}",
            f"Origin:{origin or '?'}",
            f"Created:{ca or '?'}",
            f"Outcome:{outcome or 'pending'}",
            f"ProbAtCreation:{prob}",
        ]
        if trace:
            text_parts.append(f"Trace:{str(trace)[:500]}")
        meta = {
            "pid": int(pid),
            "ticker": ticker or "macro",
            "direction": direction or "?",
            "claim_type": ctype or "?",
            "origin": origin or "?",
            "outcome": outcome or "pending",
            "created_at": ca or "?",
            "probability_at_creation": float(prob) if prob is not None else 0.0,
        }
        items.append((f"pred_{pid}", " | ".join(text_parts), meta))

    # Embed + upsert par BATCH (cure rate-limit 30/06 : 1 appel API / lot au lieu
    # de 1 / thèse → ~5 appels pour 422 lignes au lieu de 422, le free tier ~3 RPM
    # ne coince plus). Voyage accepte une liste de textes par requête.
    col = _collection()
    indexed, skipped = 0, 0
    for i in range(0, len(items), batch_size):
        if i > 0 and sleep_s:
            time.sleep(sleep_s)  # respecte 3 RPM + 10K TPM du free tier
        chunk = items[i:i + batch_size]
        embs = _embed([t for _, t, _ in chunk], input_type="document")
        if embs is None:
            skipped += len(chunk)
            continue
        try:
            col.upsert(
                ids=[c[0] for c in chunk],
                embeddings=embs,
                documents=[c[1] for c in chunk],
                metadatas=[c[2] for c in chunk],
            )
            indexed += len(chunk)
        except Exception as e:
            log.warning(f"bootstrap batch upsert failed ({len(chunk)} items): {e}")
            skipped += len(chunk)
    return {"indexed": indexed, "skipped": skipped, "total_rows": len(rows)}


if __name__ == "__main__":
    print("Collection stats:", collection_stats())
    print()
    # Sample query
    sample = find_similar("NVDA AI infrastructure capex cycle", k=3)
    for r in sample:
        print(f"  sim={r['similarity']:.3f} pid={r['metadata'].get('pid')} ticker={r['metadata'].get('ticker')} outcome={r['metadata'].get('outcome')}")
