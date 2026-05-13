"""Phase A3 — Echo cluster detection via cosine similarity over embedded signals."""

from collections import defaultdict

import numpy as np

from shared import embeddings, storage


def compute_clusters(window_hours=48, sim_threshold=0.85):
    """Find echo clusters via union-find on cosine sim > threshold.

    Returns: list of {cluster_id, signal_ids, sources, n_signals, n_unique_sources}.
    Singletons get unique cluster_ids; connected components share ids.
    """
    rows = storage.get_embedded_signals_window(hours=window_hours)
    if not rows:
        return []

    n = len(rows)
    vecs = np.array([embeddings.deserialize(r["embedding"]) for r in rows])
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vecs_n = vecs / norms
    sim_matrix = vecs_n @ vecs_n.T

    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        for j in range(i + 1, n):
            if sim_matrix[i, j] >= sim_threshold:
                union(i, j)

    groups = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)

    clusters = []
    cid_counter = 1
    for indices in groups.values():
        sig_ids = [rows[i]["id"] for i in indices]
        srcs = [rows[i].get("source_name") for i in indices if rows[i].get("source_name")]
        unique_srcs = sorted(set(srcs))
        clusters.append(
            {
                "cluster_id": cid_counter,
                "signal_ids": sig_ids,
                "sources": unique_srcs,
                "n_signals": len(sig_ids),
                "n_unique_sources": len(unique_srcs),
            }
        )
        cid_counter += 1
    return clusters


def persist_clusters(clusters):
    """Tag each signal in DB with its computed cluster_id."""
    for cluster in clusters:
        cid = cluster["cluster_id"]
        for sid in cluster["signal_ids"]:
            storage.set_echo_cluster_id(sid, cid)


def get_recent_multi_source_clusters(window_hours=48, min_unique_sources=2):
    """Return clusters with >=N unique sources (true corroboration, not self-echo)."""
    rows = storage.get_embedded_signals_window(hours=window_hours)
    by_cluster = defaultdict(list)
    for r in rows:
        cid = r.get("echo_cluster_id")
        if cid:
            by_cluster[cid].append(r)
    result = []
    for cid, signals in by_cluster.items():
        unique_srcs = {s.get("source_name") for s in signals if s.get("source_name")}
        if len(unique_srcs) >= min_unique_sources:
            result.append(
                {
                    "cluster_id": cid,
                    "signals": signals,
                    "n_unique_sources": len(unique_srcs),
                    "sources": sorted(unique_srcs),
                }
            )
    return sorted(result, key=lambda x: x["n_unique_sources"], reverse=True)
