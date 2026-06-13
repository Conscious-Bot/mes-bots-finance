# CHANTIER — Couche de Redevabilité Décisionnelle

**Statut** : Plan approuvé, exécution gatée (voir §0)
**Date plan** : 12 juin 2026
**Mode** : High Standard / Solidification — extension de la boucle, pas surface nouvelle
**Pour** : exécution Claude Code, plan-mode, une unité par session
**ADR associé** : `docs/adrs/010-decision-accountability-layer.md` (decision record §8)

---

## 0. PRÉ-REQUIS BLOQUANTS

Claude Code NE COMMENCE AUCUNE unité de ce chantier tant que ces 5 ne sont pas VERTS.

Ces items ne font PAS partie du chantier. Ce sont la barrière d'entrée. Vérifier chacun, afficher la preuve, et S'ARRÊTER si un seul est rouge.

| # | Gate | Preuve attendue | Source |
|---|---|---|---|
| G1 | Batch Brier 10 juin résolu | `SELECT count(*) FROM predictions WHERE resolved_at IS NOT NULL ≥ 40` | ledger |
| G2 | 10 sentinelles loggées | 10 entrées event-type horizon déc-2026→déc-2027 dans le ledger | ledger |
| G3 | Migration 0055 (triggers append-only) mergée | `SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE '%_no_delete' ≥ 7` | schema |
| G4 | Bug `add_sell.realized_pnl_event` corrigé (pattern #133bis) | test qui asserte `realized_pnl` lu sur `BookLine.avg_cost_eur`, pas sur VUE.avg_cost NULL | tests |
| G5 | Suite verte (baseline) | `pytest` exit 0, incl. fixes P1 `test_db_write_discipline` + `test_schema_drift` whitelist | CI |

**État à la pose du chantier (13 juin 2026)** :
- G1 ✅ 84 résolus
- G3 ✅ 18 triggers `_no_delete` (alembic head 0059)
- G4 ✅ cure pattern #133bis BookLine appliquée session 13/06
- G2 ❓ à vérifier
- G5 ❓ à confirmer baseline pytest

**Raison de la barrière** : ce chantier mesure si la discipline ajoute de la valeur. Le construire AVANT d'avoir le verdict d'observation, c'est fuir le verdict dans la sophistication — biais #3 en version produit. La barrière est non-négociable.

---

## 1. CADRE — ce que ce chantier EST

Une couche de **redevabilité décisionnelle** au-dessus du ledger de prédictions existant.

- Le ledger actuel juge les **prévisions** (Brier, calibration).
- Cette couche juge le **processus** : les vétos, les holds, et l'appareil de discipline lui-même.
- Elle répond à une question que rien ne mesure aujourd'hui : « est-ce que ma discipline ajoute de la valeur, et où fuit-elle ? »

**Sortie ultime possible et acceptée** : si la Couche 0 montre que le book ne bat pas l'indexation, la réponse honnête est « indexe et arrête ». Un système assez honnête pour produire ce verdict vaut mieux qu'un qui ne le produit jamais. Ce chantier améliore **honnêteté + calibration**, **PAS les rendements**. Ne jamais le vendre comme générateur d'alpha.

---

## 2. ARCHITECTURE — 5 idées → 4 unités → 3 couches

### La collapse (5 → 4)

Le ledger des non-pris (#1) et la pré-registration (#6) sont la **MÊME table**. Une thèse vétoée et une thèse engagée partagent le schéma : `claim / invalidation / horizon / mécanisme / hash`. Seule différence : `direction = "rejected"` + motif. → **un seul registre de thèses**.

### Les 3 couches et leur graphe de dépendance

```
COUCHE 0  null_benchmark        [standalone, zéro dépendance]   ← KILL-SWITCH, build EN PREMIER
                │
COUCHE 1  thesis_registry       [spine, sur triggers 0055]      ← record canonique des décisions
                │
        ┌───────┴────────┐
COUCHE 2 narrative_drift   bias_pnl   [consomment le registre]  ← analytics, build APRÈS données
```

- **Couche 0 gate les autres, économiquement.** Investir ~10h dans les couches 1-2 n'est justifié que si la Couche 0 montre un edge à instrumenter. Le truc le moins sophistiqué domine en valeur attendue parce que c'est un interrupteur d'arrêt.
- **Couche 2 attend** que le registre (Couche 1) ait accumulé des entrées (sinon rien à analyser).

---

## 3. SÉQUENCE / CHEMIN CRITIQUE

```
[Barrière §0 verte]
   → Unité A : null_benchmark        (~1-2h)   ← commence ici
   → [observer le delta real vs SOXX quelques semaines AVANT d'investir dans la suite]
   → Unité B : thesis_registry       (~3h)
   → [backfill rejets de session + thèses tenues → registre non vide]
   → Unité C : narrative_drift        (~3-4h)
   → Unité D : bias_pnl               (~3h)
```

Une unité = une session Claude Code = un commit propre. Jamais deux unités en parallèle.

---

## 4. SPEC PAR UNITÉ

Chaque unité passe les 5 gates High Standard (Tests / Cost / Observabilité / Failure modes / Doc) AVANT commit. Et les gates 5/5 patch : `import / ruff / mypy / pytest / smoke`. Jamais « fait » sans preuve affichée.

### UNITÉ A — `null_benchmark` (Couche 0, le juge)

**Objet** : shadow-portfolio paresseux tracké en parallèle du book réel. Répond « est-ce que la machinerie bat l'ETF sectoriel ? ».

**Implémentation** :
- Nouveau module `intelligence/null_benchmark.py`.
- Portefeuille shadow statique défini en config : `null_benchmark: {SOXX: 0.80, CASH: 0.20}` (rebalance trimestriel OU jamais — figer le choix dans l'ADR). Aligner sur KPI #6 (SPY/QQQ déjà cible) → tracker les **trois** nulles : SOXX, SPY, QQQ.
- Seed à la date de début de tracking du book réel, même capital notionnel.
- Calcul TWR book réel vs chaque nulle, net de rien (noter le coût-temps en commentaire, pas en calcul).
- Série NAV stockée append-only (`table null_benchmark_nav`).
- Accès prix : EXCLUSIVEMENT via `shared/prices.py` (passerelle §5). Jamais d'appel `yfinance` direct.
- Handler `/null_status` : real vs `{SOXX, SPY, QQQ}`, delta, depuis inception.
- Cron hebdo dimanche (à côté des summaries existants).

**Gates** :
- Tests : property-based Hypothesis sur le math TWR (somme des sous-périodes = total ; invariance au découpage temporel).
- Cost : ~0 (prix cachés, `_PX_TTL`).
- Observabilité : `/null_status` + log INFO du delta hebdo.
- Failure modes : prix indispo → dernière NAV connue + WARN, jamais crash.
- Doc : ADR 010 §résultat + ligne KPI_DASHBOARD.

**Definition of Done** : `/null_status` retourne real vs SOXX/SPY/QQQ avec ≥1 période backfillée. Preuve = output collé.

---

### UNITÉ B — `thesis_registry` (Couche 1, la colonne)

**Objet** : record canonique append-only de TOUTE thèse — engagée ET vétoée — gelé par hash, résolu contre l'original.

**Schéma table `thesis_registry`** :

| Colonne | Type | Note |
|---|---|---|
| `id` | INTEGER PK | auto-increment (§2) |
| `ticker` | TEXT NULL | UPPERCASE ; NULL pour thème pur (ex. « everything space ») |
| `direction` | TEXT | `long\|short\|watch\|rejected` |
| `claim_json` | TEXT | schéma canonique §3, sorted keys, no trailing newline |
| `mechanism` | TEXT | LE fait fondamental qui valide — distinct du prix |
| `invalidation_json` | TEXT | conditions MESURABLES (liste) |
| `horizon_days` | INTEGER | |
| `conviction` | INTEGER | 1-5 |
| `veto_reason` | TEXT NULL | rempli ssi `direction='rejected'` |
| `decided_at` | TEXT | UTC ISO 8601 + offset (§1) |
| `prior_hash` | TEXT NULL | chaîne de versions (update = nouvel append pointant l'ancien) |
| `content_hash` | TEXT | SHA-256 de la sérialisation canonique |
| `status` | TEXT | `active\|invalidated\|realized\|stale` |
| `resolution_json` | TEXT NULL | rempli à terme |

**Règles dures** :
- Table append-only : triggers `thesis_registry_no_delete + thesis_registry_no_update` (pattern migration 0055). **Étend la doctrine append-only aux THÈSES** — ferme le gap L25/L26.
- Hash : SHA-256 sur JSON canonique (sorted keys, no trailing newline, §3). Tamper-evidence.
- **Gate de falsifiabilité à l'insert** : raise ValidationError si `invalidation_json` vide ou non-mesurable. Validateur déterministe d'abord (présence de claim + horizon + condition) ; le scoring ML (Unité C) le remplace plus tard. → **une thèse infalsifiable NE PEUT PAS être committée.**
- Update autorisé mais visible : pas d'écrasement ; nouvel append avec `prior_hash`. On peut changer d'avis ; on ne peut pas prétendre ne pas l'avoir fait.
- Résolution : étendre `resolve_due_predictions` pour résoudre contre le `content_hash` d'origine, PAS la croyance actuelle.

**Handlers** : `/thesis_register` (commit thèse ou véto), `/thesis_show <id>`, `/rejections` (le livre des vétos).

**Backfill initial** (pour que le registre naisse non-vide — matière de cette session) :
- **Rejets** : SpaceX (×6 itérations, 1 entrée + chaîne), Marvell, Lumentum, Aurubis, Tesla-SpaceX merge.
- **Tenues** : la table cible 30 lignes avec leurs invalidations déjà écrites (cf. table stops/targets de session).

**Gates** : tests property-based sur hash déterministe + rejet falsifiabilité + chaîne `prior_hash` ; cost ~0 ; observabilité via handlers ; failure mode = insert invalide → raise explicite (§6, jamais silencieux) ; doc ADR 010 + REFERENCE_SCHEMA.

**DoD** : une thèse engagée + un véto committés, hashés, affichés via `/thesis_show` ; tentative d'UPDATE rejetée par trigger (preuve = erreur SQLite collée).

---

### UNITÉ C — `narrative_drift` (Couche 2a, le canari)

**Objet** : classifieur Haiku sur les messages porteurs de thèse de l'utilisateur — détecte le glissement mécanisme→mission AVANT l'engagement de capital.

**Implémentation** :
- Module `intelligence/narrative_drift.py`. Prompt dans `shared/prompts.py` UNIQUEMENT (§10), versionné `DRIFT_SCORER_V1` (§13). Tier Haiku (cascade).
- Score sur **6 axes** (0-1 chacun + composite) :
  1. **Densité de falsifiabilité** (claims mesurables + invalidation) — axe le plus fort
  2. **Profondeur d'indirection** (nb de sauts claim→cash-flow)
  3. **Existence d'un objet investissable** (pure-play à prix non-parfait)
  4. **Contamination prix-comme-preuve**
  5. **Marqueurs d'appartenance** (« je crois en », « indéfectible », fusion en *nous*)
  6. **Absence de downside**
- **Axes forts = non-gameables (2, 3) : le vocabulaire (1, 5) se blanchit, la structure non.** Pondérer en faveur des structurels.
- Ancrage empirique : dès registre N≥10 résolu, recalculer les poids depuis le profil linguistique des thèses gagnantes vs perdantes **de l'utilisateur**. Pas le lexique a priori de Claude — ses propres perdantes.
- **Couplage à l'action** : score de dérive haut → `/thesis_register` exige une réfutation écrite avant d'accepter la thèse en position (ou auto-size-down). **Sans conséquence = gadget.**
- Sortie = **miroir** comparé à la baseline de l'utilisateur, jamais buzzer temps-réel. Tourne sur ce qui est déjà écrit (theses, `/predict`).

**Seed d'entraînement** : les rejets/acceptations backfillés en Unité B sont le gold set labellisé (rejet = dérive, analyse-mécanisme = propre).

**Gates** : cost modélisé (Haiku, $/score × volume) ; tests sur parties déterministes (comptage de sauts, lexique) ; observabilité (handler `/drift <id>`) ; failure mode = LLM down → defer, ne bloque pas ; doc ADR + note CONVENTIONS.

**DoD** : scorer une thèse propre (chokepoint) et une thèse-dérive (SpaceX) du backfill, afficher le contraste sur les 6 axes. Preuve = output.

---

### UNITÉ D — `bias_pnl` (Couche 2b, le prix de l'indiscipline)

**Objet** : chiffrer ce que les biais coûtent, en euros, pas en labels.

**Implémentation** :
- Étend `bias_tagger` existant : à chaque flag biais, snapshot `price_at_flag` (via `shared/prices.py`), track forward aux horizons.
- Coût contrefactuel : biais #1 (vend trop tôt) → `(prix_actuel − prix_à_la_vente) × qty` ; biais #2 (tient trop / FOMO) → symétrique.
- Table `bias_pnl_events` append-only.
- Handler `/bias_pnl` : coût cumulé par type de biais, sur fenêtre glissante.

**Gates** : tests sur le math contrefactuel ; cost ~0 ; observabilité `/bias_pnl` ; failure mode prix indispo → flag pending, recalcul ultérieur ; doc.

**DoD** : un événement biais #1 historique chiffré bout-en-bout, coût affiché. Preuve = output.

---

## 5. CONVENTIONS À RESPECTER (rappel, sinon stop)

- Accès externes via passerelles UNIQUEMENT : DB→`storage.py`, LLM→`llm.py`, Telegram→`notify.py`, prix→`prices.py`, config→`config.py`.
- Prompts dans `shared/prompts.py` uniquement, versionnés.
- Temps interne UTC ; tickers UPPERCASE ; enums `lowercase_snake_case`.
- JSON sorted keys, no trailing newline.
- Erreurs explicites, jamais `try/except: pass` ni `default=0.5` silencieux (leçon tennis-bot).
- Append-only = triggers, pas seulement doctrine (le gap L25/L26 qu'on referme).
- Output probabiliste, jamais Buy/Sell binaire.

---

## 6. INSTRUCTIONS D'OPÉRATION CLAUDE CODE

- **Plan mode systématique** avant toute unité non-triviale (B, C, D).
- **Verify-before-patch** : grep la vraie source avant de patcher, jamais de mémoire. `assert s.count(old)==1` safe-fail.
- **Une unité = une session = un commit.** Pas de scope creep : finir propre > élargir.
- **Gates 5/5 après chaque patch** : `import / ruff / mypy / pytest / smoke`. Restart propre si bot impliqué.
- **Jamais « fait » sans preuve** (output collé, test vert affiché).
- Après chaque correction → une règle dans CLAUDE.md (sinon c'est du L25 : constaté, jamais appliqué).
- Slash command par inner-loop répété si une vérif revient.

---

## 7. NON-GOALS (anti-scope-creep — ce chantier NE FAIT PAS)

- Pas de génération de signal ni d'alpha. C'est une couche de mesure.
- Pas de nouveaux tickers, sources, ou narratifs.
- Pas de refactor `bot/main.py` opportuniste (chantier séparé).
- Pas de 6e idée « révolutionnaire » ajoutée en cours de route. Le plan est figé à 4 unités. Toute idée nouvelle → backlog, pas ce chantier.

---

## 8. DECISION RECORD (extrait en ADR 010)

**Statut** : Proposed (12 juin 2026)
**Décision** : ajouter une couche de redevabilité décisionnelle (registre de thèses hash-committé append-only + nulle paresseuse + détecteur de dérive + P&L des biais) au-dessus du ledger de prédictions.
**Contexte** : le ledger mesure les prévisions, pas le processus. Les vétos (biais #3) sont non-falsifiables. La valeur de l'appareil de discipline est non-mesurée vs indexation.
**Conséquences** : étend la doctrine append-only aux thèses ; introduit un kill-switch honnête (peut conclure « indexe ») ; ~10-12h de build gatées derrière l'observation + la dette.
**Alternatives rejetées** : ajouter des features de signal (n'adresse pas la question processus) ; rien faire (laisse la discipline non-mesurée).

---

## 9. QUESTIONS OUVERTES À TRANCHER DANS L'ADR 010

Soulevées par Claude 13/06 à la pose du chantier, à figer avant Unité B :

- **Q1 — Périmètre du `content_hash`** : target/stop sont-ils inclus ? §B colonnes ne les liste pas mais §1 cadre parle de « conditions de falsification gelées » → implicitement oui. Si oui, un repose de niveaux (Hynix Régime A → target NULL, AVGO repose) crée mécaniquement un nouvel append `prior_hash`. C'est l'effet épistémique souhaité (changer d'avis est visible), mais la table grossit à chaque sweep #135. **Vote Claude** : target/stop **dans** le hash, parce que c'est précisément ce qu'un perdant rationalisant voudrait bouger sans trace.

- **Q2 — Rebalance de la nulle** : §4 Unit A laisse « trimestriel OU jamais ». La doctrine pure `lazy` = jamais-rebalance (buy-and-hold littéral, drift naturel). Trimestriel est déjà un overlay actif et donne un avantage cosmétique à la nulle si SOXX rallie (rebalance vend les gagnants). **Vote Claude** : jamais-rebalance, fidèle à « indexe et arrête ». Sinon on compare à une nulle qui n'est plus paresseuse.

- **Q3 — Labellisation seed Unit C** : §C dit « rejet = dérive, analyse-mécanisme = propre ». Tension : SpaceX×6 backfillés sont des **bonnes décisions de rejet** (Olivier a tué la dérive narrative à temps). Donc dans le corpus, ils sont labellisés « dérive » — la prose elle-même est dérive, même si la décision était saine. Pas de contradiction logique, mais à expliciter dans l'ADR : on label le **contenu narratif**, pas la décision.
