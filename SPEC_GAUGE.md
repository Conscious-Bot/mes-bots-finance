# Spec GAUGE — axe-prix natif pur (canon final 2026-06-09)

> **Une gauge de position est un axe-PRIX en native currency** sur lequel vivent les 5 marqueurs d'une thèse (stop / partial / full décidés + cost / current). Le prix est l'unité, pas un ratio — il n'a pas besoin de choisir une référence, donc il ne peut pas mentir « dans un sens ou dans l'autre ». Les niveaux décidés restent à leurs prix fixes (jamais négatifs, jamais glissants), le marqueur cost se place honnêtement (à droite des cibles si tu as moyenné au-delà = signal-discipline), et le **P&L EUR vit dans le label texte, pas dans la géométrie**.

## 0. Décisions tranchées (gravées 09/06 après 7 pivots)

Six **décisions structurelles** et trois **micro-décisions** sortent du chemin de ce soir. Elles sont le point de départ de toute implémentation — ne pas les re-débattre, les **respecter à la lettre**.

### Les six décisions

1. **Axe ancré sur la bande décidée `[stop_native, full_native]` — fixe, stable, pas adaptatif.** L'axe adaptatif sur `[min, max]` re-redimensionne à chaque regen (jitter), et un seul outlier (AMD cur à +188%, position stoppée) écrase l'action in-band dans un sliver. La bande décidée NE BOUGE PAS — c'est ton playbook. Marqueurs hors-bande (cost > full, dot beyond) → **lane overflow compressée + chevron** (‹ / ›), pas un clamp dur (clamp = bug d'origine « dot épinglé à 100% au-dessus du target »).

2. **`cost > full` = feature, pas bug.** Quand tu as moyenné au-delà de tes propres cibles, le marqueur cost part dans l'overflow droit avec un style « stale » (opacité réduite, dashed). C'est ton signal-discipline : « ces cibles sont périmées, re-décide ». Ne pas masquer, **styliser**.

3. **Séparation EUR / natif = invariant dur + test verrou.** Le natif vit UNIQUEMENT sur l'axe (positions, ticks, dot, hover prix). L'EUR vit UNIQUEMENT dans le texte du tooltip (P&L, cost€, cur€). Jamais co-plottés — c'est le fantôme historique §6.3 (mix EUR : cost gelé + target via fx_now sur le même axe → hover « +1820% »). **Test gate** : assert que toute coordonnée d'axe est native, assert zéro symbole € dans le calcul de position visuelle.

4. **Diffusion L29 en un seul mouvement.** Les 4 callers du dashboard (position card / book row / theses panel / asym CLOSEST_TO_TARGET) + le JS hover basculent en `price-native` **ensemble**. Aucune gauge laissée sur l'ancien renderer % (sinon mode-mixte = mensonge latent). Et **suppression** dans le même commit des helpers morts : `_position_axis`, `_position_axis_pct`, `_gauge_pcts_from_cost`, ancien `_position_axis_price` (5 ticks EUR mélangés).

5. **Fail-closed cibles manquantes (L15).** Pas de `full_native` → pas de bande → rendu dégradé honnête (cost + current + tooltip « pas de cibles définies »), **jamais fabriquer une bande**. Si `stop_native` manquant : même règle (pas de borne gauche = pas de bande, dégradé). La gauge dit « je ne sais pas » plutôt que d'inventer.

6. **Sémantique précise : spatial = P&L natif ABSOLU, le % est un label.** La distance visuelle dot ↔ cost ∝ `(cur_native − cost_native)` en **monnaie native absolue**, pas en %. Cette distance n'est **PAS comparable entre lignes** (devises différentes, échelles de prix différentes). Le % vit dans le label texte. La SPEC ne prétend jamais que l'écart visuel dot ↔ cost est comparable d'une position à l'autre.

### Les trois micro-décisions

A. **Cost marqueur = caret/triangle SOUS la ligne**, pas un tick sur la ligne. Sinon il fusionne avec le dot quand P&L≈0. Distinct visuellement, lisible même au croisement.

