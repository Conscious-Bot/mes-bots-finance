#!/usr/bin/env python3
"""build_book.py — outil CONCIERGE du pilote Zero-to-Book (08/08/2026).

CSV cobaye (+ thèses d'interview) → Position Cards V3.1 en HTML autonome.
Outil d'EXPÉRIENCE, pas de produit : aucune dépendance au moteur (render pur,
inputs duck-typés), aucune écriture hors du dossier cobaye, données jamais
dans git (beta/ est ignoré).

Usage (depuis la racine du repo) :
    python3 docs/beta/tools/build_book.py --csv beta/alice/portfolio.csv \
        [--theses beta/alice/theses.json] [--out beta/alice/]

CSV attendu (en-tête obligatoire, séparateur virgule) :
    ticker,qty,pru_eur,currency,price_native[,fx_to_eur]
    MC.PA,8,585,EUR,612
    AAPL,22,148,USD,228,0.92

theses.json (rempli APRÈS l'interview, par ticker) :
    {"MC.PA": {"variant": "…", "triggers": ["…"], "stop": 480,
               "horizon": "3-5y", "conviction": 4, "anti": "…"}}

Fail-honest : ligne CSV malformée → listée et REFUSÉE (jamais sautée en
silence) ; fx manquant pour une devise inconnue → REFUS (pas de fx inventé) ;
thèse absente → la carte crie INDÉFINI (c'est voulu, ne pas compléter).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

#: FX par défaut — ÉDITER à la date de session (source : digest ou ECB du jour).
FX_DEFAULT = {"EUR": 1.0, "USD": 0.92, "DKK": 0.134, "GBP": 1.17,
              "CHF": 1.06, "JPY": 0.0058, "SEK": 0.088, "NOK": 0.086}

DISCLAIMER = ("Outil d'organisation de la réflexion — pas un conseil en "
              "investissement. Chiffres calculés depuis VOS données, FX du jour de session.")


PALETTE = ["#4c6ef5", "#12b886", "#f59f00", "#e64980", "#7950f2",
           "#1098ad", "#e8590c", "#748ffc", "#66a80f", "#adb5bd"]


def svg_donut(rows: list[dict], total: float) -> str:
    """Donut d'allocation — top 9 + « autres ». Conventions maison : thin, sobre."""
    import math
    parts = [(r["ticker"], r["qty"] * r["px"] * r["fx"] / total) for r in rows[:9]]
    rest = 1.0 - sum(w for _, w in parts)
    if rest > 0.005:
        parts.append(("autres", rest))
    segs, legend, a0 = [], [], -90.0
    for i, (tk, w) in enumerate(parts):
        a1 = a0 + w * 360
        large = 1 if (a1 - a0) > 180 else 0
        x0, y0 = 100 + 78 * math.cos(math.radians(a0)), 100 + 78 * math.sin(math.radians(a0))
        x1, y1 = 100 + 78 * math.cos(math.radians(a1)), 100 + 78 * math.sin(math.radians(a1))
        segs.append(f"<path d='M {x0:.1f} {y0:.1f} A 78 78 0 {large} 1 {x1:.1f} {y1:.1f}' "
                    f"fill='none' stroke='{PALETTE[i % 10]}' stroke-width='26'/>")
        legend.append(f"<div style='display:flex;align-items:center;gap:8px;font-size:12px'>"
                      f"<span style='width:10px;height:10px;border-radius:2px;background:{PALETTE[i % 10]}'></span>"
                      f"<span style='min-width:88px'>{tk}</span>"
                      f"<b style='font-family:var(--fm)'>{w * 100:.1f} %</b></div>")
        a0 = a1
    top3 = sum(w for _, w in parts[:3]) * 100
    return ("<div style='display:flex;gap:26px;align-items:center;flex-wrap:wrap'>"
            f"<svg viewBox='0 0 200 200' width='170' height='170'>{''.join(segs)}"
            f"<text x='100' y='95' text-anchor='middle' font-size='13' fill='#6b7280'>top 3</text>"
            f"<text x='100' y='115' text-anchor='middle' font-size='17' font-weight='650'>{top3:.0f} %</text></svg>"
            f"<div style='display:grid;gap:5px'>{''.join(legend)}</div></div>")


