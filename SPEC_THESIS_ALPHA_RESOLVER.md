# Spec THESIS ALPHA RESOLVER — variant-perception, fx-strippé, régime-strippé (canon 2026-06-11)

> **Le track-record alpha mesure si tu bats le consensus dans la devise native de l'action — pas si tu bats le marché.** Tu poses un pari contre la foule (`your_delta = ta_target − consensus_pt`), le resolver mesure 12 mois plus tard si l'action a effectivement bougé dans ton sens vs ce que le consensus attendait. Le bêta (régime, fx) est strippé par construction. C'est l'instrument qui dit "skill de variant perception" — distinct du Brier signal (return absolu court-terme), distinct du P&L EUR (mélange devise + bêta + skill). Trois couches, trois mètres, jamais agrégées ensemble.

## 0. Décisions tranchées (gravées 11/06)

Cinq décisions structurelles sortent de la session 10-11/06 (clôture Brier J+28 + red-team Olivier sur le découpage régime-confondu). Elles sont le point de départ de toute implémentation — ne pas les re-débattre.

### A. Convert consensus_pt at asof, pas at resolve

`pt_native_asof = pt_usd × fx_asof` figé à la pose. Convertir au resolve ré-injecterait le fx-drift asof→resolve dans l'alpha (mélange skill et timing fx). **Asof fige le mètre.** Le PT capturé est une promesse posée à un instant — c'est cet instant qui détermine la conversion devise.

### B. Freeze PT à asof, pas live update

Le PT consensus capturé à asof ne s'update jamais pour ce datapoint. Si le consensus s'ajuste entre asof et resolve, on garde le PT d'origine. Sinon le resolver mesure "tu as suivi un consensus qui s'est ajusté", pas "tu as battu la foule contre laquelle tu as parié". **Le pari est posé contre une cible figée, pas mouvante.**

### C. Horizon strict 12m — thèses longues = paris annuels séquentiels

Le PT consensus a SON horizon (12m, convention FMP/Bigdata). Tu ne peux pas comparer un move 2-3 ans (supercycle uranium) à une cible 12m — deux timescales = apples-to-oranges silencieux. **L'alpha se résout à 12m strict.** Une thèse longue = des paris annuels 12m séquentiels (re-pose chaque année contre un PT 12m frais). Bonus : 3 datapoints propres au lieu d'un mal-aligné.

Le champ `horizon_months` reste utile pour la **couche MÉCANISME** (M2, invalidation_triggers qui couvrent le 2-3 ans), pas pour étirer l'alpha. **Deux couches, deux horizons.**

### D. Frame natif, fx-strippé — l'alpha mesure stock-picking, pas devise

L'alpha se calcule en **devise native de l'action**, fx-strippé. Pour une action US, l'alpha peut être positif en USD pendant que tu perds en EUR (dollar baissé). C'est attendu : la devise est un **bêta séparé** sur ta thèse-action, pas du skill. **Sinon quelqu'un dira "mais mon P&L est en EUR" et re-mélangera les mètres.**

Conséquence pratique : `pt_native_asof` (converti via fx_asof) et `price_at_resolve_native` (observé directement en native) sont les deux opérandes. Aucun EUR dans la formule alpha. Le P&L EUR vit dans une couche orthogonale.

### E. Séparation stricte des trois couches — jamais agréger ensemble

```
COUCHE 1 — Brier signal (existant)
  - Mètre : return ABSOLU (action monte/baisse vs neutre)
  - Horizon : court (~30j typique)
  - Frame : neutre régime (mais dominé par régime, cf clôture J+28)
  - Source : signaux LLM/news → predictions table

COUCHE 2 — Alpha thèse (ce resolver)
  - Mètre : return RELATIF au consensus, devise native
  - Horizon : 12m strict
  - Frame : fx-strippé, régime-strippé (par construction)
  - Source : décisions humaines de thèse → thesis_predictions table

COUCHE 3 — P&L EUR (book réel)
  - Mètre : monnaie EUR convertie via fx live
  - Horizon : continu
  - Frame : full bêta (régime + fx + sizing + timing)
  - Source : transactions → positions
```

