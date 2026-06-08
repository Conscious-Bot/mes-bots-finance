# TODO — PRESAGE (mes-bots-finance)

**Refresh** : 09 juin 2026 nuit++ (désynchro broker↔DB découverte sur 5 positions, SK Hynix réaligné, cure racine `partial_close handler` ouverte)
**Mode** : **FOUNDATION FIRST. AUDITABLE PAR ADVERSAIRE.** Capstone red-team nuit++ accepte.
**Archives** : `/tmp/TODO_pre_refresh_*.md` (historique des refresh)

---

## 🔴 P0 IMMÉDIAT (09/06 nuit++) — Désynchro broker↔DB + cure `partial_close handler`

**Découverte cette nuit** : la cure money de la session précédente (Datum[Monetary], 6/6 serrures, primitif `book.value_eur`) était architecturalement correcte mais s'appuyait sur un state DB déjà désynchronisé du broker. Le pipeline broker import fait du `qty alignment` cosmétique mais ne déclenche AUCUN `partial_close handler` — donc `avg_cost_eur`, `realized_pnl`, et niveaux thèse jamais recalculés post-vente partielle.

**Portée constatée** : 5 positions avec signes de désynchro (audit `position_audit_log` id=83 SK Hynix + inventory). SK Hynix réaligné cette nuit (qty 1.4809 → 1.515580, avg_eur 1085 → 1060, rPnL 77.88 → 98.37, audit log). **4 positions attendent ground truth Olivier** :

| Ticker | qty DB | avg_eur DB | realized_pnl DB | Hypothèse |
|---|---|---|---|---|
| **ALAB** | 5.0913 | 184.92 | **+228.49** | vente partielle significative non-réconciliée |
| **MU** | 1.2969 | 431.23 | **+425.33** | vente partielle TRÈS significative |
| **CCJ** | 18.4836 | 93.62 | -7.72 | petite vente perdante |
| **6920.T** | 6.6038 | 230.51 | -2.79 | petite vente |

**Tâche #121 (P0 immédiat à froid)** — Reconciliation 4 positions : Olivier dicte timeline trades par nom (date, qty, price, partial vs full). UPDATE positions + INSERT `position_audit_log event_type=input_correction` même pattern que SK Hynix id=83.

**Tâche #122 (P0 — Sprint dédié, cure racine)** — `partial_close handler` proper : quand `broker_import` détecte qty réduite, déclencher recalc `cost_basis` (FIFO vs avg proportionnel — choix méthode comptable explicite), recalc `realized_pnl`, prompt re-target gauge thèse via `position_audit_log`. Tests : 5 invariants (cost_remaining = qty × avg_cost_eur ; realized_pnl = Σ((price_sell - avg_cost_eur_at_sell) × qty_sell) ; etc). Couvre les 5 cas ET prévient pour futures ventes partielles.

**Tâche #123** — Re-target SK Hynix par nom : Olivier dicte nouveaux stop / target_partial / target_full en EUR-broker convention. UPDATE theses + audit. Le panneau gauge SK Hynix reste bizarre tant que niveaux thèse pas re-dictés (entry_value KRW reste, current_price_eur dérivé OK, mais gauge calcule sur entry_native vs current_native).

**Tâche #124** — Audit broader : checker positions historiquement closes (status='closed') pour voir si bug a affecté la comptabilité realized des positions sorties. Si désynchro = `realized_pnl` global mensonger → fix puis re-calcul Brier closes.

---

## 🚨 PIVOT FONDATION (08/06/2026) — RECONSTRUCTION DOCTRINE EN SUSPENS

**Constat méta d'Olivier (08/06)** : « le goulot a changé de place. La session a produit ~15 docs de doctrine d'une cohérence rare et le build est à C6. L'urgent n'est PLUS de penser ou de spécifier — c'est devenu abondant. L'urgent c'est de poser la fondation que toute cette doctrine présuppose. Si je continue à empiler des specs pendant que la base reste fissurée, je reproduis exactement l'anti-pattern que l'audit d'origine a diagnostiqué : un méta-étage brillant qui court devant un socle cassé. »

**Symptômes visibles dans le repo** :
- `eur_value` figé à J-15 (stocké dans notes, pas une colonne typée live)
- Incohérence 0,5× rouge (page positions) vs 1,80× favorable (card) sur le **même ticker** → deux chemins de valorisation divergents
- 14+ imports `yfinance` hors `prices.py` (audit cornerstone seams), donc M1 (triple val/asof/source) n'est jamais honnête
- `base_health.py` (master §5 étape A3) jamais construit — pas de scoreboard, donc pas de signal binaire « base OK / base cassée »
- OTS ancrage prédictions : script existe (`scripts/integrity_anchor.sh`) mais pas wire opérationnel → chaque jour de prédictions sans ancrage = un jour de track-record improuvable après coup (irréversible, gaté par le temps)

**Verdict** : le poids du cornerstone (gouverneur, position-card, fragilité, micro v0) est sur le point d'atterrir DESSUS. Chaque feature cornerstone bâtie sur base cassée mentira en silence. Fenêtre pour corriger à pas cher = MAINTENANT, avant que le poids tombe.

### 🟢 SOCLE — la racine porteuse (masterpiece) + exécution

**Sources canoniques** :
- `SPEC_SOCLE.md` — la **masterpiece** : Datum + propagation + Gateways. M1 + fail-closed + confiance deviennent des **propriétés structurelles** de l'étage au-dessus, pas de la discipline répétée.
- `HANDOFF_SOCLE.md` — exécution ordonnée (S0-S3) + schémas SQL + gates CI + tests + DoD.

**Insight masterpiece** : tout nombre du système est un `Datum[T]` (`value, asof, source, confidence` → `staleness/degraded` calculés). Une seule règle `derive(fn, *inputs)` propage `asof=min`, `confidence=combine`, `degraded=any`. **Tout l'étage compose des Datums passés par des gateways → hérite gratuitement de M1, du fail-closed et de la confiance.**

**Résumé exécutable** :

| Stage | Tâche | Dépend | DoD |
|---|---|---|---|
| **S0** (parallèle, immédiat, IRRÉVERSIBLE) | #108 OTS anchor cron live | — | `.ots` pour ledger courant + committé |
| **S1a** (Datum primitif — la matière) | #109 `shared/datum.py` + `derive()` propagation | — | Datum frozen + derive testé |
| **S1b** (gateways prix/fx) | #106 `prices.get()/fx()` retournent `Datum[T]` + history + gate yfinance | S1a | triple partout + gate active |
| **S2** | #105 migration positions + `value_eur()` dérivé via `derive()` | S1b | `eur_value`-in-notes mort + dérivé partout |
| **S3** | #107 `base_health.py` vert | S1+S2 | GREEN sur Positions vérité + Fraîcheur + Chaîne intègre |

**Invariants porteurs** (cf `SPEC_SOCLE.md` §7) :

1. Pas de float nu au-dessus du socle (gate sur les retours non-typés).
2. Pas de bypass de gateway (gates CI prix/fx/db).
3. `degraded` jamais décidé à la main en haut — il se propage.
4. `base_health` vert = pré-condition de ship book-facing.
5. `Datum` frozen — l'étage **compose**, ne **mute pas**.

**Tant que les 4 DoD ne sont pas verts, AUCUNE partie book-facing du cornerstone (gouverneur, position-card, fragilité) ne ship.** Elles liraient une base cassée et steeraient faux avec assurance. **Le socle d'abord, le poids ensuite.**

### 🟡 EN SUSPENS (reprise après base au vert)

Tâches doctrine/refonte mises **explicitement** en suspens par décision 08/06 :

- **#99** Update 00_HANDOFF_MASTER pile §2 + séquence §5 (insérer 3 SPECs enrichis + L25 dans contrat §7)
- **#100** C7a-1 `config/alert_vocabulary.yaml` + gate CI (aucune alerte hard-codée hors registre)
- **#101** C7a-2 `config/sector_profiles.yaml` + `taxonomy.yaml` (semis tier-S d'abord)
- **#102** C7a-3 Liaison positions↔card refactor (PositionView source unique) — **doublement bloqué** : (a) demande base prix honnête, (b) résout par construction l'incohérence 0,5×/1,80× QUI VIENT DE LA BASE CASSÉE
- **#104** `scripts/audit_canonical_drift.py` + intégration `/close` (mécanisme L25)
- **#88** FUTURE : M2 self-application — Brier-scorer le moteur thesis_erosion
- **#92** FUTURE post-cornerstone-macro : build consensus micro projection per SPEC_CONSENSUS_MICRO
- Reste de C7 (wire 7 autres macro inputs + backtest historique 2015-2024) — pas reprogrammé tant que C7a non démarré

**Doctrine livrée cette session (intacte, attend implémentation)** :
- `SPEC_CORNERSTONE.md` §1 erratum (formule D corrigée via tracer-bullet C6)
- `SPEC_POSITIONS_CARD_LINK.md` enrichi (§7 archi + §8 build + §9 seams + §10 status)
- `SPEC_SECTOR_TAXONOMY.md` enrichi (§7 tests shrinkage + tier-S exclusif + §8 build + §9 seams + §10 status)
- `SPEC_ALERT_VOCABULARY.md` enrichi (§6 archi + §7 gate CI + §8 build sequence)
- `docs/LESSONS.md` L24 (walking skeleton catches formule-wrong) + L25 (suivi du canonique)
- 2 doublons SPEC créés par moi (08/06) supprimés : `SPEC_POSITIONS_CARD_LIAISON.md` + `SPEC_TAXONOMY_PROFILES.md`

---

## 🎯 VISION_PRO + ROADMAP CHRONOLOGIQUE (red-team 07/06 nuit++)

Source spec : `docs/VISION_PRO.md` + `docs/DECISION_QUALITY_ENGINE.md`. Le critere nord, unique : **auditable par un adversaire**. Une due-diligence hostile peut-elle falsifier ou verifier chaque nombre ? Si non = journal intime sophistique, pas outil pro.

### Le pivot (a garder en tete a chaque ligne)

3 plafonds structurels que la calibration sur outcomes ne perce pas :

| Plafond | Nature | Ce qui le perce |
|---|---|---|
| Auto-referentiel | l'operateur note l'operateur -> corruptible | Pre-engagement tamper-evident OTS-ancre (P1) |
| Petit-n | N=35 outcomes = bruit, latence boucle 30j | Process-grading (N=53 immediat, P2) + outside-view (P3) |
| Outcome-graded | Brier ignore quadrant LUCK | Attribution causale 2x2 (P2) |

### Phase 0 — Nettoyer les instruments (semaine 1)

- **0.1** Doc-drift check pre-commit (~45min) -- regen chiffres volatils (tests count 1107 vs annonce, LOC fichiers cites, modules "non instrumentes") + echec si AGENT_HANDOFF/README/CLAUDE.md divergent
- **0.2** Gates CI grep yfinance + sqlite3 ✅ LIVRE (commit 4058a28)
- **0.3** Lancer sondes 7j MAINTENANT (front-load latence 8 semaines) -- predictions-sondes court-horizon taggees `probe`, decouplees des theses 18-24m, accumule Brier vite. N=35 -> ~100 en 8 semaines.

### Phase 1 — Fondation tamper-evident (semaines 1-3) — STATUS PARTIEL

A0-A5 livres comme code (commits a7fc6cc + ce00c18 + 67dc11a + befe687) MAIS **non-trustless** tant que :

- ❌ `anchor_chain_head_daily.py` cron pas wire APScheduler
- ❌ OTS (opentimestamps-client) pas integre operationnel (script `scripts/integrity_anchor.sh` cree, pas execute en cron)
- ❌ ledger jsonl export git-tracke pas committe (bot.db gitignored, donc actuel = pas auditable tier)
- ❌ Bootstrap 219 predictions existantes pas ancrees (user va envoyer le script integrant compute_hash/canonical_payload/GENESIS_HASH + nonce commit-reveal sidecar)
- ❌ Hook `insert_prediction` (storage.py:850, funnel unique confirme) pas ajoute

**Next concret semaine 1** :
1. Recevoir bootstrap script user + insert_prediction hook (user va envoyer)
2. Wire `scripts/integrity_anchor.sh` en cron daily APScheduler ou crontab user
3. Install opentimestamps-client + test ots stamp end-to-end
4. Export ledger jsonl git-tracke + commit initial (bootstrap des 26 + 219)

### Phase 2 — Changer l'objet score (semaines 3-6)

- **2.1** Attribution causale 2x2 ✅ SCAFFOLD LIVRE (`track_record/attribution.py` + 13 tests). Reste a connecter au realized data (ReturnDecomposition needs Bigdata wire ou proxy)
- **2.2** Scorecard process-graded (F1) -- note operateur sur specificite kill-criteria + falsifiabilite variant_perception + taux validation-de-raison. N=53 immediat (process observable par decision, pas N=35 resolus)
- **2.3** factor_exposures -> monitor a transition (~2h) -- pattern monitor_pattern, seuil "AI-broad >75%" -> evenement + notif Telegram

### Phase 3 — Outside view (semaines 5-8)

