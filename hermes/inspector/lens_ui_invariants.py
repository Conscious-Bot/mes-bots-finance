"""Lentille UI invariants : assertions comportementales via Playwright headless.

Audit la classe de bug que les autres lentilles ne voient pas : un texte
affiche prometant une chose, un DOM/JS la trahissant silencieusement.
Exemples :
- nav item click -> section ne devient pas active (lien casse)
- tooltip claim "cap c5 22%" mais config dit 6% (string-vs-config drift)
- sector bar click -> aucune position highlightee (handler casse)
- Overview hero vs Positions hero : valeurs book divergentes (cross-page)

Read-only strict : aucune mutation DOM, aucun event side-effect cote serveur.
Playwright navigue + lit. Si Playwright absent ou serveur down, skip silent
(retourne candidats vide).

Doctrine SAS : meme contrainte que les autres lens. Verdict = utilisateur.
"""
from __future__ import annotations

import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

DEFAULT_URL = "http://127.0.0.1:8000/dashboard.html"


@dataclass
class UIInvariantFinding:
    """Une assertion UI qui a echoue."""
    invariant_id: str       # 'nav_switches_panel' / 'book_value_cross_page' / ...
    description: str        # rule textuelle
    evidence: str           # element/valeur/etat qui casse
    page: str               # data-page (ou 'global')
    confidence: int         # 80-95 (UI = concret, mais flaky possible)


