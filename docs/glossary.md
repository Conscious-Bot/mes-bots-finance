# GLOSSARY — Vocabulaire canonique PRESAGE

**Version : 1.0** (figé le 31 mai 2026)
**Rôle** : source unique du vocabulaire. Tout terme employé dans le code, l'UI, le dashboard, les posts et la doc s'y conforme.

> Cet ancien glossaire (Path 5/6 readability) est REMPLACÉ par cette version canonique v1.0. Les définitions historiques (Brier, calibration, etc.) sont absorbées et raffinées ci-dessous selon les désambiguïsations figées.

---

## Principe — deux couches

1. **Marque / éditoriale** — le nom, le tagline, la voix. Registre poétique permis.
2. **Opérationnelle** — concepts et métriques. Lexique rigoureux du forecasting, point.

**Règle d'or** : le nom peut être poétique ; le vocabulaire doit être précis. La marque vit dans la couche 1 ; jamais dans les concepts de données.

**Langue** : termes canoniques en français, équivalent anglais entre parenthèses (sert de label pour les surfaces EN, dont les posts menés en anglais).

---

## Couche 1 — Marque / éditoriale

| Élément | Valeur |
|---|---|
| Nom | **PRESAGE** |
| Tagline | « La vérité dans le bruit » / *Truth in the noise* |
| Voix | sobre, savante, honnête ; instrument de mesure, pas terminal ni app |
| Description produit | (à définir — ne pas fabriquer ici) |

À éviter dans la couche 1 comme ailleurs : thématiser le lexique technique sur la métaphore (« présages », « augures » comme termes techniques) = cosplay, à proscrire.

---

## Couche 2 — Opérationnelle

### Calibration & scoring

- **Calibration** (*calibration*) — tes prédictions à X % se réalisent-elles X % du temps.
- **Score de Brier** (*Brier score*) — règle de scoring ; 0 = parfait, plus bas = mieux.
- **Fiabilité** (*reliability*) — composante calibration du Brier ; aussi le **diagramme de fiabilité** (*reliability diagram*).
- **Discrimination** (*discrimination*) — composante « pouvoir de séparer les issues » du Brier.
- **Taux de base** (*base rate*) — fréquence a priori ; l'ancre.

### Prédictions & thèses

- **Prédiction** (*prediction*) — claim falsifiable : direction + probabilité + horizon + critère de résolution.
- **Résolution** (*resolution*) — l'événement où une prédiction expire et se mesure objectivement.
- **Horizon** (*horizon*) — délai jusqu'à résolution.
- **Conviction (1-5)** (*conviction*) — confiance ressentie ; distincte de la probabilité.
- **Probabilité (0-1)** (*probability*) — probabilité stockée de la prédiction ; jamais en pourcentage en base.
- **Thèse** (*thesis*) — vue directionnelle + critère d'invalidation. Statuts (enum) : `active | invalidated | realized | stale`.

### Risque & position

- **Stop / Cible** (*stop / target*) — les deux bornes de l'axe ; la primitive de lecture réutilisée à l'identique partout.
- **Asymétrie** (*asymmetry*) — distances brutes vers stop vs cible. Aucun verdict auto-dérivé du framework (fix anti-tautologie).

### Signaux & sources

- **Signal** (*signal*) — unité ingérée (newsletter, 8-K, macro…), typée + sentiment.
- **Matérialité** (*materiality*) — combien un signal compte pour une décision.
- **Crédibilité** (*credibility*) — score par source, affiné par les outcomes objectifs.

### Boucle de biais

- **Événement de biais** (*bias event*) — divergence loggée entre discipline et action.
- Les deux biais documentés :
  - **lock-in** (`lock_in`) — vendre les gagnants trop tôt (*locking-in / mean-reversion*).
  - **FOMO / avidité** (`fomo_greed`) — tenir au-delà du top (*FOMO / greed*).
- **Résisté** (`resisted`) — discipline suivie sous tension ; le moment à haute valeur.
- **Coût du biais / valeur de la discipline** (*cost of bias / value of discipline*) — le compteur bidirectionnel : somme signée des deltas contrefactuels.

### État de canal d'instrumentation

Lexique canonique pour décrire l'état d'un canal qui pourrait émettre des candidats biais (ou prédictions). Trois états mutuellement exclusifs ; un canal en est exactement un à un instant donné. Aucune surface ne réinvente d'autre vocabulaire.

- **actif** (*active*) — canal câblé et opérationnel. Peut émettre. Comptage à 0 lit littéralement « actif mais aucun événement qualifiant ».
- **en veille (par décision)** (*dormant by decision*) — canal câblé mais désactivé par choix explicite, documenté. Exige toujours une **raison** (le confound contextuel : phase, donnée manquante, gel délibéré) et une **condition de réactivation** (le seuil ou flag qui le rallume). Le « par décision » est obligatoire pour distinguer d'un canal qui ne tourne plus par bug.
- **non instrumenté** (*not instrumented*) — chemin existe en concept (ADR / roadmap) mais n'a pas été livré. N'implique aucune imminence ; nomme **le chemin prévu** (ex. ADR, surface, Sprint) pour rester auditable.

Règle d'affichage : un compteur à 0 sans état de canal lit faux. Toute surface qui affiche « 0 candidat » nomme l'état du canal qui produit ce zéro.

---

## Désambiguïsations figées

Deux termes du champ se chevauchent ; tranché ici, **ne plus les recroiser** :

- **« résolution »** = uniquement l'événement qui résout une prédiction. La composante du Brier que la littérature nomme parfois *resolution* s'appelle ici **discrimination**.
- **« fiabilité »** = uniquement la composante calibration du Brier (+ le diagramme). Le sens « le bot tourne-t-il » se dit **disponibilité / uptime**, jamais « fiabilité ».

---

## Règles transversales

1. **Toujours probabiliste** : jamais « Buy / Sell », jamais binaire.
2. **Pas de métaphore-marque dans les termes techniques** (voir couche 1).
3. **Les enums de statut restent en lowercase_snake_case** (cf. `CONVENTIONS.md`).

---

## Politique d'application (règle « type quand tu touches »)

Pas de grand sweep du code existant. Conforme le **code neuf** au glossaire systématiquement. Corrige l'**ancien** quand tu le touches naturellement (rule rape par effet de bord, pas par campagne).

Un sweep complet maintenant = du risque pour zéro gain pendant l'observation pré-10/06. Les anciens termes mal alignés (ex. usage historique de « résolution » au sens Brier dans certains commentaires) se rectifient au fur et à mesure.

---

**Figé v1.0.** Toute évolution = bump de version + note de ce qui change.