- **3.1** Base-rate externe Bigdata (`track_record/reference_class.py` scaffold LIVRE, stub jusqu'a wire daloopa). Catch class de reference (Kahneman) : eviter double-comptage tes propres picks dans univers ref.
- **3.2** Reference-class interne par embeddings -- etendre `signal_embeddings` (427 BGE local) aux decisions
- **3.3** Prior a deux etages -- combiner 3.1 + 3.2 avec ponderation explicite (a N=40, prior domine)

### Phase 4 — Asset defendable (semaines 8-12)

- **4.1** Track-record du copilot -- quand decision_copilot objecte et qu'on passe outre, avait-il raison ? Mesurable seulement parce que P1 rend les overrides tamper-evident.
- **4.2** Taux d'angle-mort -- boucle pre-mortem -> post-mortem. Le mode d'echec reel etait-il dans ton pre_mortem ou un angle mort ?
- **4.3** Famille de shadow-books -- discipline stricte / ignore tout / suis seulement c5 / pondere base-rate en parallele. Ressuscite `intelligence/shadow_decisions.py` (code mort).

### Phase 5 — Passage au pro (mois 4-6)

- **5.1** Separer moteur / instance -- kernel scoring-de-jugement domain-agnostique vs book/sources/factors en config
- **5.2** Multi-operateur par isolation-fichier (1 SQLite par operateur, pas Postgres+RLS)
- **5.3** Reproductibilite / pinning modele -- methodology_version + replay
- **5.4** Page track-record publique verifiable -- surface l'asset P1+P4 reproductible par tiers

### Invariants transverses (a graver)

1. **L19** Aucune nouvelle couche calibration tant que N_resolu < 100 ✅ INSCRIT
2. **L20** Outcome-graded ne suffit pas, scorer la decision (attribution 2x2) ✅ INSCRIT
3. Record append-only + OTS-ancre vs config declarative versionnee -- promotion L17
4. Reste outil de process decisionnel, jamais de recommandation (douve regulatoire RIA)
5. Construis la base pour qu'elle puisse t'humilier (volonte de publier resultat nul = credibilite)

### Le wedge

| Produit | Asset | Verdict |
|---|---|---|
| (i) Instrument jugement personnel prouvable (prosumer/Substack) | track-record verifiable | **Base** -- 80% deja construit |
| (ii) Couche discipline pour PMs discretionnaires (B2B) | track-record copilot (F2) | Expansion une fois (i) prouve |
| (iii) Kernel-as-API | -- | **Drop** (distraction) |

Construire (i) d'abord. (ii) en expansion naturelle quand F2 a prouve le lift.

### Vue dependances (spine)

```
P0.1 doc-drift ─┐
P0.2 CI gates ──┤ (parallele)
P0.3 sondes 7j ─┴───► (latence 8 sem, alimente P2/P3/P4)

P1: A0 ► A2 ► A1 ► A3 ► A4(OTS!) ► A5
     └► driver_epic capte ► P2.1 ───┐
                            P2.2 (F1) ◄── N=53 process immediat

P3.1 base-rate ext ┐
P3.2 ref-class int ┴─► prior 2 etages ◄── P2.1 definit "raison validee"

P4.1 copilot TR ◄── exige A4 + temps
P4.2 angle-mort ◄── exige pre_mortem (A3)
P4.3 shadow-books ◄── exige counterfactuals (deja la)

P5: 5.1 moteur/instance ► 5.2 multi-tenant ► 5.3 repro ► 5.4 page publique
```

---

## 🔴 P0 CORRECTIVE QUEUE v2 (red-team 07/06 nuit, refine apres correction 3 faux positifs)

**Pivot framework (red-team analysis 2)** :

| Boucle-marche (commoditisable) | Boucle-de-soi (Path 6 asset) |
|---|---|
| « ma these etait-elle juste ? » | « ma discipline a-t-elle aide ou nui ? » |
| sortie : calibration / Brier | sortie : quantification de biais |
| defendabilite : commoditisable | defendabilite : unique a l'utilisateur |
| presque 100% effort recent | encore V0 (CLI seul, J+30 seul) |

**Mouvement a plus haut levier** : inverser ce ratio. Effort va vers ce qui DECIDE (boucle-de-soi + ingestion + latence), pas vers ce qui SE DEMONTRE (M-B gates, V3 panels).

### Corrections confirmees vs P0 v1 (3 faux positifs droppes)
- ✅ factor_exposures EST mecanise + branche render.py (P0.5 v1 = faux)
- ✅ lock_in_detector EST wire `shared/positions.py:216` post-commit + a fire (bias_events id=5 SNOW vente 03/06) (P0.2 v1 = faux)
- ✅ Predictions 184 NULL = legitimes en vol (0 overdue, target_date future, systeme 26j + horizon 30j arithmetique). Resolver pas casse. (P0.3 v1 = faux)

### Vraies fondations restantes (chiffres verifies)
- render.py = **6348 lignes** (CLAUDE.md ligne 34 dit "~1860", drift ×3.4)
- AGENT_HANDOFF.md & CLAUDE.md ment sur 4+ faits materiels (414 tests / 1141, render LOC, lock_in "non instrumente", factor-exposure "absent")
- yfinance bypass : **20 fichiers** importent direct (throttle prices.py contourne, SPOF reel)
- sqlite3 hors storage.py : **101 fichiers** (9 paths `data/bot.db` hardcodes = vrais bugs override DB_PATH)
- N_resolu = 35 sur 1 bucket -> sophistication actuelle (isotonic/Platt/Wilson/bootstrap) calcule sur bruit
- self_loop V0 : J+30 seul, contrefactuel "hold strict" seul, CLI seul (l'asset Path 6 est invisible)
- 76 sources scores credibility mais ZERO metrique de correlation inter-sources (monoculture macro-penseur)

### Sequence corrective 90j (red-team)

**Semaine 1 — Fondations honnetes (~3h total)**
- **Intra-1** : 2 CI grep gates (~30min, levier maximal/effort)
  - `yfinance hors shared/prices.py` import = build rouge
  - `sqlite3.connect("data/bot.db")` litteral hors storage.py = build rouge
  - File : `scripts/ci_doctrine_grep_gates.sh` + pytest fixture/CI step
- **Intra-3** : doc drift check pre-commit (~45min)
  - `scripts/doc_drift_check.py` : regenere chiffres volatils (count tests, LOC fichiers cites, etat modules "non instrumentes")
  - Echec si CLAUDE.md/AGENT_HANDOFF.md diverge. Doctrine "type quand tu touches" appliquee a la doc.
- **New-1** : pre-registration cryptographique (~1h)
  - Hash chaque prediction a creation (probability_at_creation + target_date + baseline_price)
  - Commit hash horodate-tamper-evident (git tag signe ou OpenTimestamps)
  - Difference "je l'avais dit" vs "prouvablement dit a T0"
  - Path 5/6 asset narratif majeur (verifiable track-record)

**Semaines 2-4 — Demarrer l'horloge statistique (~2-3h)**
- **Feature-1** : sondes calibration 7j (~2h)
  - Emettre predictions-sondes 7j decouplees des theses conviction (qui restent 18-24m)
  - Tag `probe` pour ne pas polluer track-record conviction
  - 8 semaines -> N=35 -> N~100+. Calibration cesse d'etre bruit.
  - Debloque P0 statistique de tout le reste (M3-M16 mentors etc)

**Semaines 4-8 — Asset Path 6 visible (~6-8h)**
- **New-2** : shadow book = € cout cumule biais (~4h)
  - Portefeuille parallele "si j'avais suivi chaque signal discipline" vs reel
  - Trace € cumule que les biais ont coute + ce que PRESAGE a rattrape
  - Matiere existe : bias_events.counterfactual_json + decision_counterfactual (214 lignes)
  - Ressuscite `intelligence/shadow_decisions.py` (zero import actuel)
  - **Slide unique deck acquereur / post lancement** : "voici ce que mes biais m'ont coute, voici ce que l'instrument a sauve"
- **Feature-2** : self_loop V0 -> V1 (~2-3h)
  - Roadmap ecrite dans docstring : horizons 60/90/180, contrefactuels rotate_to_X (pas seulement "hold strict"), panneau dashboard
  - Aujourd'hui la boucle-de-soi est invisible (CLI). La rendre visible = transformer asset unique en chose montrable

**Semaines 8-12 — Connexion distribution + decomposition**
- **New-3** : calibration-as-content (~3h)
  - posts/ existe deja. Auto-generer mensuel "voici predit / arrive / Brier / biais rattrapes"
  - Connecte instrument (boucle) -> asset Path 6 (audience) sans travail editorial recurrent
- **Intra-2** : render.py decomposition (~6h+, tache de fond)
  - 6348 l / 121 fns / 306 commits 14j = surface regression max
  - Extraire render_data.py + render_html.py + svg_paths.py (pure, testable, property-tests gratuits)

### Backlog Intra (apres semaine 1, prioriser selon contexte)
- **Intra-4** : tuer ou ressusciter code mort (`probabilistic.py`, `reconcile.py`, `shadow_decisions.py` = 0 import). shadow_decisions = coquille de New-2 vraisemblablement.
- **Intra-5** : `except Exception` × 644 cible jobs cron + scoring_orchestrator + resolver (catch large dans resolver pourrait avaler echec prix et laisser prediction NULL forever)

### Backlog Feature (apres semaine 4, N suffisant)
- **Feature-3** : factor concentration -> monitor a transition (~2h)
  - factor_exposures calcule mais alerte pas. Pattern monitor (docs/templates/monitor_pattern.md) figé
  - Seuil "AI-broad > 75%" -> evenement journalise + notif Telegram a la transition
  - 3e monitor = 3x plus rapide que 1er (pattern figé). Ferme trou panneau-statique vs garde-active.
- **Feature-4** : calibration conditionnelle au regime (~2h)
  - macro_regime existe (22 fichiers le referencent). Slicer Brier par regime.
  - "Bien calibre en risk-on, surconfiant en risk-off" = insight 2e ordre.
  - Manque le N (debloque par Feature-1)
- **Feature-5** : anti-monoculture sources (~3h)
  - 76 sources massivement Substack macro (Tooze, Macro Compass, Coin Metrics, StL Fed)
  - Input narratif correle = faux sentiment diversite signal
  - Ajouter metrique correlation inter-sources. Anti-double-comptage signal (coherent doctrine anti-double-instrumentation L4)

### Backlog New (apres semaine 8, asset visible)
- **New-4** : panel adversarial nomme au moment decision (~3h)
  - decision_copilot fait deja un contre-argument Claude unique
  - 16 mentor-gates existent mais servent qu'a l'intake. Re-utiliser comme voix dissidentes nommees au moment du geste.
  - Taleb sur tail, Lynch sur prix-vs-croissance, 2-3 one-liners en desaccord, chacun cite sur evidence DB
  - Zero nouveau modele, UX a forte taste, usage decisionnel aux gates
- **New-5** : backtest des regles de discipline elles-memes (~4h)
  - shared/backtest.py wirable bt/ffn -- aujourd'hui seulement 2 fichiers touchent "backtest"
  - Question = "mes regles de discipline auraient-elles ajoute de l'alpha sur 5y de mes propres patterns", pas "mon book bat-il SPY"
  - Validation de l'instrument, pas du portefeuille -- ce qu'un acquereur audit

### Meta-regle a graver (L19 LESSONS apres semaine 1)
**"Aucune nouvelle couche scoring/calibration tant que N_resolu < 100."**

D'ici la, l'effort va a l'ingestion (Feature-1) et a la reduction de latence de boucle (sondes 7j), pas a de nouveaux etages. La sophistication actuelle calcule sur bruit (N=35 sur 1 bucket).

### Ce qui changerait la conclusion
Si N_resolu > 100 avec spread Brier multi-buckets -> "continue enrichir calibration" deviendrait valide. Aujourd'hui N=35 sur 1 bucket -> "gele meta, nourris la boucle" tient.

### DEFER explicite (apres P0 + ressources statistiques debloquees)
- M-B 5 mentors restants (M3 Burry / M4 Graham / M8 Buffett competence / M13 Wood / M15 Fisher 15) -- attendre N suffisant
- ffn V4 (rolling vol panel, drawdown events catalog UI)
- skfolio + FinanceToolkit + FinanceDatabase wire
- Patterns digest nouveaux repos audites

---

---

## 🟢 ÉTAT SYSTÈME (07/06 ter — QUALITY_BAR sweep 4/5 axes shippés)

- **QUALITY_BAR 4 axes shippés en séquence** (per spec docs/QUALITY_BAR.md) :
  - **Axe 3 fondationnel** ✅ positions M1 typed columns + reconcile + drop eur_value/notes
  - **Axe 5 metriques** ✅ data health + price_history backfill 5y + cron 15min reconcile
  - **Axe 4 stress-gate** ✅ seuils warn -25/breach -30 + monitor pattern + cron daily 7:00
  - **Axe 2 sources** ✅ family taxonomy + N_effective helper + chip honnête monoculture
  - **Axe 1 calibration** ⏸️ gated invariant N<100 (warmup en cours, ne PAS forcer)
- **Diagnostic monoculture live** : 74/76 sources = narrative_newsletter (97%), 1 EDGAR primary, 1 manual. Chip data health affiche honnêtement.
- **Smoke stress-gate live** : 8 scenarios évalués, tous OK, AI capex -30% → -21.4% drawdown (sous warn -25%). NB : déclaration mai disait -31%, suggère désintensification book pendant construction.
- **Post_03 J-3 réécrit** : découverte cohort fantôme (0 V1 ont target=10/06 vs 40 dans le post J-11). Réel : 173 V1 étalées 27/05→28/07, 35 résolues, Brier 0.316 (PIRE que prévu). Narratif amende honorable plus fort.
- **J-day 10/06 09:30 wired** : APScheduler date-trigger + grace 12h. Mécanique testée (dry-run + script post_resolution_brier_report).
- **L21 + L22 doctrines verrouillées** : L21 QUALITY_BAR M1/M2/M3 + fail-closed généralisé. L22 N_effective ≠ N_brute (cohorte narrative corrélée).
- **1236 tests verts** (+95 vs close bis). Ruff clean. alembic head 0038.
- **DB backups : 19 -> 6 anchors** (~89 MB vs 270 MB, -165 MB) : axe2 + chokepoint + predint (anchors 07/06) + 2 session_close + pre_migration_20260531 baseline.

### Red-team Axe 4 user + base layer fini (sub-cycle 07/06 quinquies)

- **Pente conviction compressee** : c5=6% (sommet bride) + ratio inter-tiers stable ~0.80. Doctrine "cap mesure, pas choisi" - pente TRANSITOIRE remplacee par hit-rates empiriques post N>=30 J+90. style.position_max_pct aligne a 6% pour kill knob orphelin.
- **Cluster mensonge UI fixe** : _cluster_health lit user_strategy si concentrator_thematic. Compute AI 67% / cap 70% / NOT breached (au lieu de "cap 35% / breached / over+17k" qui poussait au trim biais sell-too-early).
- **4 stops-prix chokepoint defuses** : ASML/TSM/SNPS/Lasertec UPDATE stop_price=NULL. Erreur categorie = stop-prix sur monopole structurel laisse l'humeur de marche decider la sortie au lieu de la condition de falsification. invalidation_triggers restent structurels.
- **AMD/STMPA "bug" = faux positif** : trailing manuel review-driven que user a bumped lui-meme le 06/06. Pas de logique auto-trailing dans le code.
- **Performance + Data health migrent en Method** : ce sont de l'instrumentation methodologique pas verite-du-jour. Performance ffn affiche maintenant badge rouge "PRO-FORMA · PAS TRACK RECORD".
- **Ballast live (Axe 4 (b))** : intelligence/ballast_compute.compute_ballast_strict source unique. Live 10.1% vs cible 20% vs declared YAML 14% (mai). Severite breach (gap -9.9pp). Chip dashboard surface live + divergence YAML.
- **L23 doctrine** : "toute valeur derivable est derivee live, jamais figee en YAML/DB". Generalise M1 du cas eur_value (Axe 3) a tout YAML declaratif.

### Carte-decision #1 + moteur #2 + BookLine canonique (sub-cycle 07/06 sexies)

- **Moteur #2 thesis_erosion (anti-entetement)** : confronte signaux post-opened_at aux key_drivers/invalidation_triggers via LLM Haiku. 5 verdicts dont REVIEW_DUE_DEGRADED L15 fail-closed strict. Complementaire thesis_track_record + M14. 9 tests.
- **Carte-decision #1 SEQUENCE COMPLETE (7 etapes)** :
  - Etape 1 : conviction_at_entry PIT immuable + hook drift tamper-evident (event=conviction_drift dans chain hash)
  - Etape 2 : assemble_card_inputs source unique 12 sources composees frozen
  - Etape 3 : derive_card_steer SteerVerdict 5-state + 5 regles fail-closed transverses (prix stale / these 90j+ / LLM degraded / cours absent / structural sans justif)
  - Etape 4 : ruin_budget_per_name_pct=0.015 + allow_add_steer=false config (anti-FOMO)
  - Etape 5 : refactor _position_card pour CardInputs + SteerOutput (zero re-query, badge verdict + bandeau fail-closed en tete)
  - Etape 6 : sections what-changed + discipline-flags + counter-argument depuis inputs
  - Etape 7 : 21 tests render assembly + matrice fail-closed visuelle verrouillee
- **Position-card #1 couches 1-3 (base)** :
  - Couche 1 : position_type enum (structural/priced/tactical) + tags + structural_justification REQUIS + hook tamper-evident integrity chain. Backfill 4 chokepoints (ASML/TSM/SNPS/6920.T) seq 27-30. Catch 1 user verrouille.
  - Couche 2 : position_steer ExitPolicy + SizeAction SEPARES (Catch 2 axes orthogonaux). 40 tests dont CRITIQUE Catch 2.
  - Couche 3 : render page deep-linkable + nav item "Cards". Catch 3 (structural non-borne par prix).
- **BookLine canonique amont (L23 generalisee)** : shared.book.BookLine expose 5 colonnes M1 (last_price_native, currency, price_asof, fx_rate_to_eur, fx_asof). Plus aucun reader downstream ne re-query positions. Test invariant verrouille.
- **Knob legacy style.position_max_pct retire** : TODO #73 partie 1 done. 4 enforcers routes vers cap_for_conviction. Footgun "c3 grimpe a 6%" elimine.
- **Tests : 1354 verts** (+50 cette sub-session). Ruff clean. alembic head 0042.
- **Live dimanche soir** : 26 cards / 26 REVIEW (PRIX STALE > 4h SLA) - le systeme refuse de steer dans le noir. Lundi a l'ouverture : verdicts reels.

- **M-A Calibration contract pillar COMPLET 5/5** : env singleton + L15 fail-closed + Pydantic ScoringDecision + L16 temporal splits + L17 declarative YAML/live DB.
- **M-B Thesis creation gates 11/16** : M1 Buffett + M2 Taleb + M5 Lynch + M6 Fisher + M9 Damodaran + M11 Ackman + M12 Pabrai (gates) + M7 Druckenmiller + M10 Taleb barbell + M14 Jhunjhunwala (health metrics) + M16 Munger doctrine. **5 mentors defer documente** (M3/M4/M8/M13/M15 -- effort > valeur immediate ou besoin infra additionnelle).
- **M-D Heimdall Performance V3** : 9 KPI cards (CAGR/total_return/MaxDD/DD courant/vol/Sharpe/Sortino/Calmar/**IR vs SPY**) + sparkline equity 1y avec SPY benchmark dashed overlay + drawdown chart 30j. Cache yfinance 1h portfolio + SPY.
- **Backtest framework bt 1.2.0 wire** : shared/backtest.py wrapper L16-compliant + 1er audit live `docs/backtest_audits/buy_and_hold_2026-06-07.md` (book Sharpe 1.73 ± 1.09 vs EW 1.80 ± 1.38).
- **Doctrines verrouillees** : L14-L18 (L15 fail-closed, L16 splits, L17 YAML/DB, **L18 Munger latticework**).
- **18 patterns audites** dans TODO library (11 Phase 0 + 5 nuit + 2 JerBouma + 6 express + 2 backtest). 2 libs wires (ffn + bt). FinanceToolkit + skfolio + FinanceDatabase P1/P2 post J-day.
- **1141 tests verts** (+265 vs début session 06/06 soir). Ruff clean. 0 regression.
- **alembic head 0031** (risk_signal_evaluations append-only).
- **requirements.txt** +ffn>=1.1.5 +bt>=1.2.0 (smoke install Py3.14 OK).
- **Tech debt** : scripts/risk_watch.json + scripts/target_allocation.json supprimés (YAML canonique L17). -360 lignes.
- **VM Hetzner H24 actif** : presage-bot + presage-serve.
- **Dashboard Performance panel fix** : bug colonne inexistante `avg_cost_eur` fixé (était `avg_cost`).

## 🟢 ÉTAT SYSTÈME (06/06 soir) [PREVIOUS REFRESH]

- **Calibration v5 canonique evolutive** : `config/calibration.yaml` source unique pour tous seuils + tooltips + classifier + rules + audit_metadata. Tous lecteurs (render.py / macro_regime / macro_book_warnings) délèguent à `shared/calibration.py`. Chip "calib v5 · 2026-06-06" dans panel header. Cron audit 10j tournera demain matin.
- **Friction décision active** : `/trade` 2-step confirm avec 4 contextes (régime macro + warnings ticker + cluster delta + bias + signaux 30j). Token 6-hex TTL 60s.
- **Retrospective +30j/+90j armée** : cron 9h30 daily. Snapshot canonique `position_decisions_context` à chaque `/trade confirm`. Classify_verdict {aligned_positive, aligned_negative, against_positive, against_negative, neutral}.
- **Phase A wire 4 calibrations** : cluster STRESS auto-derisk (regime STRESS + cluster >55% → cap grade 70) ; VIX 2-tier scaling (factor 0.5 si VIX >30 panique) ; min positions 8 (anti-overdilution) ; circuit breaker Elder (-6%/mois portfolio DD).
- **Audit panels v5 + fix bug structurel heat** : `heat = sum(weight × downside_pct)` au lieu de `max(tensions)`. Convention pro Van Tharp/Pro Trader Dashboard/Elder.
- **price_monitor BUG MAJEUR fixé** : currency NATIVE vs EUR comparison + ajout check target_partial qui était totalement absent. 14 alertes manquées vont firer prochain run.
- **Positions reconciliées DB ↔ broker truth** : 26 positions exactes (44 239 EUR cost, 52 763 EUR live yfinance, gap +790 EUR = FX spread Asie tickers, non-erreur). 3 anomalies corrigées (4063.T +2.5 actions, 7011.T +2.76 actions, GOOGL avg -28 EUR).
- **FX-aware tooltip Closest-to-target** : cas SK Hynix surfacé. Native vs EUR PnL côte-à-côte quand FX gap signifiant.
- **VM Hetzner H24 actif** : presage-bot + presage-serve restarted. alembic head 0030.
- **877 tests verts** (+25 nouveaux session).
- **DB backup** : `data/bot.db.backup_session_close_20260606_192531`.

- **Macro stress monitor entièrement refondu** : panel `_urgence` intelligent + warning. Triage ACT/WATCH/CALM/SILENT, regime detector 5 buckets (`intelligence/macro_regime.py`), tie-to-book warnings (`intelligence/macro_book_warnings.py`), honnêteté NULL/stale visible. Migration `0029_macro_regime_alerts`. État courant : STRESS · V3 score 120 (phase 4 CRISIS) · ACT 4 / WATCH 7 / CALM 4 / SILENT 0.
- **Bands v3 hard reality** : 10 indicateurs calibrés post-3-iterations (v2 dur -> +5% margin -> hard-fix sur 4 greens trompeurs). Cross-file consistency auditée (`_MACRO_BANDS` + `_MACRO_TIPS` + `macro_regime.py` + `macro_book_warnings.py` + `phase_ranges` + `config.yaml vol_scaling_threshold_vix=21` tous alignés).
- **Freshness améliorée** : tier1 cron 4x/jour (06h/12h/18h/22h Paris) au lieu de daily. MOVE promu tier1. `persist_signal` no-stomp fix (fetch fail garde la dernière valeur valide). Tier3 retry pattern day="1,5,10,15". CoreCPI NULL chronique fixé = 2.74% en DB.
- **CI vert** (depuis session 06/06 matin) : marker `live_data` skip 13 fichiers data-dependent, mypy fix learning.py.
- **Bot + dashboard sur VM Hetzner H24** : `ssh presage@37.27.247.126`, systemd user + linger.
- **Backup offsite Storage Box BX11** : `presage-backup.timer` daily 04:00 UTC.
- **`/audit` + `/review` Telegram handlers actifs**.
- **26 thèses refondues tailor-made** (commit 06/06 matin), gate currency_native étendu 5 champs.
- **J-day 10/06 prep** : reading contract pré-registered (N=20, M=0.03), healthchecks armed.
- **45+ commits cumulés sur 05+06/06** (10 commits macro panel après-midi). Tennis-bot intact.

---

## 📋 TECH DEBT AUDIT OSS (07/06) — Patterns library

Audit OSS de **13 repos** (Nango, FinceptTerminal, agentic-inbox, flowsint, LibreChat, TradingAgents, OpenBB, qlib, Kronos, FinRL, QuantDinger, ai-hedge-fund + verdicts rapides tushare/gs-quant/nofx/lightweight-charts/maybe/bloomberg-terminal/maestro/Kronos/FinceptTerminal).

**Doctrine 07/06 (accumulate)** : tout potentiel d'amélioration consigné ici même mineur. Filtre seulement l'inutile structurel (anti-doctrine pure, stack incompatible, license bloquante).

### Verdict global PRESAGE
Monolithe Python + SQLite WAL + APScheduler + Telegram bot est plus simple que nango, plus discipliné que Fincept, plus honnête que TradingAgents/FinRL/QuantDinger. **Ne pas pivoter d'architecture**, adopter patterns ponctuels selon priorité.

### 🔴 HAUTE priorité — top 5 (post J-day)

### 🔴 HAUTE priorité — top 5 (post J-day, ~3-4h total)
1. **Fail-closed LLM doctrine** → `intelligence/signal_scorer_v2.py` : si V2 échoue, status `degraded`, jamais score arbitraire. Ajouter L14 dans `docs/LESSONS.md`. Source : agentic-inbox `workers/lib/ai.ts`. **30 min + 1 test**.
2. **Structured Pydantic output + free-text fallback** → `signal_scorer_v2` (`ScoringDecision(prob_3m, prob_12m, base_rate)`) + `/audit` (`AuditReport`). Source : TradingAgents `agents/utils/structured.py`. **~2h**.
3. **Workflow YAML déclaratif** → migrer `scripts/risk_watch.json` + tous configs scorer/cron vers YAML versionné avec train/val/test/oos dates IN-FILE. Source : qlib `examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml`. **~1 jour**. Pivot d'audit J-day publishable. Empêche "in-sample tuning" silent. 🌟 **GROS gain doctrine**.
4. **CSP + security headers minimaux** → `dashboard/serve.py` + `site_public/track.html`. Source : nango `security.ts`. **15 min**.
5. **Env singleton typed** → consolider `shared/env.py`. Source : OpenBB `core/env.py`. **~1h**.

### 🆕 Phase 1.5 Stage 2 — risk_watch declarative/live separation (~3h, follow-up)

Phase 1.5 stage 1 a livré le pattern workflow YAML sur `target_allocation` (déclaratif pur, pas de cron writes). Reste à appliquer à `risk_watch.json` qui mélange déclaratif (rangs, ballast cibles, tickers à surveiller, scénarios, mitigation plan) et live state (current_status, last_eval_reason, last_eval_confidence cron-written).

**Architecture cible** (cf L17 LESSONS) :
- `config/risk_watch.yaml` (déclaratif uniquement, user-edited)
- Table SQLite `risk_signal_evaluations` (append-only, cron-written) — colonnes : `(id, risk_id, signal_id, status, evaluated_at, reason, confidence, evidence_ids)`

**Migration en 3 commits** :
1. Alembic migration créer table `risk_signal_evaluations` + index `(risk_id, signal_id, evaluated_at DESC)`
2. Refactor `intelligence/risk_signal_monitor.py` : lire YAML déclaratif, écrire DB. Conserver fallback JSON 1 mois.
3. Update `dashboard/render.py` lecture du current_status via `SELECT … ORDER BY evaluated_at DESC LIMIT 1`. Drop JSON après validation.

**Risque** : 3 callers actuels (`bot/jobs/daily.py`, `dashboard/render.py`, `intelligence/risk_signal_monitor.py`) — refactor coordonné requis. Tester live sur Hetzner avant drop JSON.

### 🟠 MOYENNE priorité — généralisations infra (post J-day, ~3-4h chacun)
6. **Reflection service cyclique** → généraliser `j_day_batch_close_job` en cron N-jours qui revalide auto toutes décisions âgées >7j contre outcome. `was_correct / actual_return_pct` en table. Source : QuantDinger `services/reflection.py` + `RESOLUTION_RULES registry` (commit #110) déjà à mi-chemin. **~3h**.
7. **Convention `# KNOWN-GAP:`** distincte de TODO → doc dans `CLAUDE.md` + adopter prochain commit. Source : agentic-inbox style. **5 min**.
8. **Append-only memory log + deferred reflection** (post-mortem +30j auto-écrit par Haiku 2-4 phrases). Compatible Brier ledger existant. Source : TradingAgents `agents/utils/memory.py`. **~1h**.
9. **Splits temporels stricts in-file** → tout tuning scorer/threshold doit dater train/val/test dans YAML versionné AVANT le tuning. Formalise catch session 01/06 task #42. Source : Kronos `finetune/config.py:28-32`. **30 min** (doc + 1ère application).
10. **Sample_count > 1 + temperature > 0** sur signal_scorer_v2 → distribution probabiliste vs point estimate. Source : Kronos `KronosPredictor`. **~1h**.
11. **Turbulence threshold kill-switch macro** → désactive nouvelles entrées si VIX > seuil (PAS liquidate, juste pause buys). Source : FinRL `env_stocktrading.py:turbulence_threshold`. Complète Elder circuit breaker. **~30 min**.

### 🟢 MENTOR PATTERNS — heuristiques battle-tested encodées en gates (ai-hedge-fund extracted)
Doctrine 07/06 : les principes des mentors ≠ persona LLM agents. On encode en gates déterministes.

| # | Mentor | Encodage PRESAGE | Statut | Effort |
|---|---|---|---|---|
| M1 | **Buffett/Munger quality** | Gate `solidité ∈ {Incontournable, Solide}` requis pour `conviction ≥ 4` à création thèse | 🟡 mesuré pas enforced | 30 min Pydantic validator dans `intelligence/thesis.py` |
| M2 | **Taleb/Pabrai asymmetry** | Gate `asymmetry_ratio ≥ 2` requis pour `conviction ≥ 4`. Calcul déjà fait. | 🟡 mesuré pas enforced | 30 min |
| M3 | **Burry consensus check** | `intelligence/consensus_monitor.py` : insider buy cluster + sentiment bullish + perf 6m +50% → chip "POPULAR_BET" warning dans Positions panel. Cross-check edge. | ❌ pas wiré | ~2h |
| M4 | **Graham margin of safety** | Watchlist `entry_safety_pct` field, gate "candidate" si discount < 25% intrinsic | ❌ pas wiré (post-entry only) | ~3h (nouveau workflow watchlist) |
| M5 | **Lynch thesis clarity** | Validator thesis_text : c5 doit contenir clause `because:` ou `ten_x_path:` | ❌ pas wiré | 30 min Pydantic |
| M6 | **Fisher scuttlebutt count** | Pour c≥4 : exiger ≥3 sources distinctes sur 90j | 🟡 sources trackées | ~1h gate dans création thèse |
| M7 | **Druckenmiller cut-fast** | Metric `thesis_invalidation_speed_days` : jours entre kill_criteria trigger et exit | ❌ pas trackè | ~1h instrumentation |
| M8 | **Buffett circle of competence** | Tag `in_competence_zone` per ticker, refuse c≥3 si false | ❌ pas wiré | 30 min |
| M9 | **Damodaran story→numbers** | Validator thesis_text : doit contenir au moins 1 metric quanti + 1 catalyseur narratif | ❌ pas wiré | 30 min Pydantic |
| M10 | **Taleb barbell strategy** | Dashboard métrique `barbell_score` = % book en c5 + % book en c1 ballast | 🟡 data dispo | 30 min panel |
| M11 | **Ackman concentration check** | Gate : si c5 conviction mais position pas top-5 du book → flag "under-sized vs conviction" | ❌ pas wiré | 30 min |
| M12 | **Pabrai Dhandho downside floor** | Champ `downside_eur` cap explicit par position | ❌ pas wiré | ~1h |
| M13 | **Wood disruption stays-through-DD** | Tag `disruption_axis` + règle "conviction stays during DD > -20% if thesis intact" | 🟡 tag existe | 30 min règle |
| M14 | **Jhunjhunwala long-term conviction** | Métrique `conviction_age_days` affichée (depuis dernière review) | ❌ pas affichée | 30 min chip |
| M15 | **Fisher 15 points** | Étendre axes tagging avec 5-7 axes qualitatifs supplémentaires (R&D, mgmt quality, capital allocation, etc.) | 🟡 partiel | ~3h refonte axes |
| M16 | **Munger latticework** | Meta-pattern cross-disciplinary thinking — non-encodable, garde en doctrine | ✅ doctrine | — |

**Déjà wiré (mentor patterns implicites)** :
- ✅ Munger invert → `kill_criteria_monitor` + over_cap_monitor
- ✅ Druckenmiller macro × size → régime classifier × cluster cap + STRESS auto-derisk v5
- ✅ Risk Manager → DD circuit breaker Elder + min positions + VIX 2-tier
- ✅ Portfolio Manager → `/audit` + grade panel
- ✅ Sentiment Agent → `ticker_outlook` aggregator

### 🔵 PHASE 2 (si pivot SaaS multi-user, automne 2026+)
- **Tenant ALS** (`contextvars.ContextVar`) → LibreChat pattern, filtre auto SQLite par tenant_id.
- **Per-user secrets encrypted V1/V2/V3 rotation** → LibreChat `packages/api/src/crypto/`.
- **Anti-enumeration constant-time** sur signup/reset → LibreChat `AuthService.js:434-460`.
- **`runAsSystem()` sentinel** pour crons qui doivent traverser tenant filter.
- **Agent token scope + paper-only par défaut + audit log** → QuantDinger `agent_token_service.py`. Pour API tierce future.
- **Vault AES-256-GCM + HKDF + AAD** → flowsint `flowsint-core/src/flowsint_core/core/vault.py` pour stockage credentials API broker.
- **RBAC court 35 lignes** → flowsint `permissions.py` si on ajoute jamais roles.

### 🟢 BONUS UX (post J-day, optionnel, ~30 min - 2h chacun)
- **`/healthz /livez /readyz` triplet** sur `serve.py`. **10 min**. Source : LibreChat.
- **Doc invariant header** style `BacktestEngine.h` (Fincept) sur `intelligence/lock_in_detector.py`, `intelligence/brier.py`, `intelligence/macro_regime.py`.
- **Catalog discovery MCP** (OpenBB `mcp_server/app.py` + LibreChat) si PRESAGE exposé via MCP à Claude Desktop un jour. Pattern `available_categories` / `available_tools` / `activate_tools`.
- **TradingView lightweight-charts wire** pour remplacer SVG sparklines par candlesticks pro sur Positions / Theses / Macro Stress. Apache 2.0, frontend JS via CDN, zero backend impact. **~2-3h** pour 3-4 panels.
- **Helmet/CSP rate-limit middleware** → nango `ratelimit.middleware.ts` pattern : compteur points/user Telegram pour auto-protection sur boucle bug.
- **BYOK `parseCredentials` unifié string|JSON|object** si on expose API key user un jour. Source : LibreChat `anthropic/llm.ts`.
- **Anti-hallucination pre-fetch déterministe** → quand source LLM = sentiment, injecter data dans prompt à T0 plutôt que tool-call dynamique. Source : TradingAgents `agents/analysts/sentiment_analyst.py:1-30`. Application : généraliser à mode vacances.
- **Verifier safety check 50%** : si LLM "nettoie" >50% du contenu → revert original. Source : agentic-inbox. Application : tout post-traitement LLM (résumés Telegram, formatage thèses).
- **DCF/P/E/P/S déterministe** dans `/review` handler. Pas RD-Agent ni LLM, juste pip QuantLib-Python. Pattern Damodaran. **~3h**.
- **Dual strategy runtime** : formaliser IndicatorStrategy (vectorized) vs ScriptStrategy (event-driven) dans même codebase. Source : QuantDinger pattern. **Conceptuel uniquement pour l'instant**.
- **Kline cache TTL par timeframe** : 300s intraday / 1800s daily. Actuellement `_PX_TTL=1800` mono-timeframe. **~30 min** si on ajoute intraday.

### 🚫 ANTI-PATTERNS confirmés (graver dans L14 LESSONS)
1. **Multi-agent persona debate** (TradingAgents, ai-hedge-fund, QuantDinger fast_analysis) — opposé à measure-first base-rate. Doctrine break frontal.
2. **Foundation model autoregressif sur OHLC seul** (Kronos) — zéro causalité, overfit régime de pré-entrainement. Pas de catalysts.
3. **RL agent qui apprend la policy de trading** (FinRL) — opposé de "discipline mécanisée prédéfinie". Reward hacking inévitable.
4. **Backtest sans walk-forward + sans transaction costs réalistes + sans CI** (FinRL exemple 2026 : 2 mois OOS, 5 agents → pick best) — overfitting déguisé.
5. **LLM trend prediction multi-horizon** (next_24h / 3d / 1w / 1m → BUY/SELL/HOLD) — voir QuantDinger `fast_analysis.py`. Antithèse scorer base-rate-first.
6. **Schema `z.any()` sur champs LLM** (agentic-inbox confessait) — prompt injection trivial.
7. **Stack multi-DB + Datadog/Sentry/ES** (nango) — over-engineering, anti `[[business-path-6-acted]]`.
8. **Model zoo SOTA papers tournée best-of-N** (qlib HIST/TRA/TFT/ADD…) — signature plateforme qui empile sans valider.
9. **RD-Agent intégration** (microsoft qlib partenaire NeurIPS 2025) — LLM factor mining boucle fermée = overfitting industrialisé. Casserait l'auditabilité Brier ledger PRESAGE. **DON'T INTEGRATE**.

### 📥 PATTERNS DIGEST 07/06 soir — Bloomberg-killer feedback + Heimdall UX review

Doctrine accumulation : tout ce qui est potentiellement amélioration on prend, on tag, on note source + verdict L14/doctrine.

#### 📡 Data APIs externes à évaluer (broadening data sources, post J-day)
| API | Coût | Potentiel PRESAGE | Verdict L14 | Effort |
|---|---|---|---|---|
| **FMP (Financial Modeling Prep)** | free tier généreux | fundamentals (P/E, EPS, ratios, DCF), enrich thesis création + M9 Damodaran gate | ✅ pas L14 (data déterministe pas predictive) | ~3h wire `shared/fundamentals.py` + cache TTL daily |
| **Polygon.io** | free limité | real-time US stocks/options/forex, complète yfinance pour intraday | ✅ pas L14 | ~2h si on étend `_cached_price_eur` |
| **Finnhub** | free 60 calls/min | news sentiment (déjà flagged anti-doctrine post 30/05 mais utile en data lookup) | 🟡 OK pour news, ❌ pour sentiment-as-signal | ~1h news endpoint |
| **Alpha Vantage** | free 5 calls/min | historical, low rate | 🟡 redondant yfinance | skip |
| Finviz | gratuit screener visuel | inspiration UX screener, pas API | ✅ design ref | inspiration only |
| Investing.com / TradingView eco calendar | gratuit | économique calendar enrich `seed_macro_events` | ✅ pas L14 | ~2h scrape ou JSON public |
| CoinGecko / CMC | gratuit | **drop — stock-only doctrine** | ❌ hors scope | skip |
| Streamlit | OSS | **drop — anti-doctrine "minimal moving parts" + on a serve.py** | ❌ frontend churn | skip |
| Twitter/X sentiment | API payante | **drop — sentiment-as-signal mis L14 30/05** | ❌ anti-doctrine | skip |

#### 🎯 Features candidates (catalyst + shadow)
- **Catalyst Probability & Magnitude surface** : panel dédié qui agrège proba+magnitude par catalyseur futur (earnings, FOMC, presentation produit). On a déjà la data via `signal_scorer_v2` (prob_3m/12m) + thesis `target_pct`/horizon. Manque : surface UI qui groupe par catalyst et chip "magnitude attendu". ~3h render.py + 1 query SQL. ✅ pas L14 (lit data existante, ne génère pas alpha). Priorité **MOYENNE**.
- **Shadow Portfolio "discipline-100%"** : track record alternatif simulant ce qu'aurait fait le book si toutes recos bot exécutées 100%. Différent de `shadow_scoring` (qui compare V1 vs V2). Permet quantifier le gap user-execution vs bot-pure. ~6h : table `shadow_executions`, daily cron qui réplique decision_copilot trades en virtuel, surface chip "écart-discipline" sur grade panel. ✅ pas L14 (audit de discipline, pas alpha). Priorité **HAUTE** post J-day (gros gain track-record vs réalité broker).

#### 🎨 Heimdall UX feedback (decision cockpit upgrade)
Audit qualitatif externe sur dashboard 07/06. Patterns à digérer post J-day :
- **True decision header** : 4-5 KPI cards (P&L 1D/YTD toggle, max DD, vol, hit ratio, cash %) + risk dial agrégé (STRESS+SURCHAUFFE+régime → CALME/NEUTRE/TENDU/CRITIQUE) + "Next action" tile auto-generated. ~4h render.py refonte top. ✅ pas L14. Priorité **HAUTE** (transforme monitoring → decision support).
- **Performance & regime panel** : equity curve vs benchmark + drawdown band + regime shading (bull/range/risk-off) + rolling vol/Sharpe + heatmap daily P&L 3 derniers mois. ~6h render.py + benchmark data (FMP). ✅ pas L14. **HAUTE**.
- **Concentration → fragility map** : top N positions by risk contribution (weight × volatility × correlation) au lieu de juste weight. Scenario stress (rate shock, semi -10%, KRW -5%). Correlation clusters (semi, AI infra, domestic KR). ~4h calcul + render. ✅ pas L14 (déterministe sur returns historiques). Priorité **MOYENNE**.
- **Signals → playbook** : catégorisation Entry/Trim/Exit/Watch + micro-context inline (P&L courant, distance stop, distance target, rank book) + filtres click-to-filter. ~3h. ✅ pas L14. Priorité **MOYENNE**.
- **Time & change dimension** : "Since last login" strip (positions opened/closed, stops moved, signals fired, top risk delta), Δ vs previous period toggle 1D/1W, "top deltas" tile. ~4h instrumentation `last_seen_ts` + diff query. ✅ pas L14. Priorité **MOYENNE**.
- **Click-to-filter cross-panel** : click ticker/secteur → tout dashboard se filtre. Pattern interaction. ~3h JS state. ✅ pas L14. Priorité **BASSE** (gros JS, ROI incertain).
- **Ticker slide-over fact sheet** : click ticker → panel droit avec mini chart (lightweight-charts) + EPS trend + ratios + news + inline notes. ~6h fact sheet renderer. ✅ pas L14 (data déterministe). Priorité **MOYENNE**.

#### 🟡 Indicateurs TA (RSI/MACD/SMA cross) — verdict spécial
- **NE PAS** utiliser comme decision signal (anti-doctrine "discipline mécanisée pas alpha prédictif"). L14 catch.
- **OK** afficher dans ticker slide-over comme CONTEXT visuel (lecture, pas trigger). User sait que c'est descriptif.
- RSI <30 / SMA 50>200 / MACD cross = pas dans gate de trade ni dans scorer. Strictly UI context.

#### ⚖️ Verdict global du digest
~10 patterns retenus, 4 drop (crypto/Streamlit/X-sentiment/AlphaVantage). Ordre suggéré post J-day :
1. Phase 1.2-1.5 d'abord (M-A Calibration contract — déjà sequencé)
2. True decision header + Performance panel (M-D Active monitoring upgrade)
3. Shadow Portfolio (orthogonal — gros gain track-record audit)
4. FMP fundamentals wire (M-B Thesis creation enrichment + M9 Damodaran gate)
5. Catalyst surface + slide-over fact sheet (UX polish, ROI moyen)

### 📥 PATTERNS DIGEST 07/06 nuit — 5 repos audités (anthropics + ffn + prediction-market + agentmemory + daily_stock)

Doctrine accumulation maintenue. 4 retenus / 1 drop (ZhuLinsen signals). Sécurité : `/tmp/` clones supprimés, `requirements.txt` non touché, aucun code wiré, audits read-only.

| Repo | L14 | Score | License | Verdict |
|---|---|---|---|---|
| **anthropics/financial-services** | ✅ | 9.5/10 | Apache 2.0 | Patterns gold orchestration LLM sécurisée |
| **pmorissette/ffn** | ✅ | 9/10 | MIT | Analytics pandas-native, gap Heimdall ×80% couvert |
| **jon-becker/prediction-market-analysis** | ✅ | 7.5/10 | MIT | Calibration buckets Brier prêts à fork |
| **rohitg00/agentmemory** | ✅ | 7/10 | Apache 2.0 | Temporal-graph + audit-before-delete utiles |
| **ZhuLinsen/daily_stock_analysis** | ❌ | 3/10 | MIT | DROP signals (anti-doctrine LLM BUY/SELL), salvage data_provider |

#### 🔴 P1 post J-day — Top 3 wires concrets

1. **`ffn` adoption immédiate** → `pip install ffn==1.1.5` + wrapper 5 fonctions dans `shared/portfolio_analytics.py` :
   - `to_price_index()` → equity curve (Heimdall True decision header)
   - `to_drawdown_series()` + `drawdown_details()` → DD chart + event catalog
   - `calc_perf_stats()` → CAGR/Sharpe/Sortino/Calmar bloc unique
   - `rollapply(20, vol_annual)` → rolling vol 20D/60D
   - `calc_information_ratio(returns, bench)` → IR vs benchmark
   - **Effort** : ~3h (wrapper + tests + integration render.py Performance panel). **Couvre 80% gap Heimdall**.

2. **`anthropics/financial-services` output_schema strict pattern** → si on étend `/trade` ou `/buy` Telegram un jour :
   - Reader (lit non-fiable) → Orchestrator (allowlist + validate JSON schema) → Writer (final)
   - Handoff allowlist : jamais laisser LLM output déclencher action directe sans validation Pydantic + ALLOWED_TARGETS check
   - **Effort** : MOYENNE (~4h). **P1 sécurité** si on monte un trade-bot Telegram.

3. **`prediction-market-analysis` Brier calibration buckets** → fork `src/analysis/polymarket/polymarket_calibration_by_bucket.py` :
   - SQL DuckDB pattern pour bucketing décile + ECE/MCE/Brier
   - **Pertinence** : exact pattern PRESAGE Brier ledger. Soit en source data externe (PolyMarket = base-rates marché), soit en analytics module pour notre propre ledger.
   - **Effort** : ~2h adapt SQL + Pydantic ScoringDecision integration.

#### 🟠 P2 — follow-up

4. **`agentmemory` temporal-graph versioning** → enrichit decision_audit avec causalité :
   - GraphEdge avec valid_from/valid_to + reasoning + supersededBy
   - Ex : `moved_stop → fixes(previous_breakeven_fail)` reasoning "vol spike", confidence 0.85
   - Linker GraphEdge IDs à `predictions.id` (FK)
   - **Effort** : MOYENNE (~6h). Complète Brier ledger sans le remplacer.

5. **`agentmemory` audit-before-delete pattern** → wrapper `recordAudit(operation, function_id, target_ids, details, quality_score)` AVANT toute mutation structurelle :
   - Force pattern recording-before-deletion (vs post-mortem)
   - Compatible audit table existante PRESAGE
   - **Effort** : BASSE (~1h). Foundational pour intégrité ledger.

6. **`daily_stock_analysis` data_provider/base.py** → multi-source fallback robuste :
   - Pattern abstraction efinance/akshare/tushare/yfinance avec retry/timeout/cache
   - Utile si on étend univers data au-delà yfinance
   - **Effort** : MOYENNE (~3h). NE PAS toucher agents/ ni decision/.

#### 🚫 Drop explicite

- **`daily_stock_analysis/src/agent/agents/decision_agent.py`** + `technical_agent.py` → LLM produit `signal: strong_buy|buy|hold|sell|strong_sell` + `confidence: 0-1` direct. **Anti-doctrine L14 #5 pur**. C'est encore un clone de TradingAgents amélioré côté infra mais avec le même cœur cassé. Ne pas auditer plus loin.
- **`agentmemory` chat-memory layer** → on n'est pas ChatGPT, on est ledger d'investissement. Skip embedding-heavy chat recall, garder seulement audit + graph.
- **`prediction-market-analysis` resolution detection heuristique** (price > 0.99 / < 0.01) → fragile, ne pas réutiliser tel quel pour production.

#### Verdict global digest

5 audits, 3 wires concrets P1 identifiés (ffn immédiat le plus gros gain), 3 patterns P2 follow-up, 1 drop signals. ffn = trouvaille majeure de la session — couvre direct le Performance panel Heimdall que je notais comme HAUTE priorité dans le digest précédent.

### 📥 PATTERNS DIGEST 07/06 fin de soiree — 2 audits JerBouma

| Repo | L14 | Score | License | Verdict |
|---|---|---|---|---|
| **JerBouma/FinanceDatabase** | ✅ | 8.5/10 | MIT | DB statique 353k instruments, complement config/sectors.yaml |
| **JerBouma/FinanceToolkit** | ✅ | 8.5/10 | MIT | 150+ ratios fundamentals deterministes, COMPLEMENT ffn (zero overlap) |

#### FinanceDatabase (P2 post J-day)

- **160k equities** avec sector/industry/country/exchange/market_cap (GICS standard)
- **36k ETFs + 57k funds + 91k indices + 3k cryptos + 2.5k currencies + 1.4k money markets**
- 21 fields equities (symbol, isin, cusip, figi, sector, industry_group, industry, country, MIC, market_cap tier, delisted bool)
- API : `equities.select(country='X', sector='Y', industry='Z', market_cap=['Large', 'Mid'])` + `.search(summary=['Robotics', 'AI'])`
- **PAS de doublon avec `config/sectors.yaml`** (PRESAGE custom = thematic groups + cycle phase, FinanceDatabase = GICS lookup). Complement pour :
  1. Validation ticker existe + metadata enrichment thèses
  2. Universe discovery ("semis Europe Large Cap" → 922 equities)
  3. Standardisation sector/industry pour reports interop
- Effort : ~2h wrapper + cache local. **Priorité P2** (nice-to-have, pas critique J-day).

#### FinanceToolkit (P1 post J-day, gate M9 Damodaran)

**Couverture fundamentals (150+ fonctions structurées) :**
- 23 ratios Valuation : P/E, EPS, P/B, EV/EBITDA, EV/Sales, PEG, P/CF, P/FCF, dividend_yield, earnings_yield, enterprise_value, market_cap
- 18 ratios Profitability : gross/operating/net margin, ROA, ROE, ROIC, interest_coverage, ROCE
- 10 ratios Solvency : debt/equity, debt/assets, interest_coverage, net_debt/EBITDA, FCF yield
- 21 ratios Efficiency : asset_turnover, inventory_turnover, DSO/DIO, cash_conversion_cycle
- **9 models specialisés** : Extended DuPont, **DCF intrinsic_value** (FCF projection + terminal + WACC discount), Gordon Growth, WACC, Altman Z-Score, Piotroski F-Score, Enterprise Value breakdown
- Risk (en plus de ffn) : VaR Historic/Gaussian/Student-t/Cornish-Fisher (vs ffn historique seul), CVaR variants, GARCH
- 30+ technicals : RSI, MACD, Bollinger, Ichimoku

**Zero overlap vs ffn 1.1.5** :
- ffn = portfolio analytics (equity curve, Sharpe sur returns, drawdown)
- FinanceToolkit = company fundamentals (P/E, ROE sur statements)
- Domains disjoints — adoption parallèle propre

**Source data** : FMP API primary, yfinance fallback, FRED treasury, OECD macro. Wrapper `Toolkit(api_key=fmp_api_key)`.

**Wire P1 pour M9 Damodaran gate** :
```python
# shared/fundamentals_toolkit.py
class FundamentalsAnalyzer:
    def __init__(self, fmp_api_key: str):
        from financetoolkit import Toolkit
        self.toolkit = Toolkit(api_key=fmp_api_key)
    def compute_damodaran_metrics(self, ticker: str) -> dict:
        # P/E + Extended DuPont (ROE → 5 facteurs) + Altman Z + WACC + intrinsic_value
        # Output : dict pour gate M9 validation thesis
```

Effort : ~6h P1 (wrapper + cache statements SQLite + integration tests + Heimdall card). FMP API key requise (free tier généreux mentionné dans digest précédent).

#### Drops
- `.to_toolkit()` chaining FinanceDatabase → FinanceToolkit : pattern doublon, on appelle Toolkit directement.
- FinanceToolkit Sharpe/Sortino/Calmar/drawdown : doublon ffn déjà wiré. Garder ffn comme canonical pour ces metrics.

#### Verdict 2-audits JerBouma
Pas de doublon avec stack PRESAGE actuel ni avec ffn. FinanceToolkit = building block crucial pour M9 Damodaran gate et `/review` enrichi avec DCF déterministe. FinanceDatabase = lookup pour ticker validation + universe filtering (P2). Stack ffn + FinanceToolkit + FinanceDatabase = trio analytics complet (perf + fundamentals + metadata) compatible doctrine PRESAGE.

### 📥 PATTERNS DIGEST 07/06 fin de soirée bis — 6 audits express (gh CLI metadata + README)

Doctrine accumulation maintenue. 1 retenu P2 (skfolio), 4 drops dont 2 license-bloquantes, 1 P3 framework heavy.

| Repo | ★ | License | L14 | Verdict |
|---|---|---|---|---|
| **skfolio/skfolio** | 2.0k | BSD-3 | ✅ | sklearn-style portfolio opt, P2 |
| **nautechsystems/nautilus_trader** | 23k | **LGPL-3.0** | ❌ | Rust HFT engine, drop |
| **dcajasn/Riskfolio-Lib** | 4.2k | BSD-3 | ✅ | CVXPY 26 risk measures, P2 backup skfolio |
| **man-group/ArcticDB** | 2.4k | **paid commercial** | ⚠️ | DataFrame DB Man Group, drop |
| **finos/perspective** | 11k | Apache 2.0 | ✅ | WebAssembly viz framework, P3 |
| **finos/FDC3** | 254 | CSL+Apache | ✅ | Standard desktop interop, drop |

#### skfolio (P2 post J-day, ~4h wrapper)
- sklearn-compatible portfolio optimization (BSD-3, py3.10-3.13, py3.14 likely OK, JupyterLite tutorials)
- CVXPY-backed solver, Clarabel default
- Objectifs : Min Risk / Max Return / Max Utility / Max Risk-Adjusted Return
- Risk measures (subset complet) : variance, MAD, semi-deviation, CVaR, EVaR, RLVaR, CDaR, EDaR, ULCER, max DD
- HRP (Hierarchical Risk Parity), Black-Litterman, Risk Budgeting
- **Compat PRESAGE doctrine** : output `weights` = peut être proposition de rebalance OU input pour seasoning vs conviction-normalisé. Ne PAS auto-override sizing manuel, mais surfacer "MV optimum vs ta cible" dans `/audit` enrichi
- Wire potentiel : `shared/portfolio_optimizer.py` + chip "optimum vs ta cible" dans Concentration panel Heimdall
- Doublon partiel Riskfolio-Lib : préférer **skfolio** (sklearn-style + py >=3.10 OK + plus actif récent + Discord communauté)

#### nautilus_trader (DROP)
- 23k stars mais **LGPL-3.0** = contagion potentielle si on link en SaaS Phase 2 (faut shipper le source modifié)
- Production-grade Rust core + Python control plane + multi-venue (CEX/DEX/FX/equities/futures/options)
- Optional Redis-backed state persistence (signature L14 #7 stack complexity vs SQLite WAL solo)
- **ANTI-doctrine PRESAGE** : automated live trading exécution ≠ friction décision (`/trade` 2-step confirm). Stack écrasante pour monolithe Python solo.
- Pattern event-driven message bus intéressant **conceptuellement** mais pas adoptable tel quel. Si on veut event sourcing un jour, on l'implémente à plat sur SQLite, pas via nautilus.

#### Riskfolio-Lib (P2 backup uniquement)
- 4.2k stars, BSD-3, CVXPY-based, accent académique
- 26 convex risk measures (variance, MAD, semi-deviation, FLPM/SLPM, CVaR, EVaR, RLVaR, CDaR, EDaR, UCI, ULCER)
- 4 objectifs Mean Risk : Min Risk / Max Return / Max Utility / Max Risk-Adjusted Return
- Kelly Criterion log mean-risk
- HRP/HERC/NCO Hierarchical Risk Parity variants
- **Verdict** : excellent mais skfolio choisi comme primary. Garde Riskfolio en backup si on hit limitation skfolio.

#### ArcticDB (DROP, license bloquante)
- Man Group commercial product (March 2023 successor to Arctic). **PAID license requise en production**. Open-source non-commercial seulement.
- DataFrame DB time-series billion-rows, S3/LMDB backends, columnar C++ engine
- **Over-engineering** pour PRESAGE solo (SQLite WAL ~50k rows actuels, ~500k à 5 ans = pas le profil ArcticDB)
- Si Phase 2 SaaS multi-tenant un jour : re-évaluer mais probable rester sur SQLite WAL + Postgres si vraiment massive scale
- L14 #7 stack complexity HIT + license commerciale → drop double

#### finos/perspective (P3 nice-to-have)
- 11k stars Apache 2.0, framework FINOS sponsor JPMorgan
- WebAssembly + Apache Arrow + Python + JS + Rust SDK
- 10+ chart types : line, bar, area, scatter, heatmap, treemap, sunburst, **candlestick** + grid
- Jupyter widget + standalone web component
- **Trade-off** : remplace sparklines SVG par charts pro mais lock-in framework + dépendance WASM. Vs `tradingview/lightweight-charts` déjà en TODO BONUS UX (~2-3h wire), perspective est ~10× plus lourd
- **Verdict** : si on étend à dashboards complexes interactifs (filters + drill-down click), perspective devient meilleur que lightweight-charts. Pour candlestick pur, lightweight-charts gagne (plus léger). Décision dépend de l'ambition cockpit Heimdall.

#### finos/FDC3 (DROP)
- 254 stars, CSL 1.0 standard + Apache 2.0 code
- Spec desktop interop pour Bloomberg/Refinitiv/IB qui discutent via "Intents" + "Context types" (Instrument, Position, Date, Contact)
- Patterns **conceptuellement** intéressants pour MCP discovery futur (Intent registry = allowlist Telegram commands)
- **Pas pertinent solo Telegram bot Python aujourd'hui**. Re-visite si PRESAGE expose en MCP Claude Desktop / Cowork un jour.

#### Verdict 6-audits express
1 win solide (skfolio P2 portfolio optimization sklearn-style), 5 drops/P3 propres. ffn + skfolio = stack analytics + optimization complet pour Heimdall + audit enrichi. JerBouma FinanceToolkit ajoute fundamentals. Trio cohérent.

Doctrine "accumulate broadly + drop useless only" respectée : 16 audits total cette session (11 + 5 + 2 + 6 - duplicates) = ~30 patterns extractés. Le filtre L14 a tenu sur 100% des cas.

### 📥 PATTERNS DIGEST 07/06 nuit++ — 2 audits backtest libs (vectorbt + bt)

| Repo | ★ | License | L14 | Verdict |
|---|---|---|---|---|
| **polakowo/vectorbt** | 7.8k | **Fair Code** | ⚠️ #4 | Grid search "thousands of strategies" piège overfit, Fair Code restrictif SaaS. **DROP** sauf R&D. 5/10 |
| **pmorissette/bt** | 2.9k | MIT | ✅ | Built on ffn (déjà wired), Tree+Algo composition, MIT, ALPHA stage. P2 backtest règles PRESAGE existantes. 7.5/10 |

#### vectorbt (DROP)
- Numba + Rust accelerated, vectorized backtesting au scale ("thousands of configurations in NumPy arrays")
- Design intention = grid search massif → directement L14 anti-pattern #4 (FinRL/TradingAgents "5 agents → pick best" déjà rejeté)
- **Fair Code license** : commercial use requires paid VectorBT PRO. SaaS Phase 2 = problème licensing.
- Doctrine break : "explore thousands of trading ideas" = antithèse "discipline mécanisée prédéfinie" (business_path_6_acted)
- Skip sauf R&D pure isolée (jamais en wire prod)

#### bt (P2 post J-day, ~4-6h wire)
- 2.9k stars MIT, built on top of ffn qu'on a déjà wired
- Tree structure : Nodes + Algos + AlgoStacks pour composition propre de stratégies déterministes
- ALPHA stage déclaré README (use with rigueur)
- **Cas d'usage PRESAGE-aligné** : backtester nos règles **existantes** (lock_in detector, over_cap monitor, kill_criteria) sur historique 5y. Walk-forward strict (cf L16 splits temporels figés).
- Doctrine fit L9 LESSONS : "aucun comportement prod sur modèle non backtesté" → bt = outil légitime pour valider une nouvelle règle AVANT wire prod
- **PAS pour** : "découvrir la meilleure stratégie alpha" (anti-doctrine). PRESAGE backteste pour VALIDER discipline, pas pour MAXIMISER returns.

#### Wire plan suggéré (P2 post J-day)
1. `pip install bt` (BSD MIT clean)
2. `scripts/backtest_lock_in_detector.py` : test règle lock_in sur fenêtres 2020-2024 walk-forward (cf L16). Output : Brier ledger des "what if we'd sold at +15% pnl + conviction ≥3" vs actual.
3. `scripts/backtest_over_cap.py` : pareil pour over_cap.
4. `scripts/backtest_kill_criteria.py` : pareil pour kill_criteria.
5. Doc résultat dans `docs/backtest_audits/<rule>_<date>.md` versionnés.

#### Anti-pattern vectorbt à ne pas reproduire
Si tentation "lancer 1000 configs de lock_in_detector params" → c'est exactly L14 #4. Le bon usage = 1 config FIGÉE (la nôtre), backtest WF sur 5 fenêtres, check si discipline robuste. Pas multi-config tournée best-of-N.

### Scores comparatifs

| Repo | Utilité PRESAGE | Verdict 1-line |
|---|---|---|
| agentic-inbox | 9/10 | Le plus instructif. Fail-closed + self-doc comments à reprendre. |
| LibreChat | 6/10 | Or si pivot multi-user. Tenant ALS + per-user crypto = patterns gold. |
| qlib | 6/10 | Mine d'or infra (workflow YAML, recorder, risk_analysis) ; ignorer model zoo + RD-Agent. |
| Nango | 6/10 + security 8/10 | Helmet/CSP + rate-limit middleware utiles. |
| QuantDinger | 5/10 | Reflection + agent scoping excellents ; cœur fast_analysis = doctrine break. |
| FinceptTerminal | 5/10 | Doc invariant style C++ à imiter. Python à plat catastrophique. |
| ai-hedge-fund | 4.5/10 architecture, 8/10 inspiration mentor heuristiques | Clone TradingAgents architecturalement. Mais checklist mémorable des principes battle-tested encodables en gates déterministes. |
| TradingAgents | 4.5/10 | Méthodologie fragile (N=3, SR>5 anomalie). Pydantic structured = vrai gain. |
| flowsint | 4/10 | Vault AES-256-GCM + RBAC court si multi-user. |
| Kronos | 3/10 | Foundation model OHLC = alpha prédictif déguisé. Splits stricts in-file = bon pattern à voler. |
| OpenBB | 3/10 | **AGPL + Py3.14 + bloat → inadoptable comme lib**. Fetcher 3-steps utile à connaître. |
| gs-quant | 2/10 | Dep Goldman Marquee platform, pas SDK léger. Pricing dérivés exotiques utiles si on étend `/review`. |
| FinRL | 2/10 | Anti-discipline mécanisée par construction. Turbulence kill-switch = seul pattern à voler. |
| tushare | 1/10 | Hors scope (Chinese stocks). |
| **lightweight-charts** | UX upgrade | Apache 2.0, frontend canvas pro. Remplace sparklines SVG dans dashboard.html. ~2-3h wire. |
| nofx | 0/10 | AGPL + Go. Stack incompatible. |
| maybe-finance | 0/10 | Ruby + AGPL + personal finance. Hors scope. |
| bloomberg-terminal | 0/10 | No license + redondant FinceptTerminal. |
| maestro | 2/10 | "Bloomberg CLI" 1k stars MIT. Possible inspiration CLI agent patterns si on étend. |

---

## 🟢 ÉTAT SYSTÈME (05/06 soir) [PREVIOUS REFRESH]

- **Bot + dashboard sur VM Hetzner H24** : `ssh presage@37.27.247.126`, systemd user + linger, APScheduler 26 jobs, Restart=always.
- **DB** : migree Mac→VM (parite 420 signals / 30 positions / 53 theses / 219 predictions). alembic head 0028.
- **Backup offsite Storage Box BX11** (Falkenstein, €3.84/mo) : `presage-backup.timer` daily 04:00 UTC. Premier run auto : **Sat 2026-06-06 04:04 UTC**.
- **LLM cost optimise** : tier `narrate` Sonnet pour 3 sites Opus narrative ; crons espacés (classify 30min→2h, mat_v2 + recompute_boost 1h→6h). Decision_copilot + dashboard chat restent Opus.
- **6 outils analyse data** : `thesis_clusters_brier` · `source_attribution_brier` · `calibration_plot` · `bias_ledger` · `decision_audit` · `materiality_validation`. Tous scripts CLI standalone, doctrine CI-based + dedup signal_id.
- **/audit Telegram handler** : surface decision_audit dans le flow quotidien. Tape `/audit` / `/audit 14` / `/audit MU`.
- **J-day 10/06 prep** : reading contract pre-registered (N=20, M=0.03, **verdict CI-based**), healthchecks armed.
- **26 commits aujourd'hui** (matin + extension soir). Tennis-bot intact (binaire `bot.py`).
- **Backlog ouvert** : essentiellement gated par calendrier 10/06 + 27-28/06. Pas de chantier libre actionable ce soir.

---

## ⚠️ Risques silencieux — désormais couverts par 3 vigilances auto

Les 3 patterns surveillés via `intelligence/v2_vigilance.py` (cron weekly lundi 7h, push Telegram UNIQUEMENT si ALERT/WARN) :
1. **`watch_rate`** : si > 85% sur 28j = ancrage refus / si < 20% = sur-commitment
2. **`directional_spread`** : si < 3 buckets uniques sur 120j = mono-bucket déménagé
3. **`insider_clusters_alive`** : si 0 cluster + 0 buy snapshot = job cassé ; si 0 cluster + buys existants = INFO normal large-cap (pas push)

**Risque MU-style (DB vs broker drift)** : pas encore mécanisé. À envisager post-10/06 si un autre drift apparaît. Pour l'instant : audit manuel ad-hoc.

---

## 🟡 P1 — Observation usage

**Discipline = usage > code.** J-11 jusqu'au batch resolution Brier.

- [ ] **Daily check log bot** : `tail bot.log` confirme morning_chain (6h) + evening_chain (23h) tournent OK
- [ ] **Daily gate** : doit rester 🟢 0 violations (toute violation = régression)
- [ ] **VALUE_LOG** : remplir chaque jour ce que PRESAGE t'a appris (mesure réelle de valeur, pas commits)
- [ ] **CHANTIER 06/06 — Refonte targets/stops par thèse + outil /review** :
   Tous les stops actuels à exactement -25%, targets à +50/+60% par conviction =
   générique-aveugle, pas thèse-specific.

   **⚠️ Bug urgent à fixer en premier** : 6857.T entry 24215 JPY vs target 234.82 =
   -99% (probable mismatch JPY/USD ou décimale ratée). Le gate currency_native
   aurait dû l'attraper — investiguer pourquoi il est passé.

   **Session A (~2h, code)** : build handler Telegram `/review TICKER` qui sort :
     - PnL depuis achat (positions.avg_cost vs current)
     - Perf 1y / 2y du ticker (yfinance)
     - Perf relative au sector index (SOXX/XLE/etc., besoin mapping ticker→sector)
     - Valorisation P/E + P/S vs sector median (FMP API déjà dans .env)
     - Ressenti modèle : agrégat impact_magnitude + sentiment signaux 30j
     - Phase cycle sectoriel : config user-defined (ta vue signée), pas LLM
     - News récentes par ticker (signals matched cashtag/name)
     - Cibles actuelles + asymmetry calculée

   **Session B (~1h par 2-3 thèses)** : conversationnelle, tu reviews chaque
   thèse séquentiellement avec /review output. Tu proposes nouveaux niveaux
   target_partial / target_full / stop. Je valide via thesis_invariants
   (currency_native + ratio sain) avant update DB.

   Ordre suggéré (priorité) : 6857.T (bug), puis conviction 5 (CCJ), puis c4
   (AMZN/MP), puis c3 (ENTG/LNG/MU).

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

### 07/06 ter — QUALITY_BAR sweep : 4 axes shippés + J-day prep + post_03 amende honorable

- **Doctrine non-négociable + navigation canonique** :
  - `eb38f1d` M1 doctrine premier-principe (inputs datés persistés, outputs dérivés live)
  - `4fb74c5` QUALITY_BAR.md base + L21 LESSONS M1/M2/M3 + fail-closed
  - `591885f` CANONICAL_MAP.md navigation 10 sections (4 abstraction levels, 3 substrats, 5 axes, decision tree, chantiers, doctrines L1-L21)
  - `b6abdb3` CANONICAL_MAP §5bis triggers de bascule + Polygon defer-with-triggers (3 conditions)
- **Axe 3 fondationnel** : `3851059` positions M1 typed columns + reconcile job unique + valuation live, `9d8a50b` (partie) regex strip eur_value/notes + test verrouille
- **Axe 5 metriques** : `9d8a50b` (partie) data health panel M1 freshness + chips distribution, `d4aa155` Axe 5 closing : ensure_price_history + bulk helper + Performance panel ex-yfinance + backfill 5y x 26 positions (33 654 obs) + cron 15min reconcile
- **Axe 4 stress-gate** : `ac0f53e` migration 0037 + Pydantic StressGateConfig + config seuils + intelligence/stress_gate_monitor + 3 storage helpers + APScheduler daily 7:00 + dashboard chip + 8 tests dont CRITIQUE L4
- **Axe 2 sources** : `68f5998` migration 0038 sources.family + backfill 76 sources + intelligence/source_diversity (effective_n_signals + book_source_composition) + chip "97% narrative / 1% orthogonal" + L22 LESSONS doctrine + 10 tests + 2 fixtures schema MAJ
- **J-day prep post_03** : `591795b` réécriture post_03 (cohort fantôme révélée J-3) + healthchecks J-day vérifiés (APScheduler date-trigger 09:30, dry-run message OK, post_resolution_brier_report tested)
- **Tests** : 1236 verts (+95 vs close bis), ruff clean, alembic head 0038

### 07/06 sexies — Carte-decision #1 + moteur #2 thesis_erosion + BookLine canonique amont

- `ab273ae` Kill style.position_max_pct legacy : source unique cap_for_conviction (TODO #73 part 1)
- `c61dc1f` Moteur #2 thesis_erosion : aiguillage anti-entetement driver-level (5 verdicts L15)
- `a201eae` Position-card #1 couche 1 : position_type + classifications + hook tamper-evident
- `4fd7ea0` Position-card #1 couche 2 : position_steer ExitPolicy + SizeAction separes (Catch 2)
- `99ba73b` Position-card #1 couche 3 render + BookLine canonique amont (5 colonnes M1 exposees)
- `41e4b5a` Carte-decision #1 etape 1 : conviction_at_entry PIT + hook drift tamper-evident
- `1104209` Carte-decision #1 etape 2 : assemble_card_inputs source unique 12 sources composees
- `e521251` Carte-decision #1 etape 3 : derive_card_steer + 5 regles fail-closed transverses
- `7c184f6` Carte-decision #1 etape 5 : refactor _position_card pour CardInputs + SteerOutput
- `f841b46` Carte-decision #1 etape 6 : sections what-changed + discipline-flags + counter-argument
- `bf55cd1` Carte-decision #1 etape 7 : 21 tests render assembly + matrice fail-closed visuelle
- 1354 verts (+50). Catch 1/2/3 user verrouilles par tests. alembic head 0042.

### 07/06 quinquies — Red-team Axe 4 user + base layer fini : ballast live + L23 + retention

- `38322ab` line_cap_by_conviction pente compressee sub-Kelly c5=6% ratio 0.80 + align style.position_max_pct legacy
- `34d8d0a` Axe 4 red-team #1+#2+#3 : mensonge cluster UI fix + 4 stops chokepoint defuses + diagnostic AMD/STMPA = faux positif trailing manuel
- `17c021d` Performance + Data health migrent en Method (instrumentation pas verite-du-jour)
- `2f66187` Axe 4 (b) ballast live derive + retention DB 19->6 (~165 MB) + L23 doctrine "valeur derivable = live"
- TODO #73 cap = mesure post N>=30 J+90 (transitoire en place)
- TODO #74 drawdown gate decouplee par cluster (post-J-day design)

### 07/06 bis — Session ultra-marathon : M-B finition + bt wrapper + ffn V3 + tech debt cleanup

- **M-B Pillar 2/16 -> 11/16** :
  - `623ca54` M11 Ackman concentration : conviction 5 + rang>5 book = FAIL
  - `b03e123` M5 Lynch clarity + M9 Damodaran quantitative + M12 Pabrai downside (24 tests)
  - `36033f7` M6 Fisher sources count + M7 Druckenmiller cut-fast + M10 Taleb barbell + M14 Jhunjhunwala age + M16 Munger doctrine L18
- **Heimdall Performance panel evolution** :
  - `8bae7b2` V2 : equity curve sparkline + drawdown chart 30j
  - `fb8db7f` V2 fix BUG : SELECT colonne inexistante avg_cost_eur tuait fetch
  - `0042956` V3 : SPY benchmark dashed overlay + IR vs SPY KPI (9 KPI cards 3x3)
- **Backtest framework bt 1.2.0 wire complete** :
  - `989a0bf` digest 2 audits (vectorbt drop, pmorissette/bt adopt)
  - `e2b64d8` shared/backtest.py wrapper (8 tests)
  - `8373ae3` 1er audit live `docs/backtest_audits/buy_and_hold_2026-06-07.md` : book Sharpe 1.73 ± 1.09 vs EW 1.80 ± 1.38 (book = stabilite, EW = upside extreme)
- **Tech debt cleanup** :
  - `94e9bb0` drop scripts/risk_watch.json + scripts/target_allocation.json (YAML canonique). -360 lignes nettes.

### 07/06 — Session marathon : M-A complet + audits massifs + M-B start + ffn Performance panel

- **Phase 0 absorption_roadmap foundations** (`91965a5`) : KNOWN-GAP convention + invariant header doc (3 modules) + L14 LESSONS 9 anti-patterns + /healthz /livez /readyz triplet serve.py + CSP headers. 5 sub-tasks.
- **M-A pillar Calibration contract COMPLET 5/5** :
  - Phase 1.1 env singleton typed (`4e51f39`) : shared/env.py + 7 callers migres + 10 tests
  - Phase 1.2 fail-closed L15 (`b79b0ae`) : docs/LESSONS L15 + 7 tests verrouillent signal_scorer_v2 None sur JSON malformed (jamais score arbitraire)
  - Phase 1.3 Pydantic ScoringDecision (`7ac63f6`) : intelligence/scoring_types + 28 tests + signal_scorer_v2 passe par validate_scoring_dict
  - Phase 1.4 splits temporels L16 (`caafa41`) : config/calibration.yaml audit_metadata.temporal_splits + 8 tests + freeze policy 2026-09-30
  - Phase 1.5 stage 1 workflow YAML L17 (`297b7b9`) : docs/templates/workflow_yaml_pattern + target_allocation.json -> config/target_allocation.yaml + Pydantic strict + 12 tests
  - Phase 1.5 stage 2 risk_watch declarative/live (`467540e`) : alembic 0031 risk_signal_evaluations + intelligence/risk_watch_schema Pydantic + config/risk_watch.yaml + shared/risk_watch loader + refactor risk_signal_monitor (lit YAML / ecrit DB) + render.py utilise load_with_live_state + 14 tests
- **M-B pillar amorce** (`d2eeafc`) : intelligence/thesis_creation_gates.py + check_m1_buffett_quality (conviction>=4 exige solidite Incontournable/Solide) + check_m2_taleb_asymmetry (ratio>=2.0) + 17 tests + wire dans add_thesis (warnings non-bloquant).
- **M-D building block + wire** :
  - ffn wrapper (`dbca43f`) : shared/portfolio_analytics.py (7 fonctions equity_curve/drawdown/perf_metrics/rolling_vol/IR/VaR/CVaR) + 23 tests + requirements.txt ffn>=1.1.5
  - Performance panel live (`d0af5b8`) : _performance_panel() dashboard render.py + 8 KPI cards (CAGR/Sharpe/Sortino/Calmar/MaxDD/DD courant/vol/total return). Cache yfinance 1h. CSS minimal _styles.py. Wire Vue d'ensemble entre risk_watch et blind.
- **16 audits OSS digest TODO patterns library** :
  - `9e3f3af` 5 patterns digest (Bloomberg-killer feedback + Heimdall UX review)
  - `39a9fd4` 5 audits nuit (anthropics-fs 9.5, ffn 9, prediction-market 7.5, agentmemory 7, daily_stock 3 drop signals)
  - `1e6940c` 2 JerBouma (FinanceToolkit 8.5 P1 M9 Damodaran, FinanceDatabase 8.5 P2 metadata)
  - `f77c8b6` 6 express (skfolio 8 P2, nautilus drop LGPL, Riskfolio P2 backup, ArcticDB drop license, perspective P3 framework, FDC3 drop hors-scope)
- **Doctrines L verrouillees** : L14 + L15 + L16 + L17 dans `docs/LESSONS.md`. CLAUDE.md "Catches recurrents" reference.
- **Tests + infra** : 1094 verts (+218 vs début session), ruff clean, alembic head 0031.

### 06/06 soir — Calibration v5 canonique + friction décision + audit positions truth

- **Audit pro macro v4** (`5afd248`) : FRED/JPM/GS/Bloomberg/Cboe sources. HY_OAS 230/335→300/400, USDJPY 154→155 (BoJ >73 Mds$ avr-mai 2026 confirmée), DXY 98/101→100/104, CoreCPI 2.4/2.9→2.5/3.0, MfgIP 0.95/0.28→1.0/0.0, BankReserves 3.2T/2.5T→3.0T/2.8T. Tooltips resync.
- **Canonical calibration.yaml** (`a6b3d4e`) : `config/calibration.yaml` source unique evolutif. `shared/calibration.py` loader. Tous readers (render.py + macro_regime + macro_book_warnings) délèguent. Chip audit visible header panel. Rapport `docs/calibration_audits/2026-06-06_v4.md`.
- **Audit panels v5** (`03083ca`) : RSI/Breadth/Risque/Concentration/Drawdown (StreetStats/Van Tharp/Minervini/Druckenmiller refs). **Fix bug structurel heat formula** : `max(tensions)` → `sum(weight × downside_pct)`. Convention pro. S5FI seuils canoniques préparés (fetcher à wire). Rapport `docs/calibration_audits/2026-06-06_v5_panels.md`.
- **Friction décision #1** (`b5e910c`) : `bot/handlers/trade_context.py`. `/trade buy NVDA 10 450` → renvoie 4-dim context + token 6-hex TTL 60s. `/trade confirm <token>` execute. Bias detection : LOCK_IN, FOMO, CIRCUIT_BREAKER, OVERDILUTION. Source canonique unique pour tous les contextes.
- **Tagging contextuel #2 + retrospective** (`46aea7b`) : migration 0030 `position_decisions_context`. Snapshot canonique à `/trade confirm`. `intelligence/retrospective_decisions.py` classify_verdict 5 catégories. Cron 9h30 daily +30j et +90j.
- **Phase A wire 4 calibrations** (`e8b98bf`) : cluster STRESS auto-derisk (`compute_grade` cap 70 si STRESS + cluster >55%) ; VIX 2-tier (factor 0.5 si >30) ; min positions 8 garde-fou ; **circuit breaker Elder** -6%/mois (`intelligence/circuit_breaker.py`, cron 9h45 + Telegram).
- **Fix BUG MAJEUR price_monitor** (`16ab071`) : currency NATIVE vs EUR comparison + ajout check target_partial absent. 14 alertes manquées vont firer (2 FULL + 12 PARTIAL). Tests OK.
- **Phase B audit_calibration cron 10j** (`77cc8ce`) : `intelligence/audit_calibration.py`. Daily check, trigger refresh si >10j. Sanity check 14j (stuck_warn/danger flags). Skeleton + prompt structuré pour recherche pro. Wire cron 8h00.
- **Reconciliation positions broker truth** (DB updates direct, pas de commit code) : 26 positions exactes user-provided. Cost 44 239 EUR. 3 anomalies corrigées (4063.T +2.5 actions, 7011.T +2.76, GOOGL avg -28). Backup `bot.db.backup_session_close_*`.
- **Precision B FX-aware tooltip** (`11ed595`) : cas SK Hynix. Native vs EUR PnL côte-à-côte quand FX gap signifiant. Heuristic implied_fx > 2.

### 06/06 après-midi — Macro stress monitor refonte complète

- **Phase D (honnêteté state)** (`88e5b09`) : NULL → `—` + class mute + badge `no data` rouge. Stale > tier threshold → badge `stale Nd`. Sort secondaire stale-after-fresh.
- **Phase C (triage)** (`acd3302`) : remplace tier flat list par buckets `ACT/WATCH/CALM/SILENT` ordonnés par stress. Tier chip (M&L/BANK/SLOW) préservé sur chaque row.
- **Phase A (regime detector)** (`24256e9`) : `intelligence/macro_regime.py` + migration `0029_macro_regime_alerts` + storage helpers + 9 tests dont L4 idempotence. Classifier déterministe 5 buckets (COMPLACENT/RISK_ON/LATE_CYCLE/FRAGILE/STRESS), indépendant V3 composite.
- **Phase B (tie-to-book)** (`d899d44`) : `intelligence/macro_book_warnings.py` + 9 tests. 5 règles déterministes regime × book composition. Bloc "Macro impact on book" sous indicator grid.
- **Bands v2 dur + rename CALM + tooltips resync** (`5afd248`) : 10 indicateurs durcis, tooltips audit complet (zero mismatch restant), UI label ASLEEP→CALM.
- **Accuracy** (`186406b`) : cron tier1 4x/jour, MOVE promu tier1, persist_signal no-stomp, tier3 retry day="1,5,10,15", CoreCPI NULL chronique fix (2.74% maintenant).
- **V3 phase_ranges align + VIX vol_scaling 25→21** (`266b28e` + `de8c48c`) : INDICATOR_CONFIG phase_ranges alignées bands, vol_scaling threshold descendu.
- **v3 +5% margin** (`de8c48c`) : loosen v2 dur après user "peut-être allé un peu fort". 10 indicateurs +5%.
- **v3 drift fix R1/R2/R5** (`e8dbc98`) : audit cross-file → 3 thresholds bookwarnings non syncs corrigés (TYX 4.5→4.2, USDJPY 158→154, VIX 13→12).
- **v3 hard reality** (`7d0f683`) : 4 greens trompeurs → WATCH. T10Y2Y warn 0.28→0.5, DXY warn 103→98, CopperGold band ajouté (0.0015, 0.0008), BankReserves band ajouté (3.2T, 2.5T). Score V3 98→120 (phase 4 CRISIS dans frise).
- **Cross-file consistency auditée** : tous fichiers alignés v3-fix (render.py bands + tips, macro_regime classifier, bookwarnings, debt_monitor phase_ranges, config.yaml vol_scaling).

### 06/06 matin — CI fix + /review + refonte targets 26 thèses

- **CI vert 1ère fois** : `d3b23bf` test_resolution_rules caplog flake fix, `64e4d64` mypy learning.py, `fe0238c` marker `live_data` + skip 13 fichiers, `aac6f72` ruff cleanup. Post #06 draft "trois jours de CI rouge invisible".
- **Currency_native gate étendu** (`e18ff54`) : check sur stop_price + target_price + target_partial + target_full + entry_price (avant : stop seul). Bug 6857.T target=-99% l'avait révélé.
- **Handler `/review TICKER`** (`29dc215` + `9d83446` + `0ecfb0d`) : fact-sheet contextuel zéro LLM. Config sectors.yaml (5 secteurs × cycle phase user-signed). PnL EUR (fix : positions.avg_cost = EUR convention legacy). Tested NVDA + CCJ.
- **Refonte cibles 26 thèses tailor-made** : 9 patterns selon analyse perf vs sector / valo / cycle / PnL / signaux. Strong A renforce (-15/+20/+40) sur 7 tickers, ALAB bump +60%, energy commodities -20/+15/+25, 6857.T tight -9/+10/+17, etc. Stop -25% générique aveugle remplacé partout.
- **Trailing stops profit-protection** : AMD 396 EUR (-15% from current 466 USD), STMPA.PA 53.40 EUR.
- **Data fixes positions.avg_cost** : 6857.T 4238→143 EUR (legacy pre-split), 000660.KS 1163→1060 EUR (user-provided buy 2000 EUR à 1060 - sell 490 EUR). TSLA conviction 2→4 (call personnel).
- **Audit avg_cost 26 positions** clean (3 PnL +100%+ vérifiés = vrais gains AMD/HO.PA/STMPA.PA, pas bugs).
- **11 commits** cumulés sur la journée 06/06.

### 05/06 soir — Analytics push + /audit en flow (extension)

- **LLM cost optimization** : tier `narrate` Sonnet pour 3 sites Opus narrative (portfolio_grade_llm, bot_conceptions, user_profile) + crons espacés. Decision_copilot + dashboard chat preservés Opus.
- **J-day reading contract pre-registered** : N=20, M=0.03, verdict CI-based (pas point estimate franchissant M).
- **6 outils data livrés** : thesis_clusters_brier · source_attribution_brier · calibration_plot · bias_ledger · decision_audit · materiality_validation. Tous CI-based + dedup signal_id.
- **`/audit` Telegram handler** : per-decision view dans flow quotidien (group date, verdicts mots, branches FR, markers 💸).
- **Test isolation source-direct** : fixture `isolated_full_db` pour les 2 tests INSERT → pollution TEST_E2E_DEC stoppée.
- **measure_bias TEST_* filter** : ledger boucle-de-soi etait 100% pollue (30/30 résolutions TEST). Fix source-direct + bias_ledger.py outil.
- **Fix orphan decisions 03/06** : positions.py manquait record_anchor + auto-close thèse sur full_exit. Source-direct + backfill 5 counterfactuals + SNOW thèse close.
- **Fix currency_native NaN gate** : math.isnan check ajouté.
- **PROVISION.md retrospective** : 200+ lignes catalogues tous les gotchas migration.
- **18 commits supplémentaires** (cumulé 26 jour).

### 05/06 — Migration Hetzner full + backup offsite (chantier marathon, cf SESSION_STATE close)

- **Fix mode vacances digest** (`327e1ea`) : retire double-gate `pending_llm`. 70 signaux unstuck, recovery automatique au prochain cron quand LLM revient. Memoire `pending_llm_no_double_gate`.
- **Migration full Mac→VM Hetzner CX22** (Helsinki, Ubuntu 26.04, IPv4 37.27.247.126) : user `presage` + pyenv 3.14.4 + venv + 115 packages + DB scp + OAuth rotation + cutover bot launchd-unloaded.
- **Backup offsite Storage Box BX11** (Falkenstein, €3.84/mo) : 2e ed25519 sur VM, subaccount `u608897-sub1`, systemd timer daily 04:00 UTC, dry-run pousse 6.4MB + 14MB OK.
- **4 commits pushes** : materiality_v2 fix + backup.sh portable + heimdall→presage rename + systemd backup timer.
- **2 memoires** : `pending_llm_no_double_gate` (feedback), `hetzner_migration_triggered` (project, override `migration_solofounder_only`).

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

### 30/05 (session unique 42 commits, 20 chantiers, 10 itérations arc V2)

**MATIN — Dette P0 résorbée + MU fix** (commits ...→49acd34) :
- Fix trigger ORPHAN trop large, SAF.PA thèse réécrite, Batch A (5 kill-criteria substance) + Batch B (5 currency native), fix daily_backup_job cwd, KNOWN_DEBT vidé, recalcul cluster cap CCJ.
- Phase 4 colmatage (migration 0020 drop 4 tables fossiles, alerte Telegram gate-red startup, asym rounding 2→3, 7 tests e2e pipeline).
- MU fix : qty 0.119 → 1.224 (€99.5 → €1020.10), trim fantôme #4 supprimé, decision #23 [VOIDED], filtre dans `measure_bias`. Bot redémarré caffeinate.

**APRÈS-MIDI/NUIT — Arc V2 calibration** (commits 4f34584→0108b3a) :
- **10 itérations sur l'élicitation/sourcing/tests** : audit pré-batch 10/06 révèle mono-bucket [0.608-0.658] → SIGNAL_SCORER_V2 prompt 3 étapes → bug source_name → enforcement weak→watch → sémantique P(call correct) → wire sourcing → extraction exhibits → pollution prod via tests → consolidation DB_PATH → dry-run J-11.
- **Code prod déployé** : V2 scorer (`intelligence/signal_scorer_v2.py`), wire 8-K + insider clusters (`intelligence/edgar_signal_wire.py` + `shared/edgar_exhibits.py`), `storage.DB_PATH` consolidé via `__getattr__`, hook sync `EightKSource.persist()` + `BuyClusterSource.persist()`. Forward-only strict.
- **Source unique de vérité** : V2 sur contenu réel (vs V1 estimate_probability cap [0.50, 0.72] mono-bucket). DoD e2e vérifiée : NVDA Q1 FY27 8-K → V2 prob=0.750 bullish strong. Smoke prod testé.
- **ADR 012** soft-deprecate classifieur 8-K severity. ADR README à 19 entrées.
- **3 vigilances mécanisées** (`intelligence/v2_vigilance.py` + cron weekly lundi 7h) : watch-rate, prob spread cohorte directionnelle, insider clusters alive. Push Telegram UNIQUEMENT si ALERT/WARN. **13 tests unit** + smoke run.
- **Dry-run résolution J-11 (iter 10)** : Brier 0.295 attendu (pire qu'un prior 0.5 trivial), accuracy 38%, mécanisme tourne (40/40 prix fetched). V1 mauvais comme prédit. À ne PAS publier comme track record.
- **Script `post_resolution_brier_report`** : standalone, comble le gap Telegram du 10/06 (Brier moyen + dedup cluster + WARNING mono-bucket auto). À lancer manuellement 10/06 9h05.
- **4 posts canoniques bilingues** (`posts/post_01_*..post_04_*`) : arc V2, SK Hynix bug, dry-run J-11, méta-bug iter 9. Phase A juillet du PLAN en ~60j d'avance.
- **Brand line verrouillée** : *"La vérité dans le bruit / Truth in the noise"*. README hero, AGENT_HANDOFF mention, mémoire `presage_brand` distinction substance/slogan.
- **CI fix** : `pytest -m "not slow"` (les 4 slow tests ne crashent plus la CI car secrets absents).
- **Audit security 7 patterns** : 0 vraie clé exposée. Item "hygiène secrets" validé binairement.
- **Bot.log rotation manuelle** (`scripts/rotate_bot_log.sh`) : MANUEL uniquement, jamais automatique.
- **TODO + SESSION_STATE + FICHE_TECHNIQUE + AGENT_HANDOFF + CONVENTIONS §5** refresh complet. 4 mémoires Claude sync.
- **Pattern itéré 10 fois** : *« la conclusion est toujours en avance d'un cran sur la preuve »*. Y compris sur le fix lui-même (iter 9 alias statique → test régression a montré immédiatement que ce n'était pas un fix).
- **2 tags git** : `eod-30-05` (14:00) + `eod-30-05-full` (16:20). **3 backups** locaux. **427 fast + 4 slow tests verts**. Bot PID 84607 caffeinate.

**Decision log complet** : `docs/decision_logs/01_calibration_unanchored.md` (10 itérations + 3 vigilances + draft v5 publishable).

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
