# Session State — mes-bots-finance

**Last updated**: Close 2026-06-01 (wire B2 + Pile 1.1 + audit cleanup)

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
- Premier test du dashboard: tests/test_render_smoke.py -- render() end-to-end (couvre les 8 sections, marqueurs nav + payloads PRESAGE). ~30 patches sans test -> filet pose.
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
- Repo deploy-ready, pousse. deploy/ versionne: env.example, presage-bot.service, presage-serve.service (systemd user, linger, Restart=always), PROVISION.md.
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

**Dashboard servi en HTTP (workflow durable).** `dashboard/serve.py` (stdlib, pas FastAPI) tourne déjà — port 8000, hot-reload render.py sur mtime, regen auto (`PRESAGE_REFRESH`, défaut 60s), `_PX_CACHE` chaud entre cycles. **Ouvrir `http://127.0.0.1:8000/dashboard.html`, plus de `file://`** (l'auto-reload ne marche qu'en HTTP). Lancer : `python3 -m dashboard.serve`. Santé : `tail dashboard/serve.log` (`regen Xs`, pas `FAILED`). Throttle yfinance → 30 min : `_PX_TTL=1800.0` (render.py l.50) = knob anti-ban, pas l'intervalle de regen ; tous les panneaux via `_cached_price_eur`.

**Visuel (commités).** Donut secteurs interactif SVG (`40415d0`) · distline OKLCH fin (`8f381dd`) · header sans emojis + jauge surchauffe fine.

**Sizing cible-taille (commité `90b0456`).** Par position : `alléger −X € → cible taille Z%` / `renforcer +X € → cible taille Z%` / `✓ cible taille Z%`, sous la barre sizing ; barre prix en hero pleine largeur. Modèle = conviction normalisée `cible_i = cap(conv_i)/Σ(caps tenus)×100` (somme à 100%, recalcul live, sous les caps, auto-financé). **/!\ Dépend de `line_cap_by_conviction` (4.5/3/2)** — voir ci-dessous. **Règle d'usage : `alléger`/`renforcer` = rightsize, jamais exit** ; trimmer un winner au-dessus de sa cible-taille peut nourrir le biais #1 si lu comme une sortie ; add seulement si thèse intacte.

