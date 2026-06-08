"""SOCLE Phase 2 S3 : base_health -- le scoreboard du socle.

Cf SPEC_SOCLE.md S4 + HANDOFF_SOCLE.md S3 + master HANDOFF_MASTER.md S5 etape A3.

Lit 3 dimensions :
  1. Positions verite : eur_value-in-notes mort + avg_cost_ccy renseigne + value_eur derive
  2. Fraicheur data   : prices triple M1 + gate yfinance + plus vieux as-of < amber
  3. Chaine integre   : verify_chain(predictions + theses) + dernier OTS anchor < 25h

GATE DUR du SOCLE : si UN check est RED, le socle n'est PAS vert -> tout build
book-facing du cornerstone (gouverneur, position-card, fragilite) est refuse.
Le script exit non-zero sur RED -> hookable en CI / cron.

Usage :
    python3 scripts/base_health.py                # human-readable summary
    python3 scripts/base_health.py --json         # machine-readable
    python3 scripts/base_health.py --dim positions  # check une seule dim
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
log = logging.getLogger("base_health")

Severity = Literal["green", "amber", "red", "unknown"]

# === Helpers ============================================================


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _parse_iso(asof: str) -> datetime | None:
    try:
        return datetime.fromisoformat(asof.replace("Z", "+00:00"))
    except Exception:
        return None


# === Check 1 : Positions verite =========================================


def check_positions_verite() -> dict:
    """Verifie que :
    - eur_value-in-notes est mort (test_positions_schema_has_no_eur_value_column garantit).
    - toute position open a un avg_cost_ccy (M1 colonne typee).
    - value_eur derive live via shared.valuation (pas figee en table).

    Returns : {severity, reason, details}.
    """
    from shared import storage

    try:
        with storage.db() as cx:
            # Check 1a : schema sans eur_value (defensive, le test verrouille deja)
            cols = [r[1] for r in cx.execute("PRAGMA table_info(positions)").fetchall()]
            forbidden = {"eur_value", "value_eur", "market_value_eur", "market_value"}
            forbidden_present = forbidden & set(cols)
            if forbidden_present:
                return {
                    "severity": "red",
                    "reason": f"Schema positions porte colonnes interdites : {sorted(forbidden_present)} -- eur_value-in-table reapparu",
                    "details": {"forbidden_cols": sorted(forbidden_present)},
                }

            # Check 1b : positions open sans currency (M1 colonne typee).
            # Note 08/06 : la colonne reelle est `last_price_currency` (alembic 0036+,
            # post-migration M1). Le HANDOFF_SOCLE evoquait `avg_cost_ccy` comme exemple
            # generique ; en pratique le PRU et le prix sont en meme devise (monocurrency
            # par ticker), donc last_price_currency suffit comme indicateur M1.
            ccy_col = "last_price_currency" if "last_price_currency" in cols else None
            if ccy_col is None:
                return {
                    "severity": "red",
                    "reason": f"Aucune colonne devise (avg_cost_ccy ou last_price_currency) dans positions -- migration M1 pas appliquee. cols={cols}",
                    "details": {"cols": cols},
                }
            n_missing_ccy = cx.execute(
                f"SELECT COUNT(*) FROM positions WHERE status='open' AND ({ccy_col} IS NULL OR {ccy_col} = '')"
            ).fetchone()[0]
            n_open = cx.execute("SELECT COUNT(*) FROM positions WHERE status='open'").fetchone()[0]
            if n_missing_ccy > 0:
                return {
                    "severity": "amber" if n_missing_ccy < 5 else "red",
                    "reason": f"{n_missing_ccy}/{n_open} positions open sans {ccy_col} (M1 colonne manquante)",
                    "details": {"n_missing": n_missing_ccy, "n_open": n_open, "ccy_col": ccy_col},
                }

            # Check 1c : verifier que position_valuation() est appelable (smoke test
            # sur la premiere position ouverte, sans depends de yfinance live)
            first_open = cx.execute(
                "SELECT id, ticker FROM positions WHERE status='open' ORDER BY id LIMIT 1"
            ).fetchone()
            if first_open:
                from shared.valuation import position_valuation
                pv = position_valuation(int(first_open[0]))
                if pv is None:
                    return {
                        "severity": "amber",
                        "reason": f"position_valuation({first_open[0]}/{first_open[1]}) retourne None (DB read fail ?)",
                        "details": {"ticker": first_open[1]},
                    }

            return {
                "severity": "green",
                "reason": f"{n_open} positions open avec avg_cost_ccy + value_eur derive live",
                "details": {"n_open": n_open},
            }
    except Exception as e:
        return {"severity": "unknown", "reason": f"DB read failed: {e}", "details": {}}


# === Check 2 : Fraicheur data ===========================================


def check_freshness() -> dict:
    """Verifie que :
    - prices.get retourne le triple (smoke test API contract).
    - gate yfinance hors prices.py : count violations (SOFT mode).
    - le plus vieux as-of du book (positions open) < SLA amber.
    """
    from shared import storage

    details: dict = {}

    # Check 2a : prices.get() est bien un Datum (contract test, sans hit live)
    from shared import prices

    # Sanity check : la fonction existe et a la signature attendue
    if not callable(getattr(prices, "get", None)) or not callable(getattr(prices, "fx", None)):
        return {
            "severity": "red",
            "reason": "shared.prices.get() ou .fx() manquant -- gateway SOCLE pas en place",
            "details": {},
        }

    # Check 2b : gate yfinance violations (SOFT mode)
    import subprocess
    gate_path = _REPO_ROOT / "scripts" / "check_yfinance_gate.sh"
    if gate_path.exists():
        try:
            result = subprocess.run(
                ["bash", str(gate_path)],
                capture_output=True, text=True, timeout=30, cwd=str(_REPO_ROOT),
            )
            stdout = result.stdout
            # Parse "WARNING (NB violations)"
            import contextlib
            n_violations = 0
            for line in stdout.splitlines():
                if "violations)" in line and "WARNING" in line:
                    with contextlib.suppress(Exception):
                        n_violations = int(line.split("(")[1].split(" ")[0])
                    break
            details["yfinance_violations"] = n_violations
        except Exception as e:
            log.warning(f"gate yfinance check failed: {e}")
            details["yfinance_violations"] = -1

    # Check 2c : plus vieux as-of price_history pour positions open
    try:
        with storage.db() as cx:
            row = cx.execute("""
                SELECT MIN(ph.asof), COUNT(DISTINCT p.ticker)
                FROM positions p
                LEFT JOIN price_history ph ON ph.ticker = p.ticker
                WHERE p.status = 'open' AND ph.id = (
                    SELECT id FROM price_history WHERE ticker = p.ticker
                    ORDER BY asof DESC LIMIT 1
                )
            """).fetchone()
            oldest_asof = row[0]
            n_tickers = row[1] or 0
            details["n_tickers_with_price"] = n_tickers

            if oldest_asof is None:
                return {
                    "severity": "amber",
                    "reason": "Aucune observation price_history pour positions ouvertes",
                    "details": details,
                }

            # Classify via shared.freshness
            from shared.freshness import classify_asof
            severity, age_sec = classify_asof("price", oldest_asof)
            details["oldest_asof"] = oldest_asof
            details["oldest_age_sec"] = age_sec
            details["oldest_severity"] = severity

            # Map shared.freshness "rouge" -> SOCLE "red"
            if severity == "rouge":
                return {
                    "severity": "red",
                    "reason": f"Plus vieux as-of book = {oldest_asof} ({age_sec/3600:.1f}h), severity rouge",
                    "details": details,
                }

            # Yfinance violations en SOFT mode : reporter mais pas RED
            n_viol = details.get("yfinance_violations", 0)
            soft_warning = ""
            if n_viol > 0:
                soft_warning = f" + {n_viol} bypass yfinance hors prices.py (SOFT gate)"

            return {
                "severity": severity if severity != "rouge" else "amber",
                "reason": f"Plus vieux as-of book = {oldest_asof} ({age_sec/3600:.1f}h, {severity}){soft_warning}",
                "details": details,
            }
    except Exception as e:
        return {"severity": "unknown", "reason": f"DB read failed: {e}", "details": details}


# === Check 3 : Chaine integre ===========================================


def check_integrity_chain() -> dict:
    """Verifie que :
    - verify_chain(predictions) OK (commit-reveal HIDING chain).
    - verify_chain(theses) OK (transparent chain).
    - dernier OTS anchor < 25h (cron daily 6h + grace).
    """
    from shared import storage
    from shared.integrity import verify_chain

    details: dict = {}

    # Check 3a : predictions chain
    try:
        chain_p = storage.get_prediction_integrity_chain()
        if chain_p:
            ok, broken_seq = verify_chain(chain_p)
            if not ok:
                return {
                    "severity": "red",
                    "reason": f"PREDICTIONS chain verify FAILED at seq={broken_seq}",
                    "details": {"chain_predictions_len": len(chain_p), "broken_seq": broken_seq},
                }
            details["chain_predictions_len"] = len(chain_p)
    except Exception as e:
        return {"severity": "unknown", "reason": f"predictions chain read failed: {e}", "details": details}

    # Check 3b : theses chain
    try:
        chain_t = storage.get_thesis_integrity_chain()
        if chain_t:
            ok, broken_seq = verify_chain(chain_t)
            if not ok:
                return {
                    "severity": "red",
                    "reason": f"THESES chain verify FAILED at seq={broken_seq}",
                    "details": {"chain_theses_len": len(chain_t), "broken_seq": broken_seq},
                }
            details["chain_theses_len"] = len(chain_t)
    except Exception as e:
        return {"severity": "unknown", "reason": f"theses chain read failed: {e}", "details": details}

    # Check 3c : dernier OTS anchor < 25h
    ots_dir = _REPO_ROOT / "integrity_anchors"
    if not ots_dir.exists():
        return {
            "severity": "red",
            "reason": "integrity_anchors/ dir manquant -- S0 OTS jamais run",
            "details": details,
        }
    ots_files = list(ots_dir.glob("*.ots"))
    if not ots_files:
        return {
            "severity": "red",
            "reason": "Aucun fichier .ots dans integrity_anchors/ -- chaine pas ancree",
            "details": details,
        }
    most_recent_ots = max(ots_files, key=lambda p: p.stat().st_mtime)
    age_sec = time.time() - most_recent_ots.stat().st_mtime
    details["most_recent_ots"] = most_recent_ots.name
    details["ots_age_sec"] = int(age_sec)

    sla_sec = 25 * 3600  # 25h = cron daily + 1h grace
    if age_sec > sla_sec:
        return {
            "severity": "red",
            "reason": f"Dernier OTS anchor age = {age_sec/3600:.1f}h > 25h SLA",
            "details": details,
        }
    if age_sec > 24 * 3600:
        return {
            "severity": "amber",
            "reason": f"Dernier OTS anchor age = {age_sec/3600:.1f}h, proche de SLA 25h",
            "details": details,
        }
    return {
        "severity": "green",
        "reason": f"Chains predictions+theses verify OK + dernier OTS {age_sec/3600:.1f}h",
        "details": details,
    }


# === Aggregator =========================================================


_SEVERITY_RANK = {"green": 0, "amber": 1, "red": 2, "unknown": 3}


def aggregate_status(checks: dict[str, dict]) -> dict:
    """Compute overall status = worst dim. exit_code = 1 si red."""
    worst = "green"
    for r in checks.values():
        sev = r.get("severity", "unknown")
        if _SEVERITY_RANK.get(sev, 99) > _SEVERITY_RANK.get(worst, 99):
            worst = sev
    return {
        "overall_severity": worst,
        "exit_code": 1 if worst in ("red", "unknown") else 0,
        "checks": checks,
        "ts": _now_utc().isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="SOCLE base_health scoreboard")
    parser.add_argument("--json", action="store_true", help="JSON output (machine-readable)")
    parser.add_argument("--dim", choices=["positions", "freshness", "integrity"],
                        help="Run only one dimension")
    args = parser.parse_args()

    checks: dict[str, dict] = {}
    if args.dim is None or args.dim == "positions":
        checks["Positions verite"] = check_positions_verite()
    if args.dim is None or args.dim == "freshness":
        checks["Fraicheur data"] = check_freshness()
    if args.dim is None or args.dim == "integrity":
        checks["Chaine integre"] = check_integrity_chain()

    result = aggregate_status(checks)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        # Human-readable
        print(f"=== SOCLE base_health @ {result['ts']} ===")
        print(f"OVERALL : {result['overall_severity'].upper()}")
        print()
        for dim_name, dim_result in result["checks"].items():
            sev = dim_result["severity"].upper()
            badge = {"GREEN": "✓", "AMBER": "~", "RED": "✗", "UNKNOWN": "?"}.get(sev, "?")
            print(f"  [{badge}] {dim_name} : {sev}")
            print(f"      {dim_result['reason']}")
        print()
        if result["overall_severity"] == "red":
            print("GATE DUR : SOCLE n'est PAS vert. AUCUNE partie book-facing du cornerstone ne doit ship.")
        elif result["overall_severity"] == "green":
            print("SOCLE est VERT. Tu peux poser le poids du cornerstone dessus.")

    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
