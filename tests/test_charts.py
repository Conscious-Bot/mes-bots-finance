"""Tests dashboard/charts.py helpers (#21 Plot + #22 uPlot)."""
from __future__ import annotations

import json
import re

import pytest

from dashboard.charts import plot_bars, plot_line, uplot_sparkline

# ─── plot_line ────────────────────────────────────────────────────────────


def test_plot_line_returns_html_with_payload():
    data = [{"date": "2026-06-01", "brier_avg": 0.18},
            {"date": "2026-06-08", "brier_avg": 0.15}]
    html = plot_line(data, x="date", y="brier_avg", title="Brier rolling")
    assert "<div" in html
    assert "<script type=\"module\">" in html
    assert '"date"' in html
    assert '"brier_avg"' in html
    assert "Brier rolling" in html


def test_plot_line_unique_ids():
    """2 charts -> ids distincts (Cmd+R safe)."""
    h1 = plot_line([], x="x", y="y")
    h2 = plot_line([], x="x", y="y")
    id1 = re.search(r'data-chart="(chart-\w+)"', h1).group(1)
    id2 = re.search(r'data-chart="(chart-\w+)"', h2).group(1)
    assert id1 != id2


def test_plot_line_json_payload_parseable():
    data = [{"date": "2026-06-01", "brier_avg": 0.18}]
    html = plot_line(data, x="date", y="brier_avg")
    m = re.search(r'<script type="application/json"[^>]*>(.*?)</script>',
                  html, re.DOTALL)
    payload = json.loads(m.group(1))
    assert payload == data


def test_plot_line_empty_data_renders_placeholder():
    """Sans data, le helper genere quand meme le HTML avec filtre vide."""
    html = plot_line([], x="x", y="y")
    assert "pas encore de données mesurables" in html


# ─── plot_bars ────────────────────────────────────────────────────────────


def test_plot_bars_returns_html():
    data = [{"week": "2026-W22", "n": 5}, {"week": "2026-W23", "n": 8}]
    html = plot_bars(data, x="week", y="n", title="Volume hebdo")
    assert "barY" in html
    assert "Volume hebdo" in html


# ─── uplot_sparkline ──────────────────────────────────────────────────────


def test_uplot_sparkline_returns_html():
    series = [100.0, 102.0, 101.0, 103.0, 105.0]
    html = uplot_sparkline(series)
    assert "uPlot" in html
    assert "<link rel=\"stylesheet\"" in html  # CSS CDN


def test_uplot_sparkline_default_timestamps():
    """Sans timestamps -> [0..n-1]."""
    series = [10.0, 20.0, 30.0]
    html = uplot_sparkline(series)
    m = re.search(r'<script type="application/json"[^>]*>(.*?)</script>',
                  html, re.DOTALL)
    payload = json.loads(m.group(1))
    assert payload[0] == [0, 1, 2]
    assert payload[1] == [10.0, 20.0, 30.0]


def test_uplot_sparkline_custom_timestamps():
    series = [100.0, 200.0]
    timestamps = [1717200000, 1717286400]
    html = uplot_sparkline(series, timestamps=timestamps)
    m = re.search(r'<script type="application/json"[^>]*>(.*?)</script>',
                  html, re.DOTALL)
    payload = json.loads(m.group(1))
    assert payload[0] == timestamps


def test_uplot_height_in_html():
    html = uplot_sparkline([1.0, 2.0], height=80)
    assert "height:80px" in html


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