**Aucune agrégation cross-couche.** Mélanger Brier signal et alpha thèse dans un même indicateur = la même classe de mensonge que la gauge 2-référentiels d'hier (mètres incompatibles = signe inversé silencieux). À graver en gras dans toute exposition du resolver.

## 1. Le principe en une phrase

> Tu poses un pari (`your_delta_native_pct = (your_target − pt_native_asof) / price_at_asof`) contre le consensus figé à asof, et 12 mois plus tard le resolver mesure `alpha_realized = (price_at_resolve − pt_native_asof) / price_at_asof`. Si `sign(alpha_realized) == sign(your_delta)`, ton call était directionnellement juste. La magnitude pondère par confiance pour un Brier-type score. Le bêta de marché et le fx sont strippés par construction parce que tout est en native et tout est référencé au même `price_at_asof`.

## 2. Architecture canonique

### 2.1 Helper convert : `convert_consensus_pt_to_native(consensus_ref, fx_at_asof) -> float`

```python
# shared/thesis_alpha.py
def convert_consensus_pt_to_native(
    consensus_ref: dict,      # {pt, median, currency, asof}
    fx_at_asof: float,        # fx (consensus.currency → ticker.native_currency) at asof
    asof: date,
) -> dict:
    """Convert PT consensus → devise native du ticker, FIGÉE à asof.

    Décisions A + D : asof = moment de la pose, native = devise de l'action.

    Returns:
        {pt_native: float, median_native: float, fx_at_asof: float, asof: date}
        Si consensus_ref.currency == ticker.native_currency : fx_at_asof = 1.0, no-op.
    """
```

### 2.2 Table append-only : `thesis_predictions`

Migration alembic, schéma append-only L26 (jamais UPDATE/DELETE sur une ligne posée, comme `transactions`).

```sql
CREATE TABLE thesis_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Pose (asof) — figé pour toujours
    ticker TEXT NOT NULL,
    asof DATE NOT NULL,                       -- date de pose
    asof_price_native REAL NOT NULL,          -- prix à la pose, devise native
    native_currency TEXT NOT NULL,            -- devise du ticker (EUR, USD, JPY, KRW)
    pt_consensus_raw REAL NOT NULL,           -- PT brut tel que captured (typiquement USD)
    pt_consensus_currency TEXT NOT NULL,      -- devise du PT (USD typiquement)
    pt_native_asof REAL NOT NULL,             -- pt converti en native @ fx_asof (décision A)
    fx_at_asof REAL NOT NULL,                 -- fx utilisé pour la conversion (figé)
    your_target_native REAL NOT NULL,         -- ta cible (full ou partial selon contexte)
    your_delta_native_pct REAL NOT NULL,      -- (your_target - pt_native_asof) / asof_price_native × 100
    confidence REAL,                          -- ta confiance 0-1 (optionnel, pour pondération Brier-type)
    thesis_summary TEXT NOT NULL,             -- 1 ligne narrative du pari (le pourquoi)

    -- Resolution (à 12m de asof) — rempli au resolve, jamais avant
    resolve_due_date DATE NOT NULL,           -- asof + 12 months strict (décision C)
    resolved_at DATETIME,                     -- timestamp de la résolution
    resolve_price_native REAL,                -- prix observé à resolve_due_date
    alpha_realized_pct REAL,                  -- (resolve_price - pt_native_asof) / asof_price_native × 100
    direction_correct INTEGER,                -- 1 si sign(alpha_realized) == sign(your_delta), 0 sinon, NULL si neutre
    magnitude_score REAL,                     -- Brier-type score pondéré (à définir §3)

    -- Audit
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source TEXT,                              -- 'sweep_133' / 'manual' / etc.
    notes TEXT,

    UNIQUE(ticker, asof, your_target_native)  -- pas de pose dupliquée
);
```

**INVARIANTS L26** : jamais UPDATE sur (asof, asof_price_native, pt_native_asof, your_target_native, your_delta_native_pct). Le resolver ne peut écrire QUE dans les colonnes resolve_*. Trigger SQL ou Pydantic.

### 2.3 Resolver job : `resolve_due_thesis_predictions()`

