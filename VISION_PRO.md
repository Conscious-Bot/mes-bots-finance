# PRESAGE — Vision pro & roadmap chronologique

> Document de synthèse (HEAD `0042956`, 07/06/2026). Capstone des sessions audit → pivot. L'ordre des phases **est** l'argument : chaque étape débloque la suivante, et chaque phase attaque un plafond structurel nommé. Ne pas réordonner sans casser une dépendance.

---

## 0. Le pivot (à garder en tête à chaque ligne)

On a cessé de vouloir **scorer un résultat avec plus de précision** pour **changer l'objet scoré** : la prouvabilité d'un jugement. Raison — trois plafonds *structurels* qu'aucune calibration ne perce :

| Plafond | Nature | Ce qui le perce (phase) |
|---|---|---|
| **Auto-référentiel** | l'opérateur note l'opérateur → corruptible | Pré-engagement tamper-evident ancré externe (P1) |
| **Petit-n** | N=35 outcomes résolus = bruit, latence boucle 30j | Process-grading (N=53 immédiat, P2) + outside-view (P3) |
| **Outcome-graded** | Brier ignore le quadrant *raison fausse / résultat juste* | Attribution causale 2×2 (P2) |

**Critère nord, unique :** *auditable par un adversaire*. Une due-diligence hostile peut-elle falsifier ou vérifier chaque nombre ? Si non → ce n'est pas un outil pro, c'est un journal intime sophistiqué. Tout le reste en découle.

## 1. Corrections d'audit actées (intégrité avant de bâtir)

Deux constats initiaux étaient **faux** après inspection profonde, intégrés ici pour ne pas rebâtir l'existant :
- `factor_exposures.py` mécanise déjà la décomposition multi-facteurs + stress tests, branché dashboard. Ne **pas** reconstruire — le transformer en monitor (P2).
- `lock_in_detector` est wiré (`shared/positions.py:216`) et a déjà capturé un événement réel (vente SNOW, `bias_events` id=5). Le README est périmé, pas le code.
- Resolver sain : 184 prédictions NULL = 0 en retard, toutes en vol. Le problème est la **latence de boucle** (30j), traitée P1 par les sondes.

---

## ROADMAP

### Phase 0 — Nettoyer les instruments (semaine 1, effort faible, bloquant moral)
*On ne mesure rien de fiable sur une base qui ment au prochain agent.*

- **0.1 Doc-drift check** — `scripts/doc_drift_check.py` en pré-commit qui regénère les chiffres volatils (compte tests réel 1107 vs « 414 » annoncé, LOC des fichiers cités, état des modules dits « non instrumentés ») et échoue si `AGENT_HANDOFF`/`README`/`CLAUDE.md` divergent. *Le handoff EST le contrat de reprise ; faux sur ≥3 faits matériels = la pire dette d'un projet conçu pour passation IA.*
- **0.2 Gates CI grep** — `yfinance` hors `prices.py` (19 fichiers) + `sqlite3.connect("data/bot.db")` littéral (9 sites) = build rouge. Rend réels deux invariants aujourd'hui fictifs. Les 9 chemins hardcodés sont des bugs (cassent l'override `DB_PATH` → tapent la prod en test).
- **0.3 Lancer les sondes 7j MAINTENANT** *(front-load car latence 8 semaines)* — prédictions-sondes court-horizon taggées `probe`, découplées des thèses de conviction (18-24m), pour accumuler du Brier vite. Démarre l'horloge statistique : N=35 → ~100 en 8 semaines. **Tout le reste qui dépend de N en profite — donc c'est ici, pas plus tard.**

> Dépendances : aucune. Pourquoi en premier : 0.1/0.2 sont la pré-condition d'honnêteté, 0.3 a la plus longue latence du projet.

### Phase 1 — La fondation tamper-evident (semaines 1-3) — *perce le plafond auto-référentiel*
*Sans ceci, toute métrique aval est corruptible par l'opérateur. C'est le socle « auditable par adversaire ».*

Ordre **strict** (chaque étape dépend de la précédente) :