B. **Hover JS = payload `{prix} {currency}`, jamais de % nu.** Verrou anti « +1820% » (bug 09/06 23h+ où axmax EUR était interprété comme % par le JS legacy). Le hover lit `data-axmin` / `data-axmax` en native + `data-currency` et affiche `"2,215,000 KRW"` à la position du curseur.

C. **Purge toute mention « 0 central » dans le canon.** Il n'y a pas de zéro en espace prix — c'est un axe absolu de prix natif, pas un signed-pct. Les anti-patterns interp 1 (% depuis cost) et interp 2 (2-références mélangées) sont historiques, nommés §6 mais bannis du canon actif.

## 1. Le principe en une phrase

> Sur l'axe prix natif, **les cibles sont fixes** (elles ne bougent pas avec ton PMP), **le coût est honnête** (il se place où il est, même au-delà des cibles si tu as moyenné trop haut), **le current raconte le prix réel** (pas un %), et **le P&L EUR est l'étiquette de l'argent** (séparée de la géométrie, parce que la géométrie est en native).

## 2. Architecture canonique

### 2.1 Helper unique : `_gauge_prices_native(BookLine)`

```python
# dashboard/render.py
def _gauge_prices_native(bl: BookLine | None) -> dict | None:
    """Extrait les 5 prix natifs canoniques + meta d'une position.

    Returns None si bl absent ou data insuffisante. Si stop OU full
    manque : retourne {dégradé: True} avec cost+cur seulement
    (fail-closed L15).

    Returns dict :
        currency       : str    (ex. "KRW", "USD", "EUR")
        stop_native    : float | None
        partial_native : float | None  (target_partial, optionnel)
        full_native    : float | None  (target_full)
        cost_native    : float          (avg_cost_eur / fx_now)
        cur_native     : float          (last_price_native)
        cost_eur       : float          (label P&L)
        cur_eur        : float          (label)
        pnl_eur_pct    : float          (label : (cur - cost) / cost × 100)
        has_band       : bool           (stop et full présents = bande définie)
    """
```

### 2.2 Renderer unique : `_position_axis_price(prices, *, extra_class="")`

Prend le dict produit par `_gauge_prices_native` et rend le HTML. Géométrie :

- **Bande visuelle [10%, 90%]** = `[stop_native, full_native]` mappé linéairement (in-band).
- **Lane overflow gauche [0%, 10%]** = compression log/sqrt pour valeurs `< stop_native` (ex. dot bear, ou autre).
- **Lane overflow droite [90%, 100%]** = compression log/sqrt pour valeurs `> full_native` (cost stale, dot beyond).
- **Chevrons** `‹` et `›` aux bornes 10% / 90% si une valeur tombe dans une lane overflow.
- **Si `has_band = False`** : pas de bande, fail-closed (rendu minimal cost + cur + label « pas de cibles définies »).

### 2.3 Marqueurs canoniques (5)

| Élément | Forme | Couleur | Sémantique | Notes |
|---|---|---|---|---|
| **Stop** | Tick vertical fluo | `#ff1744` (rouge) + glow | Prix décidé bornant la bande gauche | Fixe |
| **Partial** | Tick vertical fluo | `#ffd400` (jaune) + glow | Première prise de profit décidée | Fixe, optionnel |
| **Full** | Tick vertical fluo | `#00e676` (vert) + glow | Cible pleine décidée | Fixe, borne droite de la bande |
| **Cost** | Caret/triangle SOUS la ligne | gris (--steel) ; **dashed + opacity 0.6** si overflow | Ton coût natif réel | Mobile (renforcements) |
| **Current** | Dot noir sur la ligne | `var(--ink)` (neutre) ; `bear` si < stop ; `acc` si ≥ full | Prix actuel | Mobile (cours) |

### 2.4 Tooltip & label

