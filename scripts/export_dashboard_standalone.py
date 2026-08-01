#!/usr/bin/env python3
"""Exporte un dashboard.html AUTONOME — CSS, JS, fontes et logos inlinés.

Le dashboard généré référence `/static/…` en chemins absolus : ouvert en
`file://` ou déplacé ailleurs, il apparaît nu. Ce script produit un fichier
unique qui s'ouvre partout, sans serveur.

⚠ CONFIDENTIEL : le fichier produit contient le PORTEFEUILLE RÉEL (lignes,
montants, P&L, thèses). Contrairement aux dumps de code, il n'est PAS
partageable. Les liens `obsidian://` ne fonctionnent que sur la machine du
gérant (normal, ils sont laissés tels quels).

Usage :
    python3 scripts/export_dashboard_standalone.py
    python3 scripts/export_dashboard_standalone.py --out /chemin/vers/sortie.html
"""
from __future__ import annotations

import argparse
import base64
import re
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "dashboard" / "dashboard.html"
STATIC = ROOT / "dashboard" / "static"

MIME = {".png": "image/png", ".svg": "image/svg+xml", ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
        ".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf"}


def b64(path: Path) -> str | None:
    if not path.is_file():
        return None
    mime = MIME.get(path.suffix.lower(), "application/octet-stream")
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def resolve(url: str) -> Path | None:
    """/static/x.png?v=123 -> dashboard/static/x.png"""
    clean = url.split("?")[0].split("#")[0]
    if not clean.startswith("/static/"):
        return None
    return STATIC / clean[len("/static/"):]


def inline_css_urls(css: str) -> tuple[str, int]:
    """Inline les url(...) d'une feuille de style (fontes, images de fond)."""
    n = 0

    def rep(m: re.Match) -> str:
        nonlocal n
        raw = m.group(1).strip("'\"")
        if raw.startswith("data:"):
            return m.group(0)
        p = resolve(raw) or (STATIC / raw.lstrip("./"))
        d = b64(p)
        if d:
            n += 1
            return f"url({d})"
        return m.group(0)

    return re.sub(r"url\(([^)]+)\)", rep, css), n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "dumps" / "dashboard_standalone.html"))
    args = ap.parse_args()

    if not SRC.is_file():
        print(f"Introuvable : {SRC}\nGénérer d'abord : python3 -m dashboard.serve")
        return 1

    html = SRC.read_text(encoding="utf-8", errors="replace")
    src_kb = len(html) // 1024
    stats = {"css": 0, "js": 0, "img": 0, "font": 0, "css_url": 0, "manquants": 0}

    # 1. Feuilles de style -> <style> inline (avec leurs propres url() résolues)
    def rep_css(m: re.Match) -> str:
        p = resolve(m.group(1))
        if p and p.is_file():
            css, n = inline_css_urls(p.read_text(encoding="utf-8", errors="replace"))
            stats["css"] += 1
            stats["css_url"] += n
            return f"<style>\n{css}\n</style>"
        stats["manquants"] += 1
        return m.group(0)

    html = re.sub(r'<link[^>]+rel=["\']stylesheet["\'][^>]*href=["\']([^"\']+)["\'][^>]*>',
                  rep_css, html)
    html = re.sub(r'<link[^>]+href=["\']([^"\']+\.css[^"\']*)["\'][^>]*rel=["\']stylesheet["\'][^>]*>',
                  rep_css, html)

    # 2. Scripts externes -> inline
    def rep_js(m: re.Match) -> str:
        p = resolve(m.group(1))
        if p and p.is_file():
            stats["js"] += 1
            js = p.read_text(encoding="utf-8", errors="replace").replace("</script>", "<\\/script>")
            return f"<script>\n{js}\n</script>"
        stats["manquants"] += 1
        return m.group(0)

    html = re.sub(r'<script[^>]+src=["\']([^"\']+)["\'][^>]*>\s*</script>', rep_js, html)

    # 3. Préchargement de fontes -> data URI (sinon 404 hors serveur)
    def rep_pre(m: re.Match) -> str:
        p = resolve(m.group(1))
        d = b64(p) if p else None
        if d:
            stats["font"] += 1
            return m.group(0).replace(m.group(1), d)
        return m.group(0)

    html = re.sub(r'<link[^>]+href=["\']([^"\']+\.woff2?[^"\']*)["\'][^>]*>', rep_pre, html)

    # 4. Images (logos) -> data URI
    def rep_img(m: re.Match) -> str:
        url = m.group(2)
        if url.startswith("data:"):
            return m.group(0)
        p = resolve(url)
        d = b64(p) if p else None
        if d:
            stats["img"] += 1
            return f'{m.group(1)}="{d}"'
        stats["manquants"] += 1
        return m.group(0)

    html = re.sub(r'\b(src|href)=["\'](/static/[^"\']+\.(?:png|svg|jpg|jpeg|gif|webp)[^"\']*)["\']',
                  rep_img, html)

    banner = (f"<!-- PRESAGE — dashboard AUTONOME, exporté "
              f"{datetime.now(UTC):%Y-%m-%d %H:%M UTC}. "
              f"CSS/JS/fontes/logos inlinés. ⚠ CONTIENT LE PORTEFEUILLE RÉEL — "
              f"ne pas partager. -->\n")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(banner + html, encoding="utf-8")

    print(f"Source     : {SRC.relative_to(ROOT)} ({src_kb} Ko)")
    print(f"Inlinés    : {stats['css']} CSS ({stats['css_url']} url() résolues), "
          f"{stats['js']} JS, {stats['font']} fontes, {stats['img']} images")
    print(f"Manquants  : {stats['manquants']}")
    print(f"Sortie     : {out} ({out.stat().st_size // 1024} Ko)")
    reste = re.findall(r'["\'](/static/[^"\']+)["\']', html)
    print(f"Réfs /static restantes : {len(reste)}"
          + (f" → {sorted(set(reste))[:3]}" if reste else " (aucune — autonome)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
