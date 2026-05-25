# ADR 006 — Profit-take : trigger cible-only, débranchement de target_partial

**Statut** : Accepté — 25/05/2026 · High Standard / Path 5-6 · correctness audit-grade

## Problème
Le bot déclenche une prise partielle sur `price >= target_partial` à 3 endroits
(price_monitor → alerte Telegram, thesis revisit → triggers_met, shadow main →
décision challenger) + un nudge dashboard de proximité-cible. Olivier rejette
explicitement le palier intermédiaire ET la proximité : **la cible (`target_full`)
est le seul trigger de prise de profit.**

## Découverte empirique (corrige mémoire + conclusion antérieure)
`target_partial` n'est PAS saisi à la main. Sur 28 thèses actives, le ratio
`target_partial / target_full` est constant par groupe (≈0,859 / 0,875) →
valeurs **auto-dérivées par formule bulk**, pas 28 entrées manuelles. La note
« NULL sur 33 actives » est périmée.

**Conséquence : bug fleet-wide.** Toute thèse long qui s'apprécie franchit
`target_partial` (≈86-87 % du chemin) AVANT `target_full` → alerte « prends ta
partielle » sur les 28. C'est le biais *vend-trop-tôt* mécanisé et amplifié sur
tout le portefeuille (ALAB = premier arrivé au niveau, pas cas isolé).

## Décision
1. Trigger profit-take unique = `target_full`. `target_partial` ne déclenche plus :
   price_monitor (crossings "partial" long+short), thesis revisit (branche
   "target partiel"), shadow main (bascule sur `target_full`).
2. Dashboard : suppression du bloc « cibles partielles » (qui cadre l'absence de
   palier comme un manque de discipline) + du nudge proximité. Axe stop conservé.
3. `target_partial` reste champ **inerte** (référence) jusqu'au cleanup C.

## Conséquences
- **Freeze-compatible** : retire un comportement faux, ne touche pas aux prédictions
  (KPI #2). Outcomes shadow-main sur l'ancienne règle = caducs (non-perte).
- **Insight shadow** : `main` devient = `aggressive` (anti-exit-prématuré) — la règle
  disciplinée d'Olivier EST la variante anti-biais. A/B réduit à cible-vs-gain15 %
  → redesign variantes en follow-up.
- Test `test_theses_long_targets_ordered` retiré (il codifiait la règle rejetée).

## Hors scope → cleanup C (séparé)
- Null-out des 28 `target_partial` dérivés — **localiser le dériveur d'abord**
  (hors chemins .py de saisie) sinon il re-remplit.
- Arrachage du champ : asymmetry, journal, pre_mortem, risk_manager, storage,
  handlers create/edit, branche morte `_format_alert`.

## Implémentation
- Commit 1/2 : ce document + price_monitor (l'alerte Telegram, nag fleet-wide).
- Commit 2/2 : thesis revisit + shadow main + retrait test + dashboard.
