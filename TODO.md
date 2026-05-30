# TODO — PRESAGE (mes-bots-finance)

**Refresh** : 30 mai 2026 soir (post Phase 4 colmatage + MU fix)
**Mode** : Phase construction + Observation Brier jusqu'au 10/06 (J-11)
**Archives** : `/tmp/TODO_pre_refresh_*.md` (historique des refresh)

---

## 🟢 ÉTAT SYSTÈME — Tout vert

- **Gate `run_static_gate(conn)` : 0 violations** (dette KNOWN_DEBT vide)
- **407/407 tests verts** (incluant 7 e2e nouveaux : decision→cf, book view, passerelle, scoring, gate, audit, self_loop)
- **Bot tourne** : caffeinate -dimsu, détaché init (survit sleep + ferm. shell)
- **Backup quotidien** : `scripts/backup.sh` corrigé, test manuel OK (25M tarball + DB 9.9M + integrity)
- **6 ancres contrefactuelles actives** en attente J+30 (cf#55 MU voidée post-fix)
- **8 commits poussés** sur `origin/main` aujourd'hui

---

## ⚠️ Risque silencieux identifié (post-MU fix)

Le bug MU (qty 0.119 au lieu de 1.224) est resté **24h+ sans alerte**. Tu l'as
vu visuellement, pas le système. Causes :
- Aucun cross-check qty DB vs broker à intervalle régulier
- Trims fantômes (1 saisi, 0 exécuté) passent le gate (toute qty > 0 est valide)
- Le dashboard ne marque pas une position "anormalement petite" vs cost_basis

**À envisager post-10/06** : un check hebdomadaire eur_value DB vs Trade Republic (manuel ou import). Pas critique avant que les fondations Brier soient validées, mais à ne pas oublier.

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

## 🔒 SÉCURITÉ — auditée 30/05/2026, binairement OK

Audit complet 30/05 (chantier #12 de la session) :
- Repo GitHub **PRIVÉ** (`Conscious-Bot/mes-bots-finance`) ✓
- `.gitignore` couvre : `.env*`, `*.token`, `token.json*`, `credentials.json`, `oauth_tokens/`, `client_secret*`, `service-account*` ✓
- Tous fichiers sensibles locaux (`.env`, `credentials.json`, `token.json`, `.env.backup_*`, `.env.save`) sont **IGNORED** par git (vérifié via `git check-ignore`) ✓
- `.env.example` tracké comme template avec placeholders (`sk-ant-xxx`, `000000:xxx`, etc.) ✓
- Git history scan 7 patterns : `sk-ant-` (2 = placeholders template), `ghp_` (0), `xoxb-` (0), `BEGIN PRIVATE KEY` (0), `Bearer + 30+ chars` (0), `ya29.` (0), `AKIA` (0) — **aucune vraie clé exposée** ✓
- [ ] **Rotation OAuth Google** — runbook prêt, déclencheurs inactifs (pas encore lancé)

L'item "hygiène secrets faite une fois" du PLAN_ACQUIHIRE est validé binairement. Re-audit si on ouvre le repo en public.

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

### 30/05 soir — Audit pipeline Phase 4 + MU fix
- **Cascade colmatage** (commit bf8fb18) : migration 0020 drop 4 tables fossiles, alerte Telegram gate-red au startup, asymmetry rounding 2→3 décimales, test e2e pipeline (7 tests).
- **Cleanup 51 rows TEST_SL_*** + 10 cfr liées (pollution biaisant `measure_bias`)
- **MU fix** (commit 49acd34) : qty 0.119 → 1.224 (€99.5 → €1020.10). Trim fantôme du 29/05 supprimé (event #4 DELETE, decision #23 [VOIDED], cf#55 conservée append-only + filtre dans `measure_bias`).
- **2 failures découvertes + corrigées** : asym rounding (round 2→3) + patterns table restaurée (decision_copilot la query, code dead-path mais SELECT doit pas crasher).

### 30/05 nuit — Arc V2 calibration (10 itérations, 29 commits)
Audit pré-10/06 a révélé que les 40 prédictions du batch sont toutes dans probabilité [0,608-0,658] (mono-bucket). Pivot complet sur l'élicitation + sourcing + tests. **Pattern itéré 10 fois : la conclusion est toujours en avance d'un cran sur la preuve.**
- **SIGNAL_SCORER_V2** : prompt 3 étapes (base rate / ajustement / anti-ancrage), enforcement weak→watch + sémantique P(call correct), intégré dans `learning.auto_register_predictions`. Decision log `docs/decision_logs/01_calibration_unanchored.md` (10 itérations).
- **Wire SEC EDGAR primary data** : `intelligence/edgar_signal_wire.py` + `shared/edgar_exhibits.py`. 8-K + insider buy clusters → V2 → predictions. Forward-only strict. Source dédiée `SEC EDGAR 8-K` + `SEC EDGAR Insider Cluster` (cred=0.85). DoD vérifiée e2e : NVDA Q1 FY27 8-K → V2 0.750 bullish strong. Fixture régression `tests/test_edgar_exhibits.py` (marker slow).
- **Consolidation `storage.DB_PATH`** : bug pollution prod attrapé par test fail (monkeypatch _DB_PATH n'affectait pas DB_PATH). Fix via `__getattr__` module-level. Test régression `tests/test_db_path_alias.py`. Premier fix (alias statique) n'était pas un fix — itéré 9e fois sur le fix lui-même.
- **ADR 012 — severity classifier soft-deprecated** : V2 sur contenu réel discrimine mieux que mapping Item-codes. Classifieur conservé pour alerting low-latency, déprécié comme mesure evidence_strength.
- **Dry-run résolution J-11 (iter 10)** : Brier attendu 0.295, accuracy 38%, pire qu'un prior 0.5 trivial. **Le batch 10/06 NE doit PAS être publié comme track record.** Le mécanisme tourne (40/40 prix fetched, dedup OK) — V1 mauvais comme prédit.
- **3 posts canoniques bilingues** dans `posts/` (Phase A juillet en grande avance) : post_01 calibration_unanchored, post_02 comment_that_lied (SK Hynix), post_03 dry_run_eleven_days. ~700-900 mots FR + EN chacun.
- 414/414 tests verts. Bot tourne PID 84607 caffeinate avec nouveau code chargé.

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

### Calendrier discipline (REVISED 30/05 post-dry-run)

- **Maintenant → 10/06** : usage > code. **MAIS** : V1 mauvais déjà mesuré (dry-run Brier 0.295). Le 10/06 n'apporte pas de validation calibration positive — sert de baseline V1 figé pour future comparaison V2. Le "moment de vérité" devient **« est-ce que je publie quand même le mauvais chiffre comme prévu, ou je me trouve une excuse »**.
- **10/06** : batch resolution V1. À publier honnêtement (post_03 déjà drafté pour ça). Brier ~0.295 attendu, ne PAS maquiller. Le **mécanisme** tourne (vérifié dry-run), c'est V1 qui est mauvais comme prédit.
  - **9h00** : `daily_resolve_job` tourne automatiquement. Telegram envoyé avec counts (correct/incorrect/neutral) mais SANS Brier moyen.
  - **9h05** : lancer manuellement `python -m scripts.post_resolution_brier_report 2026-06-10` pour obtenir Brier + dedup cluster + warning mono-bucket. C'est ce chiffre qui compte pour la calibration.
- **Post-10/06** : observer les cohortes V2 qui s'accumulent (wire 8-K + insider clusters actifs). Première comparaison V1 vs V2 nécessitera ~2-3 mois de N V2 suffisant.
- **Path 5 / 6** : différer jusqu'à avoir N V2 suffisant pour calibration plot publishable (post-août probablement, pas 10/06).
