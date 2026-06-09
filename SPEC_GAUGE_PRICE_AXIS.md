# Spec GAUGE PRICE AXIS — la gauge sur axe-PRIX EUR, pas axe-perf

> La gauge actuelle est un **axe-perf** (% depuis un anchor unique) — ce qui force à choisir UN anchor (avg_cost OU entry) et collisionne dès qu'on veut voir 0, perf-réelle, et cible ensemble. La cure structurelle, posée 09/06 soir : passer à un **axe-PRIX en EUR** où stop, cost, entry, target, current sont des **points** à leur vraie place, et les % deviennent des **annotations textuelles**. Plus de "0" à débattre — les repères SONT les références. Plus de collision target≈0 — cost et target sont deux points distincts étiquetés, pas un effondrement.

## 0. L'idée maîtresse

L'axe-perf en pourcentage est intrinsèquement collisionnel quand on veut trois choses sur une même gauge : « 0 », « ta perf réelle », « ta cible ». Forcer un anchor (avg_cost en cost-frame, entry en thesis-frame) revient à reconnaître que c'est **deux questions différentes** (cf décision per-panneau 09/06 commit 8d6fe8c). Mais sur une **carte de position**, l'utilisateur veut voir les trois ensemble — comment va son argent ET où est sa cible.

La résolution n'est pas un troisième anchor — c'est de **sortir de l'axe-perf et passer à l'axe-prix**. Sur un axe-prix, le « 0 » disparaît : il n'y a que des **points** (stop, cost, entry, target, current) placés à leur vraie position de prix. Le dot raconte par sa POSITION ENTRE LES REPÈRES, et les pourcentages deviennent du texte d'annotation.

> Le cadre suit la question, l'axe suit le cadre. Sur axe-prix EUR, les trois questions cohabitent sans se contredire parce qu'aucune n'a besoin d'être centrée à 0.

## 1. Pourquoi EUR (pas natif)

Le natif est **séduisant** parce qu'il est FX-clean (target posé en natif). Mais il **ment sur le P&L** : la perf réelle utilisateur c'est « combien j'ai gagné en EUR » (sa devise), pas « combien le titre a bougé en KRW ». Sur un titre à FX volatile (SK Hynix KRW, 4063.T JPY), la perf native diverge de la perf EUR — l'utilisateur veut voir son argent, pas le mouvement local.

L'EUR dissout aussi le piège `fx_at_purchase` : `cost_eur` est déjà là — c'est le **PMP roulant EUR, frozen-at-buy** (cf [[SPEC_LEDGER]] §1 + `shared/ledger_pmp.py`). Pas de conversion, pas de dilemme A/B, pas de NULL à dériver.

