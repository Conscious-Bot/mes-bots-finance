# Re-resolution de 3 predictions historiques — bug wrong-day close

**Date** : 2026-05-31
**Operateur** : Claude (Opus 4.7) en pair avec Olivier
**Critique** : sol porteur ground-truth (cf strategie 31/05 #4 user)

## Resume

`intelligence/learning.py:resolve_due_predictions` utilisait
`prices.get_current_price(ticker)` au moment de l'execution du cron, au lieu
de `get_close_on(ticker, target_date)`. Sur les US tickers, le cron tournant a
09h CEST = 07h UTC, le close du jour-target n'existait pas encore (US open
13h30 UTC, close 21h UTC) — yfinance retournait donc le dernier daily
disponible = close de la veille (T-1).

Audit 31/05 sur les 6 predictions deja resolues : **3 outcomes sur 6 etaient
faux**.

## Quantification du degat (avant correction)

| id | tkr | dir | baseline | target_date | stored_final (T-1) | actual_close (T) | stored_ret | actual_ret | stored_out | actual_out | verdict |
|----|-----|-----|----------|-------------|-------------------|------------------|------------|------------|------------|------------|---------|
| 89 | COIN | bullish | 191.29 | 2026-05-27 | 180.01 | 173.78 | -5.90% | -9.15% | incorrect | incorrect | OK (deja sous -5%) |
| 50 | NVDA | bullish | 225.32 | 2026-05-29 | 214.25 | 211.14 | -4.91% | -6.29% | neutral | **incorrect** | **MISMATCH** |
| 51 | AVGO | bullish | 425.19 | 2026-05-29 | 426.58 | 446.77 | +0.33% | +5.08% | neutral | **correct** | **MISMATCH** |
| 52 | AMD | bullish | 424.10 | 2026-05-29 | 518.09 | 516.10 | +22.16% | +21.69% | correct | correct | OK (>>5%) |
| 53 | MSFT | bullish | 421.92 | 2026-05-29 | 426.99 | 450.24 | +1.20% | +6.71% | neutral | **correct** | **MISMATCH** |
| 54 | GOOGL | bullish | 396.78 | 2026-05-29 | 390.13 | 380.34 | -1.68% | -4.14% | neutral | neutral | OK (reste sous threshold) |

Les 3 mismatch ont en commun : le retour reel T passe le seuil 5% dans la
"bonne" direction, alors que le retour T-1 (proxy errone) restait sous le
seuil. Le bug masquait systematiquement les vraies resolutions substantielles.

## Action correctrice — Phase A : re-resolution DB

**Backup pris** : `data/bot.db.backup_pre_resolve_fix_20260531_152531`

**UPDATE des 3 lignes via Python parameterized** (script preserve dans le
commit) :

| id | tkr | new_final_price | new_return_pct | new_outcome | new_credibility_delta | new_brier_score |
|----|-----|-----------------|----------------|-------------|----------------------|-----------------|
| 50 | NVDA | 211.1399993896 | -6.2933% | incorrect | -0.05 | 0.391876 |
| 51 | AVGO | 446.7699890137 | +5.0754% | correct | +0.03 | 0.139876 |
| 53 | MSFT | 450.2399902344 | +6.7122% | correct | +0.03 | 0.139876 |

Constantes utilisees :
- `OUTCOME_DELTA = {"correct": 0.03, "incorrect": -0.05, "neutral": 0.0}`
- `brier_for(prob, outcome) = (prob - (1 if correct else 0)) ** 2` ; None si
  neutral ou prob absente
- Toutes ces 3 predictions : `probability_at_creation = 0.626`

## Action correctrice — Phase B : code fix

`shared/prices.py` : ajoute `get_close_on(ticker, date_str)` qui retourne le
close du `date_str` exact (ou prochain jour de marche si weekend/holiday,
yfinance auto-aligne), None si delisted/suspended ou data gap > 7j.

`intelligence/learning.py:resolve_due_predictions` : remplace
`get_current_price(ticker)` par `get_close_on(ticker, pred["target_date"])`.
Variable renommee `current_price` -> `target_close` pour clarte semantique.

Tests : ajoutes a `tests/test_prices_fx.py` pour `get_close_on` (live path,
weekend handling, delisted -> None).

## Impact sur les KPI publies

| metrique | avant correction | apres correction |
|----------|------------------|------------------|
| KPI #2 resolves substantiels (non-neutral) | 2 (1c + 1i) | 5 (3c + 2i) |
| Taux correct sur substantiels | 50% (1/2) | 60% (3/5) |
| Wilson IC95% taux correct | [9.5%, 90.5%] | [23.1%, 88.2%] (toujours non-conclusif a N=5) |

Le bot a en realite ete plus performant que ses propres stats. Une correction
qui rehausse autant qu'elle baisse — pas un cherry-pick.

## Verifications post-fix

- [x] Backup DB pris pre-modification (timestamped)
- [x] UPDATE applique via parametrized SQL (pas string interpolation)
- [x] SELECT post-UPDATE confirme les 3 nouvelles valeurs persistees
- [x] Backup memory `feedback-clean-auditable-path` cree (preference user)
- [x] Doc audit ecrite (ce fichier)
- [x] Tests get_close_on ajoutes
- [x] Full pytest verts
- [x] Bot restart pour consommer le nouveau code

## Loose ends

- Le bot tournait avec l'ancien code resolve_due_predictions au moment du
  daily_resolve_job le 29/05 06h CEST. Les prochaines resolutions (job a 9h)
  utiliseront `get_close_on` une fois le bot restarte.
- Aucune autre prediction en attente avec target_date passe a ce jour
  (verifier post-fix : `SELECT * FROM predictions WHERE resolved_at IS NULL
  AND target_date <= date('now')`).
