# TODO — PRESAGE (mes-bots-finance)

**Refresh** : 29 mai 2026 (Day 18 close, post 4-joints-brief soudés)
**Mode** : Phase construction + Observation Brier jusqu'au 10/06
**Archives** : `/tmp/TODO_pre_refresh_*.md` (backup pre-refresh ce soir)

---

## 🟢 ÉTAT SYSTÈME — Gate vert, fondations posées

- **Gate `run_static_gate(conn)` 🟢 vert** (avec dette catalogue documentée)
- **400+ tests verts**, lint clean
- **Book canonique unifié** : `shared/book.py` + `shared/position.py` (3 couches FAIT/JUGEMENT/DÉRIVÉ/HISTORIQUE)
- **Passerelle dérivée unique** : `storage.get_position_view(ticker)` + `storage.get_book_view()`
- **Boucle-de-soi V0 active** : 7 ancres contrefactuelles capturées aujourd'hui (mesure J+30)
- **5 commits poussés** sur `origin/main` (privé Conscious-Bot)

---

## 🔴 P0 — Dette gate à fixer avant 10/06

**11 violations catalogue** dans `tests/test_book_gate.py` (KNOWN_DEBT_*). À fixer une par une, retirer le ticker de la liste au fix. Date butoir : **10/06/2026** (KPI #2 batch resolution).

### Kill-criteria substance (6 thèses) — refondre en kill-criteria fondamentaux

- [ ] **TSLA** — actuel "cloture sous stop 285.63 (-25% entree)" → besoin : revenue auto / FSD revenue / Cybertruck recalls / Robotaxi delay
- [ ] **SAF.PA** — actuel "Re-evaluate within 30d" (timer, pas substance) → besoin : aftermarket margin / GTF cure costs / defense budget EU
- [ ] **AMZN** — actuel "Cassure stop 182.80 EUR -- a etoffer" → besoin : AWS YoY <15% / margin AWS / retail OI / capex hyperscaler pause
- [ ] **MP** — actuel "Cassure stop 44.24 EUR -- a etoffer" → besoin : NdPr price / DoD Defense contract / Stage 3 magnet ramp / Chine export tariffs
- [ ] **ENTG** — actuel "Cassure stop 95.18 EUR -- a etoffer" → besoin : margin advanced materials / EUV resist share / fab capex pause
- [ ] **6857.T** (Advantest) — actuel "Cassure stop 117.41 EUR -- a etoffer" → besoin : memory test ATE share / HBM TAM / SoC test margin

### Currency native mismatch (5 thèses) — stop_price + entry_price en native (JPY/KRW)

- [ ] **4063.T** (Shin-Etsu) — stop 28.89 EUR → recalibrer en JPY natif (~4350 JPY)
- [ ] **000660.KS** (SK Hynix) — stop 782.3 EUR → recalibrer en KRW natif (~1.4M KRW)
- [ ] **7011.T** (Mitsubishi Heavy) — stop 16.59 EUR → recalibrer en JPY natif (~2900 JPY)
- [ ] **6857.T** (Advantest) — stop 110.07 EUR → recalibrer en JPY natif (~19500 JPY)
- [ ] **6920.T** (Lasertec) — stop 164.01 EUR → recalibrer en JPY natif (~30000 JPY)

**Effort estimé** : 5-10 min par thèse × 11 = ~1h30 total. À répartir sur 2-3 sessions courtes.

---

## 🟡 P1 — Recalcul cluster cap suite re-tag CCJ

Le re-tag CCJ "PPA-correlated, plus ballast pur" (ce soir) **rétrécit le ballast strict** : 9.1% du book actuel (vs 16.8% avant la nuance). La cible cluster cap 70% validée ce soir l'a été AVANT ce re-tag.

- [ ] **Recalculer cluster cap réel** sur book post-rotation (MU presque sortie, CCJ partial-correlated)
- [ ] **Décider si target_cluster_cap reste 70%** ou se réajuste (peut-être 65%-72% range)
- [ ] **Re-valider drawdown tolerance** si target shifte
- [ ] Si maintien 70%, c'est OK — la dette n'est qu'à -3pp marginale

**À faire à tête reposée** (= demain matin) — pas urgent ce soir.

---

## 🟢 P2 — Observation jusqu'au 10/06

**Discipline = usage > code.** 12 jours d'observation.

- [ ] **Daily check `tail bot.log`** : morning_chain (6h) et evening_chain (23h) finissent OK
- [ ] **Daily gate** : `python3 -c "from shared import storage; print(storage.assert_book_invariants(strict=False))"` doit rester vert (= 11 violations dette, pas plus)
- [ ] **VALUE_LOG** : remplir chaque jour ce que PRESAGE t'a appris (= la mesure réelle de la valeur, pas le commit count)
- [ ] **10/06 batch resolution** : 49 predictions résolues automatiquement par cron. Vérifier que dedup Brier marche (`measure_bias()` produit chiffres signés).

---

## 📅 Calendrier dur

| Date | Item | Action |
|---|---|---|
| **30/05** demain | TODO refresh ✓ | matin frais |
| **31/05** T-2 | Hetzner ADR | **Probablement à différer** post-10/06. Pas attaquer un cloud d'un système pas-encore-Brier-validé |
| **10/06** D+12 | Batch resolution 49 predictions | Vague de résolution + 1ère mesure Brier dédupliquée. Moment de vérité. |
| **Post-10/06** | Path 6 / multi-user | Cf section "Migration time" (voir backup TODO si besoin) |

---

## 🎯 NIVEAU 2 — quand fondations validées (post-10/06)

Cadre encore valide, à attaquer **uniquement** quand Brier 10/06 valide la fondation. **Résister à construire avant.**

Ordre opérationnel validé :
1. **#5 jauge composite AI capex** (consolide, ~1j) — seul move qui réduit la surface
2. **#4 + #2 jumeaux** (pré-registration immutable + contrefactuel intent-aware) — l'asset central
3. **#1 adversaire** (bear case + sell-friction informative) — déjà partiellement amorcé (boucle-de-soi V0)
4. **#3 process score** — optionnel long-tail (rubric pré-signée requise)

Cf mémoire `niveau_2_adversary_and_proof` pour le détail des 5 moves.

---

## 🔒 SÉCURITÉ — différée (déclencheurs non atteints)

Repo GitHub **PRIVÉ** vérifié (HTTP 404 sur API publique). Credentials jamais dans git history. `.gitignore` couvre tous patterns.

- [ ] **Rotation OAuth Google** — runbook conservé. Déclencheurs : push remote PUBLIC / due-diligence Path 5 / partage Project Claude / suspicion compromission. **Aucun déclencheur actif.**

---

## 🚀 PATH 6 — quand calibration prouvée (post-10/06)

- [ ] **Calibration plot home** (money-shot Path 6) : ≥10 prédictions résolues prob-différenciée requis. Vient post 10/06.
- [ ] **Substack premier article** : fact-check SK Hynix $1,216 + reliability diagram + ledger résolu
- [ ] **presage.fi** : acheter (~10€/an, défensif)
- [ ] **Panneau biais sous surveillance** : tracker 2 biais nommés avec décision→outcome (boucle-de-soi V0 mesure déjà ; surface dashboard quand n_resolutions ≥ 5)

---

## ✅ DÉJÀ FAIT AUJOURD'HUI (29/05)

### Brief 10 points implémenté
- ① Passerelle dérivée unique (`storage.get_position_view`)
- ② Digest book-anchored (kill-criterion + validation + margin urgency scoring)
- ③ Invariant décision→outcome (predictions OR decision_counterfactual)
- ④ Crons séquencés (morning_chain / evening_chain / weekly_chain)
- 3 couches Position canonique (FAIT/JUGEMENT/DÉRIVÉ + HISTORY append-only)
- `run_static_gate(conn)` vert avec InvariantViolation strict
- `canonical_position_schema.sql` doc d'intention

### Phase 4 gate système devise
- `shared/thesis_invariants.py` (currency native + kill_criteria substance)
- Branche dans `run_static_gate` (10 checks total maintenant)
- 11 dette KNOWN_DEBT catalogue avec date butoir 10/06

### Boucle-de-soi V0
- Migration 0018 : `decision_counterfactual` + `counterfactual_resolution` (append-only)
- `intelligence/self_loop.py` : record_anchor / resolve / measure_bias / bias_context
- Cron `daily_counterfactual_resolve_job` (23h15)
- Hook chat_intent.py : capture ancre AVANT execution
- Tests `tests/test_self_loop_v0.py`

### P0 + P1 fermés (validations user)
- P0 : Repo GitHub vérifié privé
- P1 #1 : Drawdown tolerance 75 → **70%** validée (`drawdown_tolerance_validated: true`)
- P1 #2 : MU trim 50% (×2 sessions) + kill_criteria fondamentaux refondus
- P1 #3 : SNOW thèse structurée (sortie vol aveugle : entry/target/stop/4 kill-crit)
- P1 #4 : LNG maintenu + tag refiné (alt_drivers nuancés) + nouvelle mémoire `adversarial-pushback-explicit`
- CCJ : reverse scale_in + re-tag PPA-correlated + thesis fixée (stop USD natif)

### Trades du jour (chat-driven)
- SELL ALAB 616€ (profit-take winner) → BUY LNG 616€
- SELL MU 940€ + 920€ (trim 50% puis quasi-sortie) → BUY LNG 250€ + BUY CCJ 667€
- REVERSE CCJ 667€ (acknowledge STRONG_OPPOSE substance) → BUY LNG 434€ + BUY MP 233€
- 7 ancres contrefactuelles capturées (mesure J+30 = 29/06)

### Backup + cleanup + push
- 348MB snapshot frais `~/Documents/presage_backups/snapshot_20260529_220957/`
- ~400MB clutter supprimé (28 source backups + caches + DB historiques)
- Repo 1.9G → 1.5G
- Push origin/main jusqu'au `74fc117`

### Mémoires ajoutées (12 totales)
- `feedback-adversarial-pushback-explicit` : substance >> contradiction creuse
- `currency-native-invariant` : ADR 005 reformulé + pattern Cameco

---

## 🧭 Cadre maître (rappel)

### Les 4 racines (verdict 29/05) — état

1. **Source de vérité unique du book** — ✅ Soudé (book.py + position.py + storage.get_position_view)
2. **Features qui combattent la discipline** — ✅ Soudé (kill_criteria fundamental-only + gate substance)
3. **Mode maintenance permanent** — ⚠️ Phase construction active jusqu'à ~65k€ book (=15k€ encore à déployer)
4. **Métriques calibrées pour le confort** — ✅ Soudé (note 88 honnête, drawdown CTA validée, ballast haircut, Solidité refondue)

### Principe directeur — "tout output non instrumenté est gaspillé"

Chaque output doit recevoir un outcome mesurable qui se réinjecte. **La moitié des 15 vues échouent ce test** (selon ton propre verdict). À couper progressivement post-10/06 quand on aura mesure pour arbitrer.

### Calendrier discipline

- **Maintenant → 10/06** : usage > code. Brier est l'asset, pas les commits.
- **10/06** : batch resolution. Moment de vérité.
- **Post-10/06** : Niveau 2 si Brier valide. Path 5 (privé) avant Path 6 (public).