**Tooltip principal (`title`)** : un texte unique avec le P&L EUR et les prix de référence en native :

```
P&L +18.3% EUR · cost 1060€ (≈1.87M KRW) · cur 1255€ (2.22M KRW)
```

**Hover continu (JS)** : prix natif à la position du curseur (cf §0 micro-décision B).

### 2.5 Beyond / Closest — split canonique

Le rangement Closest/Beyond utilise la **même comparaison que le visuel** :

```python
is_beyond = cur_native is not None and full_native is not None and cur_native >= full_native
```

Visuel ET classement coïncident **par construction** (même mètre, même axe). Le panneau « Closest to target » sous-titre `cur < full_native` ; le panneau « Beyond target » sous-titre `cur ≥ full_native`. **AMD** (cur < full_native mais dot visuellement à droite dans l'ancien interp 1) tombe désormais clairement à gauche du tick vert et range correctement dans Closest. **SK Hynix** (cur > full_native) tombe à droite et range dans Beyond.

### 2.6 Callers (4) — bascule synchrone

| Panneau | Localisation | Source BookLine |
|---|---|---|
| Position card slider | `_position_card` | `inputs.book_line` |
| Book row Progress col | `_broker_one` | `_book_idx.get(tk)` |
| Theses panel grid | `_theses` | `_book_idx_th_inner.get(t["tk"])` |
| Asym CLOSEST_TO_TARGET | `_axisrow` | `ln` (déjà en scope) |

**Diffusion atomique** (décision §0-4) : les 4 callers + le JS hover basculent dans le même commit. Aucun ne reste sur les anciens helpers.

### 2.7 JS hover canonique

```js
// data-axmin/axmax en native, data-currency = code ISO
function fmtNative(v, currency) {
    // ex. 1234567 KRW → "1,234,567 KRW"
    return v.toLocaleString('fr-FR', { maximumFractionDigits: 2 }) + ' ' + currency;
}
```

Pas de format `+X.X%` sur les data-attrs prix. Le `%` reste dans le `title` (label P&L), pas dans la lecture position-axe.

## 3. CSS canonique

```css
.tbar-tick.stop    { background:#ff1744; box-shadow:0 0 4px rgba(255,23,68,.55); ... }
.tbar-tick.partial { background:#ffd400; box-shadow:0 0 4px rgba(255,212,0,.55); ... }
.tbar-tick.target  { background:#00e676; box-shadow:0 0 4px rgba(0,230,118,.55); ... }

/* Cost marqueur : caret SOUS la ligne (micro-décision A) */
.tbar-cost-caret {
    position:absolute; bottom:-4px;
    border-left:4px solid transparent;
    border-right:4px solid transparent;
    border-bottom:6px solid var(--steel);
    transform: translateX(-50%);
}
.tbar-cost-caret.stale {
    /* DÉVIATION code : `border-bottom-style:dashed` ne rend pas sur un triangle
       CSS border-bottom (la "bordure" est l'aire pleine du triangle, pas un
       trait). Substitut équivalent en lisibilité : opacity .5 + warn color. */
    opacity:.5; border-bottom-color:var(--warn);
}

/* Overflow chevrons */
.tbar-chevron-left, .tbar-chevron-right {
    position:absolute; top:50%; transform:translateY(-50%);
    color:var(--steel); font-size:10px; opacity:.7;
}
.tbar-chevron-left { left:1px; } .tbar-chevron-right { right:1px; }
```

## 4. Fail-closed (cibles manquantes — décision §0-5)

| `stop_native` | `full_native` | Rendu |
|---|---|---|
| ✓ | ✓ | Gauge complète avec bande [stop, full] |
| ✗ | ✓ | ⚠ KNOWN-GAP (cf note) — *idéal SPEC* : cur + cost + full visible, message hover « stop non défini » |
| ✓ | ✗ | ⚠ KNOWN-GAP (cf note) — *idéal SPEC* : cur + cost + stop visible, message hover « target non défini » |
| ✗ | ✗ | Minimal : cur + cost seulement, label « pas de cibles définies » |

**Jamais** synthétiser des bornes manquantes (pas de fallback à `cur ± 10%` ou autre). La gauge dit honnêtement ce qu'elle ne sait pas.

**# KNOWN-GAP impl actuelle** : `_position_axis_price` rend la **bande complète** (row 1) OU le **degraded binaire** (cur + cost seuls, classe `.degraded`) — les **rows 2-3** (borne unique présente : full sans stop, ou stop sans full) ne sont **pas rendues distinctement**, elles retombent dans le même degraded binaire que row 4. Anchor géométrique indéfini sans bande [stop, full] : pas de mappage canonique de la borne unique sur l'axe. Cas rare en pratique (les thèses posent stop et full ensemble). Cf `# KNOWN-GAP:` du docstring helper. À traiter quand surface, verrouillé par `test_renderer_fail_closed_when_full_missing_degraded_html`.

## 5. Tests verrouillants

Implémentés dans `tests/test_gauge_price_native.py` (21 tests, commit `8d9fd76`) :

- **H1-H4** helper (BL → dict) — fail-closed L15 + single-source L27
- **R1-R9** renderer (dict → HTML) — géométrie bande [10,90], overflow rationnel, séparation EUR-natif, hover payload prix-natif
- **C1-C6** scénarios end-to-end (BL → HTML) sur cas réalistes (SK Hynix KRW, AMD USD, 6857.T JPY, split Beyond/Closest)
- **B1-B2** verrous structurels (JS hover inset `(p-10)/80` source-grep ; KNOWN-GAP §4 documenté en source)

**Pivots** :
- H1 `test_helper_single_source_cur_eur_from_native_x_fx_never_from_eur_attr` — verrouille la cure fork rebirth via attribut piège `current_price_eur=99999` ignoré par construction
- C5 `test_no_negative_left_anywhere_on_realistic_cases` — verrouille frontalement le bug d'origine (partial négatif interp 1) sur 7 cas du book, couvre les 3 branches de `to_v` (in-band, overflow gauche AMD, overflow droit SK Hynix)

**Contrat détaillé = docstrings des tests, source unique.** Cette section pointe ; elle ne duplique pas (anti-L1 : la SPEC ne peut pas dériver des noms réels).

## 6. Anti-patterns historiques (le chemin parcouru, à ne pas refaire)

### 6.1 Tout sur cost (interp 1)

`stop_pct = (level − cost)/cost × 100`. Casse le **signe** des cibles quand tu renforces au-delà : SK Hynix target_pct = −0.65%, 6857.T partial à gauche du 0, AMD stop à droite du 0. Visuel devient incohérent (« prise de profit à perte »). **Banni** : l'axe prix natif élimine ce piège puisque les prix décidés sont fixes.

### 6.2 Tout sur entry / 2-références (interp 2)

Ticks depuis entry (stables) + dot depuis cost (P&L EUR). Casse le **classement** : visuel et test natif divergent (SK dot sous tick mais classé Beyond, AMD dot au-dessus tick mais classé Closest). **Banni** : l'axe prix natif unifie visuel et classement par construction.

### 6.3 Mélange caché (5 ticks EUR mixés)

`cost_eur` gelé + `stop_eur / target_eur` flottants via `fx_now` sur le même axe en EUR. Le JS hover affiche `+1820%` quand `axmax = 1820 EUR` parce qu'il interprète les data-attrs prix comme des %. **Banni** : §0-3 séparation EUR/natif stricte, le natif est sur l'axe, l'EUR uniquement dans le texte tooltip.

### 6.4 Axe adaptatif `[min, max]` + padding

L'axe se redimensionne à chaque regen et un outlier compresse tout le reste. **Banni** : §0-1 bande fixe `[stop, full]` + lanes overflow.

### 6.5 Clamp dur des marqueurs hors-bande

`tick_v = max(0, min(100, ...))` qui épingle dot à 100% quand cur dépasse l'axe. Perd l'info « à quel point au-delà ». **Banni** : §0-1 lanes overflow + chevron, pas de clamp.

### 6.6 Synthèse de bornes manquantes

Fabriquer `stop = cur × 0.85` ou `target = cur × 1.20` quand la thèse n'a pas défini les bornes. **Banni** : §0-5 fail-closed, la gauge dit « pas de cibles » plutôt que d'inventer.

### 6.7 `hover_pct=False` (cacher sans comprendre)

Désactiver le hover pour masquer le bug d'affichage sans nommer la cause. **Banni** : §0-3-B verrou hover prix natif.

### 6.8 Confondre partial et full pour le test Beyond

Beyond = `cur ≥ full`, jamais `cur ≥ partial`. Atteindre partial ne range pas en Beyond — c'est encore dans la bande, en route vers full.

## 7. Implementation Status

- **Gravé** : 2026-06-09 (canon final post-7-pivots, décisions tranchées §0)
- **Implémentation** : **IMPLEMENTED** (2026-06-10)
- **Étapes livrées** :
  - Étape 1 (`0e9258b`) : helper `_gauge_prices_native` + renderer `_position_axis_price` refonte + CSS caret/chevrons (non câblé)
  - Étape 2 (`99451bc`) : bascule atomique 4 callers + asym `_axis` re-sourcé BookLine (cure fork live↔cron) + JS hover géométrie inverse + suppression code mort (`_position_axis`, `_position_axis_pct`, `_gauge_pcts_from_cost`, ancien renderer EUR, branche JS `mode==='price'` morte, `fmtEur` orphelin)
  - Étape 4.1 (`8d9fd76`) : tests verrouillants §5 — 21 tests qui mordent, dont 2 pivots (H1 fork rebirth via `current_price_eur`, C5 no-negative-left frontal)
- **Fichiers livrés** :
  - `dashboard/render.py` : `_gauge_prices_native` (L338+), `_position_axis_price` (L386+), 4 callers basculés (position card / theses / book row / asym `_axisrow`), JS hover canonique géométrie inverse `(p-10)/80`
  - `dashboard/_styles.py` : CSS `.tbar-cost-caret` (+ `.stale` déviation §3 documentée), `.tbar-chevron-{left,right}`, `.tbar-tick.{stop,partial,target}` fluo + glow
  - `tests/test_gauge_price_native.py` : suite §5 complète (21 tests, helper/renderer séparés)
  - `scripts/smoke_gauge_step2.py` : smoke gate runtime (parse HTML rendu, 3 invariants split/visuel)
- **Audit drift** : `scripts/audit_canonical_drift.py`
- **Reste à boucler** :
  - **#121** (re-source KPIs theses panel L5936 sur BookLine cron) — dette de cohérence two-source côté KPI (pas gauge), ~30min
  - **#133** sweep humain cibles figées + full SK Hynix (cf [[L30]] LESSONS) — décisions a/b/c par jugement, jamais auto-recompute
  - **#134** monitor `stale_target` via `docs/templates/monitor_pattern.md` (3e monitor du gabarit, trigger dégradation)
  - **L30 expansion complète** doctrine (post-#133 pour les seuils proposés sur cas observés, pas inventés)

## 8. Le fil

> Le prix est l'unité, pas un ratio. Sur un axe prix natif, **les cibles décidées ne bougent jamais** (elles sont des prix, pas des % à recalculer), **le coût se place honnêtement** (à droite des cibles s'il les dépasse, signal-discipline), **le current raconte le prix réel** sans intermédiaire, et **le visuel coïncide avec le classement par construction** (Beyond ⇔ cur ≥ full sur l'axe). Le P&L EUR vit en texte — l'argent que tu lis dans ta devise, pas un nombre que la géométrie devrait porter. Trois contraintes incompatibles en %-depuis-une-référence-unique deviennent compatibles en prix, parce qu'en prix il n'y a aucune référence à choisir.
