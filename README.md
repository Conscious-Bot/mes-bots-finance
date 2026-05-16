# mes-bots-finance

Closed-loop personal finance intelligence: Telegram bot + Claude integration. Self-learning thesis tracker with bidirectional discipline enforcement.

## CI Status

Private repo — CI runs on every push to main against ruff + mypy (14 strict-typed modules) + pytest (128 tests). Visible in GitHub Actions tab. Badge omitted (requires public repo OR PAT setup).

Going public is a post-J+28 decision pending Brier baseline empirical.

## Stack

- Python 3.14
- SQLite (WAL mode)
- APScheduler
- Anthropic Claude API (Haiku / Sonnet / Opus cascade)
- python-telegram-bot

## Tests

```bash
make test         # pytest verbose
make test-cov     # with coverage report
```

49 property-based tests (Hypothesis) on math-critical modules:
- `shared/math_helpers.py` (credibility clamping, Brier scoring)
- `intelligence/materiality_v2.py` (composite materiality rubric)
- `intelligence/asymmetry.py` (verdict logic)
- `intelligence/learning.py` (horizon diversification)

## Architecture

See `FICHE_TECHNIQUE.md` (mission + stack + KPIs) and `docs/` for:
- `SOURCES.md` — newsletter tiers S/A/B empirical
- `failure_modes.md` — top 5 failure scenarios + runbooks

## Path 5/6 strategic mode

This project is in **High Standard / Solidification** mode, targeting either acquihire (18-24mo) or Substack/prosumer subscription (24-36mo). See `PHILOSOPHY.md` and `TODO.md` for the 4-dimensions roadmap.

