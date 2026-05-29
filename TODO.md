# TODO — HEIMDALL (mes-bots-finance)

**Refresh**: 29 mai 2026 (Day 18 close, après audit anti-stale)
**Mode**: Phase construction du book + Observation Brier jusqu'au 10/06
**Archives**: `TODO.md.backup_*` + `docs/archive/TODO_archive_20260523.md`

---

## ACCORD EN VIGUEUR — Phase construction du book

Book actuel : **43 009 € / 27 positions**. Cible documentée : **70 180 € / ~33 positions**.

Le gap (~27 k€) va massivement aux décorrélants : Énergie-pour-IA (Schneider, Prysmian, GE Vernova, Constellation, ASP Isotopes), Défense (BWXT + renforcement Thales/Mitsubishi), Robotique (Harmonic Drive), Compute & semis (Atlas Copco, Air Liquide, ASMI, Soitec, ams OSRAM, Advantest, Astera Labs, Marvell).

**Conséquence opérationnelle** : ne PAS pousser trims sur cluster_cap / ballast_strict / expo AI capex actuels — ils convergent vers la cible. Lecture informative, pas actionnable. Bascule `construction_phase: false` quand book ~65 k€.

Cadre persisté : `config.yaml.user_strategy.construction_phase: true` + badge dashboard panneau Stratégie + memoire `portfolio_construction_phase.md`.

---

## CALENDRIER

| Date | Item | État |
|---|---|---|
| **30/05** demain | Mini-ADR concentration AI Compute | **CLOS** — décision id=19 `no_action_flag` loggée 29/05 07:22, raison phase construction + 6 signaux surveillance |
| **31/05** T-2 | Hetzner migration (ADR ≠ 002, ADR 002 est `universe-scaling`) | **À ADRifier** — pas de script deploy/systemd encore. Créer ADR 002b ou 011. |
| **10/06** D+12 | Vague résolutions ~40-44 prédictions → 1ère mesure Brier | ON TRACK |

---

## VALIDATIONS USER ATTENDUES

- [ ] **Drawdown tolerance 75%** → CTA active dans panneau Stratégie : -23% AI capex de-rating = -9 892 €. À valider contre allocation **finale** 70 k€, pas photo du jour.
- [ ] **Orphelins c1** : data déjà saine (AMD 618/289, GOOGL 551/258, SAF.PA target/stop remplis, TSLA idem). **Item retiré** du TODO — bug du TODO précédent.

---

## DOABLE MAINTENANT (fair game, additif, n'impacte pas pipeline résolution)

### Court terme (cette semaine)

- ✅ **Insider buy clusters table vide** : investigué 29/05. Pas un bug — la watchlist AI-heavy montre des insiders massivement VENDEURS (NVDA -38, AVGO -95, MU -61, AMD -46). TSM seul a 26 buys mais $254k total << seuil $1M moderate. Miroir exact du signal `insider_selling_cluster` TRIGGERED capturé par risk_signal_monitor. Aucune action code requise.
- ✅ **Décisions table NULL audit** : 7/10 NULL, 6 backfillés à la main (id 13-18), id 19 reste NULL légitimement (*PORTFOLIO*). Source du bug identifiée et patchée : `intelligence/chat_intent.py:326` appelait `log_decision` sans `thesis_id`. Fix en place — auto-link via lookup ticker → thèse active.
- ✅ **Risk_watch panel construction-lens** : déployé ce soir.

### Moyen terme (~1 semaine)

- ✅ **`shared/display.py`** : audit confirme qu'il EST déjà câblé (4 imports : `morning_brief.py`, `positions.py`, `observability.py`, `portfolio_views.py`). Le TODO précédent disait "0 imports" — faux. Pas de refactor à faire.
- [ ] **TG canonical /portfolio /positions /digest** : `portfolio_views.py` et `positions.py` utilisent déjà `shared.display`. Reste à vérifier que `/digest` n'a pas de format devise hardcodé (probablement non critique).
- [ ] **`render.py` 4328 LOC** : cosmétique, split en sous-modules post-10/06.

### Path 6 (post-10/06, ouverture publique)

- [ ] **Calibration plot home** : aucun `calibration|reliability|brier` plot dans `render.py`. C'est le money-shot Path 6 — bâtir quand ≥10 prédictions prob-différenciée résolues.
- [ ] **Substack** : fact-check SK Hynix $1,216 avant publish. Viser 10/06 (batch resolution).
- [ ] **Telegram channels ingest** : `data_sources/telegram_channels.py` à créer. Architecture LEGER (channels publics, mirror gmail_.py). ADR si privés (Telethon/MTProto session).
- [ ] **Panneau biais sous surveillance** : tracker les 2 biais nommés (vendre winners trop tôt / pas vendre crypto au top) avec décision→outcome. Loop-enriching.

