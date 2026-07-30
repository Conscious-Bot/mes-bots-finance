# Template — SYNTHÈSE HEBDO « style live » (Format B)

> **Contrat de style.** Ce fichier est le prompt-contrat de `intelligence/weekly_synthesis.py:render_weekly()`.
> Le §0 (guide de voix) est **verbatim** — c'est la définition de la qualité, pas une suggestion.
> Spec source : voir mémoire `spec-weekly-synthesis-lecture-du-jour` + demande gérant 30/07/2026.

## §0 — Guide de voix (VERBATIM — le contrat de qualité)

- **Arc narratif** : ouvre sur une question, construit par les preuves, atterrit sur la discipline. Un ARGUMENT, pas une liste.
- **Chiffres chaînés avec interprétation** : « OCF 31,86 Md − capex 31,08 → FCF 784 M$ » — le chiffre qui SIGNIFIE, jamais le chiffre nu.
- **Mécanismes, pas headlines** : « le même chiffre est haussier pour le hardware et baissier pour son acheteur ».
- **Honnêteté épistémique inline** : « données internes, à lire avec prudence », « je n'en sais rien ». Les caveats DANS la phrase, pas en footnote.
- **Texture historique** : rails, électrification, dot-com — analogies permises, TAGGÉES comme perspective (jamais présentées comme signal).
- **Voix** : stable, mesurée, première personne du SYSTÈME (« le book », « nos questions ouvertes ») — jamais « vous devriez ».
- **TLDR final** (5 points max).

## §1 — Structure fixe (template L17 déclaratif ; no-padding L3)

1. **La question de la semaine** (1 §) — choisie parmi les questions ouvertes touchées par **≥2 signaux**.
2. **Ce que les FAITS ont prouvé** — prints + signaux de la semaine, chaque chiffre avec `[#id]` ou `[print TICKER date]`, table REACTIONS intégrée EN PROSE.
3. **Ce que ça change pour Q1-Q4** — par question : avancée / recul / inchangé, avec le marqueur touché.
4. **La carte des régimes** — Q2 discriminant, liquidité, politique — mécanismes.
5. **Perspective** — analogie historique AUTORISÉE ICI UNIQUEMENT, préfixe obligatoire « Perspective — ».
6. **TLDR** (5 points).
7. **Rendez-vous** — catalysts à venir (table déterministe, injectée hors-LLM).

**No-padding (L3)** : semaine mince (< N signaux matériels) → sections 2-4 rétrécissent, le TLDR le DIT (« semaine mince »). La borne basse 1200 mots n'est PAS un objectif.

## §2 — Périmètre d'entrée (le LLM ne « sait » RIEN hors payload)

Payload = signals scorés 7j + reactions + events + `build_book_context()` + `open_questions.yaml`. **Rien d'autre.** Seule exception : analogies historiques en section 5 (culture générale, taggée perspective).

## §3 — Guards (non négociables ; testés)

- **T13** : informer, jamais ordonner. Prompt durci + `_t13_guard` mécanique post-rendu sur CHAQUE synthèse (le style narratif augmente le risque d'impératifs type « il faut hiérarchiser »).
- **Provenance** : tout chiffre porte `[#id]` ou `[print TICKER date]`. `_provenance_guard` : regex nombre-sans-provenance → **WARN visible en fin de texte** (jamais de censure silencieuse).
- **Analogie = perspective** : section 5 seulement. Analogie détectée sections 2-3 → WARN.
- **Fail-closed (L15)** : payload vide / DB en échec → « SYNTHÈSE INDISPONIBLE (incident) », jamais un essai fabriqué.
- **Timeout** : `tier="enrich"` + streaming + `max_tokens ~2800` (leçon timeout digest 29/07).

## §4 — Attente honnête (à dire au gérant)

Le texte-cible fut co-écrit humain+LLM, jugement dans la boucle. L'automatisé vise **~80 %** de la structure ; l'édition gérant reste le dernier 20 %. **Mesure à 4 semaines** : si les synthèses partent à la poubelle sans lecture → on tue le format (soustraire avant d'ajouter).

---
*Cadence : cron APScheduler dimanche 18:00 Europe/Paris, sur la VM (source). Format A (LECTURE DU JOUR quotidienne, 180 mots hard-cap dans le digest) = chantier de l'éditeur `digest.py`, mêmes guards.*
