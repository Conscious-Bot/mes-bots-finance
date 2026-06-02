"""Charts helpers : Observable Plot (#21) + uPlot (#22) integration ESM.

Pattern :
- Pas de bundler ni build step -- chaque chart embarque son <script type=module>
  qui import les libs depuis CDN ESM (esm.sh, cdn.skypack.dev, jsdelivr).
- Helpers retournent un HTML string ready-to-inject dans render.py.
- Data : passe en JSON dans un <script type="application/json"> avant le chart,
  lu par le module script via document.querySelector + JSON.parse.

Usage :
    from dashboard.charts import plot_line, uplot_sparkline

    html = plot_line(
        data=timeseries,  # [{date, value}, ...]
        x="date", y="brier_avg", title="Brier 30j rolling",
        height=180,
    )
    # Embed dans render.py f-string
"""

from __future__ import annotations

import json
import uuid
from typing import Any

_PLOT_CDN = "https://cdn.jsdelivr.net/npm/@observablehq/plot@0.6.16/+esm"
_UPLOT_CDN = "https://cdn.jsdelivr.net/npm/uplot@1.6.31/dist/uPlot.esm.min.js"
_UPLOT_CSS_CDN = "https://cdn.jsdelivr.net/npm/uplot@1.6.31/dist/uPlot.min.css"


def _safe_id() -> str:
    """ID unique pour chaque chart (collisions Cmd+R safe)."""
    return f"chart-{uuid.uuid4().hex[:8]}"


def plot_line(
    data: list[dict[str, Any]],
    x: str,
    y: str,
    title: str = "",
    height: int = 200,
    color: str = "var(--acc, #5F9A4D)",
) -> str:
    """Observable Plot line chart -- pour timeseries clean (Brier rolling,
    bias cumul, predictions volume).

    Args:
        data: liste de dicts avec au minimum les cles `x` et `y`
        x: nom de la colonne date (string "YYYY-MM-DD")
        y: nom de la colonne value (number ou None)
        title: titre optionnel au-dessus
        height: hauteur en px
        color: stroke color (default var(--acc))

    Returns:
        HTML string avec <div> + <script type="application/json"> + <script type=module>.
    """
    cid = _safe_id()
    payload = json.dumps(data, default=str, sort_keys=True)
    title_html = (
        f'<div class="chart-title" style="font-family:var(--fm);'
        f'font-size:11px;letter-spacing:.12em;text-transform:uppercase;'
        f'color:var(--steel);margin-bottom:8px">{title}</div>'
        if title else ""
    )
    return f'''
<div class="chart-wrap" data-chart="{cid}">
  {title_html}
  <div id="{cid}" style="width:100%;height:{height}px"></div>
  <script type="application/json" id="{cid}-data">{payload}</script>
  <script type="module">
    import * as Plot from "{_PLOT_CDN}";
    const data = JSON.parse(document.getElementById("{cid}-data").textContent);
    const filtered = data.filter(d => d["{y}"] !== null && d["{y}"] !== undefined);
    if (filtered.length > 0) {{
      const chart = Plot.plot({{
        height: {height},
        marginLeft: 40, marginBottom: 28, marginTop: 10, marginRight: 12,
        style: {{
          background: "transparent",
          color: "var(--steel, #6B7686)",
          fontFamily: "var(--fm, monospace)",
          fontSize: "10px",
        }},
        x: {{ label: null, tickFormat: d => String(d).slice(5) }},
        y: {{ label: null, grid: true }},
        marks: [
          Plot.line(filtered, {{ x: "{x}", y: "{y}", stroke: "{color}", strokeWidth: 1.5 }}),
          Plot.dot(filtered, {{ x: "{x}", y: "{y}", fill: "{color}", r: 2 }}),
        ],
      }});
      document.getElementById("{cid}").appendChild(chart);
    }} else {{
      document.getElementById("{cid}").innerHTML =
        '<div style="font-family:var(--fm);font-size:11px;color:var(--steel);' +
        'text-align:center;padding-top:{height // 2 - 10}px">' +
        'pas encore de données mesurables</div>';
    }}
  </script>
</div>
'''


def plot_bars(
    data: list[dict[str, Any]],
    x: str,
    y: str,
    title: str = "",
    height: int = 180,
    color: str = "var(--acc, #5F9A4D)",
) -> str:
    """Bar chart pour volume hebdo predictions, ou breakdown source."""
    cid = _safe_id()
    payload = json.dumps(data, default=str, sort_keys=True)
    title_html = (
        f'<div class="chart-title" style="font-family:var(--fm);'
        f'font-size:11px;letter-spacing:.12em;text-transform:uppercase;'
        f'color:var(--steel);margin-bottom:8px">{title}</div>'
        if title else ""
    )
    return f'''
<div class="chart-wrap" data-chart="{cid}">
  {title_html}
  <div id="{cid}" style="width:100%;height:{height}px"></div>
  <script type="application/json" id="{cid}-data">{payload}</script>
  <script type="module">
    import * as Plot from "{_PLOT_CDN}";
    const data = JSON.parse(document.getElementById("{cid}-data").textContent);
    const chart = Plot.plot({{
      height: {height},
      marginLeft: 36, marginBottom: 26, marginTop: 10, marginRight: 8,
      style: {{
        background: "transparent",
        color: "var(--steel, #6B7686)",
        fontFamily: "var(--fm, monospace)",
        fontSize: "10px",
      }},
      x: {{ label: null }},
      y: {{ label: null, grid: true }},
      marks: [
        Plot.barY(data, {{ x: "{x}", y: "{y}", fill: "{color}" }}),
      ],
    }});
    document.getElementById("{cid}").appendChild(chart);
  </script>
</div>
'''


def uplot_sparkline(
    series: list[float],
    timestamps: list[int] | None = None,
    height: int = 60,
    color: str = "#5DC0C8",
) -> str:
    """uPlot sparkline -- pour series denses (10k+ points : prix historique).

    Args:
        series: liste de floats (y values)
        timestamps: list of UNIX ts (default = index 0..n-1)
        height: px
        color: stroke

    Plus light que Observable Plot pour render dense series.
    """
    cid = _safe_id()
    if timestamps is None:
        timestamps = list(range(len(series)))
    payload = json.dumps([timestamps, series])
    return f'''
<div class="chart-wrap" data-chart="{cid}">
  <link rel="stylesheet" href="{_UPLOT_CSS_CDN}">
  <div id="{cid}" style="width:100%;height:{height}px"></div>
  <script type="application/json" id="{cid}-data">{payload}</script>
  <script type="module">
    import uPlot from "{_UPLOT_CDN}";
    const data = JSON.parse(document.getElementById("{cid}-data").textContent);
    const opts = {{
      width: document.getElementById("{cid}").clientWidth,
      height: {height},
      cursor: {{ show: false }},
      legend: {{ show: false }},
      axes: [
        {{ show: false }},
        {{ show: false }},
      ],
      scales: {{
        x: {{ time: false }},
      }},
      series: [
        {{}},
        {{
          stroke: "{color}",
          width: 1.2,
          fill: "{color}1A",
          points: {{ show: false }},
        }},
      ],
    }};
    new uPlot(opts, data, document.getElementById("{cid}"));
  </script>
</div>
'''
