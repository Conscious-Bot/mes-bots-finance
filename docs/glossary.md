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
- **Résisté** (`resisted`) — discipline suivie sous tension ; le moment à haute valeur.
- **Coût du biais / valeur de la discipline** (*cost of bias / value of discipline*) — le compteur bidirectionnel : somme signée des deltas contrefactuels.

#### Biais documentés — désambiguïsation canonique

##### `lock_in` — vendre les gagnants trop tôt

**Biais #1 de PRESAGE, raison d'être de l'instrument.** Pulsion de sécuriser un gain qui court encore : prise de profit prématurée, mean-reversion réflexe sur un winner, fermeture par confort psychologique plutôt que par invalidation de thèse.

**État d'instrumentation : mécanisé** (depuis v2.c.6, 01/06/2026). Surface 2 ADR-010 §2 livrée : hook dans `shared.positions.add_sell` après commit DB (cf [LESSONS L7](LESSONS.md)) → `intelligence.lock_in_detector.detect_winner_sell` ouvre un candidat `bias_event` si gate v1 satisfait (`pnl_pct ≥ 0.15 AND conviction_at_sell ≥ 3`). Résolution canonique à +30j, observations longues (+60j, +90j) ajoutées par cron weekly `weekly_bias_event_backfill_observations_job` en append-only dans `resolution_json.observations[]` (architecture B3 : scoring immuable + enrichissement séparé). Conviction lue **at sell time** (revisits comptés), pas at creation.

**Définition gate v1 (absolu, pédagogie ship simple + log dimensions pour v2 data-driven post-90j)** — 4 dimensions logguées par candidat (`pnl_pct_at_sell`, `conviction_at_sell`, `pnl_pct_progress` = pnl / target, `time_progress` = days_held / horizon). v2 data-driven attendue après 20-30 candidats résolus : prédicat relatif `pnl_pct_progress < 0.6 AND time_progress < 0.5`.

**Bypass paths hors-scope documentés** : `scripts/import_positions_legacy.py`, `scripts/refresh_positions_2026_05_23.py`, `shared/sql_observability.py` ne passent pas par `positions.add_sell` donc le détecteur ne fire pas. Acceptable pour des opérations exceptionnelles (backfill, refresh, audit).

##### `fomo_greed` — l'enum technique (acception large)

Mécaniquement : « ne pas avoir réduit / sorti la position quand la discipline le disait ». L'enum couvre donc :
- **laisser courir un runner** au-delà de son cap (canal `over_cap`),
- **tenir une thèse cassée** au lieu d'en sortir (canal `kill_criteria`) — psychologiquement de l'aversion à la perte, rangée v1 sous `fomo_greed` faute d'un enum dédié.

**État d'instrumentation : mécanisé sur 2 canaux** — `kill_criteria` actif, `over_cap` en veille (par décision) phase construction.

##### Biais #2 historique — anti-FOMO crypto aux tops

Cas spécifique documenté empiriquement : ne pas vendre crypto sur signaux de top d'indicateurs. **Distinct de l'enum `fomo_greed` ci-dessus** : c'est un *cas* (instrument + signal-de-top) que l'enum large n'instrumente pas directement. Touché incidemment par `over_cap` si une crypto déborde son cap, mais aucun canal n'observe le signal-de-top.

**État d'instrumentation : dormant ortho.** Stock-only depuis 26/05/2026 = 0 crypto en book. Code backend (regime CRYPTO-TOP-ZONE, risk_manager, self_loop) préservé, réactivable si re-exposition crypto.

**Règle d'écriture** : ne pas écrire « biais #2 mécanisé » — c'est une fausse équivalence avec l'enum. Écrire soit `fomo_greed (enum large) mécanisé sur 2 canaux`, soit `biais #2 historique crypto-tops, dormant ortho`. Les deux ne se substituent pas.

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
