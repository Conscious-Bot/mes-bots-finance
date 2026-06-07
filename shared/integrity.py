"""A2 : tamper-evident hash chain pour decision_journal / thesis_integrity_log.

Spec red-team 07/06 nuit DECISION_QUALITY_ENGINE A2.

3 fonctions :
- `canonical_payload(d)` : json sort_keys + float formate str 6 decimales
  (sinon hash non-repro entre Python builds = verify_chain casse silencieux)
- `compute_hash(payload, prev_hash)` : sha256(canonical(payload) + prev_hash)
- `chain_append(prev_hash, payload)` : convenience helper

Genesis = 64*'0' (canonical genesis null hash).

Doctrine respectee :
- L15 fail-closed : si chain cassee (anchor_ref divergent), le moteur de
  scoring downstream refuse de scorer (jamais de verdict fabrique).
- L17 : decision_journal append-only, anchor_ref pointe vers preuve externe
  (git tag signe ou OpenTimestamps).
- Anti-double-instrumentation L4 : 1 seul lieu de canonicalisation pour
  garantir reproducibilite cross-process.

Pourquoi format float strict :
- Python json.dumps(0.1) -> "0.1" OU "0.1000000001" selon build/version
- json.loads(...)) round-trip varie
- sha256(canonical(payload) + prev) doit etre BIT-IDENTIQUE entre 2 verify
- Solution : tous les floats -> str(round(v, 6)) AVANT serialisation
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

GENESIS_HASH = "0" * 64  # canonical genesis null


def _format_floats(obj: Any) -> Any:
    """Recursive : convertit tous les floats en str fixed 6 decimales.

    Garantit que json.dumps(canonical) est bit-identique cross-build.
    Pas de fall-thru sur dict/list -> deep walk.
    """
    if isinstance(obj, float):
        return f"{obj:.6f}"
    if isinstance(obj, dict):
        return {k: _format_floats(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_format_floats(v) for v in obj]
    return obj


def canonical_payload(payload: dict[str, Any]) -> str:
    """Serialise un payload en JSON canonique reproductible.

    Order : sort_keys=True deterministe.
    Format : separators=(',', ':') = no whitespace cross-build.
    Floats : str 6 decimales -> bit-identique.

    Garantie : 2 appels avec meme dict -> meme str byte-for-byte.
    """
    return json.dumps(
        _format_floats(payload),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        ensure_ascii=True,
    )


def compute_hash(payload: dict[str, Any], prev_hash: str) -> str:
    """sha256(canonical(payload) + prev_hash). Hex digest."""
    body = canonical_payload(payload)
    h = hashlib.sha256()
    h.update(body.encode("utf-8"))
    h.update(prev_hash.encode("utf-8"))
    return h.hexdigest()


def chain_append(
    prev_hash: str | None, payload: dict[str, Any]
) -> tuple[str, str]:
    """Helper : append nouveau payload a la chaine.

    Args:
        prev_hash : hash de la row precedente, ou None = genesis (utilise GENESIS_HASH)
        payload : dict (canonicalise au moment de hash)

    Returns:
        (prev_hash_used, new_chain_hash) -- prev pour storage row, new pour
        chainage suivant.
    """
    prev = prev_hash if prev_hash else GENESIS_HASH
    new_hash = compute_hash(payload, prev)
    return prev, new_hash


def anchor_chain_head(
    head_hash: str,
    head_seq: int,
    anchor_dir: str = "integrity_anchors",  # repo root (data/ gitignored)
) -> dict:
    """A4 : anchor externe du head chain (PASSE A1-A3 du theater au reel).

    Sans A4, un attaquant local peut reecrire toute la chain (recalculer
    tous les chain_hash + payload_json) car aucune preuve externe ne fixe
    l'etat de la chain a T0. A4 ecrit le head dans un fichier git-trackable
    + (optionnel) tag signe pour push origin.

    Args:
        head_hash : chain_hash de la derniere row inseree
        head_seq : seq correspondant (pour update anchor_ref en DB)
        anchor_dir : dossier ou ecrire le fichier anchor

    Returns:
        dict {anchor_file, head_hash, head_seq, anchor_ref, git_tag_attempted}

    Strategy minimale (V0, sans git config) :
    1. Ecrire data/integrity_anchors/<YYYY-MM-DD>.txt avec head + ts
    2. Git tag (-s si gpg key configuree, sinon -a unsigned) integrity/<date>-<short>
    3. anchor_ref = format 'file:<path>' ou 'git_tag:integrity/...'

    Cron daily : scripts/anchor_chain_head_daily.py invoque cette fonction.
    """
    import os
    import subprocess
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    date_str = now.strftime("%Y-%m-%d")
    ts_iso = now.isoformat()

    # Step 1 : ecrire fichier anchor
    os.makedirs(anchor_dir, exist_ok=True)
    anchor_file = os.path.join(anchor_dir, f"{date_str}.txt")
    content = (
        f"# PRESAGE thesis_integrity_log anchor\n"
        f"date: {date_str}\n"
        f"timestamp_iso: {ts_iso}\n"
        f"head_seq: {head_seq}\n"
        f"head_chain_hash: {head_hash}\n"
        f"# Recompute via shared.integrity.verify_chain on rows up to seq={head_seq}\n"
    )
    try:
        with open(anchor_file, "w") as f:
            f.write(content)
        wrote_file = True
    except Exception:
        wrote_file = False

    # Step 2 : git tag (best-effort)
    git_tag_attempted = False
    git_tag_success = False
    tag_name = f"integrity/{date_str}-{head_hash[:8]}"
    try:
        # Try signed first, fall back to annotated unsigned
        result_signed = subprocess.run(
            ["git", "tag", "-s", "-m", f"integrity anchor {date_str}", tag_name],
            capture_output=True, text=True, timeout=10,
        )
        git_tag_attempted = True
        if result_signed.returncode == 0:
            git_tag_success = True
        else:
            # Fall back unsigned annotated
            result_annot = subprocess.run(
                ["git", "tag", "-a", "-m", f"integrity anchor {date_str}", tag_name],
                capture_output=True, text=True, timeout=10,
            )
            if result_annot.returncode == 0:
                git_tag_success = True
    except Exception:
        pass

    anchor_ref = (
        f"git_tag:{tag_name}" if git_tag_success
        else (f"file:{anchor_file}" if wrote_file else "")
    )
    return {
        "anchor_file": anchor_file if wrote_file else None,
        "head_hash": head_hash,
        "head_seq": head_seq,
        "anchor_ref": anchor_ref,
        "git_tag_attempted": git_tag_attempted,
        "git_tag_success": git_tag_success,
        "wrote_file": wrote_file,
    }


def verify_chain(rows: list[dict[str, Any]]) -> tuple[bool, int | None]:
    """Verifie integrite chaine ordonnee par seq.

    Args:
        rows : liste de dict avec keys (seq, payload_json, prev_hash, chain_hash)

    Returns:
        (ok, broken_seq_or_None) :
          - (True, None) si chaine OK from genesis
          - (False, seq) avec seq de la 1ere row brisee

    Doctrine L15 : si broken -> scoring downstream refuse de calculer (None /
    UNATTRIBUTABLE), jamais un verdict fabrique.
    """
    if not rows:
        return True, None
    sorted_rows = sorted(rows, key=lambda r: r["seq"])
    expected_prev = GENESIS_HASH
    for r in sorted_rows:
        # Decode payload (stocke en JSON string en DB)
        payload_str = r["payload_json"]
        if isinstance(payload_str, str):
            try:
                payload = json.loads(payload_str)
            except json.JSONDecodeError:
                return False, r["seq"]
        else:
            payload = payload_str
        # Recompute hash
        actual_hash = compute_hash(payload, expected_prev)
        if actual_hash != r["chain_hash"]:
            return False, r["seq"]
        # Check prev_hash row consistency
        if r["prev_hash"] != expected_prev:
            return False, r["seq"]
        expected_prev = r["chain_hash"]
    return True, None