---

## SÉCURITÉ (DIFFÉRÉ — déclencheurs définis)

- [ ] **Rotation OAuth Google** : `credentials.json` + `token.json` PAS dans git (gitignored, vérifié), MAIS encore présents dans Project Claude exposé. Runbook complet conservé dans `TODO.md.backup_pre_refresh_*` (4 étapes : Reset secret → Retirer accès → rm token → re-auth). Déclencheurs : push remote public, due-diligence Path 5, partage Project Claude, suspicion compromission.

---

## 🚀 MIGRATION TIME — ouverture produit, multi-user, site classique

**Capturé 29/05/2026 (Day 18 close)**. Cadre stratégique pour décider QUAND et COMMENT passer de single-user (Olivier) à plateforme externe. Triggers calendaires en bas.

### Verdict général : pas avant 10/06, et probablement pas avant 6 mois solo

La valeur produit aujourd'hui = **le track-record empirique** d'Olivier (Brier résolu, calibration prouvée). Sans ce track-record, HEIMDALL est une coquille analytique. Ouvrir le produit AVANT que le batch resolution 10/06 valide la thèse calibration = vendre une démo. Ouvrir APRÈS si Brier <0.3 sur ≥3 secteurs = vendre un asset.

### Multi-tenant — état réel ~30%, pas 80%

**Réutilisable** (les moteurs analytiques) :
- `intelligence/*` (kill_criteria, risk_signal, portfolio_grade, conceptions, anniversaries, copilot, topical_recurrence)
- Scoring credibility/Brier
- Cascade LLM (Haiku/Sonnet/Opus)

