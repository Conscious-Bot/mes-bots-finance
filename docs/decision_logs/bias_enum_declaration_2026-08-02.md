# Déclaration — enum de biais canonique + traduction des labels 30/07

**Date** : 2026-08-02 · **Origine** : chaîne de dry-runs 02/08 (4ᵉ trou silencieux).
**Source de vérité** : `docs/specs/terminologie_bias_events_fr.md` (31/05) — enum `bias` =
**`{lock_in, fomo_greed, other}`**, strict, français impersonnel, cognitifs sous `other`.

## Le constat (H11 : règle écrite, jamais appliquée)

La spec définit l'enum depuis mai. Ni le replay du tribunal 30/07, ni le `bias_tagger`
live ne l'appliquaient. Résultat en base : des labels **inventés** (`override_vs_tribunal`,
`bottom_timing_instinct`, `override_timing_taille`, `override_pre_print`), un **doublon
francophone** de `lock_in` (`vend_winners_trop_tot`, interdit par L1), et des **cognitifs
granulaires** du tagger (`recency_bias`, `confirmation_bias`, `overconfidence`,
`availability_heuristic`) qui, par la spec, sont `other`.

Chaque label inventé étant un singleton, `get_bias_stats` ne pouvait rien agréger : l'appareil
de mesure des biais était aveugle à ses propres décisions.

## Ce qui est corrigé (02/08, commit ci-après)

1. **Source unique** : `CANONICAL_BIAS = ("lock_in","fomo_greed","other")` dans `shared/storage.py`,
   référençant la spec.
2. **Garde écriture (fail-loud)** sur `insert_decision_with_cf` : rejette tout label hors enum,
   **doublons sémantiques compris** (validation contre la spec, jamais contre l'historique —
   sinon on canonise la dette). Seul caller passant ce param = le replay DO-NOT-RUN → zéro risque live.
3. **Mapping lecture** dans `get_bias_stats` : legacy/cognitif → enum au comptage. Le passé
   redevient agrégeable **sans réécrire la base**.

## La traduction (accepter + déclarer, PAS de chirurgie append-only)

`decision_counterfactual` est append-only (`dcf_no_update`/`dcf_no_delete`). Réécrire les 4 labels
reviendrait à **maquiller le passé** — le journal dirait qu'on avait bien taggé le 30/07, ce qui est
faux. La valeur d'un journal immuable est qu'il conserve les erreurs de son auteur. Donc les rows
gardent leur label brut ; seule la **lecture** traduit, via `_LEGACY_BIAS_MAP` :

| label brut (immuable en base) | → enum | raison |
|---|---|---|
| `override_vs_tribunal` · `bottom_timing_instinct` · `override_timing_taille` · `override_pre_print` | `fomo_greed` | même comportement : agir contre le cadre écrit sous l'impulsion |
| `vend_winners_trop_tot` | `lock_in` | doublon francophone (L1) |
| `recency_bias` · `confirmation_bias` · `overconfidence` · `availability_heuristic` | `other` | cognitifs → `other`, nuance dans le reasoning (spec) |

## Ce qui reste ouvert — PQ-009 (NE PAS conformer le tagger avant de trancher)

Deux vocabulaires de biais coexistent sans **périmètre déclaré** :
- `bias_events` / l'enum : mesure un **écart discipline↔action** (vente de winner, dépassement
  de cap, kill-criteria), détecté par des hooks mécaniques.
- `bias_tagger` : **annote le raisonnement** d'une décision avec des biais cognitifs (LLM).

Ce sont peut-être **deux objets différents** (ce que tu as fait contre ta règle vs comment tu as
pensé). Écraser le second dans l'enum du premier détruirait de l'information sous couvert de
conformité. **Avant toute conformation du tagger : lire le tagger (~30 min) et déterminer s'il
mesure le même objet.** Si oui → conformer. Si non → séparer les champs + amender la spec pour
nommer les deux vocabulaires et leurs portées (un divorce, pas une garde).

Note technique : un fail-loud sur `update_decision_bias_tags` (canal du tagger) serait **avalé par
le `try/except` des handlers** (`journal_bias.py`, `positions.py`) → biais live perdus en silence.
D'où : réparer le lecteur d'abord (fait), le writer seulement après PQ-009.
