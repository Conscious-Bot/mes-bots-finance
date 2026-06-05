"""Decompose Brier ledger par cluster narratif de theses.

Question repondue : ou est ton edge reel ? Lieu commun "j'ai un avis sur les
semis" est utile mais sous-determine. Ce script :

  1. Embed les `key_drivers` de chaque these (sentence-transformer bge-small)
  2. Cluster en K groupes (KMeans avec K choisi via silhouette score sur k=[2..6])
  3. Pour chaque cluster : tickers + sample key_drivers + Brier mean
     ± bootstrap CI sur les predictions resolues correspondantes
  4. Sortie texte structure utilisable Telegram / stdout

Lecture honnete (cf [[J-day reading contract]]) : a N=15 resolved scored, le CI
sera tres large. Le verdict per-cluster sera majoritairement "inconclusive" / NULL.
C'est attendu et c'est le contract qui dit la verite -- les clusters mono-bucket
N<5 ne disent rien. L'output est un *transparency snapshot*, pas un verdict.

Usage :
  python -m scripts.thesis_clusters_brier
  python -m scripts.thesis_clusters_brier --k 4  # force k
  python -m scripts.thesis_clusters_brier --include all  # all statuses au lieu de active+closed
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np

from shared import storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
log = logging.getLogger("thesis_clusters")

# Cohort par defaut : actif + closed-states utiles (predictions historiques liees toujours valides)
DEFAULT_STATUSES = ("active", "concluded", "realized", "superseded")
BOOTSTRAP_N = 1000
BOOTSTRAP_SEED = 42  # deterministe pour reproducibilite


def fetch_theses(conn: sqlite3.Connection, statuses: tuple[str, ...]) -> list[dict]:
    """Charge theses avec key_drivers non-null. Parse les key_drivers JSON en texte joint."""
    placeholders = ",".join("?" for _ in statuses)
    rows = conn.execute(
        f"SELECT id, ticker, conviction, direction, status, key_drivers, "
        f"       opened_at, target_price, stop_price, entry_price "
        f"FROM theses WHERE status IN ({placeholders}) AND key_drivers IS NOT NULL "
        f"AND TRIM(key_drivers) != '' AND TRIM(key_drivers) != '[]'",
        statuses,
    ).fetchall()
    out = []
    for r in rows:
        drivers_raw = r[5]
        try:
            parsed = json.loads(drivers_raw)
            if isinstance(parsed, list):
                drivers_text = " | ".join(str(d) for d in parsed if d)
            else:
                drivers_text = str(parsed)
        except Exception:
            drivers_text = str(drivers_raw)
        if not drivers_text.strip():
            continue
        out.append({
            "id": r[0],
            "ticker": r[1],
            "conviction": r[2],
            "direction": r[3],
            "status": r[4],
            "drivers_text": drivers_text,
            "drivers_raw": drivers_raw,
            "opened_at": r[6],
        })
    return out


def fetch_resolved_predictions(conn: sqlite3.Connection, tickers: set[str]) -> dict[str, list[float]]:
    """Pour chaque ticker, retourne la liste des Brier scores resolus (outcome != neutral)."""
    if not tickers:
        return {}
    placeholders = ",".join("?" for _ in tickers)
    rows = conn.execute(
        f"SELECT ticker, brier_score FROM predictions "
        f"WHERE ticker IN ({placeholders}) "
        f"  AND resolved_at IS NOT NULL "
        f"  AND outcome IN ('correct', 'incorrect') "
        f"  AND brier_score IS NOT NULL",
        tuple(tickers),
    ).fetchall()
    out: dict[str, list[float]] = {}
    for ticker, brier in rows:
        out.setdefault(ticker, []).append(float(brier))
    return out


def pick_k_via_silhouette(embeddings: np.ndarray, k_range: range) -> int:
    """Pick k that maximizes silhouette score. Returns best k."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    if len(embeddings) < max(k_range) + 1:
        return min(2, len(embeddings) - 1)
    best_k = 2
    best_score = -1.0
    for k in k_range:
        if k >= len(embeddings):
            continue
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(embeddings)
        if len(set(labels)) < 2:
            continue
        score = silhouette_score(embeddings, labels)
        log.info(f"  k={k} silhouette={score:.3f}")
        if score > best_score:
            best_score = score
            best_k = k
    log.info(f"Best k by silhouette : {best_k} (score {best_score:.3f})")
    return best_k


