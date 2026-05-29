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