Cron daily ou weekly. Pour chaque ligne où `resolve_due_date <= today AND resolved_at IS NULL` :

1. Fetch `resolve_price_native` via `shared.prices.get_price_on_date(ticker, resolve_due_date)`
   - Fail-closed si pas de prix dispo (weekend, halted, delisted) → re-essayer J+1 jusqu'à 5 jours, ensuite log error et abandon
2. Compute `alpha_realized_pct = (resolve_price_native - pt_native_asof) / asof_price_native × 100`
3. Compute `direction_correct` :
   - `sign(alpha_realized) == sign(your_delta_native_pct)` → 1
   - signes opposés → 0
   - `|alpha_realized| < ε` (≈ 1%) → NULL (neutre, exclu agrégation comme Brier signal)
4. Compute `magnitude_score` (cf §3 formule)
5. UPDATE row WITH (resolved_at=now, resolve_price_native, alpha_realized_pct, direction_correct, magnitude_score)

### 2.4 Aggregator honnête : `compute_alpha_track_record()`

```python
# scripts/post_resolution_alpha_report.py
def compute_alpha_track_record(min_n: int = 30) -> dict:
    """Verdict alpha skill, fail-closed L19 si N insuffisant.

    Returns dict avec :
    - n_resolved, n_scored (exclus neutres)
    - hit_rate (% direction_correct=1 sur scorés)
    - mean_alpha (en native_pct moyen, attention : pas comparable cross-ticker)
    - n_effective (ajusté corrélation L22 entre tickers, cluster, période)
    - ci_95_bootstrap (sur le hit_rate ET le magnitude_score)
    - verdict : 'insufficient_n' / 'no_skill_detected' / 'skill_detected' / 'anti_skill_detected'

    Décision E gravée : NE JAMAIS agréger avec Brier signal ou P&L EUR.
    Si caller veut un mélange, refuser et expliquer.
    """
```

**L19 fail-closed** : si `n_effective < min_n` ou si CI 95% englobe la baseline → `verdict = 'insufficient_n'`, pas un nombre fabriqué. Le caller affiche "verdict crédible à venir, N=X/min_n" — jamais une fausse confiance.

## 3. Formule alpha + magnitude_score

### 3.1 Alpha directionnel

```
your_delta_native_pct  = (your_target_native − pt_native_asof) / asof_price_native × 100
alpha_realized_pct     = (resolve_price_native − pt_native_asof) / asof_price_native × 100

direction_correct = 1 si sign(alpha_realized) == sign(your_delta) et |alpha_realized| ≥ ε_neutre (typique 1%)
                  = 0 si sign opposé et |alpha_realized| ≥ ε_neutre
                  = NULL si |alpha_realized| < ε_neutre (zone neutre, exclu agrégation)
```

### 3.2 Magnitude score (Brier-type pondéré confiance)

```
# Si confidence est posée à la pose :
prob_you_assigned = 0.5 + (confidence × 0.5 × sign(your_delta))
                  # ex. confidence=0.8 + delta positif → prob=0.9 que action bat consensus
outcome_realized  = 1 si alpha_realized > +ε_neutre
                  = 0 si alpha_realized < -ε_neutre
                  = NULL sinon (exclu)
magnitude_score   = (prob_you_assigned − outcome_realized) ² si outcome_realized non NULL
                  # standard Brier, mais sur alpha-direction, pas return-direction
                  # baseline no-skill = 0.25 (prob=0.5 sur tout)

# Si confidence absente :
magnitude_score = NULL → contribue à hit_rate mais pas au Brier
```

**Convention ε_neutre** : 1% en native. Adaptable par classe d'actif si nécessaire mais documenté.

## 4. Fail-closed (cas-bord)