def cluster_theses(theses: list[dict], k: int | None) -> np.ndarray:
    """Embed key_drivers et cluster. Returns labels (np.ndarray len(theses))."""
    from sklearn.cluster import KMeans

    from shared import embeddings as emb

    texts = [t["drivers_text"][:500] for t in theses]
    log.info(f"Embedding {len(texts)} theses key_drivers ({emb.model_name()})...")
    vecs = emb.embed_batch(texts)
    log.info(f"  embeddings shape : {vecs.shape}")

    if k is None:
        k_max = min(6, len(theses) - 1)
        k_range = range(2, k_max + 1)
        log.info(f"Picking k via silhouette on k={list(k_range)}...")
        k = pick_k_via_silhouette(vecs, k_range)

    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = km.fit_predict(vecs)
    return labels


def bootstrap_ci(values: list[float], n_iter: int = BOOTSTRAP_N, ci: float = 0.95) -> tuple[float, float]:
    """Percentile bootstrap CI sur la moyenne. Seed deterministe."""
    if not values:
        return (float("nan"), float("nan"))
    rng = random.Random(BOOTSTRAP_SEED)
    means = []
    for _ in range(n_iter):
        sample = [values[rng.randint(0, len(values) - 1)] for _ in range(len(values))]
        means.append(sum(sample) / len(sample))
    means.sort()
    lo_idx = int((1 - ci) / 2 * n_iter)
    hi_idx = int((1 + ci) / 2 * n_iter) - 1
    return (means[lo_idx], means[hi_idx])


def label_cluster(theses_in_cluster: list[dict]) -> str:
    """Genere un label heuristique pour le cluster a partir des top tickers."""
    if not theses_in_cluster:
        return "(empty)"
    tickers = sorted({t["ticker"] for t in theses_in_cluster})[:5]
    return ", ".join(tickers) + ("..." if len(theses_in_cluster) > 5 else "")


