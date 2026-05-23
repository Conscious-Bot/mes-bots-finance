from pathlib import Path

from dashboard.render import render


def test_render_smoke():
    """End-to-end: render() ne crashe pas, produit une page complete, 8 sections."""
    out = render()
    assert isinstance(out, Path)
    assert out.exists()
    html = out.read_text()
    assert len(html) > 15000, f"page trop petite: {len(html)} bytes"
    assert html.startswith("<!doctype html")
    assert html.rstrip().endswith("</html>")
    for nav in ("vigie", "positions", "theses", "concentration", "secteurs", "geo", "signaux", "urgence"):
        assert f'data-nav="{nav}"' in html, f"nav manquant: {nav}"
    for page in ("vigie", "positions", "theses"):
        assert f'data-page="{page}"' in html, f"section manquante: {page}"
    assert "HEIMDALL" in html
    assert "window.TK=" in html
    assert "window.HQ=" in html
