# Spec — Liaison positions ↔ card (une compute, deux rendus)

> Résout par construction le bug d'incohérence (page « 0,5× rouge » vs carte « 1,80× favorable »). Hérite de `QUALITY_BAR` (M1 source unique), `PLAN_REFONTE_ALERTES` (défaut calme, chip gagnée). La page positions et la position-card sont **deux altitudes du même objet**, jamais deux calculs.

## 0. Le principe keystone

> **Une seule fonction `compute_position(ticker) -> PositionView`.** La card rend la vue *complète* ; la ligne rend une *projection* de cette même vue. **Aucun recompute côté ligne.** → l'incohérence (deux ratios divergents pour le même nom) devient *impossible*, pas « à éviter ».

```
compute_position(ticker) -> PositionView   ← la seule source
        ├── render_card(PositionView)      ← profondeur (1 position)
        └── render_row(project(PositionView)) ← triage (N positions)
```

## 1. `PositionView` — l'objet calculé unique

Tous les indicateurs, calculés une fois, chacun avec son as-of/source (M1) :

- **Identité** : ticker, name, `type` (structural/priced/tactical), conv, horizon, opened/reviewed.
- **Marché (triple M1)** : qty, MV (€+%), P&L, cours (natif + as-of + staleness).
- **Asymétrie** : upside, downside, **ratio** (la SEULE — partagée), entry/partial/full/stop, position-dans-range (slider), **delta** (se comprime ?).
- **Sizing 3-way** : real / target-conv / target-edge / **binding** + cap-state.
- **Thèse (moteur #2)** : verdict (intact/érosion/invalidation/non-compute), drivers, triggers fired.
- **Consensus/fragilité** (cornerstone, quand wiré) : crowding, sensibilité-cycle, fragilité (confiance plafonnée au cycle).
- **Discipline flags** : over_cap, bias_open, …
- **Steer** : `exit_policy` + `size_action` + interdit/autorise + **chip gagnée** + raison.
- **degraded** : état fail-closed propagé (vrai si un input critique est stale).

## 2. Mapping des indicateurs par altitude (le « réfléchi »)

Chaque altitude montre ce qui **matters à cette altitude**, pas un dump.

| | LIGNE (triage glanceable, N lignes) | CARD (décision, 1 position) |
|---|---|---|
| But | « quelles lignes j'ouvre ? » | « que fais-je, et pourquoi ? » |
| Identité | ticker + micro-tag type/factor | header complet + opened/reviewed |
| Marché | MV/% + P&L (faits) | qty + MV + P&L + cours + as-of |
| Asymétrie | **slider** (état lu) + delta | upside/downside/ratio/entry/partial/full/stop |
| Steer | **chip gagnée SI gagnée** (sinon rien) | STEER **en tête** : exit_policy + size_action + interdit/autorise |
| Thèse | pastille verdict si non-intact | verdict + drivers + triggers |
| Fraîcheur | dot (stale → grisé) | bannière fail-closed + nombres dépendants marqués provisoires |
| **JAMAIS** | × indépendant, badge cycle, mur de rouge | — |

**Cycle** → en-tête book-level (« book 85% late »), retiré des lignes. **Le × rouge** → mort (le slider porte l'asymétrie honnêtement ; la carte porte le ratio décomposé).

## 3. Le steer = source unique, consommée deux fois

`position_steer.compute(PositionView) -> {exit_policy, size_action, chip, reason}`. La card l'affiche en détail (avec interdit/autorise) ; la ligne affiche **la chip** (si gagnée). **Une seule logique de steer** — la ligne ne décide jamais sa propre couleur.

## 4. Fail-closed propagé (cohérence M1)

Si `PositionView.degraded` (prix stale) :
- la **ligne** : dot stale + grisé ;
- la **card** : bannière + **les nombres dérivés du prix stale marqués provisoires** (ex. « rightsize ~-27,6%, prix stale → revalide »), jamais un chiffre net confiant sous une bannière fail-closed.

La bannière n'est pas cosmétique : elle dégrade *les nombres qui en dépendent*, dans les deux rendus.

## 5. Communication bidirectionnelle

- **Ligne → Card** : clic = deep-link `?ticker=…#position-card` (décidé : page, pas modal — les alertes doivent y router).
- **Card → Ligne** : le steer de la card = la chip de la ligne. Même refresh, même `PositionView`.
- Les deux **souscrivent au même objet + au même état de fraîcheur** : ils ne peuvent pas diverger.

## 6. Tests verrouillants (anti-incohérence)

- **M1 source unique** : tout nombre présent dans la ligne ET la card est **byte-identique** (assert — tue le 0,5× vs 1,80×).
- **chip dérivée** : `row.chip` provient de `PositionView.steer`, jamais d'un calcul de ligne (assert).
- **fail-closed propagé** : si `degraded`, ligne grisée ET nombres-card dépendants marqués provisoires (assert).
- **défaut calme** : >20% de lignes avec chip → build rouge (la table doit être majoritairement calme).
- **slider == ratio** : la position du slider et le `ratio` de la card dérivent du même upside/downside (assert).

## 7. Architecture code

```
dashboard/position_view.py
  compute_position(ticker: str) -> PositionView      # source unique, M1
  project_row(view: PositionView) -> RowView          # projection ligne (frozen)

dashboard/render.py
  render_card(view: PositionView) -> str
  render_row(row: RowView) -> str
  render_positions(book) -> str:                      # consomme N PositionView
    views = [compute_position(t) for t in book.tickers]
    rows = [project_row(v) for v in views]
    return _render_rows(rows)
```

- `PositionView` et `RowView` Pydantic frozen (`extra='forbid'`) — anti-tampering downstream.
- **Aucun recompute** côté ligne : `render_row` ne touche pas yfinance, ne calcule pas de ratio, ne dérive pas de chip.
- `position_steer.compute` consommé **une fois** dans `compute_position`, écrit dans `PositionView.steer`. Réutilise `CardInputs` / `SteerOutput` extraits en carte-décision étape 2/3 (PositionView = leur fusion + extension qty/mv/pnl).
- **Vocabulary discipline** (cf `SPEC_ALERT_VOCABULARY`) : `view.steer.chip ∈ enum STEER-act du registre`, jamais string libre.

## 8. Build sequence

1. Définir `PositionView` Pydantic frozen + `RowView` (projection).
2. Implémenter `compute_position(ticker)` : remplace les fragments épars (`_position_card` qui recompute, `render_row` qui re-derive).
3. Refactor `_position_card` pour consommer `PositionView` (extension de l'étape 5 carte-décision).
4. Refactor `render_row` pour consommer `RowView` projeté.
5. Tests verrouillants (M1 byte-identité + chip from steer + fail-closed propagé + défaut calme + slider==ratio + vocabulary discipline).
6. Wire deep-link `?ticker=…#position-card` depuis chaque ligne.

## 9. Seams à vérifier (verify-before-patch)

- `_position_card` actuel dans `dashboard/render.py` : où il recompute vs où il lit. Identifier tous les sites où la ligne re-derive un nombre que la card calcule.
- `position_steer.compute` actuel : déjà extrait (carte-décision étape 3). Confirmer qu'il prend un objet view-like, pas un dict ad-hoc.
- `CardInputs` / `SteerOutput` actuels (carte-décision étape 2/3) : `PositionView` est leur fusion + extension (ajoute champs ligne : qty/mv/pnl/price_staleness).
- `render_row` actuel : identifier tout calcul/dérivation côté ligne à migrer vers `compute_position`.

## 10. Implementation Status

- **Gravé** : 2026-06-XX (commit `__TBD__`)
- **Enrichi** : 2026-06-08 (sections architecture + build + seams)
- **Implémentation** : NON COMMENCÉE
- **Fichiers cibles** : `dashboard/position_view.py` (à créer), `dashboard/render.py` (à refactor), `tests/test_position_view.py` (à créer)
- **Audit drift** : `scripts/audit_canonical_drift.py` (à wirer)
- **Prochain step** : C7a-3 (cf TODO #102)

## 11. Le fil

> La carte est la **source de vérité + la profondeur** (steer en tête, évidence dessous, fail-closed propagé). La ligne est sa **projection calme** (chip gagnée + slider + delta + fraîcheur). Une seule compute, deux altitudes — l'incohérence devient impossible, et l'œil tombe sur les 1-2 lignes que la carte a jugées dignes d'attention. Positions et card ne s'affichent pas la même chose : elles affichent **la même vérité, à la bonne résolution.**
