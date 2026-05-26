# Session State — mes-bots-finance

**Last updated**: Day 15 close, 2026-05-21 21:17

## Mode actuel
**High Standard / Solidification** — Path 5/6 strategic target.
TG canonical rollout active. NO new features.

## Bot state
- PID 2608 alive, polling, scheduler 27 crons
- Tests: 335 passed
- ruff + mypy clean on touched files
- 313 tickers universe (audit pending)

## Day 15 highlights (9 ships)
1. Phase B /portfolio
2. Phase D /thesis dispatcher (5-helper, 9 sub-actions)
3. 21-theses data fix
4. Substack 2 editorial passes
5. TG canonical spec doc
6. /brief canonical
7. KPI #2 timer fix
8. /recent_8k canonical
9. /asymmetry portfolio canonical + currency fix

## Day 16 priorities (empirical, surfaced by canonical)
1. COHR 🔴 STOP NEAR resolution
2. ALAB ratio 0.40 + 25.6% P&L anomaly
3. NVDA 4 officer departures 105d + 2 unresolved decisions
4. 4 orphans c1 J+30 (AMD/GOOGL/SAF.PA/TSLA)
5. Concentration policy AI_compute 67%

## Entry point Day 16
1. cd /Users/olivierlegendre/mes-bots-finance && source venv/bin/activate
2. ps auxww | grep "bot.main" | grep -v grep   # L39: NOT pgrep -f python.*
3. Read HANDOFF.md Day 15 final close
4. Action Tier S priority order above

## Documents canoniques (entry order)
1. HANDOFF.md (Day 15 final close section = primary entry)
2. CONVENTIONS.md L37+L38+L39
3. TODO.md Day 15 closure
4. PHILOSOPHY.md High Standard
5. docs/conventions/telegram_output_canonical.md (TG spec)

## Carry-forward (not urgent)
- TG canonical P1: /portfolio, /positions, /digest
- shared/display.py canonical refactor (~5-10h)
- Universe pruning audit (313 vs 178)
- Substack SK hynix fact-check
- Canonical spec doc amendment ("color = external signal only")


## 2026-05-23 — Brier root-cause fix + dashboard hardening (tag day15-brier-dashboard, commit bbe74e4)

### Shipped (live, gates verts, committe + tagge)
- Resolution blindee: dropna `.T` dans shared/prices.py::get_current_price (tickers Tokyo renvoyaient nan) + garde nan sans import (px != px) dans intelligence/learning.py::resolve_due_predictions. Empeche nan final_price / faux "neutral" dans le batch. Bot redemarre propre, live sur cron resolve 9h.
- BRIER CAUSE-RACINE: probability_at_creation n'etait qu'un snapshot de la credibilite source (143/152 = 0.5) -> erreur de categorie (confiance source != P(cet appel correct)) -> Brier vide-mais-vert. Remplace par shared/math_helpers.py::estimate_probability(score, cred, signal_type, impact_magnitude) dans [0.50, 0.72], cable dans shared/storage.py::insert_prediction (SELECT elargi a score/type/impact). 4 tests Hypothesis. Cadre honnete: PRIOR APPRENABLE, pas verite calibree -- son job est de rendre le Brier informatif/iterable. Effet sur predictions FUTURES uniquement (id >= 158).
- Premier test du dashboard: tests/test_render_smoke.py -- render() end-to-end (couvre les 8 sections, marqueurs nav + payloads HEIMDALL). ~30 patches sans test -> filet pose.
- Re-tag narratives: AMD/ALAB/COHR -> AI_COMPUTE_2026, SAF.PA -> EU_DEFENSE_2026, GOOGL/TSLA -> MAG7_2026 (nouvelle categorie). 2 bacs admin morts. Reversible (edit notes). Effet de bord exact: AI Compute grossit -> Concentration EXCESSIVE 80%.

