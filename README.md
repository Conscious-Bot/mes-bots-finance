# mes-bots-finance

Closed-loop personal finance intelligence: Telegram bot + Claude integration. Self-learning thesis tracker with bidirectional discipline enforcement.

## CI Status

Private repo — CI runs on every push to main against ruff + mypy (16 strict-typed modules) + pytest (270 tests). Visible in GitHub Actions tab. Badge omitted (requires public repo OR PAT setup).

Going public is a post-June-2026 decision pending Brier baseline empirical (KPI #2 batch resolution 10 June 2026, ~45 predictions cluster).

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

270 tests passing — Hypothesis property-based on math-critical modules:
- `shared/math_helpers.py` (credibility clamping, Brier scoring)
- `intelligence/materiality_v2.py` (composite materiality rubric)
- `intelligence/asymmetry.py` (verdict logic)
- `intelligence/learning.py` (horizon diversification)

## Architecture

See `FICHE_TECHNIQUE.md` (mission + stack + KPIs) and `docs/` for:
- `SOURCES.md` — newsletter tiers S/A/B empirical
- `failure_modes.md` — 12 failure scenarios + runbooks (FM-1 to FM-12, codified through Day 11+12 marathon)

## Path 5/6 strategic mode

This project is in **High Standard / Solidification** mode, targeting either acquihire (18-24mo) or Substack/prosumer subscription (24-36mo). See `PHILOSOPHY.md` and `TODO.md` for the 4-dimensions roadmap.

