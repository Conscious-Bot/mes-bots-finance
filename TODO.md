# TODO — PRESAGE (mes-bots-finance)

**Refresh** : 30 mai 2026 matin (post dette KNOWN_DEBT entièrement résorbée)
**Mode** : Phase construction + Observation Brier jusqu'au 10/06 (J-11)
**Archives** : `/tmp/TODO_pre_refresh_*.md` (historique des refresh)

---

## 🟢 ÉTAT SYSTÈME — Tout vert

- **Gate `run_static_gate(conn)` : 0 violations** (dette KNOWN_DEBT vide)
- **25/25 property tests verts strict** (sets KNOWN_DEBT vides)
- **Bot tourne** : PID 81474, lancé 11:03, caffeinate -dimsu, détaché init (survit sleep + ferm. shell)
- **Backup quotidien** : `scripts/backup.sh` corrigé, test manuel OK (25M tarball + DB 9.9M + integrity)
- **7 ancres contrefactuelles** en attente mesure J+30 (boucle-de-soi V0)
- **6 commits poussés** sur `origin/main` aujourd'hui

---

## 🟡 P1 — Observation usage

**Discipline = usage > code.** J-11 jusqu'au batch resolution Brier.

- [ ] **Daily check log bot** : `tail bot.log` confirme morning_chain (6h) + evening_chain (23h) tournent OK
- [ ] **Daily gate** : doit rester 🟢 0 violations (toute violation = régression)
- [ ] **VALUE_LOG** : remplir chaque jour ce que PRESAGE t'a appris (mesure réelle de valeur, pas commits)

---

## 📅 Calendrier dur

| Date | Item | Action |
|---|---|---|
| **31/05** | Hetzner migration (ADR) | **Différer post-10/06** — pas attaquer cloud d'un système pas-encore-Brier-validé |
| **10/06** D-11 | Batch resolution 49 predictions | Vague résolution + 1ère mesure Brier dédupliquée. **Moment de vérité.** |
| **29/06** D+30 | Mesure boucle-de-soi V0 | 7 ancres contrefactuelles ALAB/MU/LNG/CCJ/MP atteignent J+30. `aggregate_brier_dedup()` + `measure_bias()` produiront premiers chiffres signés du biais "vend_winners_trop_tot". |
| **Post-10/06** | Path 6 / Niveau 2 | Conditionnel sur Brier — si validé, slice publication. Sinon retour fondations. |

---

## 🎯 NIVEAU 2 — quand fondations validées (post-10/06)

À attaquer **uniquement** si Brier 10/06 valide. **Résister à construire avant.**

Ordre :
1. **#5 jauge composite AI capex** (~1j, consolide la surface)
2. **#4 + #2 jumeaux** : pré-registration immutable + contrefactuel intent-aware
3. **#1 adversaire** : bear case + sell-friction informative
4. **#3 process score** : optionnel long-tail (rubric pré-signée requise)

Cf mémoire `niveau_2_adversary_and_proof` pour le détail.

---

## 🔒 SÉCURITÉ — différée (déclencheurs non atteints)

- Repo GitHub **PRIVÉ** ✓
- Credentials never in git history ✓
- `.gitignore` couvre tous patterns ✓
- [ ] **Rotation OAuth Google** — runbook prêt, déclencheurs inactifs

---

## 🚀 PATH 6 — quand calibration prouvée (post-10/06)

- [ ] **Calibration plot home** (money-shot Path 6) : ≥10 prédictions résolues prob-différenciée requis
- [ ] **Substack premier article** : fact-check SK Hynix $1,216 + reliability diagram + ledger résolu
- [ ] **presage.fi** : acheter (~10€/an, défensif)
- [ ] **Panneau biais sous surveillance** : surface dashboard quand n_resolutions ≥ 5

---

## ✅ DÉJÀ FAIT (29/05 + 30/05 matin)

### 29/05 — Brief 10 points implémenté
- ① Passerelle dérivée unique (`storage.get_position_view`)
- ② Digest book-anchored (kill-criterion + validation + margin urgency)
- ③ Invariant décision→outcome (predictions OR decision_counterfactual)
- ④ Crons séquencés (morning_chain / evening_chain / weekly_chain)
- 3 couches Position canonique (FAIT/JUGEMENT/DÉRIVÉ + HISTORY append-only)
- `run_static_gate(conn)` avec InvariantViolation strict
- Boucle-de-soi V0 : `intelligence/self_loop.py` + migration 0018
- P0 sécurité repo privé vérifié
- P1 #1 Drawdown tolerance 75 → **70%** validée
- P1 #2 MU trim 50% (×2) + kill_criteria refondus
- P1 #3 SNOW thèse structurée
- P1 #4 LNG maintenu + tag refiné
- CCJ : reverse scale_in + re-tag PPA-correlated + thesis fixée USD natif
- Phase 4 gate currency + kill_criteria substance (11 violations dette catalog)
- 2 mémoires : `adversarial-pushback-explicit` + `currency-native-invariant`
- Backup + cleanup + push (348M snapshot + 400M libérés)

### 30/05 — Dette P0 résorbée
- Fix trigger ORPHAN trop large (faux positifs AMD/GOOGL "post-orphan rewrite")
- SAF.PA thèse réécrite (5 drivers + 4 kill-criteria fondamentaux)
- **Batch A** : 5 kill-criteria substance refondues (TSLA, AMZN, MP, ENTG, 6857.T) — chacune 5 drivers + 5 kill-criteria fondamentaux
- **Batch B** : 5 currency native (4063.T, 000660.KS, 7011.T, 6857.T, 6920.T) — entry+target+stop convertis JPY/KRW
- **Fix daily_backup_job** : cwd manquait `.parent` → cherchait `bot/scripts/backup.sh` au lieu de `scripts/backup.sh`
- **KNOWN_DEBT_TICKERS_* sets vidés** : test strict, plus de tolérance
- **Recalcul cluster cap post re-tag CCJ** : ballast effectif 17.2% (vs 15% cible), AI cluster 74.6% (vs 70%, +4.6pp en phase construction). **Cible 70% maintenue**.
- Bot redémarré proprement avec caffeinate

### Trades du jour (29/05 chat-driven)
- ALAB 616€ → LNG 616€ (profit-take winner)
- MU 940€ + 920€ (trim ×2, quasi-out) → LNG 250€ + CCJ 667€ → reverse CCJ → LNG 434€ + MP 233€
- 7 ancres contrefactuelles capturées

---

## 🧭 Cadre maître (rappel)

### Les 4 racines (verdict 29/05) — état actuel

1. **Source de vérité unique du book** — ✅ Soudé (book.py + position.py + storage.get_position_view)
2. **Features qui combattent la discipline** — ✅ Soudé (gate fundamental-only + kill-criteria substance)
3. **Mode maintenance permanent** — ⚠️ Phase construction active jusqu'à ~65k€ book (= ~13k€ encore à déployer)
4. **Métriques calibrées pour le confort** — ✅ Soudé (note 88 honnête, drawdown CTA verte, ballast haircut, Solidité refondue)

### Principe directeur

**Tout output non instrumenté est gaspillé.** Chaque output doit recevoir un outcome mesurable qui se réinjecte. La moitié des 15 vues échouent ce test. À couper progressivement post-10/06 quand on aura la mesure pour arbitrer.

### Calendrier discipline

- **Maintenant → 10/06** : usage > code. Brier est l'asset, pas les commits.
- **10/06** : batch resolution. Moment de vérité.
- **Post-10/06** : Niveau 2 si Brier valide. Path 5 (privé) avant Path 6 (public).
