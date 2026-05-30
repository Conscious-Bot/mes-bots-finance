"""Wire SEC 8-K filings -> signals -> V2 -> predictions (A3 iter 6+).

Pre-bug audit 30/05 : `filings_8k_log` accumulait des 8-K (~43 rows) mais
ces filings ne touchaient jamais le pipeline `signals -> V2 -> predictions`.
Le scorer V2 ne voyait que des newsletters tech opinion -> mono-bucket
[0.60-0.62] structurel.

Ce module ferme la boucle :
  EightKSource.persist() -> wire_8k_to_signal() -> extract_filing_content
  -> insert signal -> auto_register_predictions (V2 call) -> insert_prediction

Decisions schema (audit decision log #01) :
- Source dediee : "SEC EDGAR 8-K" type='sec_filing' credibility=0.85 (donnee
  primaire structuree, vs 0.50 default newsletter).
- signal_type = 'catalyst' (8-K = event ponctuel material).
- score = 7 (passe filter auto_register_predictions score>=6).
- sentiment = 'bullish' (placeholder, V2 recalcule la vraie direction).
- gmail_id = 'sec_8k:{accession}' (reutilise colonne unique pour dedup forward).
- Si extract_filing_content retourne "" ou < 500 chars : skip wire (filing
  sans exhibits materials -- V2 sortirait watch ev=none = pollution ledger).

Forward-only : ce module ne backfille PAS les 43 8-K existantes. Decision
tranchee (audit iter 5) : backfill = stale-dated predictions = artefact
temporel cousin du cluster horizon=30. Seules les nouvelles 8-K ingerees
par EightKSource passent par ici.
"""

import json
import logging

log = logging.getLogger(__name__)

SEC_8K_SOURCE_NAME = "SEC EDGAR 8-K"
SEC_8K_SOURCE_TYPE = "sec_filing"
SEC_8K_SOURCE_CREDIBILITY = 0.85
MIN_CONTENT_CHARS_TO_WIRE = 500


def wire_8k_to_signal(filing: dict) -> int | None:
    """Insert une 8-K material comme signal dans `signals`, retourne signal_id.

    Args:
        filing: dict avec keys ticker, filed_at, items_raw, accession, url

    Returns:
        signal_id si insere, None si filing sans contenu material (skip propre)
        OU si deja insere (dedup, log debug).

    Side effects: HTTP request(s) vers SEC EDGAR via extract_filing_content.
    Cost: ~2-5s par filing (2 GET requests + strip HTML).

    Architecture (CONVENTIONS §5) : ce module ORCHESTRE (extract + decide),
    storage.py POSSEDE les writes DB (insert_primary_filing_signal,
    get_or_create_source_typed).
    """
    from shared import storage
    from shared.edgar_exhibits import extract_filing_content

    ticker = filing.get("ticker")
    accession = filing.get("accession")
    filing_url = filing.get("url")
    filed_at = filing.get("filed_at")
    items_raw = filing.get("items_raw", "")

    if not ticker or not accession or not filing_url:
        log.warning(f"wire_8k_to_signal: missing required fields in {filing}")
        return None

    dedup_key = f"sec_8k:{accession}"

    # Extract material content from exhibits (cover page only = filing_url stocke)
    content = extract_filing_content(filing_url)
    if not content or len(content) < MIN_CONTENT_CHARS_TO_WIRE:
        log.warning(
            f"wire_8k: {ticker} {accession} extracted only {len(content) if content else 0} "
            f"chars (< {MIN_CONTENT_CHARS_TO_WIRE}) -- skip wire (no material content)"
        )
        return None

    source_id = storage.get_or_create_source_typed(
        name=SEC_8K_SOURCE_NAME,
        type_=SEC_8K_SOURCE_TYPE,
        credibility=SEC_8K_SOURCE_CREDIBILITY,
    )

    title = f"{ticker} 8-K filed {filed_at} -- SEC items {items_raw}"
    summary = content[:800]
    content_full = content[:6000]
    entities_json = json.dumps([ticker])

    signal_id = storage.insert_primary_filing_signal(
        source_id=source_id,
        dedup_key=dedup_key,
        timestamp=filed_at,
        title=title,
        summary=summary,
        content=content_full,
        entities_json=entities_json,
    )
    if signal_id is None:
        log.debug(f"wire_8k: {accession} already wired (dedup)")
        # Recupere l'ID existant pour cohherence de retour (callers utilisent l'ID)
        # Note: cette lecture pourrait etre evitee mais wire est cold path (~1/jour
        # par ticker), pas critique.
        from shared import storage as _s
        with _s.db() as cx:
            row = cx.execute("SELECT id FROM signals WHERE gmail_id = ?", (dedup_key,)).fetchone()
            return int(row["id"]) if row else None

    log.info(f"wire_8k: {ticker} {accession} -> signal id={signal_id} ({len(content)} chars)")
    return signal_id


def wire_and_register_8k(filing: dict) -> dict:
    """End-to-end : wire 8-K -> signals -> V2 -> predictions. Retourne diagnostic.

    Returns:
        {
            "wired": bool,
            "signal_id": int | None,
            "registered_predictions": list[int],
            "reason_if_skipped": str | None,
        }
    """
    from intelligence import learning

    signal_id = wire_8k_to_signal(filing)
    if signal_id is None:
        return {
            "wired": False, "signal_id": None, "registered_predictions": [],
            "reason_if_skipped": "no material content or dedup",
        }

    # Charger le signal pour le passer a auto_register_predictions (qui attend
    # une list de dicts signal)
    from shared import storage

    with storage.db() as cx:
        sig_row = cx.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
        if not sig_row:
            return {
                "wired": True, "signal_id": signal_id, "registered_predictions": [],
                "reason_if_skipped": "signal disappeared",
            }
        sig_dict = dict(sig_row)
        # auto_register_predictions attend 'tickers' (list ou JSON string)
        sig_dict["tickers"] = sig_dict.get("entities") or json.dumps([filing.get("ticker")])

    pred_ids = learning.auto_register_predictions([sig_dict])
    return {
        "wired": True, "signal_id": signal_id,
        "registered_predictions": pred_ids,
        "reason_if_skipped": None,
    }
