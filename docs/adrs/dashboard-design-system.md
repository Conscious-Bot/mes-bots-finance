# ADR — Dashboard design system (refonte propre)

**Date** : 2026-05-24 · **Statut** : Accepté

## Contexte
`dashboard/render.py` (1600 l, 102 Ko) génère le dashboard. Bones corrects (une fonction par vue) ; la dette est dans la **couche design** :
- CSS éclaté en 4 endroits (`_CSS`, `_TH_CSS`, 2 `<style>` inline)
- valeurs **hardcodées hors tokens** : panneaux `rgba(22,32,52,.5)` / `rgba(13,20,38,.6)`, barres `#13203A`, triplets legacy `rgba(55,224,160)` / `rgba(0,224,255)`
- **dead code** : `.cmdbar*`, `_system_state`
- ~10 classes label quasi-dupliquées
- `PAL` (palette legacy) encore utilisée dans `_donut` au lieu de `SECTOR_COLORS`
- 1 seul test (smoke)

## Décision
Couche design = **source unique, token-driven**, refonte **incrémentale gatée** (ruff + render-smoke à chaque étape), pas de big-bang.

## Phases
1. Tokeniser les valeurs hardcodées → `--glass/--glass2/--tape/--barbg`. **[fait]**
2. Purger le dead code (`.cmdbar*`, `_system_state`).
3. Consolider les labels en une règle `.eyebrow`.
4. Fusionner `_TH_CSS` dans `_CSS` ; supprimer les `<style>` inline.
5. `_donut` → `SECTOR_COLORS` (retirer `PAL`).
6. Étoffer les tests (par vue, pas que smoke).

## Conséquences
- (+) Source de design unique et auditable ; changer un token propage partout.
- (+) Moins de surface ; conforme à CONVENTIONS.md (§5 une passerelle, §9 naming).
- (−) Effort réparti sur plusieurs sessions, mais risque par étape minimal.
