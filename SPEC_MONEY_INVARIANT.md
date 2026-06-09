# Spec — Invariant monétaire (régler la classe « +176056% » une bonne fois pour toute)

> Extension de `SPEC_SOCLE` aux **baselines monétaires** (pas seulement les prix). Le socle a typé `prices.get → Datum(triple M1)` ; il n'a jamais atteint `entry_price`, `avg_cost`, `stop`, `target_full` — restés floats nus. Cette spec rend **structurellement impossible** la classe de bug qui ressurgit table après table : *un ratio/P&L calculé en divisant deux nombres d'argent de devises ou de baselines différents, renvoyant un nombre confiant et faux*. Hérite de `QUALITY_BAR` (M1), `CALIBRATION_DOCTRINE` (fail-closed L15), `LESSONS`.

## 0. La maladie, nommée une seule fois

Tous ces symptômes sont **un seul bug** :

| Symptôme | Table | Cause racine |
|---|---|---|
| perf_thesis `+176056%` | theses | entry(EUR) ÷ price(KRW) — devises mélangées |
| P&L `+18726%` | positions | avg_cost(EUR) × price(native) — devises mélangées |
| `0,5×` vs `1,80×` | render | deux baselines, deux conventions |
| perf_thesis ≡ pnl_position | theses | migration a écrasé entry := avg_cost (baselines fusionnés) |

> **La maladie : un nombre d'argent vit sans son triple `(valeur, devise, asof)`, et un ratio le divise contre un autre nombre d'argent sans vérifier qu'ils sont commensurables.** Le socle a guéri ça pour les prix. On l'étend à TOUT baseline monétaire. Réglé = la classe entière devient un build-rouge, pas un patch des 3 noms.

## 1. Cure #1 — tout baseline monétaire EST un Datum (réutilise le socle, n'invente pas de type)

Cinq colonnes deviennent des `Datum` portant leur **devise** + leur **asof** :

| Colonne | Table | Sémantique du baseline | as-of |
|---|---|---|---|
| `entry_price` | theses | prix **à l'appel de thèse** | `opened_at` de la thèse |
| `stop_price` | theses | seuil d'invalidation | date de pose |
| `target_partial` | theses | cible partielle | date de pose |
| `target_full` | theses | cible pleine | date de pose |
| `avg_cost` | positions | prix **d'achat** moyen pondéré | date d'achat (dernier lot) |

`entry_price` et `avg_cost` sont **deux baselines distincts qui ne doivent JAMAIS être l'un l'autre** (cf §3).

**Pas de type `Money` parallèle — la devise voyage dans le `value` du Datum.** `Monetary = (amount: float, currency: str)` ; un montant est un `Datum[Monetary]`. Ainsi `asof`/`source`/`confidence`/`degraded`/`derive` tombent **gratuitement** du socle — aucune logique de fraîcheur ré-implémentée. `shared/money.py` porte `Monetary` + `pct_change` + `in_eur(fx_at)`, helpers **sur Datum**, jamais une hiérarchie sœur. Minimal-moving-parts.

**Gate** : un float nu retourné/stocké sur ces colonnes = build-rouge (ratchet, comme yfinance).

## 1.5 La frontière d'ingestion — une position naît native+taguée, ou ne naît pas

> Le bug récurrent a DEUX portes : l'`UPDATE` qui clobbere (fermé §3 write-once) **et** l'`INSERT` qui naît corrompu. Nettoyer l'historique sans verrouiller l'ingestion = la prochaine position JP/KR rejoue la classe à la naissance. Toute nouvelle position/thèse entre **uniquement** par un constructeur qui exige un `Datum[Monetary]` natif.

1. **Devise dérivée du ticker via le gateway, jamais saisie ni supposée EUR.** `prices.get(ticker).currency` est la source unique (`.T→JPY`, `.KS→KRW`, `.PA→EUR`, défaut USD). L'ingestion lit la **même porte** — pas de default EUR, pas de question à l'utilisateur, pas d'inférence locale.
2. **INSERT type-fermé** : la fonction d'ajout (bot `/add`, `insert_thesis`, `insert_position`) signe `Monetary(amount, currency)` requis (`extra='forbid'`, pas de default sur `currency`). Un float-nu = rejet au type, pas en review.
3. **`entry_fx_at_call` figé** depuis `fx_history@opened_at` à l'ouverture ; absent → DEGRADED, jamais le FX du jour.