### Etat track record (HONNETE)
- ~0 exploitable. Les 151 ouvertes (dont cluster de 40 du 10 juin) gardent prob = 0.5 -> Brier vide-mais-VERT. NE PAS PUBLIER.
- Vraie courbe a partir des id >= 158, exploitable ~fin juin.

### Git / hygiene
- Backlog non committe rattrape (serve.py + snapshot.py jamais committes, render.py patche multi-sessions, 33 .bak en guise de VCS). Checkpoint unique, reprendre l'atomique ensuite.
- Secrets HORS historique: git ls-files credentials.json token.json vide -> safe pour push GitHub.
- 0 .bak restant, arbre propre.

### Watch / next
- Verif prob prod: predictions id >= 158 avec prob != 0.5 = integration confirmee.
- ~27 mai: 1eres resolutions, verifier final_price sains.
- Vue calibration (surface produit Path 6): batir quand >= 10 predictions prob-differenciee resolues (~fin juin). Reliability diagram + Brier-over-time + ledger. Trancher la: neutral exclu vs binaire-0.5.
- Concentration EXCESSIVE 80% AI Compute (> 30% cap, 6 lignes > 5%): decision politique en attente.
- Logo: parke candidat A (heaume-onde), a integrer dans render.py .logo svg quand choisi.
- Classifieur 8-K met tout Item 5.02 = HIGH (bruit signal->prediction): gele observation.

---

## 2026-05-25 — Dashboard hardening + migration VPS (Phase 0). Reprise ~28/05.

### Shippe (dashboard/render.py, tout pousse, HEAD d5c9fcf)
- Ancres anti-biais theses, fusion Concentration 3-axes, sizing->VIX, gap bidirectionnel (tenues only).
- Purge ~95 LOC dead-code (leaflet/geo/runes).
- Source de prix UNIQUE via _cached_price_eur (theses + pnl): le dashboard ne lit plus le cache mort theses.last_price; fetch frais throttle (TTL 840s).
- Boucle close: render n'ecrit que si contenu change + poller Last-Modified (reload client sur vrai changement, etat nav preserve par le hash). serve.py deja autonome (regen 60s, hot-reload, fault-isole).

### DB (non versionne)
- target_partial backfill: 28 theses tenues (formule entry + 0.625*(full-entry)).
- TSLA enregistree c4: entry 380.84 / stop 285.63 / cible 609.34 (+60%) / palier 523.65. Drivers = robotaxi/FSD + supply-chain (SpaceX/Grok/X exclus: pas des actifs TSLA). Backups data/bot.db.bak_*.

### Findings
- SK Hynix EUR1147 = CORRECT (000660.KS @ 1.94M KRW, near ATH, x10 supercycle HBM). PAS un bug. Plus grosse ligne c5 -> surveiller biais FOMO/ancrage.
- 2 bugs monitoring (deferred): uptime.log fait confiance au heartbeat <1h (aveugle aux morts recentes); pgrep "python" minuscule rate le binaire "Python" majuscule -> faux DOWN + pkill inoperant.
- price_monitor = job d'ALERTE (hour=14-22 mon-fri Paris), pas source de prix; ne couvre jamais l'Asie en seance.

### MIGRATION VPS — Phase 0 FAITE, Phase 1 dans 3j
- Repo deploy-ready, pousse. deploy/ versionne: env.example, heimdall-bot.service, heimdall-serve.service (systemd user, linger, Restart=always), PROVISION.md.
- Exposition: SEUL l'OAuth Google (credentials.json+token.json) etait dans le Projet -> rotater au cutover. .env jamais partage. Secrets jamais committes (git clean).
- REPRISE: provisionner Hetzner CAX11/CX22 Ubuntu 24.04 + PAT GitHub -> suivre deploy/PROVISION.md.
  - GATE = etape 4 (test yfinance depuis la box). Attendu EUR: NVDA~185, 4063.T~39, 000660.KS~1147. Si 429/None -> proxy residentiel ou source alt AVANT de continuer.
  - Cutover: tuer bot Mac (pkill -fi "Python -m bot.main") AVANT bot box (Conflict getUpdates). serve reste 127.0.0.1, dashboard via ssh -L 8000:localhost:8000.