1. **A0 · Capture** — alembic `+ theses.variant_perception, driver_epic, benchmark (TEXT)` ; `add_thesis` capte ces 3 params (défaut None + warning si vide sur conviction≥4). *Catch verify-before-patch : 3 des 5 champs à figer n'existent pas aujourd'hui → sans A0, on signerait du NULL = integrity theater. A0 débloque aussi (b), qui lit `driver_epic`.*
2. **A2 · Hash canonique** — `shared/integrity.py` : `canonical_payload()` (json `sort_keys`, floats formatés str 6 décimales — sinon hash non-reproductible = vérif cassée) + `sha256` + `chain(prev_hash, genesis=64×'0')`.
3. **A1 · Journal** — alembic `thesis_integrity_log` append-only (style `monitor_pattern` : `created_at` DEFAULT, FK `theses`, jamais de DELETE).
4. **A3 · Hook** — dans `add_thesis` après commit (style `positions.add_sell`→`lock_in`) : append integrity row. Complémente `conviction_history` (révisions mutables) en figeant le **T0**.
5. **A4 · Ancrage externe** — `anchor_chain_head()` cron daily → tag git signé `integrity/<date>-<head8>` push origin branch-protected, **ou** OpenTimestamps ; écrit `anchor_ref`. **Non-optionnel : sans A4, A1-A3 ne contraignent pas l'opérateur (il rebâtit la chaîne) → théâtre. A4 est la ligne qui sépare l'asset de la cérémonie.**
6. **A5 · Vérif + tests** — `verify_chain()` + 7 tests dont le critique : payload muté → `chain_hash` diverge de `anchor_ref`.

> Dépendances : A0→A2→A1→A3→A4→A5. Pourquoi avant les features : aucune métrique de jugement n'est défendable tant que le pré-engagement n'est pas tamper-evident contre l'auteur lui-même.

### Phase 2 — Changer l'objet scoré (semaines 3-6) — *perce outcome-graded + petit-n (dimension process)*
*Le pivot paie ici : on score le process, pas le résultat.*

- **2.1 Attribution causale 2×2** — rubrique process×outcome. Quadrant dangereux = *raison fausse / résultat juste* (chance déguisée en talent), invisible à tout Brier. Mécanique : factor-decomposition du return réalisé vs `driver_epic` loggé (lit A0). **Asymétrie obligatoire** (catch R3) : mismatch facteur = forte evidence de chance ; match facteur = faible evidence de skill. Utiliser comme détecteur-de-chance, jamais comme tampon-de-skill.
- **2.2 Scorecard process-graded (F1)** — note l'opérateur sur spécificité kill-criteria, falsifiabilité variant_perception, taux validation-de-raison. *Déblocage clé : process observable par décision → N=53 de signal immédiat, pas N=35 résolus. Seule dimension qui échappe au petit-n, et c'est la dimension défendable.*
- **2.3 factor_exposures → monitor** — le calcul existe, l'alerte non. Pattern `monitor_pattern` : seuil « AI-broad >75% » → événement journalisé + notif à la transition. Ferme « panneau statique vs garde active ».

> Dépendances : 2.1/2.2 lisent A0 (driver_epic, variant_perception capturés). Pourquoi après P1 : scorer le process avant que le T0 soit figé = scorer du mutable.

### Phase 3 — Déborder le petit-n par l'outside view (semaines 5-8) — *perce le plafond petit-n (dimension outcome)*
*Le prior universel compense ce que 40 points ne peuvent dire.*

- **3.1 Base-rate externe (c) via Bigdata** — « profil d'entrée X distribue historiquement excess-return Y » → prior bayésien. Point dur : **problème de classe de référence** (Kahneman) — trop étroit = pas de base-rate, trop large = bruit. Éviter le double-comptage (ne pas inclure tes propres picks dans l'univers de référence).
- **3.2 Reference-class interne (F3) par embeddings** — étendre `signal_embeddings` (427, BGE local) aux *décisions* : à T0, retrouver les 8 setups passés les plus proches (par structure, pas ticker) + leur résolution + validation-de-raison. Ton outside-view propre.
- **3.3 Prior à deux étages** — combiner 3.1 (univers) + 3.2 (toi) avec pondération explicite (à N=40, le prior domine — c'est voulu).

> Dépendances : 3.2 réutilise la stack embeddings existante ; 3.1 ajoute la dépendance Bigdata. Pourquoi après P2 : l'attribution (2.1) définit ce qu'on cherche dans la classe de référence (« raison validée », pas juste « monté »).

### Phase 4 — L'instrument se note lui-même (semaines 8-12) — *construit l'asset défendable*
*La vente passe de « Olivier est bon » (invérifiable) à « l'instrument améliore les décisions de X% » (mesuré).*

- **4.1 Track-record du copilot (F2)** — quand `decision_copilot` objecte et qu'on passe outre, avait-il raison ? Mesurable seulement parce que P1 rend les overrides tamper-evident. **L'asset central d'une due-diligence.**
- **4.2 Taux d'angle-mort (F4)** — boucle pré-mortem→post-mortem : le mode d'échec réel était-il dans ton `pre_mortem` ou un angle mort ? Métrique d'humilité épistémique, infalsifiable une fois pré-enregistrée.
- **4.3 Famille de shadow-books (F5)** — « discipline stricte / ignore tout / suis seulement c5 / pondéré base-rate » en parallèle. L'écart quantifie la **valeur marginale de chaque règle** → quelles disciplines paient, lesquelles sont du folklore. Ressuscite `shadow_decisions.py` (code mort aujourd'hui).

