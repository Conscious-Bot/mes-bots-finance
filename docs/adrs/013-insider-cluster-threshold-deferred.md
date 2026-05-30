# ADR 013 — Insider cluster moderate threshold : différé post-10/06

**Status**: Accepted (30/05/2026)
**Related**: ADR 012 (8-K severity classifier deprecate), `intelligence/v2_vigilance.py`, decision_logs/01_calibration_unanchored.md iter 17

## Context

`shared/edgar._classify_buy_cluster()` classifie les insider buy clusters en `none/weak/moderate/strong`. Le seuil **moderate = `n>=3 buyers ET total>=$1M`**. Diagnostic iter 17 (session 30/05) sur 10 tickers du book :

- 9/10 tickers (NVDA, AMD, AVGO, MU, TSLA, GOOGL, META, AMZN, CCJ) : 0 insider buy détecté sur 30j
- 1/10 (MP) : 1 buyer + $0.96M → sous seuil moderate ($1M), classifié `none`

Conséquence : `insider_buy_clusters_log` à 0 rows depuis longtemps. La vigilance `check_insider_clusters_alive` a été recalibrée pour distinguer "job cassé" (0 cluster + 0 buy individuel) de "univers sans clusters" (0 cluster + buys existants mais sous seuil → status INFO normal).

Question ouverte : faut-il abaisser le seuil moderate de $1M à $0.5M pour capter les borderline (MP-style) et avoir plus de matière V2 ?

## Decision

**Pas maintenant**. Seuil `$1M` conservé. Décision reportée post-10/06.

### Rationale

Trois raisons :

1. **Discipline anti-tinkering proche moment de vérité** (cf pattern session iter 13) : ne pas toucher critère de scoring à J-11 du batch resolution. Le batch 10/06 est sous V1, mais V2 est désormais en prod pour les cohortes suivantes — modifier le seuil de detection cluster *avant* d'avoir mesuré le comportement actuel du wire serait pré-mature.

2. **Le seuil $1M existe pour une raison** : éviter les "3 directors qui achètent $50K each" = noise. Abaisser à $0.5M risque de polluer le ledger avec des clusters faibles qui sortiraient `weak` ou `none` côté V2 anyway. Coût : LLM call Sonnet pour rien.

3. **Le book est large-cap AI par construction** : les insiders d'un NVDA / AMD vendent plus qu'ils n'achètent. Aucune valeur de threshold ne va générer beaucoup de clusters sur ces tickers. Le vrai fix de matière insider = diversifier la watchlist insider vers mid-cap où les buys sont plus courants. Pas le threshold.

### Re-evaluation post-10/06

Conditions pour re-ouvrir la décision :
- (a) après 1 mois d'observation prod wire : si 0 cluster détecté sur 30j supplémentaires → confirme la rareté est structurelle, threshold = pas la cause
- (b) si vigilance `insider_clusters_alive` passe de INFO à ALERT (= job casse ou snapshots = 0) → debug d'abord, threshold après
- (c) si un cluster MP-style apparaît (n=2-3, total $0.5-$1M) sur un ticker à thèse forte et qu'on aurait voulu le voir → preuve de la valeur du seuil plus bas

## Consequence

Future-self : si tu reviens sur cette décision après le 10/06, modifier dans `shared/edgar._classify_buy_cluster()` :

```python
# Actuel :
if n >= 3 and total_m >= 1.0:
    return "moderate"

# Si on accepte d'abaisser :
if n >= 3 and total_m >= 0.5:
    return "moderate"
```

Et ajouter un test de régression dans `tests/test_*.py` qui assert un MP-style cluster (n=3 buyers, total=$0.7M, role=director) → désormais `moderate` au lieu de `none`.

## Pourquoi un ADR pour une non-décision

Parce que sans ADR, dans 3 mois quelqu'un (toi inclus) va re-poser exactement la même question et re-faire le même diagnostic. ADR = trace que la question a été tranchée *délibérément* différée, pas oubliée.
