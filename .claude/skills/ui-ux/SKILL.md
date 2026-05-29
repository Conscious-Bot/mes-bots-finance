---
name: ui-ux
description: Barre de gout UI/UX du projet (dashboard interne + futur site public). A surfacer pour toute creation ou modif d'interface, composant, visualisation, ou page. Design meaning-first, anti-generique-IA.
---

# UI/UX — barre de gout du projet

## Regles non-negociables
- **Couleur = un fait, jamais un jugement.** Le rouge marque le cote risque, le vert le cote cible. Pas un verdict "bon/mauvais".
- **Mouvement = epistemique.** L'animation revele la donnee (filtrage de l'univers, courbe de calibration qui se trace, marqueur qui se pose). Pas de parallax / glow / particules decoratifs.
- **Un seul modele de lecture, reutilise partout.** Ici : l'axe stop->cible (overview, cartes theses, asymetrie). Ne pas inventer une 2e grammaire.
- **Prominence par taille + clarte, pas par deco.** Une barre devient "star" en etant plus grande et mieux labellisee, pas via gradient/ombre/glow.
- **Chaque element gagne sa place ou degage.** Pas de redondance (barre + caption qui repetent le meme %). Pas de viz si le texte suffit.
- **Formatage minimal.** Densite d'information honnete > chrome.

## Anti-patterns (refuser)
- Cliche "cerveau-qui-brille / Cerebro litteral" = signal grift/sci-fi, tue la credibilite d'un site de track-record financier.
- Parallax-soup, scroll-jacking, tout-qui-flotte = tell generique IA.
- Sur-claim visuel depuis un petit N de donnees.

## Contexte stack
- Dashboard interne (render.py, HTML genere par Python, zero build) : motion seulement si porteuse de sens ; CSS pur, ou Motion vanilla (motion.dev) via CDN sans build.
- Site public (Path 6, post-10/06) : React + Motion (motion.dev, ex-Framer Motion). Sombre/instrument OK si retenu. Construire AUTOUR des vrais chiffres Brier, en "ouverture des livres", pas alpha prouve.
- Le skill frontend-design cote Claude couvre les details tokens/styling.
