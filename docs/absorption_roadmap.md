# Absorption Roadmap — patterns OSS → PRESAGE

**Doctrine 07/06 (cf [[feedback-accumulate-patterns-broadly]])** : accumuler tous patterns, sequencer leur adoption causalement. Chaque phase **enable** la suivante. Pas d'adoption out-of-order.

**Cible** : 54 patterns identifies (cf `TODO.md` section "TECH DEBT AUDIT OSS") absorbes en **5 phases coherentes** + 4 macro-patterns emergents.

---

## 🎯 Macro-patterns emergents

Les 54 patterns individuels se regroupent en **4 macro-patterns** qui se renforcent mutuellement :

### M-A. Calibration contract (workflow YAML + Pydantic + splits stricts)
**Patterns inclus** : Workflow YAML declaratif (qlib) + Structured Pydantic output + Splits temporels stricts in-file + Env singleton typed + Convention `# KNOWN-GAP:` + Fail-closed LLM doctrine.

**Pourquoi ensemble** : un YAML versionne signe le contrat (dates train/val/test, features, model, strategy). Pydantic typed valide les inputs/outputs. Splits in-file empechent in-sample tuning. Fail-closed garantit que LLM down ne pollue pas. Env singleton garantit que les configs ne derivent pas en silent. `# KNOWN-GAP:` documente dette technique au point de creation.

**Verdict commun** : c'est **LE pivot** du J-day publishable. Sans M-A, les autres phases construisent sur du sable.

### M-B. Thesis creation gates (mentor heuristiques encodees)
**Patterns inclus** : M1 Buffett quality + M2 Taleb asymmetry + M5 Lynch thesis clarity + M6 Fisher scuttlebutt + M8 Buffett competence + M9 Damodaran story+numbers + M11 Ackman concentration.

**Pourquoi ensemble** : tous se branchent sur le **Pydantic validator de creation thesis** (etabli par M-A). Une seule fonction valide les 7 conditions a la creation. Pas 7 fonctions disperses. Lecture unifiee "pourquoi c5 refused : [solidite, asymmetry, clarity, scuttlebutt]" au lieu d'erreurs cryptiques.

### M-C. Learning loop (reflection + memory + Brier)
**Patterns inclus** : Reflection service cyclique (QuantDinger) + Append-only memory log (TradingAgents) + Sample_count > 1 + Brier ledger existant + Splits stricts pour calibration tracking.

**Pourquoi ensemble** : la boucle d'apprentissage se nourrit d'elle-meme. Decisions T0 -> outcomes T+N -> reflection 2-4 phrases -> re-injection prompts futurs scorer V2. Le Brier ledger PRESAGE est deja 80% du chemin. M-C generalise et auto-tune.

### M-D. Active monitoring (consensus + cut-fast + macro kill-switch)
**Patterns inclus** : M3 Burry consensus monitor + M7 Druckenmiller cut-fast + Turbulence kill-switch (FinRL) + M14 conviction age + monitors existants (kill_criteria, over_cap, kca).

**Pourquoi ensemble** : tous suivent le **monitor_pattern canonique** (cf `docs/templates/monitor_pattern.md`). Table journal append-only + classify pur + check_all_transitions + 7 tests. Le 6e monitor doit etre 5x plus rapide a monter que le 5e parce que le pattern est fige.

---

## 📅 Sequence d'absorption en 5 phases

### Phase 0 — Foundations (immediat, ~2h total, no dependencies)
*Ces patterns n'ont besoin de RIEN d'autre. On peut les faire **pendant** la J-day prep si fenetre.*

| Pattern | Fichier cible | Effort | Source |
|---|---|---|---|
| Convention `# KNOWN-GAP:` doc + adoption | `CLAUDE.md` + prochain commit | 5 min | agentic-inbox |
| Doc invariant header style C++ | `intelligence/lock_in_detector.py`, `brier.py`, `macro_regime.py` | 30 min | Fincept `BacktestEngine.h` |
| L14 LESSONS : 9 anti-patterns OSS 2026 | `docs/LESSONS.md` | 15 min | Synthese audit |
| `/healthz /livez /readyz` triplet | `dashboard/serve.py` | 10 min | LibreChat |
| CSP + security headers minimaux | `dashboard/serve.py` + `site_public/track.html` | 15 min | nango |

**Gate de passage Phase 0 → 1** : commits poussés, L14 documente, tests verts.

---

### Phase 1 — Calibration contract M-A (post J-day, ~1.5 jour)
*Le pivot. Tout le reste construit dessus.*

| # | Pattern | Cible | Effort | Bloque par |
|---|---|---|---|---|
| 1.1 | Env singleton typed | Nouveau `shared/env.py`, refacto callers | ~1h | — |
| 1.2 | Fail-closed LLM doctrine | `intelligence/signal_scorer_v2.py`, status `degraded` jamais score arbitraire | 30 min + 1 test | — |
| 1.3 | Structured Pydantic output `ScoringDecision` | `signal_scorer_v2` + `/audit` AuditReport | ~2h | 1.2 (fail-closed est le filet) |
| 1.4 | Splits temporels stricts in-file | `docs/templates/calibration_yaml.md` + 1ere application sur risk_watch | 30 min | 1.5 |
| 1.5 | **Workflow YAML declaratif** (qlib) | Migrer `scripts/risk_watch.json` -> YAML versionne avec train/val/test/oos dates | ~1 jour | 1.1, 1.3, 1.4 |