**À reconstruire** (~2-3 mois sérieux d'eng) :
- **Aucune table n'a `user_id`** : theses, positions, decisions, signals, predictions, ticker_axes, conceptions, kill_criteria_alerts, copilot_interventions, chat_messages, +20 autres. Refacto ~50 fonctions `shared/storage.py`.
- **Config, canonical_perimeter, risk_watch** = fichiers globaux. À transformer en lignes DB per-user OU en `config/{user_id}/*.json`.
- **OAuth Gmail + Telegram** : une seule credential aujourd'hui. Vault secrets per-user à bâtir (KMS/Vault/encrypted-at-rest).
- **LLM cost** : aujourd'hui c'est ma carte. Multi-user = metering hard, OU pass-through API keys user (90% des users refusent).
- **Sécurité** : un `WHERE user_id=?` oublié = leak entre comptes. Recommandation honnête = **schéma Postgres par user**, pas table partagée + row-level filter.

**Mémoire globale "qui rend tous les bots meilleurs"** : bonne idée stratégiquement (distillation cross-user de patterns de biais, calibration sources, types de thèses qui tiennent). N'a de valeur qu'avec **N ≥ 50 users actifs depuis 6 mois**. Avant ça = complexité sans signal.

### Migration backend → cloud — la partie facile

- SQLite → Postgres : **trivial** (Alembic déjà câblé : `scripts/alembic/versions/`)
- Intelligence + storage + edgar + chat = Python pur, déploie partout
- Telegram bot : aucune dette d'attache locale
- Hetzner ADR déjà au TODO (à créer comme ADR 011)
- **Coût migration backend : ~1 semaine**

### Migration frontend → site classique — la partie chère

- `render.py` = **4328 LOC de f-strings Python** générant HTML statique. Aucune logique JS rich.
- Port React + REST/GraphQL = **rewrite complet** des vues. Hérite des décisions de viz (OKLCH, axe stop→cible, accordion `.geo-item`, palette parchemin Geist) mais le code est neuf.
- Estimation honnête : 2-4 semaines pour slice signup→connect→dashboard, **2-3 mois pour parité visuelle**.

**Question préalable** : as-tu besoin d'un site classique ?
- Si Path 6 = "track-record public crédible" → un dashboard SSR servi depuis le backend suffit. **Pas besoin de React SPA**.
- Le money-shot Path 6 = reliability diagram + Brier over time + ledger = ~4 charts, pas une app.
- Tu peux probablement **publier sans rewrite frontend** (rendre `render.py` accessible publiquement avec un mode "public view" qui masque positions sensibles).

### Onboarding nouvel user — c'est l'écueil principal

Pour qu'un user atteigne le niveau où le bot a de la valeur :
1. Auth + OAuth Gmail + Telegram (10 min, automatisable ✓)
2. **Importer 20-30 positions** : aucune API broker. Tout est manuel via `/position_buy`. CSV upload à bâtir.
3. **Écrire 20-30 thèses** : entry/target/stop/conviction/triggers/invalidation. ~20-30 min par ticker = **8-15h de saisie initiale**.
4. Définir stratégie (archetype, target_cap, accepted_factors, benchmark, drawdown_tolerance, ballast macros).
5. Définir canonical_perimeter + risk_watch top risks.
6. Attendre 4-8 semaines pour accumuler signaux + résolutions.

**90% des users abandonnent à l'étape 3**. C'est le problème de tous les outils sérieux de portfolio thinking (Maven Securities, Cestrian, etc.).

À construire pour rendre ça viable :
- [ ] **Génération de thèse assistée** : Sonnet pose 3 questions par ticker, drafte la thèse, l'user valide/édite. Réduit 8h → 1h.
- [ ] **Templates par archetype** (concentrator_thematic, balanced, defensive) qui pré-remplissent target_cap, accepted_factors, risk_watch starter.
- [ ] **Import broker** : commencer par CSV universel, puis Saxo/IBKR/Boursorama (long roadmap réglementaire).
- [ ] **Onboarding wizard progressif** : débloque les features au fur et à mesure (dashboard read-only J1, signals J7, kill_criteria J14).

### Domaine — décision défensive seulement

État WHOIS au 29/05 :
- `presage.com` (pris depuis 2002, GoDaddy = squat probable, broker $10k-$50k+) → **non**
- `presage.io`, `.ai`, `.finance`, `.app`, `.fr`, `.bot` → **tous pris**
- `presage.fi` (Finnish TLD, propre, utilisé en finance Europe) → **DISPONIBLE**
- `get-presage.com`, `presage-finance.com` → disponibles, mais cosmétique secondaire

Action : **acheter presage.fi** (~10€/an, défensif). Si à 10/06 le Brier valide et tu pars Path 6 public, négocier alors `presage.com` via broker Sedo/HugeDomains. Avant ça, **pas un euro** sur du naming aspirationnel.

### Séquence recommandée

1. ✅ **Maintenant** : acheter `presage.fi` (10€). Rien d'autre côté domaine.
2. **D'ici 10/06** : zéro engineering multi-user. Focus exclusif sur usage quotidien + remplir VALUE_LOG.
3. **10/06 batch resolution** : moment de vérité. Brier sectoriel <0.3 sur ≥3 secteurs + ≥1 thèse résolue calibration nette → asset. Sinon, démo.
4. **Si asset existe** : **Path 5 (privé) avant Path 6 (public)**. Vendre le cerveau à un fond / family office = 10x plus rapide qu'une plateforme SaaS, et finance la suite.
5. **Si quand même Path 6 public** : construire **d'abord** la slice publication (calibration plot + ledger résolu + 1 article Substack), PAS la slice multi-user. Le 1er user payant te dira si tu as un produit. Le 100ème user gratuit ne te dira rien.
6. **Multi-tenant à scoper** : seulement après 6 mois solo + 3+ early adopters payants qui le demandent. Avant ça = dette d'architecture pour zéro signal.

### Piège à éviter

Construire la plateforme pour des users imaginaires, et ne plus avoir le temps d'utiliser son propre outil. **HEIMDALL est valuable parce qu'Olivier l'utilise quotidiennement**. Sans cet usage, c'est une coquille — la beauté du dashboard masque le signal "VALUE_LOG vide".

---

## ADRs

001 PIT credibility (Proposed) · **002 universe scaling** · 003 targets · 004 USD canonical · 005 EUR-canonical positions · 006 debt-crisis monitor · 007 briefs ephemeral · 008 cluster-cap grandfather · **009 line-cap by conviction** · **010 concentration policy** (35% défault, suspendu pour cet user) · 011 sizing modèle conviction-normalisée (à formaliser, mentionné CLAUDE.md §2).

ADR Hetzner à créer (était mal référencé comme ADR 002).

---

## KPI timers (état réel 29/05)

| KPI | Cadence | État | Action si breach |
|---|---|---|---|
| **#2 NON-NEG** | Hebdo | 1 résolu, ~40-44 dues 10/06, **J-12 ON TRACK** | Stop 5j build |
| #3 Brier | Hebdo | N=1 insufficient (vrai post id≥158) | Alert si >0.25 |
| #4 panic sells | Mensuel | 0 GREEN | Pause + bias analysis |
| #5 décisions | Mensuel | 10 décisions ce mois, forward-only depuis 21/05 | No new thesis si <90% |
| #6 vs benchmarks | Mensuel | INSUFFICIENT (365d) | Revue trim. |

---

## DONE depuis le dernier refresh TODO (28/05 → 29/05)

### Sprint 19 — Cry-wolf elimination + lecture stricte

- ✅ `kill_criteria_monitor` refonte prompt strict fundamental-only (interdit prix/timer/sentiment, 17 faux at_risk → 0)
- ✅ Memoire `feedback-monitor-defaults` persistée (tout futur moniteur doit défaut à dormant)

### Sprint 20 — Risk_watch first-class

- ✅ `risk_watch.json` créé (Surchauffe tech / AI capex, 1 risk, 10 signaux)
- ✅ `risk_signal_monitor.py` (cron daily 08h00, eval Haiku per signal + transition notify TG)
- ✅ Détection live : `insider_selling_cluster` TRIGGERED (AVGO -$356M, AMD -$117M, MU -$54M, AMZN -$52M)
- ✅ Panneau `_risk_watch_panel()` Vue d'ensemble

### Sprint 21 — UX chat + dim

- ✅ Hover tooltips dim PF → accordion expand inline (pattern `.geo-item`)
- ✅ Auto-clear chat display 7-min idle (DB préservée)
- ✅ Stat profondeur memoire dans subtitle chat

### Sprint 22 — Boucle d'auto-amélioration

- ✅ `decision_anniversary.py` (J+30/60/90/180/365 push TG + persist chat_extracted_signal)
- ✅ `topical_recurrence.py` (aggregate chat_extracted_signals + inject dans `chat.assemble_context`)
- ✅ `user_profile.py` enrichi (6 personality dimensions + topical_obsessions + coherence_check)
- ✅ `chat.py` max_tokens 1500 → 4000 (fix truncation)

### Sprint 23 (29/05 PM) — Audit lucide post-Stratégie

- ✅ **Solidité haute 0% → 60.5%** : refonte `_compute_quality_T1_plus` lit `canonical_perimeter.solidite` (14 Incontournables). Plus le bug zombie J1.
- ✅ **Autres paris 21.8% → 16.8%** : whitelist stricte ballast (Defense / Energy / Rare earths / Industrial reshoring). Tesla et HBM ne comptent plus comme décorrélants.
- ✅ **Drawdown tolerance CTA** : panneau Stratégie surface -23% AI capex de-rating. Flag `config.yaml.user_strategy.drawdown_tolerance_validated: false`.
- ✅ **FX exposure** déplacé sous Par pays dans Concentration (devise = axe concentration, pas analyse stratégique).
- ✅ **"Ce que le bot pense" accordion** : preview 3 lignes + hover/click pour dérouler (au lieu de troncature 380 chars).
- ✅ **Phase construction badge** : panneau Stratégie + memoire durable + lens propagé risk_watch.

### Closed avant refresh

- ✅ `/journal_decision` handler existe (`bot/handlers/positions.py:654`)
- ✅ `_system_state` + `.cmdbar` supprimés (orphelins Day 17)
- ✅ MRVL filtré (qty=0, status=out_of_scope, plus de problème d'affichage)
- ✅ target_partial backfill x28 + schema debt (Day 16)
- ✅ OAuth Cloud Console refresh token 7d → 6mo

---

## MEMOIRES PERSISTÉES (auto-memory, persistent across sessions)

`/Users/olivierlegendre/.claude/projects/-Users-olivierlegendre-mes-bots-finance/memory/MEMORY.md` :

- `presage-brand` · `needle-canonical` · `viz-horizontal-bars` · `next-session-agenda` · `feedback-plug-and-animate` · `glossaire-canonique` · `tax-loss-harvest-pending` · `feedback-monitor-defaults` · **`portfolio-construction-phase`** (29/05)

---

## RED-TEAM (rappels)

- Discipline dans l'usage > dans le code. La boucle dépend de l'**usage quotidien** jusqu'au 10/06.
- `VALUE_LOG` = 1 entrée à J+14. Doc dit "vide à J+30 = signal". La beauté du dashboard peut masquer ce signal.
- Phase construction : tentation = trim "pour assainir les ratios" avant que les nouveaux noms entrent. Refuser. L'accord est documenté.

---

## GIT

- Branch `main` propre, ~5 commits depuis dernier push.
- Tag `day15-brier-dashboard` cosmétiquement mal nommé (calendrier = Day 17 quand posé).