**Axis 1 (nudge thèse bidirectionnel) — construit puis REVERTÉ (data-driven).** Branche crypto FOMO (biais #2) morte (0 crypto tenu/thèse en DB) ; gate winner `frac<75` mal-calibré (étouffe le nudge dans la zone 75-95%). Leçon : le vrai levier biais #2 est en AMONT (thèse crypto avec stop/cible le jour d'une réexposition), pas dans render.py.

**Élevé par cette session (documentaire → load-bearing).** Réconcilier `line_cap_by_conviction` 4.5/3/2 (config, désormais lu par le sizing) vs ADR 009 5/4/3, + statut soft/liant. Impacte directement les € de cible-taille ; cohorte c3 (19 pos) la plus exposée à l'écart.

**Vrai fond non-traité (la polish ≠ track record).** 27 mai : 1res résolutions informatives · 10 juin/J+28 : batch KPI #2 + revisite ADR-008 · mi-juin : pruning univers + orphelins c1.

## suite-7 close (26/05/2026)
- Crypto OUT (stock-only) : preds ETH/LINK (id 87/88) + 12 signaux sources crypto supprimes ; CRYPTO_DENY guard a la creation (learning.py auto_register). Axe biais #2 (anti-hold crypto) en pause — 0 holding crypto.
- P2 line_cap CLOS : reconciliation deja faite par ADR 009 (config 8/6/4.5/3/2 = source unique, soft, subordonne au cap cluster 35% liant). Defect cache regle : _concentration verdict folde le gouverneur cluster (>=35% -> ELEVEE, >=50% -> EXCESSIVE) ; CLUSTER_CAP->NARRATIVE_CAP ; axe dominant = these (etait mislabeled "secteur").
- Risk #1 NON audite : resolve_due_predictions L117 / storage.get_due_predictions L664 — backfille-t-il le past-due si downtime a 9h ?

## suite-8 — Dashboard cockpit canonique (27/05/2026)

Pass canonique sur le cockpit (render.py), commits e34baf3 + 7a66f0c + 4c604bb.
- **Palette par etat** (couleur = etat, pas le levier) : ROUGE breche/alarme/perte, AMBRE attention/opportunite, VERT sain, BLEU donnee neutre, INK valeur. Figee CONVENTIONS.md.
- **Concentration -> ROUGE** (alarme) + verbe "alleger sans sortir" : le rouge alerte, le mot empeche le trim-panique (biais #1). Coherent avec la page Concentration (deja rouge EXCESSIVE).
- **Metal** : technique --c (couleur d'etat) sur .kv/.gvm/.big ; chrome diagonal 2-speculaires sur titres (.phead h2 46px) -- silver brillant en dark, graphite SANS blanc en frost (regle physique : blanc sur fond clair = invisible). "40" en bleu metal. Barre .dband : textes secondaires suivent l'etat.
- 3-leviers cockpit Taille / Cible / Stop rendus distincts.

Hygiene : 1 bot.main (37896) + 1 serve (47182), no ghost. Backup OK (integrity OK). Git HEAD 4c604bb.
Residuel P3 trivial : Theses "en profit 19/40" en ROUGE = etat sain mal colore -> vert (pcls -> acc).
Vrai levier (redit) : style FIGE. Gain Path 5/6 = usage quotidien + VALUE_LOG jusqu'au batch KPI #2 du 10/06.

## suite-9 (27/05) — Bug fondamental probability_at_creation + restart discipline

DECOUVERTE (audit pipeline resolution): toutes les predictions avaient
probability_at_creation = 0.5 (145) / 0.53 (8) / NULL (1). => Brier mecaniquement
~0.25 constant, KPI #3 decoratif depuis l'origine, track record Path-6 invendable.

ROOT CAUSE (verify-before-patch, pas de rebuild panique): insert_prediction
(storage.py) RE-REQUETAIT signals.score a l'insert alors que la colonne n'est pas
encore persistee (auto_register filtre sur le score en memoire; l'ecriture DB du
score lag). estimate_probability(None,...) -> plancher 0.50. Les 0.53 = type/impact
deja ecrits (bonus +0.03) mais score absent. La formule etait SAINE; elle recevait
du vide. Le `except Exception -> None` silencieux (violation CONVENTIONS #6) = le NULL.

RESCUE: backfill (table predictions_bak_probfix = rollback) -> 153/153 recomputees
depuis la donnee signal presente. Ledger ressuscite, differencie.

FORWARD FIX (commit): thread score/signal_type/impact_magnitude
auto_register -> register_prediction -> insert_prediction; ne re-requete plus que
la credibility (source-owned, stable); fail-LOUD (error + return None) si score None
au lieu du plancher silencieux. Gates ruff/mypy/import green. Smoke end-to-end
(DB temp, yfinance bypass): 25 predictions, toutes >0.5, spread 0.576-0.652.

LESSON RESTART (couteuse): pkill/pgrep "python.*bot.main" est SENSIBLE A LA CASSE
et le binaire framework macOS est "Python" (MAJUSCULE) -> 0 match -> kills no-op ->
3 instances accumulees en conflit getUpdates (PTB retry-loop, ne meurt pas sur
Conflict). PATTERN CORRECT: pgrep/pkill -f "bot.main" (ou -i). uptime_monitor.sh
utilise deja -fi (jamais trompe). Bot relance CLEAN: 1 instance, 0 Conflict.

A FAIRE: predictions_bak_probfix garder qq jours (rollback data) puis drop.
ADR a ecrire (narratif Path-6: "comment je sais que mon Brier est juste").

## suite-9c (27/05) — COIN backfille, NVDA dummy supprime
COIN (vrai resolu, prob stale 0.5 -> brier 0.25 decoratif) recompute depuis features
creation (prob+brier honnetes). NVDA resolu = artefact de test (dummy, non detenu) ->
supprime du ledger (rollback predictions_bak_probfix). Chasse orphelins/prob-NULL faite.

## suite-9d (27/05) — Rotation OAuth Gmail FAITE
Vieux client OAuth (...92mf, secret leake) supprime en Console -> secret + refresh_token
invalides. Nouveau client Desktop, credentials.json remplace (heredoc local, secret jamais
passe en chat), re-auth OK, token.json frais, bot relance propre (1 instance, 0 Conflict).
Item securite #1 = CLOS. Backups creds morts purges.
PARKE: retirer anciens creds du Project Claude (UI). Passer app OAuth en "Production"
(onglet Audience) sinon refresh_token expire J+7 (= TODO "Push to Production").

## suite-9e (27/05/2026) — /asymmetry single-thesis de-tautologized
- format_asymmetry_single aligned with format_portfolio_asymmetry (Day-5 lesson).
- Stripped auto-derived sentiment verdicts + color icons (circular = confirmation bias).
- Kept factual events (STOP_BREACHED/TARGET_HIT) + raw distances + proximity flags.
- compute_thesis_asymmetry unchanged. Display-only, in-bounds (observation safe).
- Live effect at next bot restart (not forced tonight).

## suite-9f (27/05/2026) — Brand PRESAGE sur le dashboard (bleu-metal)
- Decision marque : PRESAGE = surface publique (dashboard/favicon/title) ; PRESAGE = nom interne (inchange).
- _LOGO swappe : ancien horn/bifrost or -> marque PRESAGE vectorisee (trace depuis la planche), traitement bleu-metal : base var(--id) #3D8BFF (curseurs, identique light/dark) + reflets bleus fixes #6FB0FF/#2057B8. Mirroir du langage metal-liquide des .kv.
- Choix bleu vs metal-chrome : le chrome gris echoue en light mode (reflets clairs disparaissent). Bleu-metal = lisible dual-mode + matche les curseurs.
- .logo svg width-based -> height-based (mark portrait), glow bleu conserve.
- Favicon SVG data-URI (mark bleu sur carre sombre) + <title>PRESAGE</title>. Display-only, observation-safe, hot-reload.

## suite-9f (27/05/2026) — Brand PRESAGE sur le dashboard (bleu-metal theme-aware)
- PRESAGE = surface publique (dashboard/favicon/title) ; PRESAGE = nom interne (inchange).
- _LOGO : ancien horn/bifrost or -> marque PRESAGE vectorisee (trace planche), traitement bleu-metal biseaute (mirroir du langage .kv).
- Couleur = var(--id) #3D8BFF (curseurs/identite). Reflets via vars theme-aware --mkhi/--mklo :
  dark #7FB6FF/#1E5AD0 (range clair), light #5C9CFF/#0B3A86 (range sombre) -> claque dans les 2 modes.
- Chrome gris ecarte (echoue en light). .logo svg height-based (mark portrait), glow bleu conserve.
- Favicon SVG data-URI + <title>PRESAGE</title>. Display-only, observation-safe, hot-reload.

## suite-9g (27/05/2026) — Mark PRESAGE -> monochrome noir/blanc
- Abandon du bleu (rejete). Mark mono theme-aware via --mkhi/--mkbase/--mklo :
  dark #FFFFFF/#DDE2EA/#9097A1 (blanc-argent), light #4A4F58/#1C1E24/#000000 (anthracite-noir).
- Fidele a la planche (noir/blanc strict), biseau metal conserve. Favicon refait en mono clair.

---

# CHECKPOINT — Session 27/05/2026 (Day 16)

Mode : High Standard / OBSERVATION jusqu'au 10/06. Freeze = code prediction/behavior.
Display-only + read-only + data-entry + docs = in-bounds.

## Shippe aujourd'hui
- Logo + favicon PRESAGE : nouveau mark interlock (SVG currentColor, theme-aware),
  favicon recentre 64x64. render.py L825/L1105/L1904. Dead CSS vars --mkhi/--mkbase/--mklo
  (L1064/1071) a nettoyer plus tard. Committe.
- target_partial backfill x28 : tous les longs tenus, tiered par conviction
  (c5:1.35 c4:1.30 c3:1.25 c2:1.20 x entry). Schema-debt "target_partial NULL partout" CLOS.
  UPDATE SQL unique, backup .backup avant. Override via /thesis set TICKER target_partial X.
- These Lasertec 6920.T C3 : thesis_id=52. entry 218.68 / partial 273.35 / full 328.02 /
  stop 164.01. Drivers = chokepoint inspection actinique masques EUV, leader malgre KLA.
  Invalidation = KLA design-in EUV mask @ foundry tier-1. Pre-mortem auto (Opus) flag
  KLA actinic design-in @ TSMC/Samsung en failure #1 (P=22%). NOTE : stop -25% = soft
  review-marker, PAS hard floor (gap risk). NE PAS resserrer a -15% (whipsaw -> biais #1).
  Protection reelle = sizing ~3.7% book + invalidation binaire.
- Geo drill-down : _geo_bars rewrite, hover=peek + click=pin, sous-liste constituents
  par pays (short-name + ticker + % + EUR). Committe f91d05e. Hot-reload, pas de restart.
- Bot restart : crash Telegram TimedOut (transitoire, pas notre code). Restart rituel OK.
  FRAGILITE : un timeout tue le bot, rien ne le relance -> fix = Hetzner+systemd.
- Cleanup NVDA : delete decisions id 2,3 (2 fixtures de test Day-1, tag test_manual_override
  + thesis_id=1 hors book). Table decisions = 1 ligne reelle (6920.T trim id=10). Backup
  /tmp/bot_pre_decdel.db. Ameliore integrite KPI #5.
- TODO : Telegram channels comme source ingestion (capture post-10/06, voir TODO.md fin).

## Loose ends (par valeur)
1. Reconciliation book Lasertec (KNOWN-WRONG) : DB 6920.T qty=8.146 / MV ~1849 EUR vs
   broker ~1579 EUR (~6.96 titres) -> book sur-estime ~270 EUR. Trim 500 EUR -> Advantest
   PAS logge. /portfolio weights faux sur cette ligne. Fix = /position_sell 6920.T +
   /position_buy 6857.T (journalise -> KPI #5). Verifier d'abord row Advantest 6857.T en DB.
2. Journal decisions quasi vide (1 entree) : LE levier reel jusqu'au 10/06. Logger chaque
   decision materielle (action ET non-action) via Telegram. Pas du code, de la discipline.
3. OAuth Testing->Production Google Cloud Console avant ~3 juin (sinon refresh_token Gmail
   expire ; prereq Hetzner headless). + retirer credentials.json/token.json des project files Claude.

## Strategique (next sessions, flagge 27/05)
- Hetzner : MacBook -> VPS 24/7. systemd Restart=always (subsume uptime). Dashboard JAMAIS
  public (net worth -> localhost + SSH tunnel). Gmail OAuth headless. Ops-only -> OK pendant obs.
- Multi-user : pivot Dim-3 Path 5/6. Multi-tenancy data-model (user_id partout, isolation).
  Seam propre : intelligence PARTAGEE (newsletters/8-K/materiality/credibility) vs portfolio/
  theses/biais PAR user. PAS avant 10/06. ADR-first. Sequence : Hetzner d'abord, multi-user apres.

## Git
HEAD = f91d05e. Branch ~26 commits ahead origin/main, UNPUSHED. data/bot.db untracked.

## Frozen jusqu'au 10/06 (rappel)
render_panel rollout (helper committe 1401e2a, unused) ; cleanup dead CSS vars ; rapatriement
~44 sites sqlite bruts ; split render.py ; recalibration 8-K ; pruning univers (311 tickers) ;
reconciliation credibility prior 0.5 + Brier de-correle AVANT outcomes juin (137 predictions
correlees = piege pseudo-replication).


---

# CHECKPOINT — Session 28/05/2026 (Day 17)

Mode : High Standard / OBSERVATION jusqu'au 10/06. Freeze = code prediction/behavior.
Display-only + read-only + data-entry + docs = in-bounds.

## Shippé aujourd'hui (3 commits + 1 ops)

- **Cockpit discipline panel (42db7e8)** : panneau meta-vitals en tête Vue d'ensemble — décisions/30j (rouge actionnable), J-13 countdown 10/06, drift book Lasertec (constant RECONCILE_FLAGS module-level), panic sells. Couleurs disciplinées (rouge=actionnable, blanc=neutre, dots éliminés). Read-only, display-only.

- **CSS token cleanup + sticky sidebar (942243b)** : audit regex → 14 vars CSS mortes supprimées (--bg2/--gold/--ink2/--panel2/--r1-3/--s1-6/--steel2). Phantom --mx/--my conservés (mouse-tracking gradient JS-defined, blind spot regex sans match var(--mx,fallback)). Sidebar position:sticky;top:0;height:100vh;align-self:flex-start. Defined 39→25, unused 0.

- **Macro reorder + tooltips + RSI/breadth + glossary (082bd6e)** :
  - Moniteur stress macro tri par (alert_status, position_in_map) — rouge en haut (Taux 30y), ambre suit (USD/JPY), reste par ordre book-relevance
  - Section "Autres" éliminée. RepoSRF/FedBalance/MfgIP_yoy reclassés tier 2, renommée "Stress bancaire & liquidité Fed"
  - `data-tip` + CSS `[data-tip]:hover::after` sur toutes .drow (zéro JS, dark+frost compatibles, max-width 300px)
  - Nouveau panneau equity internals sur Urgence : RSI(14) SPY/QQQ/SMH/IWM + Breadth RSP/SPY vs MA50 (cache TTL 30min anti-ban yfinance, helpers _rsi_14/_market_rsi/_breadth_rsp_spy module-level)
  - `docs/MACRO_GLOSSARY.md` (99 lignes) : référence longue 17+ indicateurs avec seuils et pertinence book AI_compute

- **OAuth Testing → Production (ops, sans commit code)** : GCP Console → APIs & Services → OAuth Consent Screen → Audience → PUBLISH APP (External, unverified, personal-use exception explicite dans doc Google pour scope restreint mono-user). token.json supprimé + re-auth via InstalledAppFlow → refresh_token Production-issued (plus de cap 7j). Smoke test fetch 3 messages OK. Backup `token.json.bak_20260528_104011` conservé.

## Loose ends (par valeur, post Day 17)

1. **Réconciliation book Lasertec (~270 EUR drift)** [INCHANGÉ depuis Day 16] : DB 6920.T qty=8.146 / MV ~1849 EUR vs broker ~6.96 titres / ~1579 EUR. Trim 500 EUR → Advantest PAS journalisé. Fix = `/position_sell 6920.T` + `/position_buy 6857.T`. 5 min, ton job, première vraie entrée KPI #5 hors fixture.

2. **Journal decisions (1 entrée réelle)** [INCHANGÉ] : le seul levier KPI #5 jusqu'au 10/06. Discipline d'usage, pas du code.

3. **Retirer credentials.json + token.json des project files Claude UI** : post-OAuth migration ces fichiers exposent client_secret + refresh_token Production à chaque conversation. Settings Project → Files → delete. 1 min, ton job.

4. **Hetzner migration T-3 ≈ 31 mai** : ADR 002 + deploy planifié. Olivier prépare compte Hetzner + SSH key + réflexion sur VPS tier (CX22 vs CPX21) / backup destination (Storage Box vs Mac vs S3) / OAuth headless (device-flow vs token transfer) / IMAP+AppPassword coupling. Session continue ~3-4h le jour J.

5. **Concentration policy ADR** : 6 positions > cap 5%, 46.5% AI_compute. Decision pending depuis Day 13. À tête fraîche, matin calme, pas fin de session technique.

## Strategique

- **T-3 Hetzner ADR 002** : décisions ouvertes — CX22 vs CPX21 / backup destination / OAuth device-flow ou token transfer / IMAP refactor coupling oui-non.
- **Post-10/06** : KPI #2 batch (~40 résolutions, cluster J+28). Brier mesurable → point de décision Path 5/6. Si vert → ADR 001 PIT bitemporal implementation + concentration policy + universe pruning.
- **Multi-user pivot** : ADR post-10/06, séquencé après Hetzner.

## Lessons Day 17

- **Personal-use exception Google OAuth** : pour 1 utilisateur sur scope restreint (gmail.readonly), publish unverified suffit (pas de CASA audit). Cap 100 personal accounts lifetime, on en utilise 1.
- **Verify-before-patch tient encore** : la discovery RSI a évité de re-patcher du code déjà supposé en place — en réalité perdu/jamais committé entre sessions. Lesson 13/15 sauve les bugs auto-infligés.
- **Méthode paste-channel mature** : 3 patches majeurs en série + 1 commit propre + 1 ops sécurité = ~1016 inserts, zéro régression. Assert s.count(old)==1 + .bak + gates compile/ruff/pytest = workflow stable.

## Git

HEAD = 082bd6e. ~29 commits ahead origin/main, UNPUSHED. data/bot.db untracked.
Day 17 commits : 42db7e8 + 942243b + 082bd6e. Ops OAuth sans commit.
Backups locaux non-tracked : `dashboard/render.py.bak2`, `token.json.bak_20260528_104011`.
À pousser AVANT Hetzner migration.

## Frozen jusqu'au 10/06 — RECADRÉ Day 17 (mi-session)

Critère sharper : frozen = ce qui affecte la pipeline `signal → score → prediction → resolution`. Tout le reste = fair game.

**Solidement frozen** (corrompt le batch resolution du 10/06) :
- intelligence/{learning, asymmetry, materiality_v2} : logique génération/résolution prédiction
- Credibility prior 0.5 + Brier de-correle methodology
- Classifieur 8-K recal (feed materiality → signal scoring sur 13 jours restants)
- Policy 2-week observation guardrail dans /risk_check (changerait comportement bot pendant obs)

**Unfrozen** (display/UX/refactor/data-correction/doc/handler-fix/additive-feature, zéro impact pipeline) : voir TODO.md restructuré pour la queue active. ~70% du frozen list initial du 13/05 était lumped trop large par prudence — recadré pour libérer la queue.

## Day 17 close (28/05/2026) — chantier surface command-line

**Theme**: surface de commandes alignee sur telemetrie reelle (handler_calls), pas sur modele historique. "Less surface > more discipline" applique aux commandes.

### Shipped (5 commits, tous pushes -> origin f783756)
- 6e2061a /journal_decision : enrichir reasoning d'une decision a posteriori. Decouverte: decision_type CHECK enum (no_action_flag, pas no_action).
- 8a7c923 cull -10 flats morts (thesis/journal/position_history/bias_pattern/echo_recent, 0 appels 15j) + alias /positions /value_log + restore /kpi_status on-demand.
- b0227ec restore /signals_by_type + /insider_buy_cluster_stats (handlers supprimes au refactor, data layer intact, depuis .backups/E_batch1).
- b14aae0 /tiers conviction-sizing price-free (lit config.concentration.line_cap_by_conviction = source unique; cible cap_i/Scaps*100).
- f783756 dedup signals_by_type (etait 2x) + /help genere du registre (introspection, zero drift).

### Surface 76 -> 72. Demande morte (telemetrie) servie. /help ne ment plus.

### Decisions / pushback
- Refuse "cull 30+": plafond defensible ~12. Les ~18 flats "redondants" = vocabulaire reel (asymmetry 21, portfolio_sectors 9). Telemetrie > intuition.
- Caps conviction "4.5/3/2 vs 5/4/3" RESOLU: config==ADR 009 (c5=8/c4=6/c3=4.5/c2=3/c1=2). Le 4.5/3/2 memoire etait stale.
- /tiers price-free volontaire: poids-courant-vs-cap reste au dashboard (_sizing_overcap, prix-dependant). Pas de 2e chemin prix.

### Signal portfolio emergent
- /tiers: inflation c5 = 21% > gate 20% (6/28 lignes conviction max). NE PAS de-tierer a la main — laisser Brier 10/06 trancher (ADR 009: re-tierage sur preuve N>=30).

### Etat: bot PID 56894 vivant, 72 cmds, gates verts, origin synchro (39 commits pushes). Freeze observation maintenu (display/UX/additif hors-gel).

### Loose ends (non-urgents -> 10/06)
- friction.md logge ce jour. Retirer credentials.json/token.json des project files Claude UI. Fichier `trade` untracked a elucider.
- Hetzner prep ~31/05: compte+SSH+ADR 002, 4 questions ouvertes (CX22 vs CPX21 / storage / OAuth device-flow / IMAP).
- 10/06 jour-J: ~40 predictions resolvent, premier Brier, decision Path 5/6.


## Day 17 (28/05/2026) — Dashboard A/B/C-amorce + command surface

**Command surface** (7 commits, pushes faits) : aligné sur télémétrie (handler_calls), 71 cmds, /help auto-généré du registre (fini la string V4 menteuse), 10 docstrings nues remplies, decision_type enum documenté (CONVENTIONS §2), /bot_data culled.

**Dashboard — fil rouge : single-source + couleur = fait, jamais jugement.** 4 commits atomiques :
- A `_pct` : autorité unique de format des poids → plus-grosse-ligne 9% → 8.6% (réconcilie Concentration/Positions).
- B1 : KPI "asymétrie favorable (ratio≥2)" → "proches de la cible". La tautologie Day-5 qui avait fui dans le dashboard est retirée, + le seuil local ≥2 (≠ module 1.5) tué.
- B2+C-amorce : marqueur asymétrie coloré par PROXIMITÉ factuelle (rouge stop / vert cible / neutre sinon — fini le vert-P&L flatteur) + piste teintée rouge→vert FIXE (légende d'axe identique par carte, pas un verdict). Pose l'axe sémantique unique sur tout le dashboard.

**Méta-leçon de session** : j'avais d'abord re-proposé une carte "favorable/défavorable" colorée = exactement la tautologie Day-5. Rattrapé en lisant le code (format_*_asymmetry de-tautologisé 27/05). Le dashboard avait lui-même dérivé de la leçon ; on l'a réaligné sur la couche TG.

**EN ATTENTE — prochaine session "carte Thèses" (D + sizing) :**
- *Sizing bar overshoot* : hiérarchie inversée aujourd'hui (barre = poids total, cap = tick non-labellisé à 76.9% magique, dépassement = sliver invisible). Refonte : dans-cap muet / **hors-cap rouge saturé proportionnel** / sous-cap marge verte / tick cap labellisé. Code = `th-sz`/`th-szf`/`th-szc` (L1126-1128 CSS) + bloc `_fill`/`sizebar` (~L1300). Isolable, 1 commit.
- *Déclutter* : "cible taille X%" = constante par palier répétée sur chaque carte → hisser dans l'en-tête du tier.
- *Faux précis* : "−1 944 €" → arrondi (−1 950 / −1.9k).
- *D* : page Thèses rangée par ACTIONNABILITÉ d'abord (lignes demandant décision en haut), pas par conviction. Badges conviction déjà colorés (c5 bleu/c4 vert) = moitié de D déjà faite.
- Restent E (parité light/dark des oklch fixes des barres) + F (CTA honnête decision-log, échelle macro labellisée, responsive/mobile).

**Day 17 EXTENSION (cloture reelle)** : sizing overshoot FAIT (la file ci-dessus etait obsolete sur ce point) - barre `th-sz` segmentee gris/ambre/rouge, cible = frontiere de couleur, cap = tick ; queue rouge seulement si depassement de cap. `proches-du-stop` (cockpit) seuille : rouge<10 / ambre<20 / calme>=20, echelle 0-40 -> fini la fausse alarme quand le book est sain. RESTE prochaine session : declutter sizing ("cible taille X%" hisse en en-tete de tier + arrondi EUR), D (ranking actionnabilite), E (parite light/dark des fills fixes #2A4439 / oklch), F (CTA / echelle macro / responsive).

**TOP D-SESSION (decide 28/05, "axe stop")** : unifier les 2 colonnes de la Vue d'ensemble ("Plus proches de la cible" / "Plus proches du stop") sur la PRIMITIVE des cartes Theses = marqueur sur l'axe stop->cible (`frac = (current-stop)/(target-stop)`). POURQUOI : les barres actuelles forcent une fausse symetrie illisible — gauche = barre de PROGRESSION (`_prog`, pleine=arrive=bien), droite = barre de RESERVOIR (`_marge`, pleine=marge=sur). Elles se remplissent dans des sens de "bien" opposes -> aucun modele mental commun. FIX : meme barre des deux cotes (position du prix entre stop et cible), "proche cible" = marqueur pres du bout cible, "proche stop" = pres du bout stop. Un seul modele, lu une fois, applique deux fois. La couleur (ardoise/seuil interim, NON validee par l'utilisateur) se resout DANS ce rework, pas avant. Code : `gain`/`lose`/`_prog`/`_marge`/`_mcls` ~L2115-2135 render.py.


---

## 28/05/2026 Day 17 close
HEAD origin/main = b6901e6. Session = surface commandes (Phase 1, telemetry-aligned) + refonte dashboard (Phase 2). Detail complet -> HANDOFF.md section "Day 17 close". Etat stable, tout pousse, rien en suspens correctness. Invariant dashboard grave : couleur = fait jamais jugement, un seul modele de lecture (axe stop->cible) partout. Entry next session : declutter Theses (hoist cible-taille par tier, arrondir €) + liste "A faire aujourd'hui" consolidee + legende vitals + renommer "Plus proches du stop"->"Marges les plus faibles".


## 30/05/2026 close (long session, 30+ commits, 10 iterations arc V2)
HEAD origin/main = b4ac2e3 (post #03 dry_run_eleven_days). Stable, rien en suspens correctness, 414/414 tests verts. Bot tourne PID 84607 + caffeinate + nouveau code wire charge (premier test live = job 8-K cron 6:30 demain).

**Arc principal** : audit pre-batch 10/06 a revele mono-bucket [0,608-0,658] sur 40 predictions. 10 iterations sur 8 chantiers ont remonte la chaine : formula cap -> prompt -> contamination source -> frontiere commit -> semantique P(call correct) -> wire sourcing -> extraction exhibits -> pollution prod via tests -> consolidation DB_PATH -> dry-run J-11 confirmant empiriquement le diagnostic. Decision log complet : `docs/decision_logs/01_calibration_unanchored.md` (10 iterations + 3 vigilances + draft v5 publishable).

**Pattern central** : *la conclusion est toujours en avance d'un cran sur la preuve.* Verifie 10 fois, dont une sur le fix lui-meme (iter 9 : aliaser statiquement _DB_PATH = DB_PATH n'etait pas un fix, le test regression l'a montre immediatement).

**Decisions stockees** :
- SIGNAL_SCORER_V2 integre dans `intelligence/learning.auto_register_predictions` -- cohortes futures ont un scorer non-ancre (vs V1 mono-bucket).
- Wire 8-K + insider buy clusters actifs en prod, forward-only strict, dedup gmail_id.
- `storage.DB_PATH` consolide via `__getattr__` -- _DB_PATH alias dynamique, monkeypatch propage, anti-recurrence pollution prod.
- ADR 012 : 8-K severity classifier soft-deprecated comme mesure evidence_strength (V2 sur contenu = source verite).

**Pour le 10/06 (J-11)** : dry-run dit Brier ~0,295 (PIRE qu'un prior 0,5 trivial). Mecanisme resolution tourne sans bug (40/40 prix fetched). V1 mauvais comme predit. Le 10/06 publie le V1 mauvais honnetement (post_03 deja drafte pour ca) -- premier benchmark V1 fige, future comparaison V2 post-aout.

**3 posts canoniques bilingues prets dans `posts/`** (Phase A juillet du PLAN_ACQUIHIRE en grande avance) :
- post_01_calibration_unanchored : "Six fois j'ai cru avoir fini" -- arc V2
- post_02_comment_that_lied : SK Hynix 1600x bug
- post_03_dry_run_eleven_days : J-11 dry-run honnete

**Entry next session** : observer si le job 8-K 6:30 a fait passer une nouvelle 8-K material via le wire (verifier `bot.log` + `signals` table). Si oui, premier signal V2 dans le ledger. Sinon attendre. Pas de pression -- usage > code jusqu'au 10/06.


## 31/05/2026 close — session marathon "data-trust foundation" (13 commits)

HEAD origin/main = a7413fb -> 13 commits ahead non-pushes (42 total ahead).
Bot launchd PID 4140 vivant + caffeinate sidecar. 452+ tests verts.
Migrations 0020 -> 0022.

### Cadre strategique adopte (user 31/05)

User a recadre Layer 1 ("base que tu dois avoir maintenant") + Layer 2
("features qui approfondissent l'edge") + 4-point data-trust foundation
+ "magnifier" (prendre les bonnes idees competitors + les rendre plus justes)
+ separation craft-top-website (vrai, atteignable solo) vs vernis (piege).

**Les 4 piliers data-trust closes** :
1. Contract resolution : SQL verifie pas de watch leak (direction ∈ bullish/bearish)
2. Scorer noise : audit deja run, verdict LOW (std 0.0062, single-run OK)
3. FX max-age : fx_freshness() + fx_is_stale() + FX badge dashboard
4. Quarantine v0 : 40 preds 10/06 horizon=30 hardcode taggees, 4 consumers filtrent

### 13 commits

1. f0a9386 fiabilite launchd PRESAGE + kill orphelin bot.main
2. c92a63d ficele KPI #2 exclut neutrals (3 SQL sites)
3. 2f494a3 deps declarer scipy + sklearn + statsmodels
4. ead47c3 ficele FX live yfinance + cache 4h + fallback hardcoded
5. 541aff2 ficele retire fallback magique 'or 1.1655' (dead code)
6. bce5a58 ground-truth resolve_due_predictions utilise close target_date +
   re-resolve 3 historiques (NVDA 50, AVGO 51, MSFT 53)
7. 862f80a quarantaine v0 cohort + filter consumers calibration/KPI
8. 7329968 ficele FX freshness tracking + fx_freshness/fx_is_stale
9. d607085 build-profond scaffold recalib_map + base_rates + outcome_context
10. cc1cfb4 E2 wire-up A3 dashboard surface insider_snapshots (flux 7j)
11. 1018bf2 E2 TTL label foot dashboard maj timestamp visible
12. 41fd3a8 saved-PIT prediction_audit_log append-only + wrap +
    backfill 31/05
13. f0376f9 E4 craft badge FX freshness dans foot dashboard

### Findings critiques

**KPI #2 etait gonfle +200%** : 6 resolved 28d/30d affiches, vraie substance
2 (4 neutrals comptes). Fix neutrals exclusion + alignement avec discipline
deja existante (position_invariants.py:176 le faisait dans un autre check).

**Ground-truth resolve bug ELIMINATOIRE** : utilisait current_price (=
close T-1 pour US tickers via cron 9h CEST avant US open 13h30 UTC) au
lieu de close T. 3/6 resolutions historiques FAUSSES :
- NVDA 50 neutral -> incorrect (close reel -6.29% vs -4.91% stocke)
- AVGO 51 neutral -> correct (+5.08% vs +0.33%)
- MSFT 53 neutral -> correct (+6.71% vs +1.20%)
Fix + re-resolution + backup + doc audit + PIT trail reconstruit.

**Vraie performance bot post-fix** : 3 correct + 2 incorrect + 1 neutral.
60% taux correct sur N=5, Wilson IC95% [23%, 88%] (non-conclusif a N=5
comme attendu). Bot a ete plus performant que ses propres stats.

**FX drift HARDCODED vs live** :
- HKD : -7.3% (gros)
- KRW : -3.8% (positions Samsung/SK Hynix)
- JPY : -1.5% (Lasertec)
- USD : -0.03% (essentiellement exact)

**Insider flow visible** : AVGO -$2851M ★, AMD -$938M ★, MU -$432M ★,
NVDA -$1310M (hors portef), CRWV -$5156M (hors portef). Star = position
user. Donnees ingerees depuis insider_digest cron quotidien mais
invisibles au dashboard avant 31/05.

### Discipline "voie propre auditable" actee (feedback memory durable)

User a explicite mid-session : par defaut voie propre, auditable,
professionnelle, consciencieuse. Applique en pratique :
- DB UPDATE destructif -> backup + doc audit + tests
- Code change -> tests systematiques (16 nouveaux en FX, 9 en scaffolds,
  4 en audit log)
- Migration alembic (0021, 0022) avec downgrade testable
- Audit log append-only avec trigger no_update
- Backfill scripts reproductibles (pas one-shot SQL)

### Restes pour next session

**E4 (UI craft top-website)** -- 4 items sur 5 : vitesse/zero jank, design
system tokens, chaque etat designe (loading/empty/stale/error), detail
ergonomique (defaults + clavier + single reading model), densite belle
(Bloomberg-dense Linear-clean). Multi-sessions, jugement visuel fin.

**E5 publier post #01** -- bloquant KPI #2 leve, ground-truth audit OK.
Decision plateforme (Substack ? Twitter ? site PRESAGE ?) + ton final
necessaires.

**Activation des 3 scaffolds build-profond** : recalib_map / base_rates /
outcome_context s'allument quand N predictions resolved v1 >= 30 (cf
seuils dans chaque module). Post-batch 10/06 ce sera proche, possible
qu'on les active des juillet.

**Loose ends mineurs** :
- pre-existing ruff F841 unused var dashboard/render.py:4750 (over_cap_tk)
- 42 commits ahead origin (a pousser un jour, prerequis Hetzner migration)
- rotate_bot_log.sh ligne 67-69 doublonne avec launchd (refondre quand
  prochaine rotation manuelle)
- portfolio_snapshots cron rate 6/8 jours sur fenetre (25/05 + 29/05
  missed). Pas critique mais surveiller.

**Entry next session** : si focus craft = ouvrir le dashboard live, listing
des etats casses observes. Si focus publi = relire post_01 et decider
plateforme. Si focus suite techno = lancer alembic upgrade head sur Hetzner
(en parallele de la decision deploy).


## 31/05/2026 close-bis — session continuation craft (19 commits +)

La cloture precedente (fc2369e) etait premature : user a relance pour le
craft dashboard. 19 commits supplementaires durant l'apres-midi/soir, focus
UI carre + alignement sur 4 specs strategiques user successives.

HEAD origin/main = b6901e6 -> 60 commits ahead non-pousses (vs 42 au close
precedent). Bot launchd actif PID ~4900. 452+ tests verts. Migrations
0020 -> 0022.

### Specs user absorbees (4 successives)

**Spec 1 — 5 piliers data-trust** (en cours du midi) : 4 closes (KPI #2,
FX live + max-age, ground-truth resolve, quarantine v0). Couche sante
distribution = pile manquante -> implementee wave 13.

**Spec 2 — 5 regles transversales + sequencement pre/post-10/06** :
un seul modele de lecture, couleur=fait, provenance+fraicheur, etats
honnetes-tot, self-evident. Sequencement = architecture maintenant +
remplissage avec donnee. Adoptee.

**Spec 3 — 4 architectures (regime evidence, robustesse, ergonomie, DA)**
+ 6 points sequencement pre-10/06 (track record en lead, mode advisory,
ergonomie, tokens DA, sante distribution, split monitored/reference).

**Spec 4 — Bar craft litteral (paper-and-ink)** : couleur rare aux deux
bouts de l'axe, axe stop->target primitive reutilisee, etats honnetes-tot
designes (cadre vide + diagonale qui se trace), Geist Mono partout,
filets fins zero ombre, motion epistemique.

**Spec 5 — 3 piles de la suite** :
- Pile 1 (design system, confortable) : panneau discipline/biais (2nd
  lead), hero portefeuille mis au bar, panneau evidence A3 au craft,
  surface Telegram canonique
- Pile 2 (plus au coeur) : instrumenter boucle comportementale (User Bias
  Detector mission), mode advisory (largement fait wave 10), passe
  terminologie-rigueur (besoin du glossaire colle)
- Pile 3 (rare, ne se builde pas) : publier #01, 10/06 1er track record
  + activation scaffolds

### 19 commits supplementaires (wave 1bis -> 14)

15. f0a8da1 -> not in session, ignore (artefact)
14. 504f836 charte DESIGN_SYSTEM reecrite canonique (parchemin + Geist +
    font-size tokens + etats canonique + ergonomie + voice + 10 regles or)
13. df13091 wave 2 bandeau "A AJUSTER" + smart routing + title hover +
    tokens font-size + retrait dot decoratif
12. 081250b wave 3 foot reduit mode switch only + tape 8-K plein texte
    (user image friction)
11. bf6b7c5 wave 4 hero Valeur+Note meme panneau + bump tokens font-size
    +1-2px global
10. 7fdbbd9 wave 5 page Copilot dediee entre Positions et Theses
    (chat + conceptions + conversations + chat_signals reactives)
9. fbdc129 wave 5bis synthese copilot integree page Copilot
8. 003e0db wave 6 chat idle 7min -> 2min (puis 31cd8a8 revert 7min)
7. e62de70 wave 7 Track record en tete + charte §11-13 +
   bd932d8 wave 7bis disappear quand N>=10 cible atteinte
6. 1c2c349 wave 8a tape PnL/8-K cliquable + distline title hover
5. 1948466 wave 8b sweep font-size inline +1-2px (249 sites)
4. 079068c wave 9 font -1 + accordion canonical click-only + bug fix
   _theses currency-native
3. 0730c1a wave 9b fix monkey-patch asym_mod -> NATIVE (Asia tickers
   dereglees +175408% etc., SK Hynix Lasertec Mitsubishi Advantest Shin Etsu)
2. 9f6bd8b wave 10 mode advisory : "agir maintenant" -> "examiner",
   "A AJUSTER" -> "FRICTIONS", "prends ton profit" -> "cible atteinte"
1. b183304 wave 13 sante distribution : extension scaffold ROUGE/ORANGE/
   VERT ops -> data (3 nouveaux checks horizon/conviction/FX freshness)
0. 7b1f330 wave 14 Track record refonte craft : axes primitive + courbe
   fiabilite SVG cadre vide + diagonale qui se trace au load + filets
   fins + Geist Mono labels+units + motion epistemique. Devient surface
   de reference, le reste pourra heriter du pattern.
-1. 7c6369b friction.md sync 31/05 (24 entries data-trust + UI/UX + archi)

### Findings critiques de la continuation

**Bug currency-native EUR vs NATIVE sur 2 sites** : "Marges les plus
faibles" affichait cible +175408% pour 000660.KS (SK Hynix), +23876%
pour 4063.T (Shin Etsu). Cause : `_cached_price_eur` compare a stop_price
+ target_full stockes NATIVE. Fix sur _theses() puis nouveau
_cached_price_native + monkey-patch asym_mod corrige.

**Horizon mono-bucket ALERT** : 75% des predictions hors v0 (173 sur 60j)
ont meme horizon -- probable defaut historique 30j hardcode. Sante
distribution panel surface l'alerte live. A investiguer post 10/06.

**Conviction distribution OK** : c5=5/27 = 18.5%, sous le seuil 35% WARN.
Construction phase respectee.

**FX freshness 5/5 live sous 24h** : pas de fallback hardcoded actif.

### Reste pour next session (priorise selon spec 5 user)

**A — pile 2 substance** (user said "plus au coeur"):
- Instrumenter boucle comportementale (User Bias Detector) : data model +
  capture des moments "j'ai resiste ici" + cout-de-biais mesure.
  Chantier neuf substantiel (~3-5h focalisees).
- Passe terminologie-rigueur quand user colle son glossaire.

**B — pile 1 design system** (user said "confortable, ta force") :
- Hero Valeur+Note refonte au bar Track record (heritage pattern,
  axes primitive + filets fins + Geist Mono labels+units)
- Panneau discipline/biais (2nd lead, le plus singulier) -- surface du
  User Bias Detector instrumente en pile 2
- Panneau evidence A3 (insider+8-K) porte au craft Track record
- Surface Telegram canonique cohesive avec voix dashboard

**C — pile 3 hors-build** :
- Publier #01 (decision plateforme + ton final)
- 10/06 : batch resolution + activation scaffolds recalib_map/base_rates/
  outcome_context quand N>=30

### Discipline mature de la session

- "Voie propre auditable professionnelle consciencieuse" actee comme
  feedback memory durable
- 24 frictions injectees dans friction.md (le moteur)
- Bot a tourne sans interruption malgre 15+ restarts launchd kickstart
- Aucune regression test detectee (full pytest 452+ verts)
- Architecture d'info pre-10/06 posee (Track record en lead + sante
  distribution + page Copilot dediee + mode advisory)

**Entry next session** : si focus pile 2 = ouvrir la conception boucle
comportementale (data model decision_journal + bias_capture + cout
mesure). Si focus pile 1 = hero portefeuille au bar Track record.
Si focus pile 3 = relire post_01 et choisir Substack vs Twitter vs
PRESAGE site statique.

---

## Close 2026-06-01 — wire B2 live + Pile 1.1 + audit complet

### Livre

**Pile 2.1 v2.c.3 → c.5 (commit 416d90c)** — User Bias Detector cable
end-to-end, observation-only en live :

- **c.3 resolve_one_bias_event refactor** : single-path, kill backward
  compat. Lit shares depuis `position_events` (window strict
  `[created_at, resolve_at]`). Migration tests v2.b -> shape canonique
  `{initial_qty, discipline_expected_delta}` avec value-equivalence
  preservee. **Linchpin user 01/06** : fenetre vide != erreur (0 trade
  + hold -> resisted, 0 trade + exit -> acted_on_bias).
  MissingDataError reservee au prix manquant.
- **c.4 wire_bias_trigger(recommendations)** : interrupteur idempotent
  sur cle (ticker, bias, action, ref). Anti-piege #1 sur-declenchement
  (meme reco recurrente -> kept, created_at preserve). Fail-safe strict :
  open_candidate raise ne traverse pas vers le caller. 9 tests dont
  anti-spirale.
- **c.5 wire B2 symetrique kca + over_cap** :
  - kca wire post-notify dans `check_one_thesis` (instant T fidele,
    ref `rule:kill_criteria_t{thesis_id}` stable par thesis)
  - `intelligence/over_cap_monitor.py` neuf, miroir kca : detection
    transition `dormant -> over` via journal **over_cap_alerts**
    (migration 0024, append-only). Etat decouple du cycle bias_events
    (anti-piege resolu-mais-toujours-over). Notify Telegram + wire sur
    transition uniquement.
  - `classify_position()` = source de verite unique anti-double-impl
    (bloc baseline + monitor consomment la meme fonction), raise
    MissingDataError sur qty/price manquant (§6 invariant).
  - Job daily + integration morning_chain etape 4 monitors.
- Tests : 75 verts (12 over_cap + 5 kca wire + 9 wire + 24 v2 + 6
  skeleton + 12 classify + 7 open_candidate).
- **Decision over_cap dark** : malgre 3 OVER detectes au baseline
  (4063.T 8.9%, STMPA.PA 4.7%, TSLA 3.4%), tous repassent sous cap a
  70k = artefacts denominateur phase construction (53k -> 70k cible).
  Firer = mesurer une discipline qui n'a pas dit "trimme" -> over_cap
  TENU DARK explicitement (cf [[over-cap-dark-construction-phase]]).
  kca reste actif (zero confound de phase). Premier check live kca :
  triggered=0 at_risk=0 dormant=27, $0.10 LLM. Compteur live actif sur
  canal honnete.

**Pile 1.1 panneau Discipline & Biais (commit 5fd488d + 44bdd8b)** :
- Page `data-page="discipline"` autonome, 2e rang nav entre Vue
  d'ensemble et Positions
- 3 sections, vocabulaire conforme glossary :
  - **Predictions** cluster KPI #2 (J+28 batch 10/06) : compte
    resolues/total filtre `target_date <= 10/06` (pas TOUTES V1 -- user
    01/06 critique : "5 resolues" non-cluster lit faux). Au 01/06 :
    **5/35 resolues, KPI #2 >=5 satisfait**. Brier handler honnete
    avec **baseline 0.25 nomme explicitement** (predicteur constante
    0.5, le plus faible) -- "Battre 0.25 ne demontre pas un skill".
  - **Biais `fomo_greed`** -- 2 canaux :
    - `kill_criteria` ACTIF (27 theses surveillees, bars dormant/at_risk/
      triggered avec couleur = severite)
    - `over_cap` EN VEILLE (PAR DECISION) (book + raison + condition
      de reactivation explicite)
  - **Biais `lock_in`** NON INSTRUMENTE -- chemin Surface 2 ADR-010 §2
- Helpers : `_dba_eur` (narrow no-break separateur FR), `_dba_bar`
  (couleur = severite par classe d'etat), `_dba_predictions_brier_html`
  (handler honnete N<10 / N>=10)

**Glossaire (commit eebd6d2 + 8b5cb68)** :
- Refonte v1.0 canonique committee (etait orpheline dans filesystem
  depuis 31/05)
- **Section "Etat de canal d'instrumentation"** ajoutee : 3 etats
  canonique mutuellement exclusifs (`actif` / `en veille (par
  decision)` / `non instrumente`) + regle d'affichage explicite
- **Section "Biais documentes -- desambiguisation canonique"** :
  - `lock_in` biais #1 raison d'etre, NON INSTRUMENTE (entree majeure
    en evidence, pas note de bas)
  - `fomo_greed` enum technique (acception large), mecanise sur 2
    canaux
  - Biais #2 historique anti-FOMO crypto-tops = distinct de l'enum,
    dormant ortho
  - Regle d'ecriture explicite contre fausse equivalence
- README L7 + FICHE_TECHNIQUE L68-71 + CLAUDE.md L27 : 3 renvois
  courts vers glossary, plus jamais reformuler. Discipline
  source-unique.

**Pre-J-3 anticipe (task #15 completed)** : scaffolds activation 100%
OK -- 5/5 resolutions precoces ont tous champs canoniques, Brier
recompute manual match exact (drift < 0.0001), 0 pollution sur 29
unresolved. Brier precoce N=5 = 0.248 (pile sur baseline 0.25
no-skill). Trou en projection 0.295 FICHE = projection 30/05 a
re-valider J-day quand N=35.

### Audit complet 7 dimensions

- D1 Gates : 2 fails -> 1 fixe par session (#25 ALLOWED_FILES
  bias_events.py = pattern price_monitor) + 1 fixe (#29 v2_vigilance
  schema drift + assertion stale 3 -> 6). **0 P0**.
- D2 Couverture : materiality ~17% / asymmetry ~41% encore minces.
  Finding loggue #33.
- D3 Docs : FICHE/README/CLAUDE frais (01/06), SESSION_STATE update
  c'est ce close.
- D4 Secrets : credentials.json + token.json + .env untracked +
  gitignore propre. Aucun P0.
- D5 Data integrity : alembic 0024 + WAL + quick_check ok. Backup
  cron sain (~/backups/mes-bots-finance/ snapshot 01/06 04:00,
  fausse alarme du audit qui regardait data/backups/ vestige).
- D6 Liveness : bot vivant (PID 8110), uptime heartbeat OK 11:20,
  LLM cost $2/day $27/7d budget OK. Mais bot.log telegram.Conflict
  recurrent (double-instance) + register_prediction baseline price
  manquant (SK Hynix, SAMSUNG) -- #26 et #30 backlog.
- D7 Cruft : RECONCILE_FLAGS = 0 (clean), ui-ux-pro-max gitignored
  (#31 fait), DEPRECATED = kill-switches volontaires documentes,
  pas dette (#32 faux positif).

### Cleanup session de l'apres-audit

Completes : #25 (ALLOWED_FILES bias_events) / #28 (backup fausse
alarme) / #29 (v2_vigilance test fixture + assertion) / #31
(gitignore skill) / #32 (DEPRECATED faux positif). Backlog reste :
#26 (telegram Conflict, vrai diag a faire) / #27 (ce close) / #30
(baseline price gate decision) / #33 (8 ruff residuels prexistants
+ mypy strict gate absent).

### Outils

Skill `.claude/skills/ui-ux-pro-max/` installe (44K data CSV +
scripts, gitignored). Garde-fou : skill `ui-ux` projet (anti-
generique-IA, axe stop->cible, couleur=fait) reste autorite.
Magic MCP (21st.dev) ecarte volontairement (genericiquement, hors
stack HTML/CSS direct render.py). Task #24 modernisation interface
posee avec garde-fous et declencheurs explicites.

**Entry next session** :
- J-day 10/06 (~9j) : 30 resolutions restantes du cluster doivent
  tomber, on attend le vrai Brier final. Pre-J-3 deja verifie (#15
  completed) -- pas d'action prevue d'ici la.
- Si P1 #26 (telegram Conflict) cause une notif user ratee entre-
  temps, intervention immediate.
- Densite biais ~J+30 -> Pile 1.2-1.4 heritage hero (#11) prendra
  sens contre vraies donnees.
- Vision long terme : task #24 modernisation interface PRESAGE
  contre site public presage.pro + premieres lectures honnetes.

### Extension Close 01/06 -- session prolongee apres-midi

Apres le close initial du matin, session etendue avec :

**Audit complet 7 dimensions** (commit b1c2171 cleanup + ef525f9 ruff
+ f603589 cascade) :
- 5 vrais fixes : #25 ALLOWED_FILES bias_events / #27 SESSION_STATE
  / #29 v2_vigilance fixture / #31 skill gitignored / #33 ruff 10 -> 0
- 3 faux positifs identifies : #28 backup sain / #30 register_prediction
  refuse deja / #32 DEPRECATED = kill-switches volontaires
- 2 P1 #26 telegram Conflict auto-resolu (root cause -> task #34 guard
  mono-instance preventif)

**Capitalisation post-audit** (commit 0251067) :
- docs/LESSONS.md cree (6 lecons canoniques L1-L6 : source unique,
  ne pas batir avant la donnee, etat honnete, anti-double-instrumentation,
  fail-safe strict, rituel de cloture)
- docs/templates/monitor_pattern.md cree (gabarit miroir kca/over_cap
  pour tout futur monitor)
- .claude/commands/close.md + gates.md crees (slash-commands)
- CLAUDE.md mis a jour avec 3 references source-unique

**Installation skills** :
- 17 skills officiels Anthropic + 3 OneWave AI selectifs en user-level
  (~/.claude/skills/, 11 MB, gitignored)
- Claude Squad binary v1.0.18 installe (~/.local/bin/cs) pour multi-
  session parallele
- ClaudeForge + VoltAgent + impeccable + skills "research/security/
  humanizer/etc." ecartes (anti-pattern L1 / hors-stack / sources
  tierces non verifiees)

**Audit dashboard avec nouveaux skills** :
- Rapport en 3 grilles : ui-ux projet (autorite) / frontend-design
  Anthropic / lookalike futur site public
- Verdict : systeme design mature, anti-AI-slop, "2-3 chantiers polish
  cibles a 2-3 chantiers de la facade publique, pas une refonte"
- 3 frictions lookalike identifiees : F1 pas de hero editorial /
  F2 densite interne vs curatoriale / F3 pas de ton "ouverture des
  livres" -- toutes deja gated par #11/#19/#24

**Amplification brand identite** (task #37 creee) :
- 5 axes documentes pour future migration presage.pro
- AXE 4 motion epistemique partial livre : cascade Vue d'ensemble
  (commit f603589) -- presage-cascade 320ms staggered 60ms x 8 blocs,
  gate sessionStorage.h_seen anim 1x par session
- AXE 3 grain texture noise : ABANDONNE essai (old school a toutes
  intensites cf [[feedback-no-grain-texture]])
- AXE 4 marker pose : RETIRE (imperceptible sans cause identifiee,
  cf piege #3 lecons website migration)
- 4 pieges identifies pour future site public
  [[website-migration-motion-lessons]] : sessionStorage gate,
  superposition non validee, imperceptible tolere, cache leurrant

**Net session etendue** : 5 commits supplementaires (b1c2171, 0251067,
ef525f9, f603589, 7ab97f1 + ce dernier), 531/536 tests verts en fin
de session, ruff 0 errors, working tree clean cote repo.

Note : 5 tests self_loop_v0 rouges sous timing defavorable (DB live
locked par bot PID 8110, conflit WAL). Pas une regression de cette
session (mes changes touchent du CSS) -- finding pre-existant -> task
#38 backlog. 536/536 ce matin etait chance de timing, 531/536 cet
apres-midi est mauvaise chance.

**Restant pour prochaine session** :
- Surface 2 / lock_in : conception 3 questions ouvertes (point
  d'emission, seuil winner, horizon contrefactuel). Le vrai forward.
- P1 #34 guard mono-instance preventif si Conflict revient
- Backlog #11/#19/#24 reste gated par J-day + densite biais


---

## SESSION CLOSE 03/06/2026 — Resilience arc + J-day machinery (avant break few days)

### Livré ce jour (16 commits, branch main)

**Resilience arc complet** (#93→#95→#97→#98→#94→#96) :
- `3ac571e` #93 phase 1A : LLMUnavailableError detection chokepoint + consumers catch + llm_status state machine + scoring_status='pending_llm' marker
- `0889bc9` #93 phase B : cost cap soft (Haiku auto 80%) + LLM badge bottom-right (dot only) + Telegram alert transitions
- `202a7a3` #95 : ADR-014 + canonical_predictions_filter() + brier_by_methodology()
- `cc05e03` #95 ADR-014 doctrine : 3-tier taxonomy (canonical / archive-report / substance accounting / user-lookup)
- `4b48b17` #97 ADR-014 hazard A : substance tier explicite (substance_predictions_filter) -- conversion denylist -> exclusion explicite
- `d4a9481` #98 ADR-014 hazard B : methodology_version required (Python boundary keyword-only + SQL constraint via alembic 0028 drop DEFAULT 'v1')
- `8249c71` #94 phase 1 : Scorer Protocol + LLMScorer adapter (zero-behavior change)
- `4a5adfc` #94 phase 2 : RuleScorer determinist (plancher LLM down)
- `5c32e82` #94 phase 3 : ScoringOrchestrator FLAG OFF routing (RESILIENCE_FALLBACK_ENABLED)
- `6a66d20` #94 phase 4 : degraded restitution contract source unique (dashboard/restitution.py)
- `55b048f` #96 : PairedShadowOrchestrator Champion-Challenger FLAG OFF (RESILIENCE_SHADOW_ENABLED)

**J-day machinery** (10/06 in 7 days) :
- `b9664eb` `crons/j_day_watcher.sh` + cron entries 30 10 10 6 * + 0 14 10 6 *
- `3d442d9` Out-of-band switch : healthchecks.io ping in j_day.py + J-1 preflight push cron 0 9 9 6 * + reading contract `docs/j_day_reading_contract.md`
- `0035bfe` preflight : alarm arming verification step

**Audit deep tuyauterie** :
- `21366d6` 6 docs sous `docs/audit_2026-06-03/` (5 flux + CROSS_CUTTING + SYNTHESIS)
- P1 surfaced : deployment gap (bot tournait sur code d'hier post-migration 0028), partial-resolve detection J-day, scheduler dump verify, double cron_tier* registration, lock_in instrumentation decision

**Polish** :
- `58da9aa` LLM badge bottom-right, retire prose moralisante th-anchor
- `d3d6908` LLM badge box-sizing fix (collapse → ring + dot 22x22 / 10x10)
- `b8fd294` Spec post-J-day : Contrat Fraîcheur & Mouvement (#103)

### État courant prod

- **Bot relance** ce jour ~14:35 (PID 54583/54587). Code post-#98 chargé.
- **Bot en boucle Conflict 409** au moment du close session : phantom getUpdates du PID 46307 killed à 14:30 OU collision avec autre instance.
  - Devrait se résoudre naturellement après timeout Telegram (50s+).
  - Si toujours Conflict au retour : verifier `pgrep -fl python.*bot.main` puis si OK kill + restart via `launchctl kickstart -k gui/$UID/com.olivier.presage`.
  - tennis-bot `bot.py` distinct du PRESAGE `bot.main` (memory `[[parallel_projects_tennis_bot]]`), donc pas tennis qui interfère.
- **DB** : alembic head 0028. Backup pre-migration `data/bot.db.backup_pre_0028_20260603_130643`.
- **Tests** : 907+ passants (post-#96 base), 1 skipped intentional, 3 env-flaky pre-existing (edgar / book_gate, yfinance NaN).
- **Resilience flags** : tous OFF (RESILIENCE_FALLBACK_ENABLED, RESILIENCE_SHADOW_ENABLED). Compat #93 stricte.
- **LLM** : credit_exhausted depuis ~02/06. cost_cap_hard state. Badge bottom-right = rouge. Aucun signal scorer ne tire.

### Tâches utilisateur AVANT 10/06 (10 min cumulé)

1. **Healthchecks URL** : créer compte healthchecks.io, configurer un check (cron `30 9 10 6 *`, grace 4h), copier ping URL dans `.env` comme `HEALTHCHECKS_J_DAY_URL=...`
2. **Reading contract** : réviser les 2 lignes `[YOUR CALL]` (sample floor N, verdict gap M) dans `docs/j_day_reading_contract.md`, commit avant 10/06
3. **Mac plugged in** continuous jusqu'au 10/06 (caffeinate empêche idle sleep, mais pas battery exhaust)
4. **La conversation** : 1 prosumer scarred, montrer panel discipline cold, 4 questions, observer-pas-vendre. Spec complete dans cette SESSION_STATE plus tôt + memory `[[next_session_agenda]]`.
5. **Credit Anthropic** : recharger pour que les signal scorer recommencent. Avant ça : bot opérationnel mais aucune nouvelle prediction.

### Tâches techniques pré-10/06 (déjà loggées)

- P1 audit #2 : ajouter partial-resolve detection dans `_build_brier_telegram_msg` (~15min)
- P1 audit #3 : verifier `Scheduler started with N jobs` log line contient j_day_batch_close_job avec next_run 2026-06-10 09:30 — **dès que bot stabilise**
- P1 audit #4 : verifier pas de double `cron_tier*` registration (count dans le scheduler dump)
- P1 audit #5 : décider explicit lock_in instrumentation `positions.py:399` ship vs skip

### Tâches post-J-day (10 loggées, du #99 au #108)

#99 Cross-machine guard (BLOCKS Hetzner) · #100 Heartbeat link-roundtrip · #101 Provenance stamps · #102 Aggregator-per-number · #103 Fraîcheur & Mouvement contract · #104 Wire orchestrator · #105 Validation calibration rule_v1_fallback · #106 /shadow_compare · #107 BGE phase 2b · #108 Theses panel sweet-spots (kill gauge)

### Inputs pour reprise (cold-start)

- Audit complet : `docs/audit_2026-06-03/SYNTHESIS.md` (action table prioritisée)
- Resilience spine : `intelligence/scorers.py`, `intelligence/scoring_orchestrator.py`, `intelligence/shadow_scoring.py`, `dashboard/restitution.py`
- Reading contract : `docs/j_day_reading_contract.md`
- Fraicheur & Mouvement spec : `docs/presentation_contract_freshness_motion.md`
- ADR-014 disambiguation : `docs/adrs/014-ledger-segmentation-by-methodology.md`
- J-day machinery : `bot/jobs/j_day.py`, `crons/j_day_watcher.sh`, `crons/j_day_preflight_notify.sh`


---

## SESSION CLOSE 05/06/2026 — Migration Hetzner full + backup offsite Storage Box

Le chantier majeur reporte (par construction) : passer le bot+dashboard de Mac (sleep/shutdown = 2-3j off causant le mode vacances digest stuck) a une VM Hetzner H24. Origine de la demarche : user veut `backup.sh` push offsite. En remontant le pourquoi, on a debouche sur la migration complete.

### Livre ce jour (4 commits, branch main)

**Bug fix matin** :
- `327e1ea` [P1] materiality_v2 : retire double-gate `pending_llm` → `impact_magnitude IS NULL` seule source de verite. 70 signaux unstuck (1 cron drain + 0 fail). Memoire [[pending-llm-no-double-gate]].

**Prep backup script portable** :
- `e771c11` [ops] backup.sh : PROJECT_DIR auto-detect + env vars `BACKUP_REMOTE_HOST/PATH/PORT/SSH_KEY`. Echec push offsite non-fatal. Warn loud si non configure (sur serveur distant = doctrine INTERDIT silencieux).

**Systemd units rename** :
- `76b5927` [ops] deploy/heimdall-*.service → presage-*.service + fix `PRESAGE_PORT` env var (HEIMDALL_PORT n'etait pas lu, ignored silently).

**Systemd backup timer** :
- `ce004b6` [ops] deploy/presage-backup.{service,timer} : oneshot daily 04:00 UTC, Persistent=true, EnvironmentFile %h/.config/presage/backup.env (secrets hors git).

### Migration Hetzner (executee, non commit dans repo car infra)

VM provisionnee : **CX22 x86_64, Ubuntu 26.04 LTS, IPv4 37.27.247.126, Helsinki**. User `presage` (sudo NOPASSWD, ed25519 key Mac depose a creation VM). pyenv + Python 3.14.4 + venv + 115 packages requirements.txt (torch, anthropic, transformers, telegram, apscheduler). 2G swap + TMPDIR sur disque ($HOME/.cache/pip-tmp persistant `.bashrc`). yfinance GO/NO-GO **PASSE** depuis IP datacenter (NVDA + 4063.T + 000660.KS reels).

OAuth Google rotation effectuee (ajout nouveau client_secret `GOCSPX-xgSJt…BACbk` sans suppression de l'ancien `GOCSPX-TM4Rqx…thNb` — **TODO user : delete l'ancien dans console.cloud.google.com**). `.env` + `credentials.json` + `token.json` scp vers VM (mode 600, owner presage). OAuth refresh-token valide depuis VM (15 labels Gmail visibles, `NewsLetters` matche).

DB snapshot atomique `sqlite3 .backup` (14MB, integrity OK) scp vers VM. Parite confirmee Mac↔VM : 420 signals / 30 positions / 53 theses / 219 predictions.

`presage-serve.service` + `presage-bot.service` deployes (`~/.config/systemd/user/`). `loginctl enable-linger presage` (survit reboot). serve.service start AVANT cutover (validation tunnel SSH dashboard `localhost:8001`→`VM:8000` OK, 200 OK, 476KB HTML valide).

**CUTOVER execute** : pkill Mac bot + `launchctl unload ~/Library/LaunchAgents/com.olivier.presage.plist` (le launchd respawnait sinon — important catch). Re-snapshot DB pour catch les writes recents, atomic swap sur VM (stop serve / `mv bot.db.new bot.db` / restart serve). VM bot `systemctl --user enable --now presage-bot.service` → **Scheduler started with 26 jobs**, 1x Conflict 409 Telegram (~30s overlap window) auto-resolu, premier `[SQL] digest.fetch_signals_for_synthesis rows=16` confirme bot actif sur DB migree. Telegram `/brief` valide e2e par user depuis phone.

**Backup offsite Storage Box BX11** (Falkenstein, 1TB, €3.84/mo, ID #591212) : subaccount `u608897-sub1` cree (base dir `/.ssh/`, **TBD: a re-configurer vers `/presage` pour isolation propre**, scope minimal). Cle ed25519 dediee `~/.ssh/backup_storagebox` sur VM (jamais sur Mac, jamais en repo). Authorized_keys uploaded via SFTP + password (`Presage-Backup-2026!` defini puis utilise une fois — **TODO user : reset a un random fort, password n'est plus utilise apres bootstrap**). Test rsync+key auth OK, dry-run full backup poussee : 6.4MB tarball + 14MB bot.db sur `presage-backups/`. Timer `presage-backup.timer` enable, **prochain trigger Sat 2026-06-06 04:04 UTC** (jitter +0..5min).

### Etat infra apres cutover

- **Bot Telegram + dashboard** : VM Hetzner systemd (linger, Restart=always, demarre au boot, 26 jobs APScheduler)
- **DB** : migree depuis Mac, integrite OK, alembic head 0028
- **Backup** : daily 04:00 UTC → Storage Box, 14j rotation locale, Persistent (catch-up si VM off)
- **Mac** : launchd `com.olivier.presage` unloaded (plus de respawn), bot Mac dead, serve.py local toujours up sur :8000 (inoffensif mais inutile, peut etre kille a froid)
- **tennis-bot** : intact comme demande, separable par binaire `bot.py` (vs `bot.main`)
- **Github** : main au courant (4 commits pushes), repo cloned VM via deploy key SSH (read-only scope)
- **Anthropic budget** : 70 signaux scored ce matin apres unstuck. Toujours risque depletion identique aux jours precedents, mais le mode vacances digest se debloque desormais tout seul au prochain cron quand l'API revient (fix `327e1ea`).

### Taches user residuelles (5 min cumule, tout est non-bloquant)

1. **Google OAuth ancien secret** : console.cloud.google.com → Credentials → ton client `711001773276-…` → delete l'ancien secret `GOCSPX-TM4Rqx…thNb`. 2 min. Sinon 2 secrets actifs en parallele = surface elargie.
2. **Kill Mac serve.py** : `lsof -nP -iTCP:8000 -sTCP:LISTEN` → kill le PID Python (PID 2301 a la fin de session). Cosmetique.
3. **Storage Box password reset** : console Hetzner → storage-box-1 → Subaccounts → `…` u608897-sub1 → Reset password → genere random fort. La cle SSH suffit pour les backups, le password n'est utilise nulle part en prod.
4. **Storage Box base dir** : actuellement `/.ssh/` (clic accidentel pendant le setup). Sub-optimal pour isolation. Edit subaccount → BASE DIRECTORY → tape `presage` (new_directory racine). Backups continueront a marcher tant que `~/.config/presage/backup.env` est sync (BACKUP_REMOTE_PATH=presage-backups inchange).
5. **Anthropic credits** : reload selon ton rythme. Plus de surveillance critique requise — le pipeline survit aux pannes.

### Memoires Claude sync ce jour

- `pending_llm_no_double_gate` : feedback regle source unique de verite cron drain
- `hetzner_migration_triggered` : project, override `migration_solofounder_only` sur partie infra

### Inputs pour reprise (cold-start)

- Acces VM : `ssh presage@37.27.247.126` (cle ed25519 Mac)
- Tunnel dashboard : `ssh -L 8001:localhost:8000 presage@37.27.247.126` puis http://localhost:8001/dashboard.html
- Logs bot : `journalctl --user -u presage-bot -f` sur VM
- Logs backup : `journalctl --user -u presage-backup.service` + `systemctl --user list-timers presage-backup`
- Storage Box browse : `sftp -P 23 -i ~/.ssh/backup_storagebox u608897-sub1@u608897-sub1.your-storagebox.de` (depuis VM)
- Mac : `~/Library/LaunchAgents/com.olivier.presage.plist` reste sur le disque (unloaded) — re-load possible via `launchctl load` si rollback necessaire
- Backup pre-rotation OAuth : `credentials.json.pre-rotation-20260605` (Mac, untracked)

### Entry next session

- **Verifier le 1er backup automatique** : Sat 2026-06-06 04:04 UTC. `ssh presage@37.27.247.126 'journalctl --user -u presage-backup -n 30'` doit montrer un run reussi. Si fail, debugger avant la prochaine fenetre 24h.
- **J-day 10/06** : le batch resolution Brier (cron `j_day_batch_close_job` date-trigger 2026-06-10 09:30) tourne maintenant **sur la VM**, pas sur Mac. Le scheduler dump initial montrait 26 jobs charges. Verifier explicitement le 09/06 que ce job est bien dans la liste avec next_run correct (P1 audit #3 du SESSION_STATE 03/06 reste valable, mais a verifier cote VM maintenant).
- Si tu reprends apres pause : verifier `systemctl --user is-active presage-bot presage-serve` retourne `active` x2.


---

## SESSION CLOSE 05/06/2026 — Extension soir : analytics push + /audit en flow

Continuation de la session marathon du 05/06. Apres la migration Hetzner +
backup offsite + J-day prep du matin/aprem, la soiree s'est focalisee sur la
construction d'outils d'analyse data + leur surface dans le flow.

### Livre (18 commits supplementaires, branch main)

**LLM cost optimization** :
- `aee073d` Tier `narrate` (Sonnet) ajoute pour restitution narrative.
  Switch 3 sites Opus→Sonnet : portfolio_grade_llm, bot_conceptions,
  user_profile. Espacement crons : classify 30min→2h, mat_v2 + recompute_boost
  1h→6h. Doctrine validee : ne PAS toucher decision_copilot ni dashboard/chat
  (user-facing copilot quality preservee).

**J-day reading contract pre-registration** :
- `d298b01` N=20, M=0.03 commit, **verdict CI-based** (pas point estimate
  franchissant M). M=0.03 reste comme readability floor mais le binding
  verdict est CI bootstrap excluant baseline 0.250. Section "Pre-resolution
  forecast" ajoutee : V1 cohort 10/06 essentiellement decide d'avance comme
  "did not earn / inconclusive" -- M=0.03 mord vraiment sur V2.

**P1 fix orphan decisions + currency NaN** :
- `16e22bb` 5 decisions du 03/06 (74-78) orphelines : positions.py manquait
  `record_anchor`. Source-direct fix + auto-close these sur full_exit +
  backfill 5 counterfactuals marker `backfill_05_06_orphan` + close SNOW
  these 53 active→concluded. Test edgar e2e schema fix (manque scoring_trace
  + source_metadata + methodology_version columns).
- `53446f8` currency_native gate : `math.isnan` check ajoute. Avant : NaN <= 0
  False -> ratio NaN comparait False -> faux mismatch fire. ALAB/MP plus
  rejetes par yfinance NaN occasionnel.

**Doc + setup** :
- `50b8ea1` PROVISION.md retrospective post-migration : 200+ lignes catalogues
  tous les gotchas reels (user non-root, swap 2G + TMPDIR persistant, deploy
  key SSH > PAT, OAuth Add secret nouvelle UI, launchd unload avant pkill,
  Storage Box subaccount + cle SFTP, Healthchecks).
- `8566520` `.claude/settings.json` projet (3 ruff check patterns durables)
  + `.gitignore credentials.json.pre-*`

**6 outils d'analyse data (chantier majeur)** :
- `aacefc7` + `76ae9dd` **thesis_clusters_brier.py** : KMeans embedding
  key_drivers + Brier per cluster + decomposition par conviction × direction
  × status. Output cohort : silhouette 0.046 faible (key_drivers partagent
  "AI capex"), tous Brier ~0.30 INCONCLUSIVE.
- `31b20d7` **source_attribution_brier.py** : Brier par source signal avec
  dual reporting raw vs dedup signal_id. Revelation cohort : 25 raw = 9
  signaux uniques (compression 3.6x par theme correlation).
- `069f0b2` **calibration_plot.py** : reliability diagram + ECE. Confirme
  empiriquement V1 mono-bucket [0.626, 0.658] (spread 3.2pt seulement). ECE
  dedup = 30.7pt = antiskill grave (predicted 0.64, realized 0.33).
- `68b661c` **measure_bias filter TEST_*** + **bias_ledger.py**. Decouverte
  critique : ledger boucle-de-soi 100% pollue par tests e2e (30/30 resolutions
  TEST_SL_*). Avant fix : "100% lock_in confirme -6000 EUR" = mensonger.
  Apres fix : 0 vraies resolutions, 13 ancres reelles pending mature ~28/06.
- `f4b2041` + `bf4a9a4` **decision_audit.py** : per-decision view avec
  classification PUSHED_THROUGH / BLIND_SPOT / COPILOT_WRONG / OK / PENDING.
  Cohort 21 decisions / 16 avec copilot / 13 avec cf / 0 mature.
- `3d48fc0` **materiality_validation.py** : Spearman rho impact_magnitude vs
  Brier quality. rho=-0.254 directionnel ANTI-correle (sous seuil ±0.3,
  FLAT verdict). Materiality_v2 V1 pourrait etre miscalibree -- a confirmer
  post-J-day a N plus grand.

**Test isolation fix source-direct** :
- `2b56b5c` `test_pipeline_end_to_end.py` ajout fixture `isolated_full_db`
  opt-in pour les 2 tests qui INSERT (decision_creates_counterfactual_anchor
  + position_audit_log_append_only). Pollution stoppee a la source : 50
  TEST_E2E_DEC count avant/apres run = identique. La pollution historique
  (200 rows) reste en append-only mais ignored au query-time.

**Telegram handler /audit en flow quotidien** :
- `f5cabf5` + `db7f198` + `3a12f59` **`/audit` handler** : reuse logique
  decision_audit.py + format Telegram compact lisible.
  - Pattern : group par date · verdicts en mots (⛔ Stop · ⚠️ Pression · ✓ OK)
    · branches cf en francais (vs vendre · vs garder) · 💸 marker winner-sell
  - Coverage corrige (count only non-NULL verdicts)
  - Wired dans bot/registry.py
  - Deploye VM + restart bot. Tape `/audit` ou `/audit 14` ou `/audit MU`.

### Findings de cette extension

- **V1 mono-bucket confirme** : probas distinctes 0.626/0.638/0.656/0.658 (3.2pt).
- **Compression theme correlation** : 25 predictions = 9 signaux indep (3.6x).
- **Ledger boucle-de-soi 100% pollue** (avant fix) par tests TEST_SL_*.
- **5 décisions du 03/06 sans counterfactual** = positions.py manquait record_anchor.
- **0/30 ancres reelles mature** : premiers verdicts vers 27-28/06.
- **Materiality_v2 rho=-0.254** : directionnel inverse, sous seuil significance.

### Etat post-extension

- VM tourne H24, /audit dispo Telegram + 6 scripts CLI ad-hoc
- 26 commits cumulatifs aujourd'hui (matin + extension soir)
- Pollution test data : stoppee a la source + filtree query-time
- J-day reading contract pre-registered avec methodologie CI-based

### Outils ajoutes (extension)

- 6 scripts standalone CLI : `scripts/thesis_clusters_brier.py` ·
  `source_attribution_brier.py` · `calibration_plot.py` · `bias_ledger.py` ·
  `decision_audit.py` · `materiality_validation.py`
- 1 Telegram handler : `/audit` (la seule surface user-facing reguliere)
- 1 backfill script one-shot : `backfill_orphan_decisions_20260605.py` (done)

### Entry next session (extension override le matin)

- **Verifier le 1er backup automatique** : Sat 2026-06-06 04:04 UTC. Toujours
  le 1er trigger automatique a observer demain matin.
- **Tester /audit en flow regulier** -- tirer 1x/jour pendant 1 semaine pour
  voir si la routine prend. Si oui = on garde. Si non = simplifier output
  ou retirer du registry.
- **J-day 10/06** : armer mentalement, sortir `post_resolution_brier_report.py`
  9h05 + run les 6 outils d'analyse pour decomposition. Les resultats seront
  probablement INCONCLUSIVE/NULL par construction N=15 dedup.
- **D+30 boucle-de-soi 27-28/06** : 1ers verdicts reels (13 ancres ALAB/MU/LNG/
  CCJ/MP/...) sur biais #1. C'est le VRAI test du projet, pas le 10/06.
- **Materiality_v2 audit** : si rho reste anti-correle a N plus grand
  post-J-day, c'est un meta-bug a investiguer (scorer pose etiquette inverse
  a realite predictive).


---

## SESSION CLOSE 06/06/2026 — CI fix + /review + refonte targets 26 theses

Session continue jusqu'au matin du 06/06 puis chantier majeur de la journee :
diagnostic + fix CI (rouge depuis toujours), construction du handler /review
TICKER, et refonte tailor-made des cibles sur LES 26 theses actives du book.

### Livre (11 commits, branch main)

**CI red 3-jours fix complet (jamais ete vert sur 100 runs)** :
- `d3b23bf` test_resolution_rules_registry : caplog flake en suite -> monkeypatch
  direct sur learning.log.error. Pattern documente dans test_portfolio_metrics
  + test_sql_observability mais nouveau test ne l'avait pas suivi.
- `64e4d64` CI mypy : 2 errors learning.py (registered list[int] annotation,
  float(rule.get()) cast object incompatible). Locally Success, was blocking CI.
- `fe0238c` + `aac6f72` CI : marker `live_data` + skip 13 fichiers qui lisent
  storage.DB_PATH (data/bot.db gitignored, absent en CI -> sqlite3
  OperationalError sur 100 tests). Pytest.ini + ci.yml updated. Result : CI
  vert pour la 1ere fois historiquement sur commit aac6f72.
- `d5aa953` post #06 draft : "trois jours de CI rouge invisible" -- recit du
  debug + lecon doctrinale "un commentaire dans le code n'est pas un mecanisme".

**Currency_native gate etendu** :
- `e18ff54` extension du gate a target_price + target_partial + target_full +
  entry_price (avant : stop_price seul). Bug 6857.T target_price=234.82 vs
  entry_price=24215 JPY = -99% ratio aberrant l'avait revele. Tolerance haute
  relevee 1.1 -> 3.0 pour supporter targets +60-100% above current.

**Handler /review TICKER (chantier majeur)** :
- `9d83446` config/sectors.yaml : mapping ticker -> sector + index benchmark +
  cycle_phase user-signed. 5 secteurs : semis (SOXX, late), energy_commodities
  (XLE, early), defense_industrials_eu (XAR, mid), tech_mega (XLK, late),
  auto_ev (DRIV, contraction). 26 tickers couverts.
- `29dc215` bot/handlers/review.py + bot/registry.py + shared/storage.py
  (get_signals_for_ticker enrichi avec impact_magnitude). Fact-sheet
  contextuel zero LLM : PnL + perf 1y/2y vs sector index + valo (P/E, P/S
  via yfinance.info) + cibles + asymmetry + top 3 signaux + cycle note.
  /review NVDA et /review CCJ smoke-tested OK.
- `0ecfb0d` /review fix PnL EUR : positions.avg_cost stocke EUR (convention
  legacy), pas native. Bug revele via 6857.T affichant +531% au lieu de +1.3%.
  Audit positions/avg_cost vs entry_price ratio montre la convention claire :
  Asia 0.001-0.006 (1/JPY), US 0.37-0.94 (1/USD), EU 0.78-0.83 (proche 1).

**Refonte cibles 26 theses (tailor-made, doctrine non-aveugle)** :
- Avant : stop -25% partout, partial +30-35% par conviction, full +50-60%.
  Generique-aveugle, pas these-specific.
- Apres : 9 patterns differents appliques selon analyse contextuelle
  (perf vs sector, valo, cycle, PnL, signaux recents) :
  * **Strong A renforce** : ASML.AS, TSM, COHR, GOOGL, AMD, MU, STMPA.PA --
    -15% / +20% / +40%
  * **ALAB bump** : -15% / +25% / +60% (current 275 EUR depassait full 245)
  * **EU defense A standard** : SAF.PA, SU.PA -- -15% / +15% / +30%
  * **HO.PA protection profit** : -10% / +15% / +30% (PnL +184% massif)
  * **Energy commodities** : CCJ, LNG, MP -- -20% / +15% / +25%
  * **6857.T tight** : -9% / +10% / +17% (cycle late + valo P/E 112)
  * **000660.KS late memory** : -15% / +15% / +25%
  * **C standard** : BESI.AS, KLAC, 6920.T, 7011.T, TSLA -- -12% / +12% / +25%
  * **B revision** : SNPS, 4063.T, AVGO, ENTG, AMZN -- -10% / +10% / +20%

**Data fixes positions.avg_cost** :
- 6857.T : 4238 (legacy pre-split EUR) -> 143 EUR (vrai cost basis user-provided)
- 000660.KS : 1163 -> 1060 EUR (vrai cost basis : 2000 EUR a 1060/share - 490
  sell at 1325/share -> avg reste 1060)
- TSLA : conviction 2 -> 4 (call personnel user, pas data-driven)

**Trailing stops profit-protection** :
- AMD : stop 328 EUR -> 396 EUR (= -15% from current 466 USD, locks +2.6% gain
  min vs +177% PnL actuel)
- STMPA.PA : stop 44.66 EUR -> 53.40 EUR (= -15% from current 62.82, locks +1.6%
  vs +175% PnL)
- HO.PA skip (trailing aurait degrade le stop existant)

### Audit avg_cost complet sur 26 positions

Verifie systematiquement avg_cost vs current_price_in_eur :
- 0 nouveau bug detecte (au-dela des 2 fixes)
- 3 PnL +100%+ flagges comme suspects : AMD, HO.PA, STMPA.PA -- verifie
  manuellement, ces gains sont REELS (AMD AI rally 2023->26, Thales pre-Ukraine,
  ST Micro rally). Pas un bug, vraie position long-tenue.
- Convention EUR pour positions.avg_cost confirmee coherente sur 24 positions.
- Implication : le track record post-J-day pourra etre publie sans honte sur
  les PnL.

### Findings / leçons

- **CI red invisible** : 100 runs jamais verts. Le repo a toujours eu le bug
  CI (storage.DB_PATH absent en CI) -- jamais corrige, jamais signale. Lecon
  doctrinale (cf post #06) : "un commentaire dans le code n'est pas un
  mecanisme, mecaniser la connaissance via gate (linter, fixture autouse)".
- **Bug 6857.T target_price + avg_cost** : double bug currency. Gate ne
  checkait que stop_price -> a passe silencieusement. Gate etendu maintenant.
  Cf risque similaire sur autres positions, audit clean fait.
- **PRESAGE refonte targets = progres doctrinal, pas predictif** : "plus proche
  du reel" sur dimensions discipline + audit trail. PAS sur dimensions alpha
  predictif (qui n'est pas le wedge anyway per [[business-path-6-acted]]).
  Risque cache = faux sentiment de progres ("tailor-made donc mieux" n'est
  pas une preuve).

### Outils ajoutes

- `bot/handlers/review.py` (handler `/review TICKER`)
- `config/sectors.yaml` (mapping ticker -> sector + cycle phase user-signed)
- pytest.ini marker `live_data` documente
- `.github/workflows/ci.yml` skip `-m "not slow and not live_data"`

### Entry next session

- **CI desormais vert** -- premiere fois historique. A garder en lisant la
  CI badge github sur chaque push. Si rouge -> investiguer immediatement.
- **Verification trading IRL sur les nouvelles cibles** : Mac + VM ont les
  26 thèses refondues avec patterns documentes dans theses.notes. Si tu
  touches un stop ou un target dans les jours/semaines a venir, le contexte
  est defendable (audit trail propre). Surveiller particulierement les 3
  trailing stops (AMD, STMPA.PA) qui sont above-entry.
- **Cycle phases user-signed** : a re-evaluer trimestriellement
  (~01/09 prochaine). Si late->mid sur semis change, tout les patterns
  derive doivent etre revisites.
- **J-day 10/06** : prep complete, healthchecks armed. Tirer
  `post_resolution_brier_report` 9h05 + les 6 outils analyse data.
- **D+30 boucle-de-soi 27-28/06** : 13 ancres reelles mature. Premiers
  vrais verdicts biais lock_in. `python -m scripts.bias_ledger` te dira.

### Audit avg_cost backlog (audit suivant)

Pas urgent, mais a revisiter avant publication track record public :
- Verifier 2-3 positions plus anciennes pour confirmer la convention EUR
  tient sur la duree (notamment KLAC, ASML.AS, ENTG qui sont prises depuis
  longtemps a priori).
- Documenter la convention `positions.avg_cost = EUR` en commentaire
  schema/migration alembic dediee.

---

## Close 2026-06-06 (apres-midi) — Macro stress monitor refondu (Phase A/B/C/D + accuracy + 3 iterations de calibration)

Session monolithique sur le panneau "MACRO STRESS MONITOR -- score X" de
`_urgence` (dashboard/render.py). User initial : "à nous de developper ce
panneau et le rendre vraiment intelligent et warning". Livraison en 4
phases + 3 iterations de calibration suite a audits successifs.

### Livre

**4 phases architecturales (commits `88e5b09` -> `acd3302` -> `24256e9`
-> `d899d44`)** :
- **Phase D (honnetete)** : NULL value plus rendue `0.0000%` en vert mais
  `&mdash;` + class mute + badge `no data` rouge. Stale > tier threshold
  : badge `stale Nd`. Sort secondaire stale apres fresh meme dot.
- **Phase C (triage)** : remplacement liste plate `tier 1/2/3` par
  buckets `ACT NOW / WATCH / CALM / SILENT` ordonnes par stress.
  Tier chip (M&L / BANK / SLOW) preserve sur chaque row.
- **Phase A (regime detector)** : `intelligence/macro_regime.py` +
  migration `0029_macro_regime_alerts` + `shared/storage.py` helpers
  insert/get_latest + 9 tests (dont L4 idempotence + missing-data safe).
  Classifier deterministe 5 buckets (COMPLACENT / RISK_ON / LATE_CYCLE
  / FRAGILE / STRESS), independant V3 composite. Chip regime dans le
  header avec tooltip detaille triggers.
- **Phase B (tie-to-book)** : `intelligence/macro_book_warnings.py`
  + 9 tests. 5 regles deterministes regime x composition book :
  R1 semis concentration / R2 carry unwind JP / R3 growth-tech
  dominance / R4 auto_ev stress / R5 complacent hedge. Bloc "Macro
  impact on book" sous l'indicator grid.

**Accuracy chantier (commit `186406b`)** suite user "we need the data
to always be the latest, accuracy is the basic of what we need" :
- `cron_tier1_daily` : hour=6 -> hour="6,12,18,22" (4x/jour).
- MOVE bond vol promu tier2_weekly -> tier1 daily.
- `persist_signal` no-stomp fix : fetch fail (FRED late publish,
  network glitch) ne stomp plus NULL la derniere valeur valide.
- `cron_tier3_monthly` : day=1 -> day="1,5,10,15" retry pattern
  pour rattraper FRED late publish (CPI publie typiquement mid-month).
- CoreCPI NULL fix : 5j de NULL chronique resolu, value 2.74% maintenant
  en DB.

**Calibration iterations (3 commits)** :
- `5afd248` (bands v2 dur) : 10 indicateurs durcis (VIX 16/22->14/18,
  HY 250/400->220/320, TYX 4.0/4.6->3.8/4.2, etc.). Tooltips resync
  (zero mismatch tooltip-vs-band restant). Rename UI label ASLEEP -> CALM.
- `266b28e` (gauges align) : V3 phase_ranges aligne sur bands +
  VIX vol_scaling_threshold 25 -> 20.
- `de8c48c` (v3 +5% margin) : user "peut-etre alle un peu fort,
  rajoute 5% de marge". Loosen v2 dur. Score V3 126 -> 98.
- `e8dbc98` (drift fix R1/R2/R5) : audit cross-file revele 3 thresholds
  dans macro_book_warnings.py non syncs avec v3 (TYX 4.5->4.2,
  USDJPY 158->154, VIX 13->12).
- `7d0f683` (hard reality) : user "are the greens realistic ?".
  Audit 8 CALMs revele 4 trompeurs. Reverse +5% margin sur T10Y2Y
  (warn 0.28->0.5) + DXY (warn 103->98). Ajout bands explicites pour
  CopperGold (0.0015, 0.0008) et BankReserves (3.2T, 2.5T). Score V3
  98 -> 120 (phase 4 CRISIS).

### Etat final post-session (data fresh Mac + VM)

- **Regime** : STRESS (VIX 21.51 > 21 trigger)
- **V3 composite** : score 120, phase 4 CRISIS (frise)
- **Buckets** : ACT 4 / WATCH 7 / CALM 4 / SILENT 0
- **ACT NOW (4)** : VIX, TYX, USDJPY, BTC_drawdown180 (tous P3+)
- **WATCH (7)** : Gold, HY_OAS, CoreCPI, DXY, T10Y2Y, BankReserves,
  CopperGold (tous P2)
- **CALM legitime (4)** : KRE, FedBalance_yoy, MfgIP_yoy, MOVE
- **Book warnings (3 actifs)** : R1 HIGH raise stops semis (64%),
  R2 HIGH verify JP hedge (23%), R4 MED rightsize TSLA
- **CoreCPI** : 2.74% en DB (etait NULL chronique)
- **VM systemd** restarted x4, dashboard live a `localhost:8001` via tunnel

### Cross-file consistency (audit explicite mi-session)

- `dashboard/render.py` _MACRO_BANDS : v3-fix (10 entries)
- `dashboard/render.py` _MACRO_TIPS : v3-fix tooltips resync
- `intelligence/macro_regime.py` classifier : v3-fix (8 constants)
- `intelligence/macro_book_warnings.py` R1/R2/R5 : v3-fix
- `intelligence/debt_monitor.py` INDICATOR_CONFIG phase_ranges : v3-fix
- `config.yaml` vol_scaling_threshold_vix : 20 (= _VIX_STRESS)
- `composite_phase_from_score` (22/60/115) : unchanged volontairement

### Tests

- `tests/test_macro_regime.py` : 9 tests (5 regimes + L4 idempotence
  + missing-data safe + 6+ warn threshold boundary)
- `tests/test_macro_book_warnings.py` : 9 tests (R1-R5 fire + silent
  when no condition + sort by severity + max 4 cap + empty book safe)
- Full suite : 854 + 18 new = ok au moment du commit `7d0f683`

### Outils ajoutes

- Migration alembic `0029_macro_regime_alerts` : table journal
  append-only des evaluations regime (status, score, danger/warn/calm/
  silent counts, triggers JSON, transition).

### Entry next session

- **Cron tier1 4x/jour actif** : verifier qu'il tourne correctement
  (logs `dashboard/serve.log` + `tail -f` du bot service systemd VM).
  Si fail, monitor `data/bot.db` debt_signals age via badge `stale Nd`
  dans le panel (auto-surface).
- **CoreCPI tier3 retry pattern** : la prochaine refresh automatique
  est `2026-07-01` puis 05/10/15 du mois. Verifier que CoreCPI reste
  populated (badge `no data` doit etre absent ; CoreCPI ne doit pas
  re-tomber a NULL).
- **Regime track** : le journal `macro_regime_alerts` est present mais
  `check_regime_transition` n'est PAS encore cable a un cron. Add
  call apres `cron_tier1_daily` pour persister + notifier les
  transitions (FRAGILE -> STRESS par exemple). Deferred Phase A.5.
- **VIX vol_scaling actif (threshold 21)** : actuellement VIX 21.5
  > 21 = sizing reduce -30% sur toute nouvelle position. Si tu prends
  une nouvelle position, le size sera 70% du target normal. Si ca te
  derange (phase construction), rebump a 22 ou 23 (mais classifier
  STRESS suivra independant).
- **Frise V3 = phase 4 CRISIS** : score 120, c'est honnete vu les
  5 P3 + 6 P2. La frise tagged exploratoire toujours mais le visuel
  fait sens. Si tu trouves CRISIS trop alarmiste, relax
  `composite_phase_from_score` (22/60/115) -> (30/80/150).
- **Telegram dispatch markdown bug** : observe pendant cron_tier3
  ("Bad Request: can't parse entities"). Non bloquant mais a fix.
  Probable double-asterisque ou char markdown unescaped dans
  `_dispatch_alerts`. Investiguer si recurrent.
- **J-day 10/06 imminent** (J-4) : prep complete pre-session, aucune
  action ajoutee aujourd'hui. Tirer `post_resolution_brier_report`
  9h05.

---

## Close 2026-06-06 (soiree) — Calibration pro v5 + friction decision + audit positions truth

Session monstre apres-midi+soiree avec multiple chantiers structuraux.
Le panneau macro stress monitor a passe de "v2 pieces hardcoded" a
"v5 canonical evolutif". Le systeme intervient maintenant au point de
decision (`/trade` 2-step), mesure les outcomes (retrospective +30j/+90j)
et detecte ses propres signaux qui ratent (audit_calibration sanity check).

### Livre (16 commits supplementaires + 1 close)

**Audit calibration v4 macro + canonical** :
- `5afd248` audit pro v4 (FRED/JPM/GS/Bloomberg/Cboe/Tradingeconomics)
  -> HY_OAS recalibre 230/335->300/400, USDJPY 154->155 (BoJ intervention
  >73Mds$ depenses avr-mai 2026 confirmee), DXY 98/101->100/104,
  CoreCPI 2.4/2.9->2.5/3.0, MfgIP 0.95/0.28->1.0/0.0,
  BankReserves 3.2T/2.5T->3.0T/2.8T (ajuste taille bilan x2 depuis 2019)
- `a6b3d4e` canonical `config/calibration.yaml` source unique evolutive,
  shared/calibration.py loader, refactor render.py + macro_regime +
  macro_book_warnings pour lire de la, chip "calib v5 - 2026-06-06"
  dans panel header
- `docs/calibration_audits/2026-06-06_v4.md` rapport archive

**Audit panels v5 + fix bug structurel** :
- `03083ca` audit RSI/Breadth/Risque/Concentration/Drawdown (StreetStats/
  StockCharts/CXO/SentimenTrader/VanTharp/Minervini refs)
  -> Risque WRONG STRUCTUREL : `heat = max(tensions)` faux,
  fixe en `heat = sum(weight_share * downside_pct)`. Sur le book
  actuel : heat 60deg ancien -> 16.6% capital at risk
  -> Cluster 70% supercycle dangereux en STRESS (audit identifie le
  besoin d'un auto-derisk gate, livre Phase A plus tard)
  -> Breadth manque S5FI (preparé canonique mais wire fetcher Phase ulterieure)
- `docs/calibration_audits/2026-06-06_v5_panels.md`

**Friction decision #1** :
- `b5e910c` `bot/handlers/trade_context.py` : compute_trade_context
  retourne {regime, cluster_share_before/after, regime_warnings,
  bias_warnings, signals_30d_str}. Pattern 2-step :
  /trade buy NVDA 10 450 -> renvoie context + token 6-hex TTL 60s
  /trade confirm <token> -> execute
  /trade cancel <token> -> annule
- Detection bias : LOCK_IN si sell PnL >= 15% + conviction >= 3 ;
  FOMO si buy apres run +15% sur 7j ; CIRCUIT_BREAKER si Elder
  active ; OVERDILUTION si sell amenerait book sous min_positions 8

**Tagging contextuel #2 + retrospective** :
- `46aea7b` migration 0030 `position_decisions_context` (snapshot
  canonique au confirm), `intelligence/retrospective_decisions.py`
  classify_verdict {aligned_positive, aligned_negative, against_positive,
  against_negative, neutral}, cron 9h30 daily processe +30j et +90j.
  Etat futur : alimente bias_ledger en donnees per-decision.

**Phase A wire 4 calibrations v5** :
- `e8b98bf` cluster STRESS auto-derisk dans compute_grade (cap a 70
  si regime STRESS + cluster > 55%) ; VIX 2-tier scaling (factor 0.5
  si VIX > 30) ; min positions 8 (anti-overdilution); portfolio
  circuit breaker Elder (-6%/mois) + cron 9h45 + Telegram alert.

**Fix BUG MAJEUR price_monitor** :
- `16ab071` Le code comparait current_price_in_eur avec target_full /
  target_partial / stop_price qui sont stockes en NATIVE currency
  (KRW/JPY/USD selon ticker, doctrine `[[currency-native-invariant]]`).
  Resultat : 12 alertes manques + faux stops triggered.
  Le commentaire dans le code "EUR canonical, DO NOT migrate" etait
  obsolete (anterieur a la migration native).
  Fix : prices.get_current_price (NATIVE) + ajout check target_partial
  qui etait totalement absent du code (bug #2).
  Apres fix : 14 alertes firent correctement (000660.KS + ALAB FULL,
  10 PARTIAL sur 4063.T/6857.T/6920.T/AMD/CCJ/ENTG/KLAC/LNG/MU/STMPA.PA).
  6 faux triggered_stop_at clearés.

**Phase B audit_calibration cron 10j** :
- `77cc8ce` `intelligence/audit_calibration.py` : daily check, si
  last_audit > 10j trigger run_audit_refresh : sanity check auto sur
  historique 14j (stuck_warn / stuck_danger / never_warn flags),
  ecrit `docs/calibration_audits/YYYY-MM-DD_v(N+1)_skeleton.md` avec
  findings auto + prompt structure pour recherche pro humaine ou
  Claude Code. Telegram ping. Doctrine voie clean auditable :
  pas d'auto-apply, user review + apply manuellement.
- Wire cron 8h00 quotidien daily check.

**Reconciliation positions DB <-> broker truth** :
- User a envoye qty + avg_cost reels pour ses 26 positions :
  20 CTO (Trade Republic) + 6 PEA (Boursorama). Bulk UPDATE
  positions table Mac + VM avec ses valeurs exactes.
  Cost total post-update : 44 239 EUR.
  Valeur yfinance live : 52 763 EUR (gap +790 EUR sur tickers
  asiatiques = FX spread broker vs yfinance, non-erreur).
  Anomalies signifiantes detectees :
   - 4063.T : qty 112.76 -> 115.26 (+2.5 actions, buy non-logge)
   - 7011.T : qty 109.97 -> 112.73 (+2.76 actions, buy non-logge)
   - GOOGL : avg 285.42 -> 257.60 (-28 EUR/share, cost surestime)
   - AMZN, 6920.T : ecarts mineurs avg/qty
  Gate position_invariants : 0 violations post-update.

**Precision B FX-aware tooltip** :
- `11ed595` cas SK Hynix : panel "Closest to target" affichait
  "+11.3% beyond" en KRW natif mais user perceived seulement +8.6%
  en EUR. FX KRW s'est affaibli 26% depuis creation thesis.
  Doctrine currency-native-invariant preservee, tooltip enrichi :
   "native 2,070,000 vs target 1,860,305 = +11.3% en native |
    EUR : 1151.33 vs avg cost 1060.00 = +8.6% gain reel"
  Heuristic detection : implied_fx > 2 = ticker non-USD.

**Precision A audit (existing infra)** :
- recalibrate_source_credibility EXISTE deja (cron mensuel 1er 6h00 +
  monthly_track_record_snapshot_job 8h00). DRY-RUN retourne 0 sources
  car canonical_predictions_filter exclut V1 (ADR 014). Sur 35
  resolutions, toutes sont V1. Le mecanisme attend V2 = automne 2026.
  Pas de fix code, documentation honnete via commit message.

### Etat final post-session

- 877 tests verts (+ ~25 nouveaux dans la session)
- Mac + VM synced
- alembic head 0030 (position_decisions_context)
- Backup DB : data/bot.db.backup_session_close_20260606_192531
- Calibration v5 canonical avec chip audit visible dans panel
- 26 positions reconciliées avec broker truth (44 239 EUR cost exact)
- Price monitor cron fixe (14 alerts manques vont firer prochain run)
- Friction decision active sur /trade (2-step confirm)
- Retrospective +30/+90j arme (cron 9h30 daily)
- Cluster STRESS gate + VIX 2-tier + min positions + Elder breaker actifs
- Audit calibration cron 10j tournera demain matin 8h
- VM presage-bot + presage-serve restartes plusieurs fois durant la session

### Entry next session

- **J-day 10/06 imminent (J-4)** : verifier `daily_resolve_job` 9h00 +
  `post_resolution_brier_report` 9h05. Healthchecks armed. Brier ~0.295
  attendu (V1 mediocre = baseline figee pour future comparaison V2).
- **Price monitor : verifier que les 14 alertes manques ont firé**
  proprement lors du premier cron 14h00 (lundi 08/06). Telegram
  attendu avec emojis 🎯/🎯🎯 selon partial/full.
- **Friction décision : tester live `/trade` flow** en condition
  reelle. Ajustments UX possibles : token TTL 60s assez ? tooltip
  lisible ? bias warnings utiles vs noise ?
- **Position decisions context : remplir au moins 1 row test** via
  un `/trade confirm` pour valider le pipeline snapshot -> +30j.
- **Audit calibration cron** : verifier que 8h00 demain matin ecrit
  un skeleton dans `docs/calibration_audits/`. Sanity check current
  state : 9 findings auto (BTC/CopperGold/CoreCPI stuck_warn) -
  attendus en regime FRAGILE actuel.
- **D+30 boucle-de-soi 27-28/06** : 13 ancres reelles mature. Premiers
  vrais verdicts biais lock_in.
- **Anomalies positions** : 4063.T et 7011.T avaient des actions non-logges
  (+2.5 et +2.76 actions). Trouver les trades manquants dans le journal
  broker historique si traceabilite importe pour Brier future.
- **Telegram markdown bug** : recurrent sur multiple alerts (price_monitor +
  cron_tier3). Pollue le dispatch + masque les notifications. A fix
  separement, non-bloquant fonctionnellement.
- **FX-aware tooltip** : verifier visuellement sur le dashboard que
  l'enrichissement apparait bien pour SK Hynix sur "Closest to target".
