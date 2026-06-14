"""edgartools wrapper — VALUE-ADD ONLY vs existing shared/edgar.py.

Honest scope audit 14/06/2026 :

EXISTING shared/edgar.py couvre deja Form 4 / 8-K / insider clusters etc.
edgartools NE DUPLIQUE PAS — il ajoute 10-Q structured access que PRESAGE
ne couvrait pas :
- tenq_context     : snapshot 10-Q (financials + sections) pour LLM thesis review
- risk_factors_10q : Part II Item 1A texte brut
- income_statement : XBRL revenue/EPS/operating income

Use cases doctrine `business_path_6_acted` (discipline mecanisee) :
- Thesis prep : tenq_context pour audit 10-Q + risk factors changement
- Position review : risk_factors_10q pour detecter risk nouveau material
- Cross-check : income_statement vs yfinance .info

Fail-soft : sans edgartools ou ticker introuvable, retourne dict {error:...},
jamais leve. Cf memory feedback_red_team_verify_before_assert.
"""
from __future__ import annotations

import contextlib
import os

try:
    from edgar import Company, set_identity
    _IDENTITY_SET = False
except ImportError:
    Company = None
    set_identity = None
    _IDENTITY_SET = False

DEFAULT_EMAIL = os.environ.get("EDGAR_IDENTITY", "ofmlegendre@gmail.com")


def _ensure_identity() -> bool:
    global _IDENTITY_SET
    if set_identity is None:
        return False
    if not _IDENTITY_SET:
        set_identity(DEFAULT_EMAIL)
        _IDENTITY_SET = True
    return True


def _latest_10q_filing(ticker: str):
    """Helper : return EntityFiling for latest 10-Q (single object, not list)."""
    if not _ensure_identity():
        return None
    try:
        c = Company(ticker)
        flist = c.get_filings(form="10-Q")
        if len(flist) == 0:
            return None
        return flist[0]
    except Exception:
        return None


def tenq_context(ticker: str) -> dict:
    """Snapshot 10-Q via TenQ.to_context() : financials key + sections + accession.

    Format text designe LLM-ready (NVIDIA case 14/06 : 500 chars header avec
    Revenue/Net Income/Total Assets + liste sections + actions).
    """
    f = _latest_10q_filing(ticker)
    if f is None:
        return {"ticker": ticker.upper(), "error": "no 10-Q or fetch failed"}
    try:
        o = f.obj()
        ctx_text = o.to_context() if hasattr(o, "to_context") else str(o)
        return {
            "ticker": ticker.upper(),
            "filing_date": str(f.filing_date),
            "accession": f.accession_no,
            "context": str(ctx_text)[:8000],
        }
    except Exception as e:
        return {"ticker": ticker.upper(), "error": f"tenq_context: {type(e).__name__} {e}"}


def risk_factors_10q(ticker: str, max_chars: int = 6000) -> dict:
    """Part II Item 1A Risk Factors du dernier 10-Q. Texte brut tronque max_chars."""
    f = _latest_10q_filing(ticker)
    if f is None:
        return {"ticker": ticker.upper(), "error": "no 10-Q or fetch failed"}
    try:
        o = f.obj()
        text = None
        if hasattr(o, "get_item_with_part"):
            with contextlib.suppress(Exception):
                text = o.get_item_with_part("Part II", "Item 1A")
        return {
            "ticker": ticker.upper(),
            "filing_date": str(f.filing_date),
            "accession": f.accession_no,
            "text": str(text)[:max_chars] if text else None,
            "text_chars_full": len(str(text)) if text else 0,
        }
    except Exception as e:
        return {"ticker": ticker.upper(), "error": f"risk_factors: {type(e).__name__} {e}"}


def income_statement_10q(ticker: str) -> dict:
    """XBRL income statement du dernier 10-Q. Renvoie repr() Statement pour preview."""
    f = _latest_10q_filing(ticker)
    if f is None:
        return {"ticker": ticker.upper(), "error": "no 10-Q or fetch failed"}
    try:
        o = f.obj()
        inc = o.income_statement
        if callable(inc):
            inc = inc()
        return {
            "ticker": ticker.upper(),
            "filing_date": str(f.filing_date),
            "accession": f.accession_no,
            "preview": str(inc)[:3000] if inc is not None else None,
        }
    except Exception as e:
        return {"ticker": ticker.upper(), "error": f"income_statement: {type(e).__name__} {e}"}


def thesis_enrichment(ticker: str) -> dict:
    """Composite call : tout ce qu'edgartools apporte de net new pour thesis review."""
    return {
        "ticker": ticker.upper(),
        "tenq_context": tenq_context(ticker),
        "risk_factors_10q": risk_factors_10q(ticker, max_chars=6000),
        "income_statement_10q": income_statement_10q(ticker),
    }


if __name__ == "__main__":
    import json
    import sys
    ticker = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
    result = thesis_enrichment(ticker)
    print(json.dumps(result, indent=2, default=str)[:5000])
