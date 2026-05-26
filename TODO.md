# TODO — HEIMDALL Sentinelle (mes-bots-finance)

**Refresh**: 23 mai 2026 (Day 17)
**Mode**: High Standard / Observation jusqu'au 10/06/2026
**Archive**: backlog historique (Day 2-16) → `docs/archive/TODO_archive_20260523.md`

---

## OBSERVATION (jusqu'au 10/06)

Règles : PAS de nouvelle feature / ticker / source / handler. Daily /brief. Auto-summaries dimanche. Le 10/06 : ~40-44 prédictions auto-résolvent → première vraie mesure Brier → point de décision Path 5/6.

---

## VÉRIFIER (empirique, court terme)

- **Prob fix en prod** : `max_id` actuel = 157, toutes à 0.5. La prochaine prédiction créée (id 158) doit porter une prob != 0.5 → intégration confirmée. Pas encore observable.
- **~27 mai** : premières résolutions — vérifier `final_price` sains (garde `px != px` posée).

---

## DÉCISION-TIME UX (Day 16 friction map, sprint 16-18)

1. /risk_check sémantique (add position vs eval position existante)
2. /thesis premortem : pas de résolution ticker→ID
3. premortem non-rétroactif sur ~21/33 theses
4. /thesis set : ambiguïté devise (EUR storage vs USD display)
5. schéma 3 colonnes target (target_price legacy probablement mort + partial + full)
6. /asymmetry single-thesis : verdict tautologique (leçon Day 5 non-appliquée à la vue single)
7. /thesis set : pas d'auto-journal décisions (gap KPI #5)
8. Bot n'encode pas la policy 2-week observation → /risk_check re-recommande trim. Guardrail : `thesis_age < 14d` → prepend "WITHIN_OBSERVATION_WINDOW"

---

## DÉCISIONS PORTFOLIO (opérateur — Olivier)

- **Concentration AI Compute ~80%** : trim direction vs bump policy. Requise avant prochain /position_buy.
- **COHR (#31)** : hold-to-stop $324.37, review 30/05 (override risk_check trim par policy 2-week).
- **NVDA** : 4 départs officers en 105j + 2 décisions non résolues → /risk_check NVDA candidat.
- **Orphans c1** AMD/GOOGL/SAF.PA/TSLA : re-taggés en narratifs le 23/05 MAIS target/stop toujours NULL. J+30 = 16/06 : remplir target/stop ou clore.

---

## PRODUIT Path 6

- **Vue calibration** (LA surface produit) : à bâtir quand ≥10 prédictions prob-différenciée résolues (~fin juin). Reliability diagram + Brier-over-time + ledger résolues. Trancher : neutral exclu vs binaire-0.5. **NE PAS publier le Brier des 157 legacy (à 0.5).**
- **Substack** : fact-check SK hynix $1,216 avant publish ; viser 10/06 (batch resolution).
- **Logo** : intégrer candidat A (heaume-onde) dans render.py `.logo svg` + favicon.

---

## INFRA / DETTE

- shared/display.py canonical refactor (~5-10h)
- ADR 005 P2 audit résiduel : position_events.price, positions.realized_pnl, decisions.price_at_decision (pattern ratio cross-source Lesson 15)
- target_partial NULL sur 33/33 theses (schema debt)
- Univers prune mi-juin (313 vs 178 baseline — "less surface")
- TG canonical restant : /portfolio, /positions, /digest
- Classifieur 8-K : tout Item 5.02 = HIGH (bruit signal→prediction) → recal post-observation
- Policy 2-week observation → encoder dans PHILOSOPHY.md + guardrail bot
- schema debts : last_reviewed vs last_revisit_at (doublon, un mort) ; opened_at format (space, no offset) vs last_revisit_at (T+offset)
- OAuth Cloud Console "Push to Production" (refresh token 7d → 6mo)

---

## GIT

- `origin/main` 2 commits derrière (push quand prêt — secrets confirmés hors historique)
- Tag `day15-brier-dashboard` cosmétiquement mal nommé (calendrier = Day 17)

---

## PROJETS PARKÉS (séparés, non démarrés)

- **Personal Dashboard** (voice→Whisper→Supabase→frontend) — repo séparé probable, distinct de mes-bots-finance. Scoping ouvert.
- **VPS migration** (Hetzner CX22 ~€6/mo) — post-10/06, trigger = KPI #2 GREEN + demande validée.

---

## ADRs

001 PIT credibility (Proposed) · 002 universe scaling · 003 targets · 004 USD canonical · 005 EUR-canonical positions · 006 debt-crisis monitor · 007 briefs ephemeral · 008 cluster-cap grandfather. Voir `docs/adrs/`.

---

## KPI timers

| KPI | Cadence | État | Action si breach |
|---|---|---|---|
| **#2 NON-NEG** | Hebdo | 1 résolu, ~40-44 dues 10/06, J-18 ON TRACK | Stop 5j build |
| #3 Brier | Hebdo | N=1 insufficient (vrai post id≥158) | Alert si >0.25 |
| #4 panic sells | Mensuel | 0 GREEN | Pause + bias analysis |
| #5 décisions | Mensuel | forward-only depuis 21/05 | No new thesis si <90% |
| #6 vs benchmarks | Mensuel | INSUFFICIENT (365d) | Revue trim. |

<!-- BRAINSTORM-2026-05-24 -->

---

## 🧭 Brainstorm stratégique (24/05/2026) — add / cut / fix / red-team

Cadre = PHILOSOPHY ("enrichit la boucle ou feature isolée ?") + High Standard ("moins de surface > plus de discipline").

### 🔀 Décision en attente (bloque le reste)
- [ ] **Trancher le reframe** : le dashboard est-il un outil d'ops perso (→ une table suffirait, on sur-investit l'esthétique) OU l'artefact public Path 6 (→ design = marketing, screenshot-first, 1 hero-view qui raconte la discipline) ? Décide toute la suite.

