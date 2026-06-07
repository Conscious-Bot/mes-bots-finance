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


class NonCanonicalTypeError(TypeError):
    """Type non-canonicalisable dans le payload (datetime, Decimal, etc).

    Catch #1 red-team 07/06 nuit++ : default=str dans canonical_payload
    etait un footgun de repro. Un payload contenant datetime / Decimal
    se stringifie d'une facon qu'un tiers ne reproduit pas sans connaitre
    le type d'origine. Pour de la prouvabilite, on INTERDIT explicitement
    (raise) plutot que de stringifier en douce.

    Convention : le caller doit normaliser les types AVANT canonical_payload
    (isoformat() pour datetime, str(Decimal(...)) pour Decimal, etc).
    """


_ALLOWED_PRIMITIVES = (str, int, bool, type(None))


def _format_floats(obj: Any) -> Any:
    """Recursive : convertit tous les floats en str fixed 6 decimales.

    Garantit que json.dumps(canonical) est bit-identique cross-build.
    Pas de fall-thru sur dict/list -> deep walk.

    RAISE NonCanonicalTypeError sur tout type non-primitive (catch repro).
    """
    if isinstance(obj, float):
        return f"{obj:.6f}"
    if isinstance(obj, bool):
        # bool est sous-classe de int en Python, traiter avant int
        return obj
    if isinstance(obj, _ALLOWED_PRIMITIVES):
        return obj
    if isinstance(obj, dict):
        return {k: _format_floats(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_format_floats(v) for v in obj]
    # Catch repro : tout autre type = footgun
    raise NonCanonicalTypeError(
        f"Type {type(obj).__name__!r} non canonicalisable. Normaliser AVANT "
        "canonical_payload (datetime.isoformat() / str(Decimal) / etc). "
        "Cf catch red-team 07/06 nuit++ : default=str interdit pour prouvabilite."
    )


def canonical_payload(payload: dict[str, Any]) -> str:
    """Serialise un payload en JSON canonique reproductible.

    Order : sort_keys=True deterministe.
    Format : separators=(',', ':') = no whitespace cross-build.
    Floats : str 6 decimales -> bit-identique.
    Types interdits : tout sauf str/int/bool/None/float/dict/list/tuple
      -> raise NonCanonicalTypeError.

    Garantie : 2 appels avec meme dict -> meme str byte-for-byte.
    """
    formatted = _format_floats(payload)
    return json.dumps(
        formatted,
        sort_keys=True,
        separators=(",", ":"),
        # PAS de default=str : footgun repro. Tout type non-JSON-primitive
        # doit etre normalise AVANT par le caller.
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


class AnchorFailedError(RuntimeError):
    """Anchor externe n'a pas reussi -> chain non-prouvable a T0.

    Catch #2 red-team 07/06 nuit++ : silent fallback to file: violait L15.
    Une chain non-ancree externe = exactement le moment ou le downstream
    doit REFUSER de scorer. L15 fail-closed loud, pas swallow.

    L'absence d'OTS receipt = absence de preuve trustless (operateur solo +
    repo prive = pas de tiers contraint).
    """


def anchor_chain_head(
    head_hash: str,
    head_seq: int,
    anchor_dir: str = "integrity_anchors",
    require_ots: bool = True,
) -> dict:
    """A4 : anchor externe trustless du head chain.

    Catch #1 red-team : git tag privé != trustless. L'operateur solo
    controle le repo, peut git tag -d + push --force. La seule preuve
    trustless dans cette position = OpenTimestamps (Bitcoin anchor) ou
    publish dans audience tierce.

    Strategy V1 (post-catch) :
    1. Ecrire integrity_anchors/<date>.txt (git-trackable, audit local)
    2. OTS stamp file (preuve Bitcoin trustless, async ~confirmation)
    3. git tag annotated (audit secondaire, pas preuve)
    4. Si require_ots=True : RAISE AnchorFailedError si ots non dispo
       (L15 fail-closed loud : chain non-ancree -> downstream refuse)

    Args:
        head_hash, head_seq : head courant chain
        anchor_dir : git-trackable
        require_ots : si True, raise si ots absent (default). False =
          best-effort pour environnements dev sans ots wire.

    Returns:
        dict avec anchor_file + ots_file + git_tag + anchor_ref classifie

    Raises:
        AnchorFailedError si require_ots=True ET ots non dispo / fail.
    """
    import shutil
    import subprocess
    from datetime import UTC, datetime
    from pathlib import Path

    now = datetime.now(UTC)
    date_str = now.strftime("%Y-%m-%d")
    ts_iso = now.isoformat()

    # Step 1 : ecrire fichier anchor (echec = fail-closed loud)
    anchor_path = Path(anchor_dir)
    anchor_path.mkdir(parents=True, exist_ok=True)
    anchor_file = str(anchor_path / f"{date_str}.txt")
    content = (
        f"# PRESAGE thesis_integrity_log anchor\n"
        f"date: {date_str}\n"
        f"timestamp_iso: {ts_iso}\n"
        f"head_seq: {head_seq}\n"
        f"head_chain_hash: {head_hash}\n"
        f"# Recompute via shared.integrity.verify_chain on rows up to seq={head_seq}\n"
    )
    with open(anchor_file, "w") as f:
        f.write(content)

    # Step 2 : OTS stamp (preuve trustless Bitcoin) -- catch #1 fix
    ots_available = shutil.which("ots") is not None
    ots_file = None
    if ots_available:
        result_ots = subprocess.run(
            ["ots", "stamp", anchor_file],
            capture_output=True, text=True, timeout=30,
        )
        if result_ots.returncode == 0:
            ots_file = anchor_file + ".ots"
        else:
            if require_ots:
                raise AnchorFailedError(
                    f"ots stamp failed (rc={result_ots.returncode}): "
                    f"{result_ots.stderr[:200]}. Chain NON-prouvable a T0."
                )
    elif require_ots:
        # L15 loud : pas d'OTS = pas de preuve trustless
        raise AnchorFailedError(
            "opentimestamps-client (ots) non installe. Sans OTS, "
            "git tag prive seul = THEATER (operateur solo controle repo). "
            "Install : pip install opentimestamps-client. "
            "Bypass dev (NON-PROUVABLE) : require_ots=False."
        )

    # Step 3 : git tag annotated (audit secondaire, PAS preuve trustless)
    git_tag_attempted = False
    git_tag_success = False
    tag_name = f"integrity/{date_str}-{head_hash[:8]}"
    try:
        result_annot = subprocess.run(
            ["git", "tag", "-a", "-m", f"integrity anchor {date_str}", tag_name],
            capture_output=True, text=True, timeout=10,
        )
        git_tag_attempted = True
        git_tag_success = (result_annot.returncode == 0)
    except Exception:
        pass

    # anchor_ref classification : OTS > git_tag > file
    if ots_file:
        anchor_ref = f"ots:{ots_file}"
    elif git_tag_success:
        anchor_ref = f"git_tag:{tag_name}"  # WEAKER : pas trustless
    else:
        anchor_ref = f"file:{anchor_file}"  # WEAKEST : local-only

    return {
        "anchor_file": anchor_file,
        "ots_file": ots_file,
        "ots_attempted": ots_available,
        "head_hash": head_hash,
        "head_seq": head_seq,
        "anchor_ref": anchor_ref,
        "git_tag_attempted": git_tag_attempted,
        "git_tag_success": git_tag_success,
        "trustless": ots_file is not None,  # bool clair pour caller
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
