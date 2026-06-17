# SPEC — Signal régime « Moore / Compute-Cost Cycle » (EXPLORATOIRE)

**Statut** : design, non-câblé. Créé 13/06/2026. Démote L9 par défaut (aucune décision pilotée tant que pas backtesté sur cycles connus).

## But

Indicateur **avancé** de la santé du moteur de demande du book semi/AI : le coût-compute décline-t-il (→ Jevons, demande s'auto-entretient) ou s'aplatit-il (→ plafond ROI, top capex) ? C'est la variable-charnière du pari single-factor AI-capex — plus causale et plus en amont que VIX/taux pour CE book.

## Le problème central (à ne pas contourner)

**On ne peut PAS valider un régime « AI-capex » : N=1 cycle (2023-2026).** L9/L13 → tout signal calibré là-dessus reste exploratoire à vie. Donc on **scinde** :

| Couche | Mesure | Validable ? | Rôle |
|---|---|---|---|
| **Cœur cycle semi** | Cycle coût/mémoire/capex large | **OUI** — multiples cycles historiques (N réel) | peut être backtesté, puis promu |
| **Overlay AI** | Proxies AI-spécifiques | NON (N=1) | reste démoté/exploratoire, ne pilote rien |

Le cœur porte la validation ; l'overlay AI est une lecture, jamais un gate.

## Inputs candidats (proxies + source + dispo)

**Cœur cycle (historique long, validable) :**
- **Marges brutes mémoire (MU + SK Hynix)** — proxy propre du cycle mémoire, **gratuit** (financials via bigdata/LSEG), 20+ ans. Cycle boom-bust net.
- **SEMI book-to-bill** — indicateur de cycle semi canonique, historique long. L'ancre de validation #1.
- **Capex hyperscaler YoY** (guidance, filings) — confirmation demande, laggard, gratuit.
- **$/GB DRAM+NAND** (TrendForce/DRAMeXchange — payant ; proxy gratuit = marges mémoire ci-dessus).

**Overlay AI (court, exploratoire, démoté) :**
- **Spot GPU cloud** ($/H100-hr) — observable ~2023+, AI-spécifique, court.
- **Prix token API** (labs frontière, $/Mtok dans le temps) — chute vite, observable, **bruité** (subventionné sous le coût → ne pas sur-interpréter).
- **Premium HBM** — récent, AI-spécifique.

## Architecture (conforme système)

- **Déclaratif** : poids/bandes des proxies en `config/moore_cycle.yaml` + Pydantic + bloc `audit_metadata.temporal_splits` (L16 — train/val/oos datés AVANT tuning).
- **Live state** : table append-only `moore_cycle_evaluations` (L17), migration alembic + trigger immutable (cf 0058).
- **classify pur** : `classify_cycle_regime(proxies) -> {regime, confidence, asof}` ; régimes = `expansion / peak / contraction / trough` ; **fail-closed L15** (proxies manquants → `None`, pas de régime fabriqué).
- **Pattern monitor** (`docs/templates/monitor_pattern.md`) : journal + classify + check_all_transitions + 7 tests dont le critique L4.
- **Démote L9** : label « exploratoire / non calibré », couleurs neutres, **ne pilote NI sizing NI conviction** tant que non backtesté ≥3 cycles historiques.

## Validation (L11 — vérifier les labels, pas les supposer)

Ancres = les retournements semi connus, **labellisés empiriquement** (pas au feeling) :
- Bust mémoire **2022-2023** (contraction franche).
- Downturn **2018-2019** (peak→contraction).
- Reprise post-COVID **2020-2021** (trough→expansion).
- Calmes/transitions intermédiaires.

Pour chaque ancre : tirer 2-3 indicateurs indépendants (marge mémoire, B:B, capex YoY) et confirmer que le label macro correspond AVANT de juger le classifier (L11).

## Premier milestone (borné, gratuit, sans câblage)

1. Assembler 3 séries gratuites : **marges brutes MU + Hynix**, **SEMI B:B**, **capex hyperscaler YoY** (via bigdata/LSEG).
2. Labelliser à la main les 3-4 retournements historiques ci-dessus.
3. Tester si un composite SIMPLE sépare expansion vs contraction sur ces cycles CONNUS.
4. Si oui → le cœur cycle est réel, on formalise le YAML + temporal_splits. Si non → on jette, pas de sur-construction.

**Aucun overlay AI, aucun câblage sizing à ce stade.** L'overlay AI s'ajoute APRÈS que le cœur passe la validation, et reste démoté.

## Séquençage

**Après le keystone convictions** (le sizing/PF d'abord), et **backtest avant pilotage** (L9/L19). Ce spec est le travail de design ; l'exécution = le milestone 1 ci-dessus, data-first, quand le PF est figé.

## Implementation Status

**NOT_STARTED** — design 13/06/2026, gated derrière keystone convictions (sizing/PF) + backtest L19. Premier milestone (assembler 3 séries gratuites + label 3 ancres + test composite) éligible quand PF figé. Aucun fichier cible à l'heure actuelle.

**Red-team noté 17/06/2026** (cf conversation) :
- Les 3 proxies cœur sont coïncidents/laggard, pas leading — tension avec "indicateur AVANCÉ" du But.
- N=3 cycles borderline pour validation composite ; historique mémoire 1990s+ disponible si data assembly assumée.
- Composite doit être pre-registered dans `config/moore_cycle.yaml` AVANT de regarder validation cycles (anti garden-of-forking-paths).
- Pass threshold ex-ante à définir ("accuracy ≥ X% sur 3 ancres, sinon abandon").
- AI overlay : rôle à clarifier (lecture narrative vs futur calibration). Si narrative → c'est un widget, pas un SPEC item.
- Token prices : exclure plutôt que filtrer post-hoc (doctrine = pas de bad data sous caveat).

À reprendre quand le SPEC sera dégated.