def decompose_by_key(
    theses: list[dict],
    pred_briers: dict[str, list[float]],
    key_fn,
    key_label: str,
) -> None:
    """Decompose Brier par dimension arbitraire (conviction, direction, etc.)
    Print les buckets non-vides en ordre value descendant.
    """
    buckets: dict[object, list[dict]] = {}
    for t in theses:
        k = key_fn(t)
        if k is None:
            continue
        buckets.setdefault(k, []).append(t)

    # Sort buckets : par valeur descendante pour conviction (5->1), alphabetique sinon
    try:
        sorted_keys = sorted(buckets.keys(), key=lambda k: (-int(k),))
    except (TypeError, ValueError):
        sorted_keys = sorted(buckets.keys(), key=lambda k: str(k))

    print(f"─── DECOMPOSITION BY {key_label.upper()} ───")
    for k in sorted_keys:
        in_bucket = buckets[k]
        tickers = sorted({t["ticker"] for t in in_bucket})
        briers: list[float] = []
        for tk in tickers:
            briers.extend(pred_briers.get(tk, []))
        line = f"  {key_label}={k} : n_theses={len(in_bucket)} ({len(tickers)} unique tickers)"
        if len(briers) >= 5:
            mean = sum(briers) / len(briers)
            lo, hi = bootstrap_ci(briers)
            envelope = lo <= 0.250 <= hi
            if envelope:
                verdict = "INCONCLUSIVE"
            elif hi < 0.250:
                verdict = "EARNED (CI<0.25)"
            else:
                verdict = "DID NOT EARN (CI>0.25)"
            line += f" | Brier(N={len(briers)}) mean={mean:.3f} CI[{lo:.3f}, {hi:.3f}] {verdict}"
        elif briers:
            mean = sum(briers) / len(briers)
            line += f" | Brier(N={len(briers)}<5) mean={mean:.3f} NULL (sample trop petit)"
        else:
            line += " | Brier: 0 resolved (pas de prediction resolue sur ces tickers)"
        print(line)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--k", type=int, default=None,
                        help="Force k clusters. Sinon silhouette score picks.")
    parser.add_argument("--include", choices=["default", "all", "active"], default="default",
                        help="Cohort : default (active+closed), all (toutes), active only.")
    args = parser.parse_args()

    statuses_map = {
        "default": DEFAULT_STATUSES,
        "all": ("active", "concluded", "realized", "superseded", "deleted", "out_of_scope"),
        "active": ("active",),
    }
    statuses = statuses_map[args.include]

    conn = sqlite3.connect(storage.DB_PATH)
    try:
        theses = fetch_theses(conn, statuses)
        log.info(f"Loaded {len(theses)} theses (status IN {statuses})")
        if len(theses) < 4:
            log.error(f"Pas assez de theses ({len(theses)} < 4) pour clusterer utilement.")
            return

        labels = cluster_theses(theses, k=args.k)
        n_clusters = int(labels.max()) + 1

        all_tickers = {t["ticker"] for t in theses}
        pred_briers = fetch_resolved_predictions(conn, all_tickers)
        log.info(f"Predictions resolved+scored : {sum(len(v) for v in pred_briers.values())} pour {len(pred_briers)} tickers")
    finally:
        conn.close()

    # Agregate per cluster
    print("\n" + "=" * 78)
    print("THESIS CLUSTERS — BRIER DECOMPOSITION")
    print("=" * 78)
    print(f"Cohort : {len(theses)} theses (statuses={statuses})")
    print(f"K clusters : {n_clusters}")
    print(f"Resolved+scored predictions : {sum(len(v) for v in pred_briers.values())}")
    print("Baseline no-skill Brier : 0.250")
    print()

    for cid in range(n_clusters):
        in_cluster = [theses[i] for i in range(len(theses)) if labels[i] == cid]
        cluster_tickers = sorted({t["ticker"] for t in in_cluster})
        cluster_briers: list[float] = []
        for tk in cluster_tickers:
            cluster_briers.extend(pred_briers.get(tk, []))

        print(f"─── Cluster {cid} ─── n_theses={len(in_cluster)} ────")
        print(f"  Tickers : {', '.join(cluster_tickers[:12])}" + (" ..." if len(cluster_tickers) > 12 else ""))
        convict_dist = {}
        for t in in_cluster:
            c = t["conviction"]
            convict_dist[c] = convict_dist.get(c, 0) + 1
        print(f"  Conviction : {dict(sorted(convict_dist.items(), reverse=True))}")

        # Sample 2 key_drivers
        sample = in_cluster[: min(2, len(in_cluster))]
        for s in sample:
            preview = s["drivers_text"][:140].replace("\n", " ")
            print(f"  ex {s['ticker']} (c{s['conviction']}): {preview}{'...' if len(s['drivers_text']) > 140 else ''}")

        # Brier
        if len(cluster_briers) >= 5:
            mean = sum(cluster_briers) / len(cluster_briers)
            lo, hi = bootstrap_ci(cluster_briers)
            envelope_baseline = lo <= 0.250 <= hi
            if envelope_baseline:
                verdict = "INCONCLUSIVE (CI englobe baseline 0.250)"
            elif hi < 0.250:
                verdict = "EARNED its cost (CI<baseline)"
            else:
                verdict = "DID NOT EARN (CI>baseline)"
            print(f"  Brier (N={len(cluster_briers)}) : mean={mean:.3f} CI95%[{lo:.3f}, {hi:.3f}] -> {verdict}")
        else:
            print(f"  Brier : N={len(cluster_briers)} < 5 -> NULL (sample trop petit)")
        print()

    print("=" * 78)
    print()

    # Decomposition par dimensions canoniques (orthogonales aux clusters narratifs)
    decompose_by_key(theses, pred_briers, lambda t: t["conviction"], "conviction")
    decompose_by_key(theses, pred_briers, lambda t: t["direction"], "direction")
    decompose_by_key(theses, pred_briers, lambda t: t["status"], "status")

    print("=" * 78)
    print("Note : N par cluster reste petit (cohort entier ~15-30 resolved).")
    print("Lire les verdicts comme transparency snapshot, pas comme binding read.")
    print("CI bootstrap assume independance des predictions (n'est pas le cas")
    print("  -- predictions theme-correlated -> uncertainty reelle > CI affiche).")
    print("=" * 78)


if __name__ == "__main__":
    main()