**Filet sous la porte** : même ingestion trouée, `pct_change` (§2) asserte la commensurabilité → une position mal-taguée sort **DEGRADED bruyant**, jamais un ratio faux confiant. Le pire cas est visible le jour même.

## 2. Cure #2 — UNE primitive de ratio monétaire, qui asserte la commensurabilité

```python
# shared/money.py
def pct_change(frm: Datum, to: Datum) -> Datum:
    assert frm.currency == to.currency, \
        f"pct_change cross-devise interdit: {frm.currency} vs {to.currency} — convertis d'abord via fx()"
    return derive(lambda a, b: (b / a - 1) * 100, frm, to)   # hérite degraded/asof/confidence
```

- **La SEULE voie** pour calculer un ratio/P&L monétaire. Tout `(a/b - 1)` à la main sur des variables d'argent = build-rouge (ratchet).
- Comparer `price(KRW)` à `entry(EUR)` ⟹ **convertis d'abord** : `to_eur = fx_convert(price_krw)` (chaque conversion est elle-même un `Datum`, traçable), PUIS `pct_change(entry_eur, to_eur)`. **mais espace-de-calcul ≠ fusion-des-baselines**.
- **EUR canonique pour l'affichage (décidé 08/06 — exigence utilisateur)** : on **STOCKE natif** (input devise étrangère sans perte, fait historique préservé) et on **AFFICHE EUR partout**. Toute valeur du dashboard = `Money.in_eur(fx)`, via l'unique convertisseur. `perf_thesis_pct` et `pnl_position_pct` se calculent tous deux en **EUR-space**, **baselines distincts** : `entry_eur = entry_native × fx_figé-à-l'appel`, `avg_cost_eur = avg_cost_native × fx_figé-à-l'achat`. **Les FX des baselines sont FIGÉS** (sinon la perf dérive avec l'EUR du jour = bruit) ; seul `price_eur` utilise le FX live. La distinction `entry ≠ avg_cost` survit en EUR → le veto §5 tient. Comme natif + fx-figé restent stockés, la `perf_thesis` **native-space** (skill isolé du change) reste un *dérivé calculable à la demande* — choisie EUR par défaut, jamais perdue.
- L'`assert` transforme le `+176056%` en **erreur bruyante** au lieu d'un nombre faux confiant. C'est ça, fail-closed structurel.
- Baseline irrécupérable (entry clobberé, non recouvrable) ⟹ `pct_change` retourne `degraded` / `None` (L15), **jamais** un nombre fabriqué.

## 3. Cure #3 — la doctrine qui a manqué (→ LESSONS L28)

> **Aucune migration n'écrase un baseline avec un autre baseline.** `entry_price` n'est jamais affecté depuis `avg_cost` (ni l'inverse). Une migration de *devise* (native→EUR) reconvertit une valeur **dans la même sémantique**, elle ne **substitue jamais** une autre colonne. La corruption `entry := avg_cost_eur` est précisément cette interdiction violée.

`perf_thesis_pct` (track-record du **jugement**, baseline = appel) et `pnl_position_pct` (P&L du **capital**, baseline = achat) sont l'**asset central** de PRESAGE (pivot de provabilité). Les fusionner = Goodhart sur son propre track-record. Interdit par construction (§5 test-verrou).

**Le lock structurel (pas seulement la doctrine) — `entry_price` write-once.** L25 interdit l'overwrite, mais une doctrine ne ferme pas le vecteur ; une structure le fait. `entry_price` est **settable à l'ouverture de la thèse, immuable ensuite** (trigger DB ou guard storage-layer ; toute mutation post-open = rejet, sauf correction explicite loggée + raison). Un baseline immuable-post-création **ne peut pas** être clobberé par un `UPDATE` ultérieur — c'est exactement le vecteur (`UPDATE theses.entry_price = avg_cost`) qui a détruit le track-record le 06/06. Le write-once est le « jamais again » réel ; L25 en est la justification, le trigger en est l'exécution.

## 4. Cure #4 — les gates (ratchet, allumées au compte courant)

```bash
# scripts/check_money_invariant.sh  — decreasing-only, comme la gate yfinance
# (a) float nu sur colonne baseline monétaire
# (b) ratio (a/b-1) ou (b/a-1) sur variables d'argent hors shared/money.pct_change
rg -n '\b(entry_price|avg_cost|stop|target_full)\b\s*[-/]' \
   --glob '!shared/money.py' bot shared intelligence dashboard \
   | rg -v 'pct_change' && exit 1 || exit 0
```

**Ratchet jumeau sur les migrations alembic** (ferme le vecteur à la source) :
```bash
# tout nouveau float-nu monétaire ajouté par une migration = échec build
rg -n '(entry_price|stop_price|avg_cost|target_full|target_partial)\s+REAL' \
   scripts/alembic/*.py && exit 1 || exit 0
```

Les deux gates allumées **maintenant** au compte de violations courant, cliquètent vers zéro à chaque colonne migrée. Aucun commit ne remonte le compteur.

## 5. Tests verrouillants (ce qui rend la régression impossible)

1. **Commensurabilité** : `pct_change` cross-devise lève (assert testé sur KRW vs EUR).
2. **Baselines distincts ⟹ métriques distinctes** (LE veto sur le collapse) :
   `entry_baseline ≠ position_baseline (ex. AMD) ⟹ perf_thesis_pct ≠ pnl_position_pct` (assert).
   *Ce test échoue sous « Voie A ». Il EST l'interdiction permanente de fusionner.*
3. **Byte-identité** : tout nombre présent ligne ET card dérive du même `Datum` (déjà gravé, étendu aux 4 baselines).
4. **Fail-closed baseline** : baseline non-récupérable ⟹ métrique `degraded`, pas un nombre (L15).
5. **No-baseline-overwrite** : test qui rejoue chaque migration sur fixture et asserte `entry_price` jamais égal à `avg_cost` post-migration (sauf coïncidence numérique légitime documentée).
6. **Ingestion native (frontière §1.5)** : `insert_thesis`/`insert_position` sur un ticker `.T`/`.KS` → `entry_currency` = JPY/KRW automatiquement (jamais EUR), et un INSERT float-nu (sans `Monetary`) est rejeté au type. Test : ajouter une fixture 6501.T → assert `entry_currency == "JPY"` et `pct_change` ne lève pas.

## 6. La cure étagée (PAS un big-bang — même discipline que le seam)

> « Une bonne fois pour toute » = la **classe** réglée par type+gate+primitive (petit, porteur), **pas** un sweep de 3h sur toutes les tables. La donnée se nettoie en étagé, ratchet.

```
1. VERIFY (avant tout patch) : dump entry/avg_cost/ccy + AMD contrôle ; git log -p de la
   migration coupable ; récupérabilité du natif (backup propre / price_history@opened_at).
   Vérifier qu'aucune thèse n'est ouverte APRÈS le backup (sinon orphan → DEGRADED).
2. shared/money.py : Monetary + pct_change (assert commensurabilité) + in_eur, additif, testé seul, vert.
3. Migration M1 des 5 colonnes : +value +currency +asof. LA RESTAURATION DEPUIS BACKUP NATIF
   SE FAIT DANS CETTE MIGRATION, jamais avant (sinon on restaure en float-nu non-tagué = on
   rejoue la classe). Baseline irrécupérable → DEGRADED marqué, jamais inventé. DROP des floats
   nus après vert. Idempotente, backup DB d'abord, walking-skeleton sur SK Hynix → écran.
4. Write-once sur entry_price (trigger/guard) + gates ratchet (code + alembic) allumées au compte courant.
5. Tests verrouillants §5 (surtout #2, le veto anti-collapse, AMD témoin).
6. Reroute perf_thesis_pct (NATIVE-space) / pnl_position_pct (EUR-space) via pct_change — baselines distincts conservés.
```

> **Le flow est atomique conceptuellement** : grave (spec) → M1 (migration qui *inclut* le restore) → reroute. On ne restaure jamais la donnée native dans l'ancien schéma float-nu « en attendant » — ce serait répéter exactement l'erreur qu'on corrige.

## 8. Le cœur unique — model et panneaux bougent ensemble (la cohérence end-to-end)

> « Régler à la source » ne suffit pas si 15 panneaux re-calculent chacun leur conversion. La source juste + 15 cœurs = toujours +218% chez l'un, +176056% chez l'autre. La cure : **un seul battement**. Union de cette spec (Money) et de `SPEC_POSITIONS_CARD_LINK` (un compute, deux rendus) — généralisée à *tous* les panneaux.

**Le pipeline unique (source → écran) :**
```
Datum[Monetary] natif (entry/avg_cost/stop/target)          ← LA SOURCE (§1)
        │  prices.get()/fx() → Datum[Monetary]
        ▼
compute_position(ticker) → PositionView                      ← UN calcul / position
        │  (perf_thesis + pnl en EUR-space, baselines figés, via pct_change §2)
        ▼
get_all_positions_views() → dict[ticker, PositionView]       ← LE CŒUR (battement unique, 1×/regen)
        ▼
chaque panneau = projection PURE du dict                     ← LES MEMBRES (zéro calcul)
```

**Les membres (panneaux impliqués — tous projettent, aucun ne calcule) :**
Vue d'ensemble (distline) · Positions (lignes + donut secteurs) · Risque (jauge surchauffe) · Thèses (sizing/perf/barre prix) · Concentration / cluster health · Performance · Urgence · Closest-to-target / sizing over-cap. **Tout panneau touchant un nombre monétaire lit `get_all_positions_views()`, jamais `prices`/`fx`/un ratio local.**

**La garantie « ensemble en cœur » (test de cohérence — le verrou nouveau) :**
1. **Subset monétaire** : l'ensemble des nombres d'argent rendus par TOUS les panneaux pour un ticker ⊆ les champs de son `PositionView`. Un panneau qui rend un montant non-traçable à la vue = build-rouge (AST/grep gate).
2. **Unisson sous perturbation** : perturbe la source (prix +X% sur un ticker) → un seul regen → **tous** les panneaux reflètent le delta de façon identique et simultanée (golden test). Aucun panneau stale, aucun divergent.
3. **Battement unique** : `get_all_positions_views()` appelé **exactement une fois** par regen (assert sur le call-count) — pas N fetches épars.

**Séquence d'union (étagée, pas big-bang — même discipline que le seam) :** la source (§6) d'abord ; puis `PositionView` porte du `Monetary` (perf native / pnl EUR) ; puis `get_all_positions_views()` devient le cœur ; puis les membres migrent **un par un**, byte-identité assertée à chaque (tout diff = finding) ; le test de cohérence §8 ferme l'arc. Le cœur bat juste avant que le premier membre en dépende (walking-skeleton).

## 7. Implementation Status

- **Gravé** : 2026-06-08 (date approximée — session ledger marathon)
- **Implémentation** : IN_PROGRESS — Datum primitif + helpers livrés via socle (cf SPEC_SOCLE), pnl_position_pct_eur helper canonique livré (TODO #118 completed), migration M1 colonnes en cours, panneaux dashboard pas tous migrés (cf TODO #120 CURE RACINE positions seam — NOT big-bang)
- **Fichiers cibles** : `shared/datum.py` (Datum[Monetary] livré via S1a), `shared/position_pnl.py` (pnl_position_pct_eur helper unique), `scripts/check_money_invariant.sh`, `tests/test_money_invariant.py`
- **Doctrine ajoutée** : LESSONS **L28** (montant = `Datum[Monetary]`, jamais float nu : no-baseline-overwrite + write-once + `pct_change` asserte la commensurabilité). Exécution end-to-end (cœur unique) = **L27** (cohérence mécanique > vigilance). Diffusion vérifiée (calcul ≠ source servie) = **L29**.
- **Audit drift** : `scripts/audit_canonical_drift.py`
- **Prochain step** : CURE RACINE positions seam additif (TODO #120) — migration étagée render.py par visibilité décroissante. NE PAS big-bang.

## 8. Le fil

> Avant : chaque table re-jouait le même bug parce que l'argent y vivait en float nu, et chaque ratio devinait la devise. Après : un baseline monétaire **EST** un Datum `(valeur, devise, asof)`, et **une seule** primitive calcule les ratios — qui refuse de diviser des nombres incommensurables. Le `+176056%` ne se patche pas, il devient **impossible** : soit l'assert lève, soit la métrique sort `degraded`. Et `perf_thesis ≠ pnl_position` est verrouillé par test — l'asset central (track-record du jugement) ne peut plus être fusionné par une migration distraite. Réglé une bonne fois = la racine est un type + une règle + un veto, pas une vigilance répétée.