> Dépendances : 4.1 exige P1 (overrides figés) + temps (N override résolus) ; 4.3 exige les counterfactuals (`bias_events.counterfactual_json`, 214 lignes déjà là). Pourquoi ici : c'est la couche qui *vend*, elle a besoin de toutes les précédentes comme substrat.

### Phase 5 — Le passage au pro (mois 4-6) — *construit la base produit*
*Auditable par adversaire = exigence, pas option.*

- **5.1 Séparer moteur / instance** — extraire le kernel scoring-de-jugement (pré-registration → attribution → base-rate → process) domaine-agnostique ; book/sources/facteurs → **config déclarative** (L17 le supporte déjà). Tant que `factor_exposures` hardcode AI-capex et que `sources` = tes newsletters, il n'y a pas de produit, il y a ton instance.
- **5.2 Multi-opérateur par isolation-fichier** — **un SQLite par opérateur**, pas Postgres + RLS. Préserve « less surface », zéro requête tenant-filtrée. Résout le `KNOWN-GAP: tenant filter` proprement. *Fork à acter maintenant ou dette plus tard.*
- **5.3 Reproductibilité / pinning modèle** — le LLM est la surface de risque : pinner la version de modèle par `methodology_version` (champ existe) + rejouabilité d'un score avec le modèle exact, ou fallback déterministe (`scoring_orchestrator` le fait). Sans ça, « reproductible » est un mensonge (cf drift `opus-4-7` dans les logs).
- **5.4 Page track-record publique vérifiable** — surface l'asset P1+P4 : prédictions pré-enregistrées + ancrage + Brier + lift copilot, ré-dérivables par un tiers. C'est le wedge (i) matérialisé.

> Dépendances : 5.1 avant 5.2 (on n'isole pas par tenant ce qui n'est pas séparé du book). Pourquoi en dernier : productiser avant d'avoir l'asset (P4) = vendre du vide.

---

## Invariants transverses (à graver, valables sur toutes les phases)

1. **Aucune nouvelle couche de calibration tant que N_résolu < 100.** À N=35 sur 1 bucket, chaque étage méta élargit l'écart appareil/données. L'effort va à l'ingestion + latence de boucle (P0.3), pas aux étages.
2. **Record append-only ancré vs config déclarative versionnée** — invariant architectural dur, plus aspirationnel (L17 promu).
3. **Reste un outil de process décisionnel, jamais de recommandation.** « Le bot ne trade pas » est la douve réglementaire (hors terrain RIA/advice). Porteur, garder religieusement.
4. **Construis la base pour qu'elle puisse t'humilier.** Le tail-risk existentiel : le lift mesuré de l'instrument pourrait être ~0 ou négatif. Mais un instrument capable de mesurer sa propre inutilité est le seul en qui un adversaire peut croire. La volonté de publier le résultat nul *est* la crédibilité qui vend.

## Le wedge

| Produit | Asset | Verdict |
|---|---|---|
| **(i) Instrument de jugement personnel prouvable** (prosumer/Substack) | ton track-record vérifiable | **Base — 80% déjà construit, jugement prouvable est rare** |
| (ii) Couche discipline pour PMs discrétionnaires (B2B) | track-record du copilot (F2) | Expansion une fois (i) prouvé |
| (iii) Kernel-as-API | — | **Drop (distraction)** |

Construire (i) d'abord. (ii) en expansion naturelle quand F2 a prouvé le lift. La taste = n'en bâtir qu'un.

## Vue dépendances (spine)

```
P0.1 doc-drift ─┐
P0.2 CI gates ──┤ (honnêteté, parallèle)
P0.3 sondes 7j ─┴───────────────────────────────► (latence 8 sem, alimente P2/P3/P4)

P1: A0 ─► A2 ─► A1 ─► A3 ─► A4(ancrage) ─► A5
     │                                       │
     └─► driver_epic capté ─► P2.1 ──────────┤
                              P2.2 (F1) ◄─────┘ (N=53 process immédiat)
                                   │
P3.1 base-rate ext ──┐             │
P3.2 ref-class int ──┴─► prior 2 étages ◄── P2.1 définit "raison validée"
                                   │
P4.1 copilot TR ◄── exige A4 + temps
P4.2 angle-mort ◄── exige pre_mortem pré-enregistré (A3)
P4.3 shadow-books ◄── exige counterfactuals (déjà là)
                                   │
P5: 5.1 moteur/instance ─► 5.2 multi-tenant ─► 5.3 repro ─► 5.4 page publique
```

> Le fil : **honnêteté (P0) → prouvabilité (P1) → bon objet scoré (P2) → puissance statistique (P3) → asset défendable (P4) → produit (P5).** Chaque flèche est une dépendance dure, pas une préférence.