def pnl_bars(rows: list[dict]) -> str:
    """Latent % par position (PRU EUR vs valeur EUR) — le garde M1 du renderer
    revérifie ; ici même calcul, même source, aucune invention."""
    items = []
    for r in rows:
        val = r["qty"] * r["px"] * r["fx"]
        pnl = (val / (r["qty"] * r["pru_eur"]) - 1) * 100 if r["pru_eur"] else None
        if pnl is None:
            continue
        items.append((r["ticker"], pnl))
    if not items:
        return ""
    mx = max(abs(p) for _, p in items) or 1
    bars = []
    for tk, pnl in items:
        w = abs(pnl) / mx * 50
        color = "#12b886" if pnl >= 0 else "#e03131"
        left = 50 - (w if pnl < 0 else 0)
        bars.append(
            "<div style='display:grid;grid-template-columns:90px 1fr 64px;gap:10px;align-items:center'>"
            f"<span style='font-size:12px'>{tk}</span>"
            "<div style='position:relative;height:10px;background:#f1f3f5;border-radius:5px'>"
            f"<div style='position:absolute;left:{left:.1f}%;width:{w:.1f}%;height:10px;"
            f"border-radius:5px;background:{color}'></div>"
            "<div style='position:absolute;left:50%;top:-2px;width:1px;height:14px;background:#dee2e6'></div></div>"
            f"<b style='font-family:var(--fm);font-size:12px;text-align:right;"
            f"color:{color}'>{pnl:+.0f} %</b></div>")
    return "<div style='display:grid;gap:7px'>" + "".join(bars) + "</div>"


def ccy_band(rows: list[dict], total: float) -> str:
    """Répartition par devise — barre unique."""
    agg: dict[str, float] = {}
    for r in rows:
        agg[r["ccy"]] = agg.get(r["ccy"], 0) + r["qty"] * r["px"] * r["fx"] / total
    parts = sorted(agg.items(), key=lambda x: -x[1])
    seg = "".join(f"<div style='width:{w * 100:.2f}%;background:{PALETTE[i % 10]}' title='{c}'></div>"
                  for i, (c, w) in enumerate(parts))
    lab = " · ".join(f"{c} {w * 100:.0f} %" for c, w in parts)
    return ("<div style='display:flex;height:9px;border-radius:5px;overflow:hidden;margin-bottom:6px'>"
            + seg + f"</div><div style='font-size:11.5px;color:#6b7280'>{lab}</div>")


def read_portfolio(path: Path) -> tuple[list[dict], list[str]]:
    rows, errors = [], []
    with open(path, encoding="utf-8-sig") as f:
        for i, r in enumerate(csv.DictReader(f), 2):
            try:
                ccy = (r["currency"] or "EUR").strip().upper()
                fx = float(r["fx_to_eur"]) if r.get("fx_to_eur") else FX_DEFAULT.get(ccy)
                if fx is None:
                    raise ValueError(f"devise {ccy} sans fx_to_eur — le renseigner, pas l'inventer")
                rows.append({"ticker": r["ticker"].strip(), "qty": float(r["qty"]),
                             "pru_eur": float(r["pru_eur"]), "ccy": ccy,
                             "px": float(r["price_native"]), "fx": fx})
            except Exception as e:
                errors.append(f"ligne {i}: {e} — {dict(r)}")
    return rows, errors


