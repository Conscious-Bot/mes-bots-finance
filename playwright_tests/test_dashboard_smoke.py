"""Playwright smoke tests dashboard (#23).

Run :
    pytest playwright_tests/ --browser=chromium

Pas dans la pytest suite par defaut (cf playwright_tests/conftest.py).
Setup une-fois :
    pip install pytest-playwright
    playwright install chromium
"""
from __future__ import annotations

import pytest

# Skip toute la suite si pytest-playwright n'est pas installe
playwright = pytest.importorskip("playwright.sync_api")


def test_dashboard_loads_without_errors(page, dashboard_server):
    """Page charge sans console errors."""
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.goto(f"{dashboard_server}/dashboard.html")
    # Wait for content
    page.wait_for_selector(".phead h2", timeout=10000)
    assert not errors, f"Console errors: {errors}"


def test_dashboard_has_sidebar_nav(page, dashboard_server):
    """Sidebar nav presente avec 9 items."""
    page.goto(f"{dashboard_server}/dashboard.html")
    page.wait_for_selector(".nitem", timeout=5000)
    items = page.query_selector_all(".nitem")
    assert len(items) >= 8, f"Expected >=8 nitem, got {len(items)}"


# Tests cahier-de-bord supprimes 02/06 user "mode cahier a supprimer"


def test_dark_mode_toggle_works(page, dashboard_server):
    """Bouton dark/light toggle modetgl applique body.midnight."""
    page.goto(f"{dashboard_server}/dashboard.html")
    page.wait_for_selector(".modetgl", timeout=5000)
    page.click(".modetgl")
    page.wait_for_timeout(100)
    is_midnight = page.evaluate(
        "() => document.body.classList.contains('midnight')"
    )
    # On peut etre dans n'importe quel etat initial (prefers-color-scheme).
    # On verifie juste que toggle change quelque chose.
    page.click(".modetgl")
    page.wait_for_timeout(100)
    is_midnight_2 = page.evaluate(
        "() => document.body.classList.contains('midnight')"
    )
    assert is_midnight != is_midnight_2