**Asymétrie nommée (honnête, pas un bug)** :
- `cost_eur` est **gelé** (fait EUR : tu as payé des EUR, c'est figé pour toujours dans le ledger).
- `target_eur` est **flottant** (fait natif converti live : la cible est un prix natif KRW, sa valeur EUR aujourd'hui dépend du FX du jour).
- L'un fixe, l'autre flottant **par nature, pas par négligence**. Et c'est honnête : ton résultat EUR à la cible native dépend vraiment du FX.

## 2. Repères canoniques sur l'axe (5 points)

```
│←──────────────────── axe = prix EUR ────────────────────→│
│                                                          │
stop_eur    cost_eur     entry_eur     target_eur     ●cur_eur
│              │             │              │             │
│            (gelé)        (×fx_now)     (×fx_now)     (live)
│                                                          │
[bear si cur<stop]                          [acc si cur>target]
```

| Repère | Source | Devise | Note |
|---|---|---|---|
| `stop_eur` | `BookLine.stop_price × fx_rate_to_eur` | EUR (flottant) | Niveau natif × fx_now |
| `cost_eur` | `BookLine.avg_cost_eur` | EUR (gelé) | PMP roulant frozen-at-buy, source canonique |
| `entry_eur` | `BookLine.entry_price × fx_rate_to_eur` | EUR (flottant) | Niveau natif × fx_now |
| `target_eur` | `BookLine.target_full × fx_rate_to_eur` | EUR (flottant) | Idem |
| `cur_eur` | `book.value_eur(ticker, qty=1).value.amount` (équivalent) | EUR (live) | Le dot |

(BookLine expose déjà `.stop_eur`, `.target_full_eur`, `.entry_eur`, `.current_price_eur` — properties livrées commit `ffc3286` ce soir.)

## 3. Annotations textuelles (les % comme tooltip riche)

Les pourcentages quittent l'axe et reviennent comme **étiquettes** qui racontent les deux questions :

```
Tooltip exemple SK Hynix :
  ─────────────────────────
  P&L : +18.3% depuis ton coût (cur 1254€ vs cost 1060€)
  Thèse : +46% depuis entry · target +23% · beyond +19%
  ─────────────────────────
```

Les deux frames cohabitent dans le tooltip — aucune n'est centrée. Le dot, lui, parle uniquement par sa **position sur l'axe** (entre cost et target, ou au-delà du target, etc.).

## 4. Géométrie (axe ouvert, pas symétrique-50%)

L'axe actuel `_position_axis` est centré sur `entry` (param) à 50% visuel, avec `ax = max(|stop_pct|, |target_pct|, ...) × 50%` autour. Pour passer à l'axe-prix :

- **Étendre** l'axe au range `[min_repere, max_repere]` + padding (5% par côté).
- **Stretch** linéaire : chaque prix EUR mappé à sa position visuelle proportionnelle.
- Pas de notion de "50% = zéro" — le dot tombe où il tombe sur la ligne, naturellement.

```python
def _position_axis_price(stop_eur, cost_eur, entry_eur, target_eur, cur_eur, ...):
    points = [p for p in (stop_eur, cost_eur, entry_eur, target_eur, cur_eur) if p is not None]
    p_min, p_max = min(points), max(points)
    pad = (p_max - p_min) * 0.05
    p_min -= pad; p_max += pad
    def to_visual(p):
        return (p - p_min) / (p_max - p_min) * 100.0
    # ... rendu HTML avec ticks à to_visual(stop_eur), to_visual(cost_eur), etc.
```

Le dot est `acc` si `cur_eur > target_eur`, `bear` si `cur_eur < stop_eur`, sinon noir.

## 5. Fallback (cost_eur NULL, target absent, etc.)

- Si `cost_eur` NULL (position sans avg_cost — rare) → ne pas afficher le tick cost. Les 4 autres repères suffisent.
- Si `target_eur` NULL (thèse sans target) → afficher l'axe stop-cost-entry-cur sans target tick (le ratio "beyond" disparaît).
- Si `entry_eur` NULL (position sans thèse active) → axe stop-cost-target-cur (la card affiche un blank entry).
- **fail-closed** : si moins de 2 repères + cur, ne pas rendre la gauge (return "" comme actuel).

## 6. Transition de la gauge actuelle (les 4 callers)

La gauge actuelle `_position_axis(entry, stop, target, current, pnl_position_pct)` est anchor-agnostique (cf docstring commit `ffc3286`). Le refacto introduit **une nouvelle fonction** `_position_axis_price()` qui prend les 5 repères distincts. Les 4 callers migrent vers la nouvelle :

| Caller | État actuel (09/06 soir) | État cible |
|---|---|---|
| Position card L2483 | cost-frame avg_cost EUR | **axe-prix EUR** |
| Book row Progress L6433 | thesis-frame natif | **axe-prix EUR** |
| Theses panel L6026 | thesis-frame natif | **axe-prix EUR** |
| Asym CLOSEST_TARGET L7104 | thesis-frame natif | **axe-prix EUR** |

**TOUS** les panneaux convergent vers la même gauge enrichie (5 repères au lieu de 3+anchor). Les deux questions sont alors honorées sur **chaque** gauge — plus de per-panneau distinct, le découpage cost-frame/thesis-frame DISPARAÎT au profit de la gauge unique riche.

C'est la vraie complétude post-09/06 : on a posé per-panneau parce qu'on était sur axe-perf ; sur axe-prix, le découpage n'a plus de raison d'exister, **un seul rendu pour tous les panneaux**.

## 7. Tests verrouillants

- `test_axis_renders_5_points_when_all_present` : 5 ticks visibles à leurs positions proportionnelles.
- `test_skhynix_target_not_collapsed_to_zero` : SK Hynix (cur > target en KRW) → dot à droite du target tick, badge "beyond" affiché, target tick à sa propre position (pas collé au cost).
- `test_ccj_target_above_cost` : CCJ (target_eur ≈ cost_eur en EUR à cause du PMP roulant) → les deux ticks distincts visibles, dot entre.
- `test_dot_bear_when_below_stop` : `cur_eur < stop_eur` → dot rouge.
- `test_dot_acc_when_above_target` : `cur_eur > target_eur` → dot vert.
- `test_fallback_no_target` : gauge rendue avec stop/cost/entry/cur seulement (pas de target).
- `test_money_invariant_eur_only` : aucun mix natif+EUR (assertion sur chaque tick).

## 8. Seams (verify-before-patch)

- **`fx_rate_to_eur` du jour** : doit être unique par regen pour cohérence stop_eur / entry_eur / target_eur (sinon micro-divergences inter-ticks au sein d'une même gauge). Probable déjà cohérent via `prices.fx()` cache, mais à confirmer.
- **target_eur ratio FX-invariance** : assert `cur_eur / target_eur == cur_native / target_native` (au bruit float près) — c'est le point qui rend le ratio FX-clean. Test à graver.
- **avg_cost_eur NULL** (positions VUE post-0049 si BookLine absente) : ne casse pas le rendu, juste retire le tick cost. Cf §5.
- **Coût du calcul** : 5 ticks au lieu de 3 = ~marginal sur regen. Pas de gateway call supplémentaire (tout depuis BookLine déjà chargé).
- **CSS class names** : la gauge actuelle utilise `sig-ent0` (gauge centrée sur entry). La nouvelle peut garder ou avoir une class distincte `sig-price`. Polish au moment du build.

## 9. Anti-patterns à bannir

- **Axe natif** (revenant à la cure soir 09/06 entry-frame natif) : le natif ment sur le P&L EUR. Banni — l'utilisateur veut voir son argent dans sa devise (cf §1).
- **Forcer un anchor pour "centrer" la gauge** : sur axe-prix, il n'y a plus de centre. Pas de tentation de re-poser un "0" arbitraire.
- **Mix EUR + natif sur les ticks** (même gauge) : money-invariant L28 — un seul système unitaire par gauge.
- **Annoter le tooltip en native** quand l'axe est EUR : confusion. Tooltip suit l'axe (EUR + ratio % depuis chaque référence).

## 10. Implementation Status

- **Gravé** : 2026-06-09 (soir tard, post-27-commits, design tranché par red-team Olivier)
- **Implémentation** : NOT_STARTED — refacto structurel à frais à tête reposée (cf #122)
- **Fichiers cibles** : `dashboard/render.py` (nouvelle `_position_axis_price()` + migration des 4 callers), `tests/test_position_axis_price.py` (à créer ; cf §7)
- **Audit drift** : `scripts/audit_canonical_drift.py`
- **Prochain step** : W0 = créer `_position_axis_price()` + migrer caller le plus visible (position card L2483) + test SK Hynix beyond. Garder l'ancien `_position_axis` pour les 3 autres callers transitoirement (seam additif, pas big-bang — cf [[feedback_seam_not_big_bang]]).

## 11. Le fil

> La gauge actuelle force un anchor parce qu'elle vit sur l'axe-perf. Sur l'axe-prix, **il n'y a plus d'anchor à choisir** — les repères SONT les références, le dot raconte par sa position, et les pourcentages reviennent comme annotations honnêtes des deux frames (P&L cost-frame · thèse thesis-frame) sans qu'aucun n'ait à être centré. Le « target ≈ 0 » SK Hynix disparaît parce que cost et target deviennent **deux points distincts sur la même ligne de prix**, pas un effondrement sur un zéro mal défini. EUR est la devise honnête (ton argent), avec une asymétrie acceptée : cost gelé (fait EUR), target flottant (fait natif × fx_now). Trois questions, un seul axe — c'est la cure structurelle qui ferme le débat avg_cost-vs-entry pour de bon.