def _server_reachable(url: str, timeout: float = 1.5) -> bool:
    """TCP probe rapide sur host:port du serveur (avant lancer Playwright)."""
    p = urlparse(url)
    host = p.hostname or "127.0.0.1"
    port = p.port or (443 if p.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _playwright_available() -> bool:
    """Check Playwright sync_api importable."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _check_nav_switches_panel(page, fails: list[UIInvariantFinding]) -> None:
    """Pour chaque [data-nav=X], le clic doit activer section[data-page=X]
    ET la section doit avoir une hauteur rendue > 0.

    Robustesse anti-flake : wait_for explicite sur .active (max 2s) avant
    de mesurer la hauteur. Un timeout = vrai fail (pas du bruit).
    """
    nav_ids = page.locator("[data-nav]").evaluate_all(
        "els => [...new Set(els.map(e => e.dataset.nav))]"
    )
    for nav in nav_ids:
        try:
            page.locator(f'[data-nav="{nav}"]').first.click(timeout=3000)
        except Exception as e:
            fails.append(UIInvariantFinding(
                invariant_id="nav_switches_panel",
                description="Every [data-nav=X] click must activate section[data-page=X] with height > 0",
                evidence=f"data-nav='{nav}' : click failed ({type(e).__name__})",
                page=nav,
                confidence=85,
            ))
            continue
        section = page.locator(f'section[data-page="{nav}"].active').first
        try:
            section.wait_for(state="attached", timeout=2000)
            is_active = True
        except Exception:
            is_active = False
        if not is_active:
            fails.append(UIInvariantFinding(
                invariant_id="nav_switches_panel",
                description="[data-nav=X] click must add .active to section[data-page=X]",
                evidence=f"data-nav='{nav}' clicked but section[data-page='{nav}'] not .active after 2s",
                page=nav,
                confidence=90,
            ))
            continue
        box = page.locator(f'section[data-page="{nav}"]').first.bounding_box()
        h = box["height"] if box else 0
        if h == 0:
            fails.append(UIInvariantFinding(
                invariant_id="nav_switches_panel",
                description="Active section must render with height > 0",
                evidence=f"section[data-page='{nav}'].active but bbox.height=0 (panel invisible)",
                page=nav,
                confidence=85,
            ))


def _check_book_value_cross_page(page, fails: list[UIInvariantFinding]) -> None:
    """Overview hero book value == Positions hero book value (textually).

    Strip whitespace / non-breaking spaces avant comparaison. Tolere variations
    cosmetiques (€ collé / espacé) en normalisant les chiffres seulement.
    """
    import re
    def _digits(s: str) -> str:
        return re.sub(r"[^0-9]", "", s or "")

    page.locator('[data-nav="vigie"]').first.click()
    page.wait_for_timeout(200)
    overview_v = page.locator('section[data-page="vigie"] .ov-hero .v').first
    if overview_v.count() == 0:
        return
    ov_text = overview_v.evaluate("e => e.textContent.trim()")

    page.locator('[data-nav="positions"]').first.click()
    page.wait_for_timeout(200)
    pos_v = page.locator('section[data-page="positions"] .v').first
    if pos_v.count() == 0:
        return
    pos_text = pos_v.evaluate("e => e.textContent.trim()")

    if _digits(ov_text) != _digits(pos_text):
        fails.append(UIInvariantFinding(
            invariant_id="book_value_cross_page",
            description="Overview hero book value must match Positions hero book value",
            evidence=f"Overview='{ov_text}' Positions='{pos_text}' (digits diverge)",
            page="vigie+positions",
            confidence=90,
        ))


def _check_sector_bar_links_to_rows(page, fails: list[UIInvariantFinding]) -> None:
    """Dans chaque .pos-acct card, le clic sur un .pos-sec-row[data-sec=X]
    doit highlight (.sec-hi) au moins 1 tr[data-sec=X] de la MEME card.

    Scope card = doctrine du handler JS (cf dashboard/_scripts.py _DONUT_JS).
    """
    page.locator('[data-nav="positions"]').first.click()
    page.wait_for_timeout(300)
    n_cards = page.locator("section[data-page=positions] .pos-acct").count()
    for ci in range(n_cards):
        card_sel = f"section[data-page=positions] .pos-acct >> nth={ci}"
        bars_secs = page.locator(card_sel).locator(".pos-sec-row[data-sec]").evaluate_all(
            "els => [...new Set(els.map(e => e.dataset.sec))]"
        )
        for sec in bars_secs:
            # Verifier prerequis : card a au moins 1 row tr[data-sec=sec]
            esc_sec = sec.replace('"', r'\"')
            n_rows = page.locator(card_sel).locator(f'tr[data-sec="{esc_sec}"]').count()
            if n_rows == 0:
                fails.append(UIInvariantFinding(
                    invariant_id="sector_bar_links_to_rows",
                    description="Sector bar displayed must have ≥1 matching row in same .pos-acct",
                    evidence=f"card #{ci} bar data-sec='{sec}' but 0 tr[data-sec='{sec}'] in same card",
                    page="positions",
                    confidence=92,
                ))
                continue
            try:
                page.locator(card_sel).locator(
                    f'.pos-sec-row[data-sec="{esc_sec}"]'
                ).first.click(timeout=3000)
            except Exception:
                continue
            page.wait_for_timeout(150)
            n_hi = page.locator(card_sel).locator(
                f'tr[data-sec="{esc_sec}"].sec-hi'
            ).count()
            if n_hi == 0:
                fails.append(UIInvariantFinding(
                    invariant_id="sector_bar_links_to_rows",
                    description="Sector bar click must highlight ≥1 row in same .pos-acct",
                    evidence=f"card #{ci} clicked bar '{sec}' but 0 row got .sec-hi",
                    page="positions",
                    confidence=88,
                ))


def scan(url: str = DEFAULT_URL, timeout_ms: int = 15000) -> dict[str, Any]:
    """Run UI invariants sur le dashboard servi.

    Returns:
        dict avec 'candidates_raw' (list[UIInvariantFinding]) + status meta.

    Pre-flight :
    - Playwright importable ?
    - URL reachable (TCP probe) ?
    Si KO -> skip silent, status documente.
    """
    if not _playwright_available():
        return {
            "candidates_raw": [],
            "status": "skipped",
            "reason": "playwright not installed (pip install playwright + playwright install chromium)",
            "url": url,
        }
    if not _server_reachable(url):
        return {
            "candidates_raw": [],
            "status": "skipped",
            "reason": f"server unreachable at {url} (start dashboard.serve first)",
            "url": url,
        }

    from playwright.sync_api import sync_playwright

    fails: list[UIInvariantFinding] = []
    error: str | None = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                _check_nav_switches_panel(page, fails)
                _check_book_value_cross_page(page, fails)
                _check_sector_bar_links_to_rows(page, fails)
            finally:
                browser.close()
    except Exception as e:
        error = f"{type(e).__name__}: {e}"

    return {
        "candidates_raw": fails,
        "status": "ok" if not error else "error",
        "reason": error,
        "url": url,
        "n_fails": len(fails),
    }