### Residus (post-migration)
- 8 positions tenues sans alerte stop/cible (check_thesis_triggers ne les itere pas) — trou discipline ~1h.
- Fixes monitoring (heartbeat-age, pgrep casse).
- Dette schema: 2 colonnes cible (target_price vs target_full).
- composite stress non cable au sizing (VIX seul).
- VRAI goulot: VALUE_LOG quasi vide -> USAGE quotidien jusqu'au 10/06 (KPI#2 batch ~45 predictions).


---

## 25/05/2026 (suite) — Concentration policy + readout dashboard

**2 commits**: `df89dc8` [policy] cap cluster 57% + caps par conviction · `d33fa9c` [dashboard] readout cluster vs cap (page Concentration). HEAD = d33fa9c, origin/main aligne, tree clean.

**Policy ratifiee (option a)** — source de verite `config.yaml > concentration`:
- `cluster_max_pct: 0.57`, `assumed_cluster_shock: 0.35` -> 0.57*0.35 = 0.1995 < `drawdown_stop_pct 0.20` (cale juste sous le stop).
- `line_cap_by_conviction`: c5 8 / c4 6 / c3 4.5 / c2 3 / c1 2 (%). `style.position_max_pct` 0.05 -> 0.08.
- Cluster `semis_ai` = 28 tickers (semis/equip/EDA/memoire/connectivite). Hyperscalers + power-for-AI hors cap.
- Enforcement: MANUEL via dashboard jusqu'au 10/06 ; post-KPI#2 -> `risk.validate_enabled: true` + wiring `risk_engine.validate()` (line cap + somme cluster, WARN).

**Etat empirique**: book ~51.5K EUR, 28 lignes. Cluster semis_ai ~73% (cible 57%). 4 c5 >5%: 4063.T 8.5 / ASML.AS 8.2 / TSM 7.7 / SNPS 7.0.

**OUVERT — usage, a executer (PAS du code)**:
- Rebalance ~8K EUR semis -> drivers decorreles (healthcare/financials/defense/crypto, deja univers, non tenus).
- ALAB: enregistrer la prise d'1/3 (palier 257.81 EUR franchi, alerte LEGITIME confirmee EUR-canonique). Flags anchoring/loss_aversion du risk_check #7 = FAUX (prix mal source).
- 6920.T: reconcilier la these AVANT vente. risk_check #8: these longue c2 (cible 412) vs vente baissiere = incoherent. Update/close, ou cite la data, ou ne vends pas.

**Finding tech (defer)**: le risk_check ne s'injecte PAS le prix live -> raisonne aveugle sur prix-vs-palier (ALAB #7 a cru "sous le palier" alors qu'au-dessus). Fix candidat: passer get_current_price_in_eur dans le contexte du prompt. Freeze-safe (advisory read-only).

## Session 25/05/2026 — ADR-006 (target_partial cible-only) + hygiène suite

### Shipped — 6 commits, tous poussés, suite 351 verte
- **ADR-006** : profit-take déclenche UNIQUEMENT sur la cible (`target_full`). `target_partial` débranché de tous les triggers.
  - c1 `75ee554` : alerte Telegram price_monitor + `docs/adrs/006-target-partial-cible-only.md`
  - c2 `c6aa888` : thesis revisit + shadow main → `target_full` ; invariant rejeté retiré
  - c3 `51065a6` : dashboard — bloc "cibles partielles" + nudge proximité supprimés (message anti-biais "laisse courir" conservé)
