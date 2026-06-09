> ⚠️ SUPERSEDED 2026-06-09 (minuit) — Ce document (canon 2-références) ET le code committé `ee4c6f6` (interp 1) sont DEUX étapes rejetées qui se contredisent. Décision tranchée : **AXE PRIX NATIF PUR** (stop/partial/full = prix décidés fixes, axe ancré sur la bande [stop, full], cost+current = marqueurs, P&L EUR en label, zéro EUR sur l'axe). NE PAS « corriger » le code vers ce canon. Réécriture complète + implémentation en attente (demain, reposé).

# Spec GAUGE — le principe canonique des jauges de position

> **Une jauge de position raconte deux questions sur la même ligne** : *« où tu visais »* (les niveaux décidés en amont — stop rouge, target_partial jaune, target_full vert) et *« où tu en es »* (ta perf actuelle depuis ton coût réel). Le 0 central gris = ton coût. Les ticks racontent ta décision, le dot raconte ton argent. Le split Closest/Beyond range les positions selon la vérité FX-invariante (`cur_native ≥ target_full_native`), pas selon l'apparence visuelle. **Ce mélange de référentiels est assumé, justifié et nommé** — c'est l'unique manière de présenter les deux questions sans mentir sur aucune.

## 0. L'idée maîtresse

Une gauge de position ne réduit pas à un seul mètre. Elle réunit **deux faits** dont l'utilisateur a besoin simultanément :

1. **Ton intention figée** : *« j'avais décidé que stop = −15%, partial = +15%, full = +30% »* — ce sont des **décisions** prises au moment de la thèse, qui ne doivent pas bouger quand le portfolio évolue.
2. **Ton état actuel** : *« je suis à +18% depuis mon coût réel »* — c'est ton **P&L EUR**, ce qui compte pour ton argent aujourd'hui.

Ces deux faits vivent dans des **référentiels différents** :
- Les niveaux décidés sont en **% depuis entry** (le prix d'appel, le point de la décision originale)
- Le P&L est en **% depuis cost** (avg_cost EUR, ton coût réel après éventuels renforcements)

**La cure naïve** (UN mètre unique) ne marche pas. Soit on cale tout sur cost (alors target_pct dérive avec le PMP et devient parfois négatif quand tu renforces au-dessus du target initial — SK Hynix : target_pct = −0.7%), soit on cale tout sur entry (alors le dot raconte « perf depuis l'appel », pas ton P&L EUR — tu perds le nombre qui compte).

**La cure juste** : on accepte les deux référentiels sur la même gauge, on les nomme, et on garantit la lecture cohérente par un **split sémantique** (Closest/Beyond) basé sur la vérité FX-invariante du dépassement (`cur_native ≥ target_full_native`).

> Les ticks (stop / partial / full) racontent ta décision (depuis entry). Le dot raconte ton argent (depuis cost). Le 0 = ton coût. Le split FX-invariant range les positions selon la réalité, pas l'apparence.

## 1. Les invariants canoniques

### 1.1 Référentiels par grandeur

| Grandeur | Référentiel | Formule | Sémantique |
|---|---|---|---|
| `cost_native` | dérivé | `avg_cost_eur / fx_rate_to_eur` (fx LIVE, un seul fx par position) | Ton coût natif au taux d'aujourd'hui — fait que `dot_pct ≡ P&L EUR` |
| `dot_pct` | depuis cost | `(cur_native − cost_native) / cost_native × 100` | **Ta perf actuelle = ton P&L EUR depuis ton coût** |
| `stop_pct` | depuis entry | `(stop_native − entry_native) / entry_native × 100` | **Le stop décidé en amont, en % depuis le prix d'appel** |
| `target_partial_pct` | depuis entry | idem | **La première target (partial) décidée en amont** |
| `target_pct` (= full) | depuis entry | idem | **Le target full décidé en amont** |

### 1.2 Le 0 central

Le tick **gris** central de la gauge représente **ton coût actuel** (cost_native). C'est ton « point de départ » au sens « depuis quand je compte ma perf ». Le dot vit à la distance signée de ce 0 (= ta perf actuelle).

### 1.3 Les ticks décidés — code couleur canonique

| Tick | Couleur | Position | Sémantique |
|---|---|---|---|
| **Stop** | **rouge** | `stop_pct` (gauche, négatif typique) | Le niveau où tu sors si ça tourne mal |
| **0** | **gris** | 0% (50% visuel, centre) | Ton coût — point de départ de la perf |
| **Target partial** | **jaune** | `target_partial_pct` (droite, positif typique) | La première prise de profit décidée |
| **Target full** | **vert** | `target_pct` (droite, plus loin) | La cible finale décidée |
| **Dot** | noir / bear / acc | `dot_pct` | Ta perf actuelle (= P&L EUR) |

Le code couleur (rouge / jaune / vert) suit la **convention de gradient de risque-rendement** : rouge = on sort en perte, jaune = première victoire (prise de profit recommandée), vert = succès complet de la thèse.

### 1.4 Le test de dépassement

**Le split Closest/Beyond utilise `cur_native ≥ target_full_native`**, pas `frac_raw ≥ 100` ni `dot_pct ≥ target_pct`. C'est :

- **FX-invariant** : ratio natif, le fx_now s'annule
- **Robuste au signe** : reste correct même si target_pct (depuis entry) est calculé différemment de dot_pct (depuis cost) — pas de division par un dénominateur qui peut devenir négatif (cf l'anti-pattern §3.4)
- **Sur target_full** (pas partial) : on parle de dépassement de la cible finale, pas de la première prise

### 1.5 La géométrie visuelle

L'axe est centré sur 0 (50% visuel = cost). La projection est symétrique :

```
ax = max(|stop_pct|, |target_pct|, |dot_pct|, 10.0)
tick_visual_pct = 50 + (level_pct / ax) × 50
```

Le 10% plancher évite un axe micro qui collerait tous les ticks au centre quand la position n'a presque pas bougé.

### 1.6 Couleurs du dot

- **bear (rouge)** si `dot_pct ≤ stop_pct` (stop cassé)
- **acc (vert)** si `dot_pct ≥ target_pct` (target full atteint visuellement)
- **neutre (noir)** sinon

Note : le dot vert ne suffit pas à classifier en Beyond — c'est le test `cur_native ≥ target_full_native` qui range. Sur SK Hynix le dot peut être visuellement sous le target full tic (+18 < +23 depuis entry) tout en étant Beyond en native (cur 2.22M > target 1.86M).

## 2. Pourquoi le mélange de référentiels est juste (et nommé)

Le mélange « dot depuis cost / ticks depuis entry » est **délibéré**, pas un accident. Il répond à trois contraintes :

1. **Le dot doit raconter ton argent** (P&L EUR). Pas perf depuis appel — l'utilisateur veut savoir combien il gagne maintenant.
2. **Les ticks doivent être stables** quand tu renforces. Si on les calcule depuis cost, ils bougent à chaque achat additionnel — pas honnête vs ta décision originale.
3. **La gauge doit être lisible côte à côte avec d'autres positions**. Si target_pct varie par ticker en fonction de l'historique des renforcements, les gauges ne sont plus comparables.

Le **test de dépassement** vit séparément dans le natif (`cur ≥ target_full`) pour ne pas dépendre du choix de référentiel d'affichage. C'est la **vérité FX-invariante** qui range, l'**affichage** est une projection lisible.

> Deux référentiels sur la même gauge ne mentent que si on prétend qu'il n'y en a qu'un. Nommés, ils racontent deux questions distinctes sans confusion.

## 3. Anti-patterns à bannir (les mensonges nommés du chemin 09/06)

### 3.1 Tout sur cost (interp 1 naïve)

`stop_pct = target_pct = (level_native − cost_native) / cost_native × 100`. Conséquence : quand tu renforces au-dessus de entry initial, cost grimpe, target_pct devient parfois négatif (cas SK Hynix : −0.7%). Le tick target finit visuellement collé au 0 — pas « le point qu'on a décidé », mais « le % vs cost actuel ». **Faux pour la gauge demandée.**

### 3.2 Tout sur entry (interp 2 naïve)

Tous les calculs (ticks + dot) depuis entry de thèse. Conséquence : le dot raconte « perf depuis l'appel », pas le P&L EUR. L'utilisateur perd le nombre qui compte vraiment (ton argent).

### 3.3 Mélange caché (5 ticks EUR mixés)

Stockage de `cost_eur` (gelé) + `stop_eur / target_eur` (flottants via fx_now) sur le même axe en prix EUR. Conséquence : le hover JS calcule `v = axmin + (axmax − axmin) × p/100` et affiche un PRIX en EUR comme s'il était un %. KLAC : axmax = 1820 EUR → hover affiche « +1820% ». **Le JS ne distingue pas les frames.**

### 3.4 Split par `frac_raw ≥ 100`

`frac_raw = dot_pct / target_pct × 100` se casse dès que `target_pct < 0` : SK Hynix avec target_pct=−0.7%, dot_pct=+18% → `frac_raw = 18 / (−0.7) × 100 = −2571%` < 100 → wrongly Closest. **Le dénominateur signé piège le test.** La vérité = `cur_native ≥ target_full_native` (FX-invariant, pas de division).

### 3.5 `hover_pct=False` (cacher sans comprendre)

Désactiver le hover pour masquer le bug d'affichage « +1820% » sans nommer la cause (mix de frames dans le JS). Le bug reste, juste invisible.

### 3.6 `cost_native` figé ou avec fx d'achat historique

`cost_native = avg_cost_eur / fx_at_purchase`. Conséquence : sur tickers FX-volatils, `dot_pct = (cur_native − cost_native) / cost_native` ne correspond plus au P&L EUR (le fx_now ne s'annule plus). On rejoue la divergence natif-vs-EUR. **`fx_now` est obligatoire**, un seul fx par position.

### 3.7 Confondre partial et full pour le test de dépassement

Le split Closest/Beyond doit utiliser `cur_native ≥ target_full_native`, **pas** `cur_native ≥ target_partial_native`. Une position qui a atteint partial mais pas full reste **dans Closest** (en route vers la cible finale). Beyond = full atteint.

## 4. Architecture

### 4.1 Helper canonique

```python
# dashboard/render.py
def _gauge_pcts_from_cost(bl: BookLine | None) -> dict[str, float | None]:
    """Calcule les % canoniques de la gauge.

    dot_pct depuis cost (≡ P&L EUR), ticks depuis entry (décisions stables).
    Returns : {cost_native, cur_native, target_native, entry_native,
               stop_pct, target_pct (full), target_partial_pct, dot_pct}
    """
```

### 4.2 Renderer canonique

```python
def _position_axis_pct(
    stop_pct, target_pct, dot_pct,
    *,
    target_partial_pct=None,  # canonique : tick jaune entre 0 et target_pct
    extra_class="",
    pnl_position_pct=None,
) -> str:
    """Gauge de position — UN SEUL renderer pour tous les panneaux.

    Tous params en %. 0 central = cost (tick gris). Stop tick rouge à stop_pct,
    target_partial tick jaune à target_partial_pct, target full tick vert à
    target_pct. Dot à dot_pct. Couleur dot : bear/acc/neutre.
    Tooltip "P&L X%" (= dot_pct ≡ P&L EUR).
    """
```

### 4.3 Code couleur CSS canonique

```css
.tbar-tick.stop      { background: var(--bear);    }  /* rouge */
.tbar-tick.entry     { background: var(--steel);   }  /* gris central = cost (label legacy "entry" conservé) */
.tbar-tick.partial   { background: var(--warn);    }  /* jaune = première prise de profit */
.tbar-tick.target    { background: var(--acc);     }  /* vert = target full = cible finale */
```

### 4.4 Callers (4)

Tous les panneaux qui affichent une gauge de position consomment `_gauge_pcts_from_cost` puis `_position_axis_pct` :

| Panneau | Localisation | Source ticker |
|---|---|---|
| Position card slider | `_position_card` ~L2570 | `inputs.book_line` |
| Book row Progress col | `_broker_one` ~L6560 | `_book_idx.get(tk)` |
| Theses panel grid | `_theses` ~L6120 | `_book_idx_th_inner.get(t["tk"])` |
| Asym CLOSEST_TO_TARGET | `_axisrow` ~L7270 | `ln` (déjà en scope) |

### 4.5 Split Closest/Beyond

```python
_beyond = [tk for tk in _axis if _axis[tk]["_cur"] >= _axis[tk]["_tgt"]]
_targets = [tk for tk in _axis if _axis[tk]["_cur"] < _axis[tk]["_tgt"]]
```

Test natif uniquement (cur ≥ target_full). Tri par ratio `_cur / _tgt` (FX-invariant).

## 5. Invariants porteurs

1. **Un seul fx par position** : `fx_rate_to_eur` (live, ~15min cron) sert pour `cost_native`. Pas de mix fx historique + fx live.
2. **Le dot ne ment jamais sur le P&L EUR** : `dot_pct = (cur_eur − avg_cost_eur) / avg_cost_eur × 100` (algébriquement équivalent à la formule en native via fx_now).
3. **Les ticks ne bougent pas avec les renforcements** : ils restent figés au % décidé en amont (depuis entry).
4. **Le test de dépassement est FX-invariant** : `cur_native ≥ target_full_native`. Aucune division par un % signé.
5. **Money-invariant L28 préservé** : aucun mix natif + EUR sur la même ligne (cost_native, stop_native, target_partial_native, target_native, cur_native sont tous natifs ; les % sont des ratios pures).
6. **Le code couleur canonique** est figé (rouge stop / gris cost / jaune partial / vert full). Aucune surface dashboard ne réinvente une autre convention de couleur pour la même information.

## 6. Tests verrouillants

- `test_gauge_cost_is_avg_cost_in_native` : `cost_native × fx_now ≈ avg_cost_eur` (cohérence du calcul)
- `test_dot_pct_equals_pnl_eur` : `dot_pct ≈ (current_eur − avg_cost_eur) / avg_cost_eur × 100`
- `test_ticks_from_entry_stable_vs_avg_cost_changes` : modifier avg_cost ne change pas stop_pct ni target_pct ni target_partial_pct
- `test_skhynix_dot_under_target_visually` : SK Hynix gauge → dot_pct (+18%) < target_pct (+23%), visuellement sous le tic vert
- `test_skhynix_classified_beyond_via_native` : `cur_native ≥ target_full_native` → ranged in Beyond
- `test_no_div_by_zero_when_target_pct_signed` : positions où target_pct est négatif ne crashent ni ne misclassifient
- `test_partial_tick_yellow_full_tick_green` : le HTML rendu contient `class="tbar-tick partial"` et `class="tbar-tick target"` aux bonnes positions
- `test_partial_under_full_when_both_present` : `target_partial_pct < target_pct` (gradient de prise de profit, jaune entre 0 et vert)

## 7. Implementation Status

- **Gravé** : 2026-06-09 (soir tard, post-7-pivots gauge ; principe final tranché par red-team Olivier)
- **Implémentation** : IMPLEMENTED — commits `9032cca` (helper + renderer + 4 callers + split FX-invariant), à compléter par le commit qui suit (tick partial jaune canonique)
- **Fichiers cibles** :
  - `dashboard/render.py` : `_gauge_pcts_from_cost`, `_position_axis_pct`, 4 callers, split Closest/Beyond, CSS classes `.tbar-tick.partial/.target/.stop/.entry`
  - `tests/test_position_axis_price.py` (existants, à enrichir avec les serrures §6 quand revisite)
- **Code mort à cleanup** : `_position_axis_price` (5 ticks EUR mélangés, plus appelé depuis commit `9032cca`), branche JS `data-axis-mode="price"` (plus de caller)
- **Audit drift** : `scripts/audit_canonical_drift.py`
- **Prochain step** : cleanup code mort, enrichir tests verrouillants §6, vérifier que la CSS canonique des ticks est définie partout (style guide du dashboard).

## 8. Le fil

> Une gauge n'est pas un seul nombre. Elle est l'arc entre deux questions : *« où tu visais »* (le passé décidé, les ticks rouge/jaune/vert) et *« où tu en es »* (le présent vécu, le dot). Forcer un seul référentiel ment dans un sens ou dans l'autre. Le principe juste accepte les deux, les ancre chacun sur son point de référence sémantique (entry pour la décision, cost pour le P&L), code les ticks en gradient rouge→gris→jaune→vert (perte→coût→première prise→cible finale), et garde la **vérité du dépassement** dans le natif FX-invariant (`cur ≥ target_full`) pour ranger les positions sans tricher. Le 0 central = ton coût, parce que c'est depuis là que tu mesures ton argent. Les ticks restent figés aux % décidés, parce que tes décisions ne doivent pas bouger avec ton PMP. Et le panneau Beyond range les positions dépassées avec la vérité native, même quand l'affichage visuel suggère « pas encore » — parce que l'affichage sert la lecture, et le rangement sert la vérité.