**Gate de passage Phase 1 → 2** :
- 1 calibration tournant via YAML
- L4 LESSONS update : "in-sample tuning = compile error, pas warning"
- Tests Brier ledger fonctionnent sur le YAML

---

### Phase 2 — Thesis creation gates M-B (post Phase 1, ~5h)
*Maintenant Pydantic + YAML sont en place, les gates mentor s'agregent dans un seul validator.*

Fichier cible : nouveau `intelligence/thesis_creation_gates.py` qui consume `ScoringDecision` Pydantic + applique 7 conditions.

| # | Pattern | Effort | Note |
|---|---|---|---|
| 2.1 | M1 Buffett quality (solidite ≥ Solide pour c≥4) | 30 min | Data existante |
| 2.2 | M2 Taleb asymmetry (ratio ≥ 2 pour c≥4) | 30 min | Data existante |
| 2.3 | M5 Lynch thesis clarity (clause `because:` ou `ten_x_path:` requis c5) | 30 min | Validator regex |
| 2.4 | M6 Fisher scuttlebutt (≥3 sources distinctes 90j pour c≥4) | ~1h | Query `signals_for_ticker` |
| 2.5 | M8 Buffett circle of competence (tag `in_competence_zone`) | 30 min | Nouveau tag |
| 2.6 | M9 Damodaran story+numbers (1 metric + 1 catalyseur) | 30 min | Validator |
| 2.7 | M11 Ackman concentration check (c5 = top-5 du book) | 30 min | Cross-check book |

**Gate Phase 2 → 3** :
- Tentative creation c5 sur ticker Fragile = error explicite multi-condition
- /audit handler reporte coverage des gates sur book existant

---

### Phase 3 — Active monitoring M-D (post Phase 2, ~5h)
*Patterns qui suivent `monitor_pattern.md` canonique (journal + classify pur + transitions + 7 tests).*

| # | Pattern | Effort | Note |
|---|---|---|---|
| 3.1 | Turbulence kill-switch macro (VIX > seuil = pause buys, pas liquidate) | 30 min | Complete Elder breaker existant |
| 3.2 | M3 Burry consensus monitor (`intelligence/consensus_monitor.py`) | ~2h | 6e monitor, suit pattern canonique |
| 3.3 | M7 Druckenmiller cut-fast metric (`thesis_invalidation_speed_days`) | ~1h | Instrumentation |
| 3.4 | M14 conviction_age_days chip | 30 min | Dashboard |
| 3.5 | M13 Wood disruption stays-through-DD rule | 30 min | Tag conditional |

**Gate Phase 3 → 4** : monitors loggent transitions, dashboard surface les chips, fomo_greed wire fonctionne.

---

### Phase 4 — Learning loop M-C (post Phase 3, ~5h)
*Maintenant Pydantic + monitors + reflection peuvent s'assembler en boucle apprentissage continue.*

| # | Pattern | Effort | Note |
|---|---|---|---|
| 4.1 | Append-only memory log + deferred reflection | ~1h | TradingAgents pattern |
| 4.2 | Sample_count > 1 + temperature > 0 sur scorer V2 | ~1h | Distribution probabiliste |
| 4.3 | Reflection service cyclique (generalisation j_day_batch) | ~3h | QuantDinger pattern |
| 4.4 | Lien Brier ledger + monitors transitions (audit cross) | 30 min | Consume sortie 3.2 |

**Gate Phase 4 → 5** : J-day post-mortem N+1 lit auto les decisions V1, ecrit `was_correct/actual_return_pct` sans intervention manuelle.

---

### Phase 5 — UX surface (post Phase 4, ~5-10h, optionnel)
*Maintenant la donnee est riche, l'UX peut la montrer.*

| Pattern | Effort | Note |
|---|---|---|
| TradingView lightweight-charts wire (4 panels) | ~3h | Apache 2.0, CDN, zero backend impact |
| M10 Barbell score panel | 30 min | % book c5 + % book c1 |
| DCF/P/E/P/S deterministe dans `/review` | ~3h | pip QuantLib-Python |
| M15 Fisher 15 points etendu axes tagging | ~3h | 5-7 axes supplementaires |
| Catalog discovery MCP (post-Hetzner stable) | ~3h | Si on expose via Claude Desktop |
| BYOK `parseCredentials` unifie | ~1h | Pre-requis Phase 6 SaaS |

---

### Phase 6 — SaaS multi-user (seulement si pivot explicite, ~1 semaine)
*Block isolement. Aucune adoption sans trigger user explicit re-pivot.*

