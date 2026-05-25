# STAR FEATURE & roadmap moat

Defini 25/05/2026. Le coeur differenciant + la frontiere de valeur reelle.

## Le star feature

PAS le PnL (table stakes), pas l'asymetrie (support), pas la calibration seule (standard, vide jusqu'au 10/06).

**La boucle de correction bidirectionnelle des biais de l'operateur, au point de decision.** Le bot intercepte les deux biais nommes (vendre winners trop tot ; ne pas trimmer aux tops) AVANT le commit, et mesure si la correction produit de l'edge.

- Mecanisme = interception (risk_check + bias_tagger). Demontre 25/05 : risk_check #6-8 ont chope unexplained_action / anchoring / narrative_shift_without_data / recency_bias -> ALAB (raison ajoutee), 6920.T (invalidation -> lean marginal calibre).
- Sortie vendable = la PREUVE chiffree que les decisions disciplinees battent les biaisees.
- Defendable : lie aux biais empiriques perso (PLTR@9, NVDA@130, crypto FOMO), se calibre dans le temps. Aucun terminal / stock-picker LLM ne modelise les failure modes de l'operateur.

## Modelisation dashboard : le « Discipline Ledger »

- Axe biais #1 (vendre trop tot) : sorti avant cible ? regret cumule (prix apres sortie : continue = regret / reverse = bonne sortie).
- Axe biais #2 (pas trimmer au top) : top/cible touche sans trim -> gains rendus ?
- Overlay : chaque risk_check + flags, et si ecoutes.
- Tendance : moins de decisions flaggees, calibration ^, regret v.

## Roadmap (range par plus-value reelle)

Deux axes de vraie valeur : PROUVER l'edge, et PRODUIRE du contenu Path 6. Le reste est du jardinage.

1. Ledger contrefactuel « heed vs override » (couronne). Logge action prise + action recommandee, resous LES DEUX -> chiffre qui vend tout. CAPTURE buildable maintenant (logging additif, freeze-safe) ; analyse/viz post-volume.
2. Benchmark « self-mecanique » : variante qui applique TES regles sans discretion. Ta discretion ajoute-t-elle de l'edge ?
3. Biais conditionnes par regime (#1 en risk-off ? #2 en euphorie ?).
4. Pre-mortem -> post-mortem qui se ferme (le failure mode predit s'est-il produit ?).
5. Pushback conditionne par taux de biais (« tu as early-sold 6/8 winners ; celui-ci en a la signature »).
6. La boucle auto-genere l'artefact public Path 6 (calibration + case studies).

## Build gate

Tout est data-gated. Seul le CAPTURE (#1) vaut un build maintenant. Analyse + viz post-10/06. Principe : approfondir LE star, pas eparpiller de la surface.