### ➕ ADD (uniquement si ça ferme la boucle)
- [ ] **Panneau "biais sous surveillance"** : tracker les 2 biais nommés (vendre winners trop tôt / pas vendre crypto au top), montrer decision→outcome — pas des positions statiques. C'est le produit, loop-enriching.
- [ ] **Home calibration plot (money-shot Path 6)** : câbler maintenant, remplir au 10 juin quand les 45 predictions résolvent ("convictions 70 % → 70 % réel ?").

### ✂️ CUT (inversion temporelle : solidifier OU supprimer)
- [ ] Avancer l'**audit de pruning univers** (178 tickers, ~22 thésés ; couper ce qui ne produit aucune matière décisionnelle 90j).
- [ ] Supprimer **dead code frais** : `_system_state` + `.cmdbar` (orphelins depuis le rail foot).
- [ ] Évaluer **redondance onglets** : "Secteurs" vs "Concentration" ; "Signaux" (déclenche une action ou log brut ?). Un onglet qui ne déclenche rien dilue.

### 🔧 FIX (narratif audit-grade / defensible — Path 5)
- [ ] **SÉCURITÉ URGENT** : retirer `credentials.json` + `token.json` (client_secret en clair) du Project Claude + régénérer côté Google Cloud Console. Red flag acquéreur.
- [ ] **Saisir vraies thèses** (conviction/cible/stop/invalidation) sur les 8 orphelins — le thesis tracker (cœur du bot) est vide sur 8/28 positions. Plus haut levier.
- [ ] Revoir les **4 c1** (AMD/GOOGL/SAF.PA/TSLA) → J+30 ~16 juin.
- [ ] Dette §5 : **unifier les deux writers** (`shared/positions.py` + `storage.py` = une seule passerelle).
- [ ] **Unifier display EUR** (`portfolio_views.py` + sites multiples : $ → €).
- [ ] **Unifier les 3 définitions de "open"**.
- [ ] **Filtre held** sur MRVL (thèse active mais position fermée) dans paliers Positions.

### 🎯 RED-TEAM (risques de queue Path 5/6)
- Le track record ne s'accumule jamais assez : la boucle dépend de l'**usage quotidien** jusqu'au 10 juin, pas du code. Mantra : "discipline dans l'usage > dans le code".
- Érosion solo : `VALUE_LOG` = **1 entrée** à ~J+14 ; le doc dit "vide à J+30 = signal". La beauté du dashboard peut masquer ce signal.

### 🥇 Pari semaine (PAS du code)
Thèses sur les 28 positions + revue 4 c1, puis **usage quotidien jusqu'au 10 juin**. Le dashboard est prêt à le refléter ; c'est l'usage qui crée l'asset.

<!-- SECURITY-OAUTH-ROTATION -->

---

## 🔒 SÉCURITÉ (DIFFÉRÉ 24/05/2026) — Rotation OAuth Google [HAUTE PRIORITÉ]

**Différé volontairement** le 24/05 (risque accepté, pas risque absent). Exposition déjà réelle : `client_secret` (GOCSPX-…) + `refresh_token` (scope gmail.readonly) en clair dans `credentials.json` / `token.json`, présents dans les fichiers du Project Claude. Access token périmé (13/05) mais le refresh_token reste actif → rotation requise, l'expiration ne suffit pas.

**Déclencheurs — à faire AVANT :**
- tout push du repo vers un remote public ou partagé
- toute exposition due-diligence / acquéreur (Path 5)
- tout partage du Project Claude
- toute suspicion de compromission

**Runbook (ordre impératif, aucun secret ne transite par un chat) :**
1. Cloud Console → apis/credentials?project=mes-bots-finance → client OAuth `711001773276-…` → Reset secret (ou delete + recreate "Desktop app") → télécharger nouveau credentials.json, remplacer le local.
2. myaccount.google.com/permissions → app mes-bots-finance → Retirer l'accès (tue le refresh_token actuel).
3. Local : `rm -f token.json` puis `python -c "from data_sources.gmail_ import get_service; get_service()"` → consentement navigateur → token.json propre.
4. Project Claude → réglages fichiers → retirer credentials.json + token.json (restent locaux + gitignorés).

Ordre : 1 avant 3 (sinon re-auth avec l'ancien client). Vérif : le print du re-auth affiche l'email du profil Gmail.

## Findings session 25/05/2026 (post ADR-006)

### Feature candidate — page Géo
Vue concentration géographique (US / EU / Asie). render_smoke l'anticipait (nav `geo` + `window.HQ=` données pays/siège), jamais bâtie. Valeur réelle vu le spread Asie (000660.KS, 6857.T, 4063.T) + EU (.PA/.AS) + US. = nav + window.HQ + bucketing pays.

### risk/ wiring (post-10/06) — cap tiéré
`risk/sizing.position_size()` n'applique que le cap PLAT (`style.position_max_pct` = 0.08, plafond c5), aveugle à `line_cap_by_conviction`. Au câblage de `risk.validate()`, enforcer le cap par conviction LÀ (validate connaît la conviction, sizing non) — sinon une ligne c2 peut être sizée à 8 %.

## suite-7 (26/05/2026)
- [pause] Axe crypto / biais #2 — stock-only depuis 26/05. Reactivation = routing -USD + retrait CRYPTO_DENY.
- [done] P2 line_cap : clos (ADR 009 + fix verdict gouverneur render.py).
- [open] Risk #1 : resolve backfill past-due (downtime 9h) — non audite.
