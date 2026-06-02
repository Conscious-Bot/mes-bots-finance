# Playwright visual smoke tests (#23)

Tests E2E visuels du dashboard via Chromium headless. Pas dans la pytest
suite principale -- run separement.

## Setup une fois

```bash
pip install pytest-playwright
playwright install chromium
```

## Run

```bash
pytest playwright_tests/ --browser=chromium
```

Ou pour debug visuel :

```bash
pytest playwright_tests/ --browser=chromium --headed --slowmo=300
```

## Couverture actuelle

- `test_dashboard_loads_without_errors` : page render OK, zero console error
- `test_dashboard_has_sidebar_nav` : sidebar nav 9 items presents
- `test_cahier_toggle_button_visible` : bouton CAHIER visible
- `test_cahier_toggle_applies_class` : clic CAHIER applique class body
- `test_dark_mode_toggle_works` : toggle dark/light fonctionne

## Quand ajouter un test

Avant tout merge sur dashboard/render.py qui touche un selector critique
(.nitem, .modetgl, .cahier-toggle, .phead, ...). Lance `pytest
playwright_tests/` localement, ajoute le selector au panier des invariants
si nouveau.

## Limitations

- Sert dashboard/ via http.server stdlib -- pas le live-reload de serve.py.
  Faut regenerer via `render()` dans la fixture.
- Pas de tests JS asynchrones complexes (Cmd+K modal, sparkline hover) --
  ajout selectif si necessaire.
- Pas integre CI (Playwright + chromium = >500 MB image). Run local
  before push critique.
