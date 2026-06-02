"""Generateur site_public/track.html (#24 modernisation).

Utilise compute_public_track_record + compute_all_timeseries + dashboard
charts helpers (Observable Plot) pour rendre une page publique honnete
avec :
- KPIs canoniques (predictions / bias / theses / alpha)
- Charts evolution (Brier rolling 30j, bias cumul, predictions volume)
- Methodologie collapsible
- Posts recents

Pattern : utilise les helpers livres en session 02/06. Aucune duplication
de logique. Modifications futures de la mecanique se propagent
automatiquement.

Run :
    python3 scripts/render_public_track.py
    -> ecrit site_public/track.html

Ou via monthly_track_record_snapshot_job (cron 1er du mois) :
    snapshot JSON + HTML page mis a jour ensemble.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _format_eur(v: float | None) -> str:
    if v is None:
        return "—"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:,.0f} €".replace(",", " ")


def _format_pct(v: float | None, decimals: int = 1) -> str:
    if v is None:
        return "—"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.{decimals}f}%"


def _status_class(status: str) -> str:
    return {"OK": "acc", "WARN": "warn", "ALERT": "bear",
            "INSUFFICIENT_DATA": "steel"}.get(status, "steel")


def _render_html(record: dict, timeseries: dict) -> str:
    from dashboard.charts import plot_line

    pred = record.get("predictions", {}) or {}
    bias_list = record.get("bias_events", []) or []
    theses = record.get("theses", {}) or {}
    by_posture = theses.get("by_posture", {}) or {}
    alpha = record.get("alpha", {}) or {}
    methodology = record.get("methodology", {}) or {}
    posture_global = record.get("posture_global", "INSUFFICIENT_DATA")

    pred_brier = pred.get("brier_avg")
    pred_n = pred.get("n_resolved", 0)
    pred_acc = pred.get("accuracy_pct")

    # Chart Brier rolling
    brier_data = timeseries.get("brier_rolling", []) or []
    brier_chart_html = plot_line(
        brier_data, x="date", y="brier_avg",
        title="Brier rolling 30j", height=160,
        color="var(--acc)",
    )

    # Chart bias cumul lock_in
    bias_lock_in_data = timeseries.get("bias_cumul_lock_in", []) or []
    bias_lock_chart_html = plot_line(
        bias_lock_in_data, x="date", y="cumul_delta_eur",
        title="Lock-in delta cumulé (EUR)", height=160,
        color="var(--bear)",
    )

    # Chart bias cumul fomo_greed
    bias_fomo_data = timeseries.get("bias_cumul_fomo_greed", []) or []
    bias_fomo_chart_html = plot_line(
        bias_fomo_data, x="date", y="cumul_delta_eur",
        title="Fomo-greed delta cumulé (EUR)", height=160,
        color="var(--warn)",
    )

    # Bias rows
    bias_rows = []
    for b in bias_list:
        if not b.get("n_resolved"):
            bias_rows.append(
                f'<tr><td>{b["bias"]}</td><td>0</td><td>—</td>'
                f'<td><span class="tag steel">non instrumenté</span></td></tr>'
            )
            continue
        bias_rows.append(
            f'<tr><td>{b["bias"]}</td>'
            f'<td>{b["n_resolved"]}</td>'
            f'<td class="num">{_format_eur(b["total_delta_signed_eur"])}</td>'
            f'<td><span class="tag {_status_class(b.get("posture", ""))}">{b.get("posture", "—")}</span></td></tr>'
        )
    bias_table = "".join(bias_rows)

    # Posts liste (statique pour l'instant ; à wirer post)
    posts = [
        ("2026-06-02", "Mon modèle macro a échoué hors échantillon. Voici pourquoi je le publie.",
         "Le verdict honnête d'un backtest qui devait valider V3."),
        ("2026-05-30", "Le fix qui n'était pas un fix",
         "Quand le test que tu écris pour empêcher un bug attrape ton propre patch."),
        ("2026-05-29", "J-11 dry-run honnête",
         "Le mécanisme tourne. La calibration est mauvaise. Les deux verdicts comptent."),
    ]
    posts_html = "".join(
        f'<li><span class="post-date">{d}</span>'
        f'<span class="post-title"><a href="#">{t}</a>'
        f'<span class="small"> · {s}</span></span></li>'
        for d, t, s in posts
    )

    # Date as_of
    as_of_raw = record.get("as_of") or datetime.now(UTC).isoformat()
    as_of_short = as_of_raw[:16].replace("T", " ")

    # KPI cards values
    brier_val = (
        f'<div class="kpi-val">{pred_brier:.3f}</div>' if pred_brier is not None
        else '<div class="kpi-val placeholder">— J+28</div>'
    )
    acc_cap = (
        f'<div class="kpi-cap">accuracy {pred_acc}%</div>' if pred_acc is not None
        else f'<div class="kpi-cap">N={pred_n}</div>'
    )

    total_bias = record.get("bias_total_delta_signed_eur", 0)
    bias_cumul_str = _format_eur(total_bias)

    alpha_html = ""
    if alpha and "error" not in alpha and alpha.get("alpha_pct") is not None:
        alpha_pct = alpha["alpha_pct"]
        alpha_html = (
            f'<div class="kpi"><div class="kpi-lbl">Alpha vs {alpha.get("bench_ticker", "?")}</div>'
            f'<div class="kpi-val">{_format_pct(alpha_pct)}</div>'
            f'<div class="kpi-cap">{alpha.get("window_months", "?")} mois · '
            f'book {_format_pct(alpha.get("book_return_pct"))}</div></div>'
        )
    else:
        alpha_html = (
            '<div class="kpi"><div class="kpi-lbl">Alpha vs SOXX</div>'
            '<div class="kpi-val placeholder">— Q3</div>'
            '<div class="kpi-cap">décomposition trimestrielle</div></div>'
        )

    return f'''<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PRESAGE — Track record</title>
  <meta name="description" content="Public track record d'un portefeuille single-stock avec détection mécanisée des biais comportementaux.">
  <style>
    :root {{
      --bg:#FBFAF8; --ink:#1A1814; --steel:#6B7686; --line:#E8E4DE;
      --acc:#5F9A4D; --bear:#C24332; --warn:#D6A748; --panel:#FFFFFF;
      --fm:'Geist Mono', ui-monospace, monospace;
      --fb:'Geist', 'Inter', system-ui, sans-serif;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{ --bg:#0E0D0B; --ink:#F1ECE3; --steel:#9CA3AD; --line:#262320; --panel:#16140F; }}
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:var(--fb); background:var(--bg); color:var(--ink);
            line-height:1.55; -webkit-font-smoothing:antialiased; }}
    .wrap {{ max-width:780px; margin:0 auto; padding:56px 24px 96px; }}
    .brand {{ font-family:var(--fm); font-size:11px; letter-spacing:.16em;
             text-transform:uppercase; color:var(--steel); margin-bottom:32px; }}
    h1 {{ font-size:34px; font-weight:300; letter-spacing:-.015em; margin:0 0 14px; line-height:1.15; }}
    .lede {{ font-size:17px; color:var(--steel); margin:0 0 16px; max-width:62ch; }}
    .updated {{ font-family:var(--fm); font-size:11px; color:var(--steel); letter-spacing:.06em; }}
    .updated b {{ color:var(--ink); }}
    .posture-pill {{ display:inline-block; padding:3px 11px; border-radius:99px;
                     font-family:var(--fm); font-size:10px; letter-spacing:.1em;
                     text-transform:uppercase; font-weight:600; }}
    .posture-pill.acc {{ background:color-mix(in srgb,var(--acc) 16%,transparent); color:var(--acc); }}
    .posture-pill.warn {{ background:color-mix(in srgb,var(--warn) 16%,transparent); color:var(--warn); }}
    .posture-pill.bear {{ background:color-mix(in srgb,var(--bear) 18%,transparent); color:var(--bear); }}
    .posture-pill.steel {{ background:color-mix(in srgb,var(--steel) 12%,transparent); color:var(--steel); }}

    section {{ margin:48px 0; }}
    h2 {{ font-family:var(--fm); font-size:11px; font-weight:600; letter-spacing:.18em;
          text-transform:uppercase; color:var(--steel); margin:0 0 18px;
          display:flex; align-items:center; gap:14px; }}
    h2::after {{ content:""; flex:1; height:1px; background:var(--line); }}
    p {{ margin:0 0 14px; max-width:62ch; }}
    .small {{ font-size:13px; color:var(--steel); }}

    .kpis {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(160px, 1fr));
              gap:14px; margin:18px 0; }}
    .kpi {{ background:var(--panel); border:1px solid var(--line); border-radius:8px;
            padding:16px 18px; }}
    .kpi-lbl {{ font-family:var(--fm); font-size:9px; letter-spacing:.14em;
                text-transform:uppercase; color:var(--steel); margin-bottom:6px; }}
    .kpi-val {{ font-size:26px; font-weight:300; color:var(--ink); font-variant-numeric:tabular-nums; }}
    .kpi-val.placeholder {{ color:var(--steel); font-size:18px; font-style:italic; }}
    .kpi-cap {{ font-family:var(--fm); font-size:11px; color:var(--steel); margin-top:4px; }}

    .chart-grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:18px; }}
    .chart-card {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px 16px; }}

    table.t {{ width:100%; border-collapse:collapse; font-family:var(--fm); font-size:12px; }}
    table.t th, table.t td {{ padding:8px 6px; border-bottom:1px solid var(--line); text-align:left; }}
    table.t th {{ font-size:10px; letter-spacing:.08em; text-transform:uppercase;
                  color:var(--steel); font-weight:500; }}
    table.t .num {{ text-align:right; font-variant-numeric:tabular-nums; }}
    .tag {{ display:inline-block; padding:1px 6px; border-radius:99px; font-family:var(--fm);
            font-size:9px; letter-spacing:.06em; text-transform:uppercase; font-weight:600;
            border:1px solid currentColor; }}
    .tag.acc {{ color:var(--acc); }}
    .tag.warn {{ color:var(--warn); }}
    .tag.bear {{ color:var(--bear); }}
    .tag.steel {{ color:var(--steel); }}

    ul.posts {{ list-style:none; padding:0; margin:0; }}
    ul.posts li {{ padding:12px 0; border-bottom:1px solid var(--line);
                    display:flex; gap:14px; align-items:baseline; }}
    ul.posts li:last-child {{ border-bottom:none; }}
    .post-date {{ font-family:var(--fm); font-size:11px; color:var(--steel);
                   letter-spacing:.04em; flex-shrink:0; width:80px; }}
    .post-title {{ font-size:14px; }}
    a {{ color:var(--ink); text-decoration:underline; text-decoration-color:var(--line);
          text-underline-offset:3px; }}
    a:hover {{ text-decoration-color:var(--ink); }}

    .methodology details {{ background:var(--panel); border:1px solid var(--line);
                             border-radius:8px; padding:14px 18px; }}
    .methodology summary {{ font-family:var(--fm); font-size:11px; letter-spacing:.12em;
                              text-transform:uppercase; color:var(--steel); cursor:pointer;
                              font-weight:500; }}
    .methodology dl {{ display:grid; grid-template-columns:max-content 1fr;
                        gap:6px 16px; margin-top:14px; font-family:var(--fm); font-size:12px; }}
    .methodology dt {{ color:var(--steel); }}
    .methodology dd {{ margin:0; color:var(--ink); font-variant-numeric:tabular-nums; }}

    footer {{ margin-top:72px; padding-top:24px; border-top:1px solid var(--line);
              font-size:12px; color:var(--steel); }}
  </style>
</head>
<body>
<div class="wrap">

<header>
  <div class="brand">PRESAGE · track</div>
  <h1>Public track record d'un instrument de discipline.</h1>
  <p class="lede">
    Portefeuille single-stock géré avec détection mécanisée des biais
    comportementaux. Brier scores, lock-in et fomo-greed résolus, alpha
    décomposé. Mise à jour mensuelle automatique.
  </p>
  <div class="updated">
    Statut : <span class="posture-pill {_status_class(posture_global)}">{posture_global}</span>
    · mis à jour <b>{as_of_short}</b>
  </div>
</header>

<section>
  <h2>KPIs canoniques</h2>
  <div class="kpis">
    <div class="kpi">
      <div class="kpi-lbl">Prédictions résolues</div>
      <div class="kpi-val">{pred_n}</div>
      <div class="kpi-cap">{pred.get("n_open", 0)} ouvertes</div>
    </div>
    <div class="kpi">
      <div class="kpi-lbl">Brier moyen</div>
      {brier_val}
      {acc_cap}
    </div>
    <div class="kpi">
      <div class="kpi-lbl">Biais cumulé</div>
      <div class="kpi-val">{bias_cumul_str}</div>
      <div class="kpi-cap">lock_in + fomo_greed + other</div>
    </div>
    {alpha_html}
  </div>
</section>

<section>
  <h2>Calibration et discipline (timeseries)</h2>
  <div class="chart-grid">
    <div class="chart-card">{brier_chart_html}</div>
    <div class="chart-card">{bias_lock_chart_html}</div>
    <div class="chart-card">{bias_fomo_chart_html}</div>
  </div>
</section>

<section>
  <h2>Biais comportementaux — bilan</h2>
  <table class="t">
    <thead>
      <tr><th>Biais</th><th>Résolus</th><th class="num">Δ EUR cumulé</th><th>Posture</th></tr>
    </thead>
    <tbody>{bias_table}</tbody>
  </table>
</section>

<section>
  <h2>Thèses actives</h2>
  <div class="kpis">
    <div class="kpi">
      <div class="kpi-lbl">Total</div>
      <div class="kpi-val">{theses.get("n_active", 0)}</div>
    </div>
    <div class="kpi">
      <div class="kpi-lbl">OK</div>
      <div class="kpi-val">{by_posture.get("OK", 0)}</div>
    </div>
    <div class="kpi">
      <div class="kpi-lbl">WARN</div>
      <div class="kpi-val">{by_posture.get("WARN", 0)}</div>
    </div>
    <div class="kpi">
      <div class="kpi-lbl">ALERT</div>
      <div class="kpi-val">{by_posture.get("ALERT", 0)}</div>
    </div>
  </div>
</section>

<section class="methodology">
  <h2>Méthodologie</h2>
  <details>
    <summary>Voir paramètres et règles</summary>
    <dl>
      <dt>Scorer version</dt><dd>{methodology.get("scorer_version", "?")}</dd>
      <dt>Horizon prédictions</dt><dd>{methodology.get("prediction_horizon_days", "?")} j</dd>
      <dt>Horizon lock-in</dt><dd>{methodology.get("lock_in_horizon_days", "?")} j</dd>
      <dt>Cibles lock-in / conviction</dt>
      <dd>c5 +70% · c4 +60% · c3 +50% · c2 +40% · c1 +30%</dd>
      <dt>Seuils magnitude (exit ≥)</dt>
      <dd>c5 ≥25% · c4 ≥35% · c3 ≥50% · c2 ≥75% · c1 ignoré</dd>
      <dt>Recal credibility</dt>
      <dd>fenêtre 180j · plancher 0.30 · plafond 0.95</dd>
    </dl>
  </details>
</section>

<section>
  <h2>Publications</h2>
  <ul class="posts">{posts_html}</ul>
</section>

<footer>
  PRESAGE · construit en solo · pas de fundraising, pas d'API payante, pas de partenaires payés.
  Le track record est l'unique référence.
  <br>
  <a href="mailto:hello@presage.pro">RSS / email (bientôt)</a> ·
  <a href="https://github.com/...">repo public</a>
</footer>

</div>
</body>
</html>'''


def main() -> Path:
    from intelligence.track_record_aggregator import compute_public_track_record
    from intelligence.track_record_timeseries import compute_all_timeseries
    from shared.storage import DB_PATH

    cx = sqlite3.connect(DB_PATH)
    try:
        record = compute_public_track_record(cx)
        timeseries = compute_all_timeseries(cx)
    finally:
        cx.close()

    html = _render_html(record, timeseries)
    out = ROOT / "site_public" / "track.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}")
    return out


if __name__ == "__main__":
    main()