| Cas | Comportement |
|---|---|
| PT consensus manquant à asof | **Ne pas poser la ligne.** Pas de pari sans benchmark. Log skip. |
| fx_at_asof indisponible | Idem — fail-closed L15, jamais de fallback fx=1.0 silencieux (cf bug CCJ fx_at_purchase=1.0 du 10/06). |
| `resolve_price_native` indisponible à resolve_due_date | Retry J+1 jusqu'à J+5. Ensuite log error, laisser `resolved_at=NULL`, surface dans monitor. |
| Ticker delisted entre asof et resolve | `resolved_at=now`, `alpha_realized_pct=NULL`, `notes='delisted'`. Exclu agrégation. |
| Position vendue avant resolve_due_date | **Le pari reste résolu à 12m** — l'alpha mesure la prédiction, pas l'exécution P&L. Ne pas court-circuiter par l'event de vente. |
| Re-pose d'une thèse identique (même target_native) à un asof+1 | Ligne SÉPARÉE (les datapoints sont des paris annuels séquentiels, décision C). |
| Multi-target (partial + full) sur une même thèse | Lignes SÉPARÉES (1 par target_native). Évite la confusion "quel target a battu". |

## 5. Tests verrouillants

Implémentés dans `tests/test_thesis_alpha_resolver.py` (à créer post-spec) :

- **A1** test_convert_at_asof_freezes_fx : pose à asof avec fx_asof=1.055, fx live=1.10 → pt_native_asof reste basé sur 1.055.
- **A2** test_convert_no_op_when_currencies_match : consensus EUR + ticker EUR → pt_native_asof = pt_consensus_raw, fx_at_asof=1.0.
- **B1** test_pt_consensus_frozen_post_pose : update consensus_ref dans portfolio_rules.yaml après la pose → la ligne thesis_predictions ne bouge pas.
- **C1** test_resolve_at_12m_strict : asof=2026-06-11 → resolve_due_date=2027-06-11 exact.
- **C2** test_long_thesis_requires_yearly_reposes : thèse "supercycle 2-3 ans" doit produire 3 lignes annuelles séquentielles, pas 1 ligne 36m.
- **D1** test_alpha_native_strippe_fx : asof_price=100 USD, resolve_price=110 USD, pt_native_asof=105 → alpha=+5%. Indépendant du fx EUR/USD entre asof et resolve.
- **D2** test_alpha_not_pnl_eur : action US en gain USD pendant que EUR/USD a baissé → alpha positif (le pari skill est juste), P&L EUR séparé (négatif possible). Les deux coexistent honnêtement.
- **E1** test_aggregator_refuses_brier_signal_mix : tenter de combiner alpha avec Brier signal → ValueError("layers must be aggregated separately").
- **E2** test_layers_documented_in_aggregator_output : le verdict dict contient explicitement `layer: "thesis_alpha"` et un `not_compatible_with: ["brier_signal", "pnl_eur"]`.
- **F1** test_fail_closed_when_pt_missing : pose sans PT consensus → no-op, log skip, table inchangée.
- **F2** test_fail_closed_when_fx_missing : pose avec fx_at_asof=None → no-op, log skip.
- **F3** test_aggregator_returns_insufficient_n_below_threshold : n_effective=5 → verdict='insufficient_n', pas de point estimate.
- **G1** test_append_only_resolve_columns_only : tenter UPDATE sur asof_price_native → SQL trigger / Pydantic raise. Seules `resolved_at`, `resolve_price_native`, `alpha_realized_pct`, `direction_correct`, `magnitude_score` sont mutables post-insert.

## 6. Anti-patterns (le chemin à ne pas reprendre)

### 6.1 Convert PT au resolve, pas à asof

Réinjecte le fx-drift asof→resolve dans l'alpha. L'alpha mesure alors un mélange skill stock-picking + skill timing fx. **Banni** : Décision A.

### 6.2 Live-update PT consensus

Mesure "tu as suivi le consensus", pas "tu as battu la foule contre laquelle tu as parié". Le PT consensus est une promesse posée par les analystes à un instant donné — c'est contre cet instant que tu paries. **Banni** : Décision B.

### 6.3 Étirer horizon thèse (3 ans) contre PT 12m

Apples-to-oranges. Le PT consensus mesure 12m, étirer la résolution à 36m mélange deux timescales. **Banni** : Décision C. Une thèse longue = paris annuels séquentiels.

### 6.4 Calculer alpha en EUR

Mélange skill stock-picking et exposition devise. L'alpha cherche à isoler le skill, pas à le polluer. **Banni** : Décision D.

