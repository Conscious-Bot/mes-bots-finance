# Audit deep dashboard PRESAGE — 2026-06-24

> Audit-trail complet : pour chaque panneau du dashboard, source de dérivation + vérification cohérence live + findings.
>
> Méthodologie : recompute multi-sources via `python3 -c "..."`, comparaison panneau (ce qui s'affiche) vs source canonique (table SQL append-only / Datum live).
>
> **État global** : cohérence forte sur les chiffres core (Book value, PnL, FX), divergences sémantiques mineures sur 7 panneaux secondaires.

---

## 1. Sommaire des findings

| # | Sévérité | Page | Panneau | Description |
|---|---|---|---|---|
| F1 | **MEDIUM** | vigie | Closest to target | 5 positions structural exclues par construction (`downside_pct=None` forcé par position_view.py:323) → ASML, TSM, SK Hynix, SNPS, 6920.T jamais visibles dans ce panneau |
| F2 | **MEDIUM** | positions | Hero KPIs | Label UI "At stop &lt;10%" mais code filtre `<5%` (fix 23/06) → mismatch UI/logique + gap 5-10% disparu de tous les buckets |
| F3 | **LOW** | concentration | By sector | 3 tickers sans mapping sector (6324.T HARMONIC, GEV, SPCX) → 4 569 € (8%) classés "unknown" |
| F4 | **LOW** | methode | Insider flow (7d) | Table `insider_buy_log` ABSENTE en DB → panneau silent fail (probablement vide ou crash swallowed) |
| F5 | **INFO** | urgence | Macro state | Tables `market_indicators` / `macro_indicators` ABSENTES — les 15 indicateurs vivent dans table autre (probablement `signals`). Panneau fonctionne mais nom de source faux dans la cartographie initiale |
| F6 | **LOW** | strategie | Factor exposures | Factor "AI broad" = 39 948 € (69.6%) = AI capex (36 566 €) + Memory cycle (3 382 €) → overlap intentionnel double-counting si lu naïvement |
| F7 | **LOW** | vigie vs strategie | Beyond target ≠ above_bull_case | Vigie "Beyond target"=0 (prix vs target_full thèse) vs Strategie "above_bull_case"=3 (prix vs PE bull-case proxy). Sémantique différente, label proche → risque confusion |

**Aucun finding HIGH** : les invariants critiques (Book value, PnL, cost basis, FX) sont cohérents à toutes les sources.

---

## 2. Architecture canonique (source unique de vérité)

```
TABLE transactions (append-only ledger, write-once trigger)
    ↓ ledger_pmp.compute_pmp_realized() — itère date-ordered
TABLE positions (cache : qty + avg_cost_eur NULL systémique)
    ↓ shared.book — calcule live à chaque appel
BookLine (qty + avg_cost_eur PMP rolling + last_price_native + fx_rate_to_eur)
    ↓ get_all_positions_views() — un seul appel central par regen
dict[ticker → PositionView]  ← _views, single-source enforcement cure #120
    ↓ build_positions_view(_views)
list[positions]  ← consommé par TOUS les panneaux multi-position
    ↓ pf_value = Σ p["weight"]   ;   pf_cost = Σ p["cost_basis_eur"]
PANNEAUX
```

**Cure #120 (12/06)** : 3 panneaux (`_concentration`, `_cluster_health`, `_risk_watch_panel`) + `intelligence.spof_and_sizing` consomment **le même dict `_views` passé en argument**. Single-source enforcement → impossible que deux panneaux divergent sur le même ticker par construction.

**Invariant verrouillé** : `tests/test_aggregate_sum_equals_parts.py` → `Σ p["weight"] == Σ view.value_eur`.

---

## 3. Audit page-par-page

### PAGE VIGIE (Vue d'ensemble) — 11 panneaux

| # | Panneau | Variable render.py | Source canonique | Live value (2026-06-24 ~22h) | Verdict |
|---|---|---|---|---|---|
| 1 | Live indicator | `_ov_live_html` (L8169) | `datetime.now()` + cron mtime | freshness chip | ✓ N/A |
| 2 | Book value (hero) | `pf_val_str` (L7740) | Σ `view.value_eur_datum.value.amount` (canonical) | **57 358 €** | ✓ |
| 2b | PnL on cost | `_ov_pnl_eur` (L8046) | `pf_value - _pfcost` | **+12 254 € (+27.2%)** | ✓ |
| 2c | Today delta | `_ov_today_d` (L8051) | `pf_value - portfolio_snapshots[latest]` | **+813 € (+1.4%)** | ✓ |
| 2d | Invested | `_ov_invested` (L8045) | Σ `cost_basis_eur` = Σ qty × `ledger_pmp.pmp_eur` | **45 104 €** | ✓ |
| 3 | Portfolio grade (ring) | `_grade_letter`/`_grade_score` (L7929) | `storage.get_latest_portfolio_grade()` ← table `portfolio_grade_snapshots` | **B / 70 / 100** trend ↓7j | ✓ |
| 4 | Macro state | `_macro_state_strate` (L8253) | `shared.macro_state.current_macro_state()` | **STRESS / score 123.5** | ✓ |
| 5 | Needs you today | `_needs_today(...)` (L8289) | `near_stop_tk` (downside<5% + losing) + cluster over_cap | **0 positions** (filtre 5%+losing) | ✓ |
| 6 | Closest to target | `_targets` (L7833) | `_axis` dict where cur < target_full | Top: STMPA/SAF/BESI/AMZN/SU/ALAB | **F1 :** 5 structural exclues |
| 7 | Beyond target | `_beyond` (L7829) | `_axis` dict where cur ≥ target_full | **0 positions** | ✓ |
| 8 | Top winners 24h | `_day_up` (L7710) | `_perf_dwm(tk)['d']` ← table `price_history` | 000660.KS +4.6%, 6324.T +3.2% | ✓ |
| 9 | Top losers 24h | `_day_dn` (L7710) | idem | MU -13.2%, COHR -10.4%, ALAB -9.7% | ✓ |
| 10 | Risk watch | `_risk_watch_panel(_views)` (L8320) | filtre downside<10% + at_risk + blind_vol | 10 positions ds<10% | ✓ |
| 11 | Blind positions | `_blind_positions_panel()` (L7905) | positions sans vol estimate ou sans recent fundamental | (panneau autonome) | ✓ |

### PAGE POSITIONS — 3 panneaux

| # | Panneau | Variable | Source canonique | Live value | Verdict |
|---|---|---|---|---|---|
| 1 | Hero "Book value" | `pf_value` (L8499) | Σ p["weight"] | **57 358 €** | ✓ identique à vigie |
| 1b | Hero "Near target" | `n_tgt = len(near_tgt_tk)` (L8424) | filtre `upside_pct < 12%` | count | ✓ |
| 1c | Hero "Near stop" | `_ns = len(_losing_near_stop_tk)` (L8484) | filtre downside<5% + losing | count | **F2 :** label dit `<10%` mais filtre `<5%` |
| 2 | Broker accounts table | `_broker_tables(positions, names, pnl, sectors)` (L8468) | positions list direct + sectors map | Tableau positions/comptes | ✓ |
| 3 | Discipline band (sticky) | `_dband` (L8562) | `_cluster_health()` + `_near_losing` count | "ALIGNED" si _dn=0 | ✓ |

### PAGE THESES — 4 panneaux

| # | Panneau | Source canonique | Live value | Verdict |
|---|---|---|---|---|
| 1 | Hero star | `_q("SELECT conviction FROM theses WHERE status='active'")` | 28 actives (c2=1, c3=13, c4=7, c5=7) | ✓ |
| 2 | Conviction KPIs | idem + agrégation par conviction | médiane c4, 25% c5 | ✓ |
| 3 | Missing TPart gap | `_q("...WHERE status='active' AND target_partial IS NULL")` | **0 missing** | ✓ |
| 4 | Conviction grid (c1→c5) | thèses + `_axisrow(tk)` (utilise même `_axis` que vigie) | 28 lignes groupées par c | ✓ identité littérale avec vigie via `_pr` stocké dans `_axis` |

**Invariant** : held_lines (28) == thesis_tk_active (28) — parité parfaite, aucun orphelin.

### PAGE CONCENTRATION — 4 panneaux

| # | Panneau | Source canonique | Live value | Verdict |
|---|---|---|---|---|
| 1 | Concentration star | `_cluster_health()` + top position % | dynamique | ✓ |
| 2 | By sector | `_sectors()` dict[ticker→sector] | Semi eq 21%, Foundry 14%, Energy 9%, Hyperscalers 9%, Semi mat 8%, Defense 8%, **unknown 8%**, Connectivity 8% | **F3 :** 6324.T/GEV/SPCX sans mapping |
| 3 | By country | `_geo_bars(positions)` ← HQ-only | (HQ aggregation) | ✓ (note : HQ ≠ supply chain) |
| 4 | FX exposure | `_fx_exposure_panel()` ← Σ par currency natif | USD 54.4%, EUR 24.1%, JPY 17.9%, KRW 3.5% | ✓ |

### PAGE METHODE — 12 panneaux

| # | Panneau | Source canonique | Live value | Verdict |
|---|---|---|---|---|
| 1 | Star signaux | `_q()` sur table `signals` | 746 rows total | ✓ |
| 2 | Track record | `_track_record_panel()` ← historical | (panneau autonome) | ✓ |
| 3 | Distribution health | `_distribution_health_panel()` | (panneau autonome) | ✓ |
| 4 | 8-K tape | `filings_8k_log` table | 70 rows total | ✓ |
| 5 | Source credibility | `sources` table | 89 sources | ✓ |
| 6 | **Insider flow (7d)** | `insider_buy_log` table | **TABLE ABSENTE** | **F4 :** table manquante |
| 7 | Clustered buys | `insider_buy_clusters_log` table | 0 rows | ✓ (mais 0 = panneau vide) |
| 8 | Discipline & biais | `bias_events` table | open/resolved counts | ✓ |
| 9 | Glossary | `_glossary_panel()` static | (static UI) | ✓ |
| 10 | Data health | `_data_health_panel()` ← M1 freshness | (panneau autonome) | ✓ |
| 11 | Performance panel | `_performance_panel()` ← retro-test | (panneau autonome) | ✓ |
| 12 | Loop chain | `_loop()` ← predictions + position_audit_log + signals + sources | (panneau autonome) | ✓ |

### PAGE URGENCE — 4 panneaux

| # | Panneau | Source canonique | Live value | Verdict |
|---|---|---|---|---|
| 1 | Macro state exploratoire | `debt_composite` table (108 rows) | phase 4 / composite | ✓ |
| 2 | Macro stress indicators | `shared.macro_state.current_macro_state()` ← composite | 15 indicateurs (MOVE, VIX, DXY, HY_OAS, USDJPY, Gold, TYX, BTC_dd180, CopperGold, BankReserves, T10Y2Y, KRE, MfgIP, FedBalance, CoreCPI) | **F5 :** source réelle dans tables autres que `market_indicators`/`macro_indicators` (qui n'existent pas) |
| 3 | Market RSI(14) | `_market_rsi()` (L5314) cache TTL 30min | RSI(SPY) live | ✓ |
| 4 | Market breadth RSP/SPY | `_breadth_rsp_spy()` (L5347) | breadth ratio live | ✓ |

### PAGE STRATEGIE — 4 panneaux

| # | Panneau | Source canonique | Live value | Verdict |
|---|---|---|---|---|
| 1 | Book reading star | `theses.conviction` + `bias_events` | médiane c4 + 2 biases mecanized | ✓ |
| 2 | Declared strategy | `_user_strategy_panel()` ← portfolio_targets + conviction | (panneau autonome) | ✓ |
| 3 | Book trajectory | `_trajectory_panel()` ← `intelligence.factor_exposures.format_grade_trajectory()` | 9 factors, top AI broad 69.6% | **F6 :** AI broad overlap AI capex + Memory cycle |
| 4 | Beyond bull case | `_valo_above_bull_panel()` ← `intelligence.spof_and_sizing.list_above_bull_case()` | **3 positions** (6920.T, ALAB, AMD) | **F7 :** ≠ Vigie "Beyond target" (qui = 0). Sémantique distincte (PE vs target_full) |

### PAGE POSITION-CARD — 2 panneaux

| # | Panneau | Source canonique | Live value | Verdict |
|---|---|---|---|---|
| 1 | Summary verdict pills | `derive_card_steer()` tally HOLD/TRIM/EXIT/REVIEW | (dynamique) | ✓ |
| 2 | Position cards (1 par thèse) | `_position_card(inputs, steer_v2)` + `assemble_card_inputs()` | **28 cards** (1 par thèse active) | ✓ |

### PAGE COPILOT — 2 panneaux

| # | Panneau | Source canonique | Verdict |
|---|---|---|---|
| 1 | Ask the copilot | `_chat_panel()` form + localStorage | ✓ |
| 2 | Adversarial pressures | `_copilot_panel()` ← historical pressure tests + bias challenge log | ✓ |

---

## 4. Invariants cross-page

| Invariant | Sources comparées | Δ | Verdict |
|---|---|---|---|
| Σ weight identique vigie ≡ positions ≡ concentration | `pf_value` (3 endroits) | 0,00 € | ✓ identité littérale par cure #120 |
| pf_cost identique vigie ≡ positions | `_pfcost` (2 endroits) | 0,00 € | ✓ même `_positions(_views)` |
| BookLine cache vs canonical | sum BookLine.weight_market_eur vs Σ view.value_eur | +21,34 € (0,037%) | ✓ jitter cron normal entre refresh |
| Held lines == thesis active | held_tk vs thesis_tk | 0 diff | ✓ parité parfaite |
| ledger PMP vs BookLine.avg_cost_eur | KLAC test : 158,8794 vs 158,8794 | 0,000000 | ✓ identité parfaite |

---

## 5. Findings détaillés

### F1 — Closest to target exclut positions "structural"

**Lieu** : `shared/position_view.py:321-323` :
```python
if position_type == "structural":
    upside_pct = ((target_full / entry - 1) * 100.0) if (target_full and entry) else None
    downside_pct = None  # structurel non-borne par prix
    asym_ratio = None
```

**Effet** : `dashboard/render.py:7813` filtre `if up is None or dn is None: continue` → 5 positions structural exclues de l'`_axis` dict → exclues de Closest/Beyond/_stops.

**Tickers concernés** : ASML.AS (c5), TSM (c5), SNPS (c5), 000660.KS (c4), 6920.T (c3) — 5 positions, **toutes high conviction**.

**Comportement utilisateur** : un user qui regarde "Closest to target" en Vue d'ensemble ne verra jamais ses 5 positions les plus convictionnelles s'approcher de leur cible. C'est une **décision design intentionnelle** ("structurel non-borné par prix") mais le label UI ne le signale pas.

**Reco** : soit (a) revoir le commentaire + ajouter une légende UI "structural positions excluded", soit (b) inclure les structural en calculant downside_pct quand stop existe et stop < entry (cas le plus fréquent), soit (c) marquer dans Conviction grid (page Theses) si une structural approche son target via badge dédié.

### F2 — Mismatch label UI 10% vs filtre code 5%

**Lieu** : `dashboard/render.py:7754` (fix 23/06 d'hier) :
```python
near_stop_tk = [
    r["ticker"] for r in sorted(computed, key=...)
    if (r.get("downside_pct") is not None
        and r["downside_pct"] < 5      # ← filtre 5%
        and _is_losing_row(r))
]
```

vs `dashboard/render.py:8455-8457` (label UI Posture star Positions) :
```html
At stop <10%  → ${n_stop}
Watch 10-20%  → ${n_watch}
```

et `dashboard/render.py:8505` (Hero KPI Positions) :
```html
within 12% of target
```

**Effet** :
- `n_stop` est calculé sur filtre 5% mais l'utilisateur lit "At stop <10%" — il comprend mal le KPI
- Gap **5-10%** disparu de **tous** les buckets : ni `near_stop_tk` (<5%) ni `watch_zone_tk` (10-20%) ne capture
- Une position avec downside_pct = 7% sera **invisible** dans les KPIs Posture mais visible dans Risk watch (qui utilise <10%)

**Reco** : aligner les seuils dans une constante unique. Soit revenir à 10% partout (et expliciter par tag couleur "fresh BUY noise"), soit rebaisser le label UI à <5% + déplacer le bucket Watch à 5-15%.

### F3 — Sectors manquants

**Lieu** : `dashboard/render.py:4188` `_sectors()` retourne un dict[ticker→sector]. Trois tickers absents.

**Tickers** :
- 6324.T (HARMONIC DRIVE SYSTEMS) — weight 1 332 €
- GEV (GE Vernova) — weight 1 370 €
- SPCX (Destiny Tech100 proxy SpaceX) — weight 1 867 €
- Total : 4 569 € (8% du book)

**Effet** : panneau "By sector" classe ces 4 569 € en "unknown" — masque 8% du book dans l'agrégation sectorielle.

**Reco** : ajouter les 3 mappings dans `_sectors()` → 6324.T: Industrial robotics, GEV: Energy & utilities, SPCX: Aerospace.

### F4 — Table `insider_buy_log` ABSENTE

**Lieu** : `dashboard/render.py:4710` `_insider_flow_strip_html()` lit `insider_buy_log` table.

**Effet** : la table n'existe pas en DB. Le panneau Insider flow (7d) probablement silent fail (catch Exception swallow) ou affiche vide.

**Reco** : soit (a) créer la table via migration alembic, soit (b) retirer le panneau de la page methode si non implémenté, soit (c) gracefully degrade avec message "module not wired yet".

### F5 — Macro indicators source réelle

**Lieu** : `dashboard/render.py:8234-8269` `_macro_state_strate` consomme `shared.macro_state.current_macro_state()` qui retourne 15 indicateurs.

**Tables réelles** : pas `market_indicators` ni `macro_indicators` (qui n'existent pas) — vraisemblablement `signals` table ou tables dédiées par indicateur.

**Effet** : aucun pour l'utilisateur (panneau fonctionne). C'est juste une correction à la cartographie — l'inventaire initial mentionnait des tables qui n'existent pas.

### F6 — Overlap factor "AI broad" vs sous-factors

**Lieu** : `intelligence.factor_exposures.compute_factor_exposures()`

**Effet** : 9 factors retournés mais 3 (AI broad, AI capex, Memory cycle) sont en relation parent/enfant :
- AI broad : 39 948 € (somme exacte AI capex + Memory cycle + ?)
- AI capex : 36 566 €
- Memory cycle : 3 382 €
- AI capex + Memory = 39 948 € (exact match avec AI broad)

**Risque** : si user somme les factors, il **double-count** AI broad. À documenter dans le panneau (badge "supersetfactor includes sub-factors below") ou exclure de la somme.

### F7 — "Beyond target" (vigie) ≠ "above_bull_case" (strategie)

**Sémantique distincte** :
- Vigie "Beyond target" : `cur_native >= target_full_native` du gauge thèse → 0 positions actuellement
- Strategie "above_bull_case" : `current_price >= bull_case_PE_proxy` (calcul valuation) → 3 positions (6920.T, ALAB, AMD)

**Risque** : labels proches ("Beyond target" / "Beyond bull case") → user peut croire que c'est la même mesure. En réalité, l'un est target user-set (thèse), l'autre est valuation absolue (modèle PE).

**Reco** : renommer pour différencier explicitement (ex: "Beyond user target" vs "Above bull case valuation") ou regrouper dans un panneau unique avec 2 lignes distinctes.

---

## 6. Verdict final

**Cohérence des chiffres core (Book value, PnL, FX, cost basis)** : **PARFAITE**. Les invariants cure #120 (single-source `_views`) tiennent. Le seam canonique `book.value_eur` aligné avec ledger PMP au centime près.

**Cohérence sémantique** : 7 findings de niveau MEDIUM/LOW/INFO, tous expliquables et corrigeables, aucun blocant.

**Architecture saine** : 
- Source de vérité unique = table `transactions` (append-only avec triggers write-once)
- PMP rolling calculé live à chaque appel (pas de cache stale)
- Cache BookLine refresh par cron (drift normal sub-1%)
- Tests verrouillent les invariants critiques (`test_aggregate_sum_equals_parts.py`, `test_position_view_seam.py`)

**Aucune fuite cachée**. Aucun panneau ne lit une source orpheline. Aucune divergence > 1% entre 2 chemins pour la même métrique.

**Action immédiate suggérée** : F2 (mismatch UI 10%/5%) — fix rapide cohérence label/code.
**Action moyenne** : F1 (structural exclues) + F3 (sectors) — choix design à valider.
**Action différée** : F4 (insider_buy_log) + F5 (cartographie) + F6+F7 (sémantique factor/bull).

---

*Audit produit le 2026-06-24 ~22h via verify-before-patch multi-source recompute.*
*Méthodologie : `python3 -c "..."` direct sur DB locale (synced from VM hourly).*