def build_inputs(row: dict, weight: float, th: dict) -> NS:
    return NS(
        ticker=row["ticker"],
        thesis={"conviction": th.get("conviction"), "horizon": th.get("horizon", "?"),
                "opened_at": "", "variant_perception": th.get("variant", ""),
                "invalidation_triggers": json.dumps(th.get("triggers", []), ensure_ascii=False),
                "stop_value": th.get("stop"), "stop_currency": row["ccy"]},
        book_line=NS(qty=row["qty"], avg_cost_eur=row["pru_eur"],
                     current_eur=row["qty"] * row["px"] * row["fx"],
                     last_price_native=row["px"], last_price_currency=row["ccy"],
                     price_asof="", fx_rate_to_eur=row["fx"]),
        weight_pct=weight, conviction_current=th.get("conviction"),
        over_cap_status=None, kill_status="dormant", kill_at=None,
        bias_events_open=[], counter_argument_brief=th.get("anti"),
        counter_argument_at="9999-12-31" if th.get("anti") else None,
        erosion_driver_status=[], last_cf=None, similar_situations=[],
        next_event=({"date": th["next_event"], "description": "earnings"}
                    if th.get("next_event") else None),
        binding_target_pct=None,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--theses", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    from dashboard.position_card import render_position_card

    csv_path = Path(a.csv)
    out_dir = Path(a.out) if a.out else csv_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    theses = json.loads(Path(a.theses).read_text(encoding="utf-8")) if a.theses else {}

    rows, errors = read_portfolio(csv_path)
    if errors:
        print("⛔ CSV REFUSÉ — corriger d'abord (aucune ligne sautée en silence) :")
        for e in errors:
            print("  ", e)
        return 1

    total = sum(r["qty"] * r["px"] * r["fx"] for r in rows)
    rows.sort(key=lambda r: -(r["qty"] * r["px"] * r["fx"]))
    steer = NS(verdict=NS(value="HOLD"), target_qty_delta_pct=None, bandeau="")
    cards, n_th, facts = [], 0, []
    print(f"— {len(rows)} positions · book {total:,.0f} € —".replace(",", " "))
    for r in rows:
        val = r["qty"] * r["px"] * r["fx"]
        w = val / total * 100
        th = theses.get(r["ticker"], {})
        n_th += bool(th.get("variant"))
        if th.get("next_event"):
            facts.append((str(th["next_event"]), r["ticker"]))
        print(f"  {r['ticker']:12s} {w:5.1f} %  {val:10,.0f} €".replace(",", " "))
        cards.append(render_position_card(build_inputs(r, w, th), steer))

    n_und = len(rows) - n_th
    facts.sort()
    facts_html = "".join(
        f"<div style='display:flex;gap:14px'><span style='font-family:ui-monospace,monospace'>"
        f"{d}</span><span>{t}</span></div>" for d, t in facts[:6]) or "<div>aucun fait daté</div>"
    overview = (
        "<div style='background:#fff;border:1px solid #e3e6eb;border-radius:10px;padding:20px 24px;margin:20px 0'>"
        f"<div style='font-size:26px;font-weight:650'>{total:,.0f} €</div>".replace(",", " ")
        + f"<div style='color:#6b7280;margin:4px 0 14px'>{len(rows)} positions · "
        f"{n_th} thèses structurées · {n_und} à définir</div>"
        "<div style='display:flex;gap:22px;font-weight:600;margin-bottom:14px'>"
        f"<span style='color:#3a9d4e'>{len(rows) - n_und} suivies</span>"
        + (f"<span style='color:#b8860b'>{n_und} INDÉFINI</span>" if n_und else "")
        + "</div>"
        "<div style='font-size:12px;letter-spacing:.14em;color:#6b7280;margin-bottom:6px'>PROCHAINS FAITS</div>"
        f"<div style='font-size:13px;line-height:1.7'>{facts_html}</div></div>")
    html = ("<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>PRESAGE — votre book</title>"
            "<style>:root{--fm:ui-monospace,monospace;--ink:#1a1d21;--steel:#6b7280;--line:#e3e6eb}"
            "body{font-family:system-ui;background:#f6f7f9;margin:0 auto;padding:32px;max-width:860px}"
            ".pc-card{background:#fff;border:1px solid var(--line);border-radius:10px;margin:20px 0}"
            "</style></head><body><h2 style='font-weight:600'>PRESAGE — votre book</h2>"
            f"<p style='color:#6b7280;font-size:13px'>{DISCLAIMER}</p>"
            + overview
            + "<div style='background:#fff;border:1px solid #e3e6eb;border-radius:10px;"
              "padding:20px 24px;margin:20px 0'>"
              "<div style='font-size:12px;letter-spacing:.14em;color:#6b7280;"
              "margin-bottom:14px'>ALLOCATION</div>"
            + svg_donut(rows, total)
            + "<div style='font-size:12px;letter-spacing:.14em;color:#6b7280;"
              "margin:20px 0 10px'>P&amp;L LATENT PAR POSITION</div>"
            + pnl_bars(rows)
            + "<div style='font-size:12px;letter-spacing:.14em;color:#6b7280;"
              "margin:20px 0 8px'>DEVISES</div>"
            + ccy_band(rows, total)
            + "</div>"
            + "".join(cards) + "</body></html>")
    out = out_dir / "book.html"
    out.write_text(html, encoding="utf-8")
    print(f"→ {out}  ({len(rows)} cartes, {n_th} thèses, {len(rows)-n_th} INDÉFINI)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