### 6.5 Agréger alpha + Brier signal dans un même indicateur

Mètres incompatibles (relatif vs absolu, 12m vs court, fx-strippé vs régime-confondu). Produit la même classe de mensonge silencieux que la gauge 2-référentiels d'hier. **Banni** : Décision E.

### 6.6 Conclure le skill sur N petit dans un seul régime

Le piège chopé en direct le 10-11/06 sur le Brier signal J+28 : "perma-bear détecté" sur N=53 mono-régime = artefact, pas finding. L'aggregator alpha est verrouillé fail-closed L19 jusqu'à N_effective ≥ 30 ET CI sortant strictement de baseline. **Banni** par construction de l'agrégateur.

### 6.7 Court-circuiter la résolution par l'event de vente

Si tu vends la position avant resolve_due_date, le pari reste résolu à 12m. L'alpha mesure la prédiction directionnelle, pas l'exécution. Court-circuiter masquerait les paris qu'on aurait dû tenir et qui auraient battu le consensus. **Banni** : Fail-closed §4.

### 6.8 Pose sans PT consensus ("ma conviction tout court")

Sans benchmark, pas de variant-perception possible — c'est juste un return absolu. Une pose alpha exige un PT consensus de référence. Si absent, log skip et la décision reste qualitative (registre sweep markdown, pas thesis_predictions). **Banni** : Fail-closed §4.

## 7. Implementation Status

- **Gravé** : 2026-06-11 (canon post-clôture Brier J+28 + red-team séparation régime/biais)
- **Implémentation** : **NOT_STARTED** (banner SUPERSEDED retiré dès la première implémentation)
- **Pré-conditions déjà acquises** :
  - `ConsensusRef.currency` obligatoire (e090bb9, 10/06)
  - `portfolio_rules.yaml` tagged `currency: USD` sur 11 lignes
  - Tests verrouillants currency : `test_consensus_ref_currency_required`, `_invalid_rejected`
- **À livrer** :
  - `shared/thesis_alpha.py` : helper convert + helpers Brier-type magnitude
  - `migrations/0051_thesis_predictions.sql` : table append-only L26 + triggers immutabilité
  - `shared/storage.py` : `insert_thesis_prediction()` + `get_due_thesis_predictions()` + `update_thesis_resolve_fields()` (writer-only sur colonnes resolve)
  - `bot/jobs/thesis_alpha_resolver.py` : cron daily/weekly resolver
  - `scripts/post_resolution_alpha_report.py` : aggregator avec N_effective + CI bootstrap + verdict fail-closed L19
  - `tests/test_thesis_alpha_resolver.py` : suite §5 (~15 tests)
- **Backfill SK + CCJ** : posées dans `docs/sweep_targets_2026-06.md` le 10/06. À ingérer dans `thesis_predictions` table en première écriture post-migration (asof=2026-06-10, resolve_due_date=2027-06-10).
- **Prochain step** : implémenter dans cet ordre : (1) helper `convert_consensus_pt_to_native`, (2) migration table, (3) writer storage, (4) resolver job, (5) aggregator + tests. Retirer le banner SUPERSEDED en tête de SPEC dans le commit final.
- **Timing attendu du premier verdict** : 2027-06-10 + ~30 paris accumulés = pas avant fin 2027 / début 2028. C'est L13 — patience instrumentée, pas gratification. L'instrument se monte maintenant pour qu'il accumule honnêtement.

## 8. Le fil

> Le Brier signal mesure des intuitions court-terme dans le régime de l'instant. Le P&L EUR mesure l'argent total mélangé. L'**alpha thèse** isole une chose et une seule : ton skill de stock-picking contre la foule, dans la devise de l'action, sur l'horizon où la foule a parié elle aussi (12m). Pas plus. Si tu bats régulièrement le consensus en native sur 12m, tu as un skill — indépendamment du régime de marché, indépendamment du fx, indépendamment de combien tu as taillé tes positions. C'est le mètre qui ne ment pas parce qu'il ne prétend mesurer qu'une seule chose. **Trois couches, trois mètres, jamais mélangées.** Le payoff est dans 12-18 mois ; l'instrument se monte aujourd'hui.