| Pattern | Effort |
|---|---|
| Tenant ALS (`contextvars.ContextVar`) | ~1 jour |
| Per-user secrets encrypted V1/V2/V3 rotation | ~1 jour |
| Anti-enumeration constant-time | ~30 min |
| `runAsSystem()` sentinel | ~2h |
| Agent token scope + paper-only + audit log | ~1 jour |
| Vault AES-256-GCM + HKDF + AAD | ~3h |
| RBAC 35 lignes | ~2h |

---

## 🔗 Cartographie des connexions

```
Phase 0 (Foundations)
    │
    ├── 0.1 KNOWN-GAP convention      ─┐
    ├── 0.2 Doc invariant headers       │
    ├── 0.3 L14 LESSONS                 ├──► transversaux, utiles partout
    ├── 0.4 /healthz /livez /readyz     │
    └── 0.5 CSP + security headers     ─┘

Phase 1 (Calibration contract M-A)
    │
    ├── 1.1 Env singleton ──┐
    ├── 1.2 Fail-closed ────┼──┐
    ├── 1.3 Pydantic ────────┘  │
    ├── 1.4 Splits in-file      ├──► YAML versionne signe le contrat
    └── 1.5 Workflow YAML qlib ─┘

Phase 2 (Thesis gates M-B)  [requires 1.3, 1.5]
    │
    └── M1, M2, M5, M6, M8, M9, M11 ──► 1 validator Pydantic unifie

Phase 3 (Active monitoring M-D)  [requires monitor_pattern + 1.3]
    │
    ├── 3.1 Turbulence kill-switch
    ├── 3.2 Consensus monitor (M3)
    ├── 3.3 Cut-fast metric (M7)
    ├── 3.4 Conviction age chip (M14)
    └── 3.5 Disruption rule (M13)

Phase 4 (Learning loop M-C)  [requires 1.5, 3.x]
    │
    ├── 4.1 Memory log + reflection
    ├── 4.2 Sample_count > 1
    ├── 4.3 Reflection service cyclique
    └── 4.4 Brier ↔ monitors cross-audit

Phase 5 (UX surface)  [requires Phase 4 data riche]
    │
    └── Charts, panels, /review extension, MCP catalog

Phase 6 (SaaS, isolated)  [requires explicit pivot]
    │
    └── Tenant ALS, secrets, vault, RBAC, agent tokens
```

---

## 📐 Regles d'absorption

1. **Pas de skip de phase.** Phase 2 sans Phase 1 = gates qui croient avoir un Pydantic typed mais en fait non.
2. **Pas de mid-phase pause prolongee.** Une phase commencée doit s'achever avant la suivante. Sinon dette mid-state.
3. **Chaque phase merite un commit dedie minimum** (1-3 commits OK, 0 ou 10 = mauvais signal).
4. **Tests verts a chaque gate de passage.** Pas de `pytest -m "not slow and not live_data"` rouge entre phases.
5. **L LESSONS update obligatoire** quand phase enseigne quelque chose (ex L14 = anti-patterns OSS = Phase 0 livraison).
6. **Phase 0 peut s'inserer pendant J-day prep** (faible cost, no risk). Phase 1+ post J-day strict.

---

## 🎬 Cadence proposee

- **J-day 10/06** : on tire post_resolution_brier_report. RAS sur absorption.
- **J+1 a J+3 (11-13/06)** : digerer outcome J-day, publier honnetement le Brier V1 sur site_public.
- **Semaine J+4 a J+10 (14-20/06)** : Phase 0 complete + entamer Phase 1. Foundations clean.
- **Semaine J+11 a J+17 (21-27/06)** : Phase 1 livree + entamer Phase 2.
- **D+30 boucle-de-soi 27-28/06** : Phase 2 livree, Phase 3 entame.
- **Juillet** : Phases 3-4 livrees, learning loop tourne pour vrai.
- **Aout** : Phase 5 UX surface livre si fenetre, sinon defer.
- **Automne 2026** : si pivot SaaS trigger explicit, Phase 6.

**Sortie cumulee** : ~3-4 mois pour Phases 0-5 a cadence solofounder lifestyle. Acceptable.

---

## ⚠️ Pieges a eviter

1. **Tentation de fusionner Phase 1 + Phase 2** : "tant qu'on y est, autant faire les gates". Erreur : Phase 1 sans tests Brier valides = Phase 2 fragile.
2. **Sauter Phase 3 pour aller direct Phase 4** : "le learning loop est plus interessant". Erreur : sans monitors instrumentes, la reflection lit du bruit.
3. **Pulluler Phase 5 UX** : "ces charts c'est cool". Erreur : 10 panels visuels sur de la donnee non-validee = vapor.
4. **Demarrer Phase 6 prematurement** : "le multi-user c'est notre vrai marche". Erreur : sans track record V2 publie, multi-user = SaaS sans produit. Cf `[[business-path-6-acted]]`.

---

## Reference patterns

Liste source : `TODO.md` section "TECH DEBT AUDIT OSS (07/06) — Patterns library" + commit `7add10d`.

Memoire associee : `[[feedback-accumulate-patterns-broadly]]` (accumule large), `[[business-path-6-acted]]` (pas SaaS premature), `[[feedback-clean-auditable-path]]` (voie clean), `[[scorer-v2-canonical]]` (signal_scorer_v2 canonical).