- **Découverte clé** : `target_partial` était AUTO-DÉRIVÉ (ratio ~0.86/0.875 sur 28 thèses), pas saisi à la main. Bug fleet-wide — le palier était franchi AVANT la cible → nag "vends ta partielle" sur les winners = biais vend-trop-tôt mécanisé et amplifié. La note mémoire "NULL sur 33 actives" était périmée.
- **2 reds soldés** : render_smoke (navs alignés sur l'IA réelle, `86247b3`) ; test_sizing (cap lu depuis config — live 0.08, snapshot 0.05, le code était correct, `0647466`).
- Findings instrumentés `7815c08`.

### Reste — hors scope, basse urgence (moteur ignore déjà le champ)
- Cleanup C : null-out des 28 `target_partial` dérivés (**LOCALISER le dériveur d'abord** sinon il re-remplit) + arrachage asymmetry/journal/pre_mortem/risk_manager/storage/handlers + branche morte `_format_alert`. Résidu cosmétique : le champ reste affiché inerte dans le /thesis card Telegram + asymmetry.

### Next session — bascule MATIÈRE, pas hygiène
- Diag : `pgrep bot.main` ; `tail uptime.log` ; `predictions WHERE outcome_evaluated_at IS NULL` (count + min/max target_date).
- Calendrier : ~10/06 batch KPI#2 (45 prédictions) ; ~16/06 orphans c1 (AMD/GOOGL/SAF.PA) ; mi-06 universe pruning.

## Day 15 — 25 May 2026 — Boucle d'apprentissage auditée bout-en-bout + bras aller réparé

### Shipped
- **commit 89a43e0** [fix] estimate_probability recentré: pivot score 6→3, pente 0.02→0.032 (1 ligne).
  - Bug: 148/156 prédictions à proba 0.5 défaut → Brier plancher-né 0.25 → KPI#3 (<0.20) inatteignable, boucle sur point fixe dégénéré à 0.5. Cause: le terme score ne s'activait qu'au-dessus de 6, mais la distribution réelle centre à ~4.
  - Spread vérifié 0.50→0.66 selon force du signal. test_dynamic_range_over_support ajouté (l'invariant d'amplitude que les 4 tests existants — bornes/monotonie/ordre/plancher — ne capturaient pas: une constante 0.5 les passait tous).
  - Bot redémarré sur code neuf (PID 35449).

### Carte vérifiée de la boucle
- **Bras aller** (signal → prior différencié): RÉPARÉ.
- **Bras retour** (résolution → crédibilité → re-rentre via (cred-0.5)*0.4): CÂBLÉ, DEUX writers:
  1. Immédiat/résolution — learning.py:153 update_source_credibility(delta). OUTCOME_DELTA +0.03/−0.05/0, asymétrique, amplitude saine (clean). Tire dès 1ère résolution (~27 mai), PAS gardé min_n.
  2. Mensuel — recalibrate_source_credibility_from_hitrate(min_n=10), storage:1018, recompute depuis AVG(brier).
- **Trou C** (reliability diagram): INEXISTANT. Table `calibration` = fantôme (0 producteur/consommateur/rendu). = asset Substack à construire.
- État: 157 prédictions (156 ouvertes, target 27mai–20juil), crédibilités encore toutes 0.5 (bras alimenté aujourd'hui, pas encore tiré). 352 tests verts. Contrainte = TEMPS-jusqu'aux-résolutions, pas code. NO new features.

### Décisions ouvertes (prochaines sessions, PAS urgent, sans-data-encore)
- **ADR — réconcilier les 2 writers crédibilité**: incrémental catégoriel (hitrate) vs mensuel (Brier) = objectifs divergents, peuvent tirer en sens inverse. Trancher le sens de « crédibilité ». Penchant: Brier.
- **Construire C**: requête sur predictions résolues, bucket par probability_at_creation → hit-rate vs diagonale. Zéro stockage neuf. 7e vue dashboard ou /calibration. Trigger N≥~30 résolues.
- **Rider hygiène (~15min)**: storage.insert_prediction docstring menteuse + except silencieux (CONVENTIONS rule 6). OUTCOME_DELTA doc "2x" vs réel 1.67x. KPI_DASHBOARD.md cassé (colonne morte outcome_evaluated_at; règle coupe sur "signaux" pas résolues).
- **Pruning sources — revue 3 mois = DÉBIT pas précision**: Stratechery $15 non-Tier-S = candidat coût-vs-matière. Précision-pruning = 6-9 mois (N≥~25 résolues/source).
- Note: bande neutre ±5% → ~½ des résolutions ne bougent pas la crédibilité → feedback effectif ~½ nominal.

### Day 15 — suite (25 mai, après-midi)
- **ADR 007 shippé** : doc fa1b58e + impl 27cc018. Crédibilité = Brier-mono-autorité ; application incrémentale catégorielle retirée (delta toujours stocké pour audit).
- **target_partial — cleanup visible fait** : 28 valeurs actives nullées (backup data/bot.db.backup_avant_null_target_partial_*). Disparaît de tous les affichages (lecteurs gardent sur None). price_monitor vérifié : règle rejetée MORTE (89/123/134 = formatter inatteignable, aucun trigger "partial" ne survit). ADR-006 correctness confirmée.
  - À FROID (dead-code, sans effet visible, PAS urgent) : retirer branches mortes formatter price_monitor + debrancher lecteurs (asymmetry ×3 contrat, journal, pre_mortem [wart "$None"], risk_manager, affichage thesis, query dashboard) + FERMER le vecteur de réintro (EDITABLE_NUM misc.py + param thesis_crud). D'ici là : NE PAS set target_partial à la main.
- **Shadow — spec VERROUILLÉ, build à froid** : main=cible-only / conservative=trim-tôt (biais #1) / aggressive=hold-past-cible (biais #2). Test empirique « discipline vs mes 2 biais ». Output time-gated. Patch compute_exit_variants à écrire.
- Restart fait pour rendre estimate_probability + ADR-007 live avant les résolutions du 27 mai.


## Day 15 suite-2 — Concentration policy + frein (2026-05-25)

**Commits** : a6e51c0 (plan canaris) · 975b30c (ADR 008) · b2d8d83 (ADR 008 amend mécanique frein).

### Décidé & gravé
- **ADR 008 — concentration** (`docs/adrs/008-concentration-policy.md`, Accepted) : 67% AI_compute = pari concentré **assumé** (pas dérive). Cap position = **entrée/cost-basis, pas MV** (anti biais #1 — un cap MV vend les gagnants). Plat **non-tiéré** jusqu'à validation Brier. Plafond narratif **30% → 75%** (config.yaml, max dur, garde-fou biais #2). Queue acceptée yeux ouverts : winter sévère ≈ -€13-14K / **-33% portfolio** (corrélation intra-cluster → 1). Invalidation niveau-portefeuille : capex hyperscalers ↓ 2T / roll HBM / air-pocket sovereign-AI.
- **Mécanique frein (corrigée, vérifiée)** : gates drawdown portfolio (`reduce 0.08`, `stop 0.20`) = gardes **à l'entrée**, ne vendent rien, **inertes** (validate() non câblé). Aucun trigger de sortie auto. Sortie réelle = stops par thèse (alerte price_monitor) → manuel.

### Conclusion frein (parké, post-observation, behavior-affecting)
Le frein manquant n'est **pas** un trim-auto-sur-drawdown — ce serait mécaniser le biais #1 au niveau portfolio (vendre le bas de la volatilité cyclique semis, whipsaw). Drawdown = bruit ; rupture de thèse = signal. Bon frein en couches : (a) stops par nom [existe, alerte] + (b) **moniteur d'invalidation thèse AI_compute** keyé sur observables ADR 008 §7, sur ingestion existante [à construire]. = l'item brake réel.

### À froid (rien d'urgent — contrainte liante = temps→résolutions du 27 mai)
- Moniteur d'invalidation AI_compute (frein réel ci-dessus).
- risk.validate() câblage : poids **cost-basis**, enforce 5% entrée + 75% narratif + drawdown gates. Plus bloqué par la policy (ADR 008 la fixe).
- Triage des 6 over-cap : entry-oversized (trim) vs appreciation (garde+stop), via /positions + /tiers, apply manuel — à classer ensemble.
- Canaris (`docs/plans/loop_health.md`) : Step 0 (C2) buildable maintenant, C1 dort jusqu'à N≥20, C4 ~été, C5 jamais. Chaque canari ship avec son test broken-trips.
- Hygiène (inchangé) : target_partial dead-code removal + fermer vecteur ré-intro ; insert_prediction docstring + silent-except rule-6.

### Discipline
Forme gravée (3 docs). La matière n'avance qu'avec les résolutions. Ne pas laisser les plans devenir un prétexte à coder de l'observabilité au lieu d'attendre la data.


## Day 15 suite-3 — Sizing policy + bugs ops (2026-05-26)

**Commit** : e02bd56 (ADR 008 amend. 1).

### ⚠️ SUPERSEDED par suite-4 (bas du fichier) — Décidé & gravé — ADR 008 Amendement 1 (cap tiéré conviction + cadence)
- Book **conçu délibérément** (15–23 mai, 28 lignes, sizing conviction + chokepoint) — pas de la dérive. Corrige le cadrage « surtaille = erreur ». Cap plat (point 3) incohérent avec un book intentionnellement tiéré → superseded.
- **Cap tiéré cost-basis à l'entrée** : c5=8 / c4=6 / c3=5 / c2=4 / c1=3. **Gate de nombre ≤20% en c5** (KPI inflation → cap dur ; conviction ordinale). Sous le narratif 75%. Caveat corrélation documenté (chokepoints = même chaîne semi → top 8% yeux ouverts). Tiers validés par Brier à N≥30.
- **Cadence** : caps bindent le capital *neuf* maintenant (pas d'ajout sur over-cap sans override loggé) ; book grandfathered ; **1ère découpe structurelle J+30 = ~22 juin** (dernière ligne 23 mai), consolidée avec orphan-c1 (~16 juin) + pruning. Exception permanente : sorties risque (invalidation thèse + stops) jamais gelées.

### État portefeuille (snapshot 2026-05-26)
- 28 lignes, cost-basis €42 141 / MV €51 429 (+22% global — régime favorable ≠ conviction validée).
- Seul outlier au-dessus du c5 : Shin-Etsu (4063.T) 10,7% cost-basis (8,6% MV, -1,8%) → 1er point d'agenda du 22 juin.
- Triage **résolu** : pas de trim maintenant → 1ère découpe 22 juin.

### Bugs ops découverts (à froid, PRIORITÉ readout)
1. **Telegram output cassé sur handlers longs** (`/brief`, `/positions`, `/tiers`) : data rassemblée OK, `sendMessage` final échoue en silence (no error handler). Couche sortie → sûr à réparer hors observation. EN COURS. Fix = error handler Telegram + chunk >4096.
2. **Pattern `pgrep "python.*bot.main"` rate le Python framework (P majuscule)** → gravé dans PROCEDURE_URGENCE + QUOTIDIENNE + probablement le checker uptime → KPI #1 suspect. Fix → `bot.main`. A causé le faux « bot down » + masqué 2 zombies (Conflict getUpdates).

### Bot
- Instance unique PID 37118 (après kill de 2 zombies). Crons OK, boucle de fond intacte. Seul le readout Telegram est KO.


## Day 15 suite-4 — Réconciliation concentration + correction bugs ops (2026-05-26)

**⚠️ Supersede les sections concentration de suite-2 et suite-3** (faites à l'aveugle, readout `/portfolio` cassé, contredisaient la policy enforced).

**Commits** : 837aefb (retrait doublon ADR 008 + revert config + ADR 009).

### Ce qui a été défait
- `008-concentration-policy.md` (mon doublon) **retiré** : il faisait du cap position tiéré l'invariant liant, alors que `008-cluster-cap-grandfather.md` (Accepted) avait rétrogradé le cap position en soft et fait du **cluster** l'invariant. Mauvais axe, construit aveugle.
- config `narrative_max_pct 0.75 → 0.30` **revert** : le bot n'enforce pas ce knob.
- Salvage → `009-conviction-soft-tiers-and-brake.md` : tiers conviction recadrés en **alertes soft subordonnées** au cap cluster + clarification frein. Cadence J+30 abandonnée (revue gouvernée par le trigger J+28 d'ADR 008).

### Ce que le CODE applique aujourd'hui
- `positions.py CLUSTER_CAP_PCT = 35.0` (cluster, parsé `theses.notes sector_thesis_id:`). Position cap soft. ADR 009 = alertes soft tiérées par-dessus (non liant).
- Aucun enforcement auto (`validate()` non câblé) → manuel/visuel jusqu'au wiring.

### ✅ Contradiction RÉSOLUE par ADR 010 (2026-05-26) — cap cluster = 35% risk-adjusted, config aligné (0.57→0.35). Contexte préexistant ci-dessous conservé.
- config `cluster_max_pct: 0.57` — ratifié **Day 14** (`df89dc8`, « option a, source de vérité ») par dérivation risk-budget (0,57×0,35 ≈ 0,20 stop).
- ADR `008-cluster-cap-grandfather` + code `positions.py` = **35%** (comportemental).
- `/portfolio` affiche « max sizing 8% » vs ADR « 5% soft ».
→ Le code applique 35 ; SESSION_STATE Day 14 dit que 0,57 lie. Lecture plausible : code resté en arrière de la dernière décision doc (ou l'inverse). **Deux "sources de vérité" concurrentes — un seul doit rester.** Non urgent (rien n'enforce auto avant 10/06), mais bloquant pour le câblage validate().

### Correction bug ops #1 de suite-3 (diagnostic FAUX)
« Telegram cassé sur handlers longs + chunk >4096 » = **erroné**. Vraie cause :
- 2 instances zombies → Conflict getUpdates (Telegram = 1 poller) → réponses coupées. Masqué par le pattern pgrep cassé (`Python` framework, P majuscule).
- `/positions` et `/tiers` **ne sont pas des commandes enregistrées** (registry : `portfolio`, `position`) → ignorées en silence. Mauvais nom, pas un bug.
- `/brief` fonctionne → pas de souci de longueur, **chunk >4096 inutile**.
- Fait : error handler Telegram (`6bc2438`) + kill 2 zombies + instance unique.
- À froid (CORRIGÉ 26/05) : le checker live (`crons/uptime_monitor.sh` + `scripts/bot_health_check.sh`) utilise DÉJÀ `pgrep -fi` (§16) → PAS cassé, KPI #1 OK. Le « → bot.main » était une mauvaise direction (fix §16 = `-i`, pas un changement de pattern). Résidu corrigé : PROCEDURE_QUOTIDIENNE:11 (+ `-i`) + CONVENTIONS:397 (snippet mutilé). Sites runbook stale (`-f` sans `-i`) = hygiène optionnelle, non urgent.


## Day 15 suite-5 — ADR 010 + decouverte line_cap_by_conviction (2026-05-26)
- **ADR 010** : contradiction cap cluster 35-vs-57 RESOLUE -> 35% risk-adjusted (choc underwrite >=57%) ; config aligne (cluster_max_pct 0.57->0.35, assumed_cluster_shock 0.35->0.57) + commentaire corrige ; code deja a 35 (positions.py). Commit b785035.
- **/!\ Decouvert, a froid** : config `concentration.line_cap_by_conviction` (c5=8/c4=6/c3=4.5/c2=3/c1=2) DIVERGE d'ADR 009 (c5=8/c4=6/c3=5/c2=4/c1=3). ADR 009 ecrit sans voir ce bloc config (meme blind-spot que le reste de la session). Commentaire config dit "remplace style.position_max_pct" -> statut soft-vs-liant ambigu vs ADR-008 ("5% soft"). A reconcilier a froid : trancher chiffres (4.5/3/2 vs 5/4/3) + statut. Basse urgence : non-wired, purement documentaire.


## Day 15 suite-6 — Dashboard modernisation + sizing cible-taille (2026-05-26)

**Dashboard servi en HTTP (workflow durable).** `dashboard/serve.py` (stdlib, pas FastAPI) tourne déjà — port 8000, hot-reload render.py sur mtime, regen auto (`HEIMDALL_REFRESH`, défaut 60s), `_PX_CACHE` chaud entre cycles. **Ouvrir `http://127.0.0.1:8000/dashboard.html`, plus de `file://`** (l'auto-reload ne marche qu'en HTTP). Lancer : `python3 -m dashboard.serve`. Santé : `tail dashboard/serve.log` (`regen Xs`, pas `FAILED`). Throttle yfinance → 30 min : `_PX_TTL=1800.0` (render.py l.50) = knob anti-ban, pas l'intervalle de regen ; tous les panneaux via `_cached_price_eur`.

**Visuel (commités).** Donut secteurs interactif SVG (`40415d0`) · distline OKLCH fin (`8f381dd`) · header sans emojis + jauge surchauffe fine.

**Sizing cible-taille (commité `90b0456`).** Par position : `alléger −X € → cible taille Z%` / `renforcer +X € → cible taille Z%` / `✓ cible taille Z%`, sous la barre sizing ; barre prix en hero pleine largeur. Modèle = conviction normalisée `cible_i = cap(conv_i)/Σ(caps tenus)×100` (somme à 100%, recalcul live, sous les caps, auto-financé). **/!\ Dépend de `line_cap_by_conviction` (4.5/3/2)** — voir ci-dessous. **Règle d'usage : `alléger`/`renforcer` = rightsize, jamais exit** ; trimmer un winner au-dessus de sa cible-taille peut nourrir le biais #1 si lu comme une sortie ; add seulement si thèse intacte.

**Axis 1 (nudge thèse bidirectionnel) — construit puis REVERTÉ (data-driven).** Branche crypto FOMO (biais #2) morte (0 crypto tenu/thèse en DB) ; gate winner `frac<75` mal-calibré (étouffe le nudge dans la zone 75-95%). Leçon : le vrai levier biais #2 est en AMONT (thèse crypto avec stop/cible le jour d'une réexposition), pas dans render.py.

**Élevé par cette session (documentaire → load-bearing).** Réconcilier `line_cap_by_conviction` 4.5/3/2 (config, désormais lu par le sizing) vs ADR 009 5/4/3, + statut soft/liant. Impacte directement les € de cible-taille ; cohorte c3 (19 pos) la plus exposée à l'écart.

**Vrai fond non-traité (la polish ≠ track record).** 27 mai : 1res résolutions informatives · 10 juin/J+28 : batch KPI #2 + revisite ADR-008 · mi-juin : pruning univers + orphelins c1.

## suite-7 close (26/05/2026)
- Crypto OUT (stock-only) : preds ETH/LINK (id 87/88) + 12 signaux sources crypto supprimes ; CRYPTO_DENY guard a la creation (learning.py auto_register). Axe biais #2 (anti-hold crypto) en pause — 0 holding crypto.
- P2 line_cap CLOS : reconciliation deja faite par ADR 009 (config 8/6/4.5/3/2 = source unique, soft, subordonne au cap cluster 35% liant). Defect cache regle : _concentration verdict folde le gouverneur cluster (>=35% -> ELEVEE, >=50% -> EXCESSIVE) ; CLUSTER_CAP->NARRATIVE_CAP ; axe dominant = these (etait mislabeled "secteur").
- Risk #1 NON audite : resolve_due_predictions L117 / storage.get_due_predictions L664 — backfille-t-il le past-due si downtime a 9h ?
