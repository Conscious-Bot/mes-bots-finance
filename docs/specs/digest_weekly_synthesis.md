# SPEC — SYNTHÈSE HEBDO « style live » + LECTURE DU JOUR (v1, 30/07/2026)

> Origine : demande gérant — « j'aimerais que mon digest ressemble plus à ce genre
> de texte » (résumé du live 29/07). Analyse : ce style est un format HEBDOMADAIRE.
> Le forcer en quotidien = padding les jours creux (viole L3 état honnête) + plus
> de surface d'hallucination (viole L15). Architecture retenue : DEUX formats.

## 0. Ce qui fait la qualité du texte-cible (guide de voix, distillé du live)

1. **Arc narratif** : ouvre sur une question, construit par les preuves, atterrit
   sur la discipline. Un ARGUMENT, pas une liste.
2. **Chiffres chaînés avec interprétation** : « OCF 31,86 Md − capex 31,08 →
   FCF 784 M$ » — le chiffre qui SIGNIFIE, jamais le chiffre nu.
3. **Mécanismes, pas headlines** : « le même chiffre est haussier pour le hardware
   et baissier pour son acheteur ».
4. **Honnêteté épistémique inline** : « données internes, à lire avec prudence »,
   « je n'en sais rien ». Les caveats DANS la phrase, pas en footnote.
5. **Texture historique** : rails, électrification, dot-com — analogies permises,
   TAGGÉES comme perspective (jamais présentées comme signal).
6. **Voix stable, mesurée, première personne du SYSTÈME** (« le book », « nos
   questions ouvertes ») — jamais « vous devriez ».
7. **TLDR final** (5 points max).

## 1. FORMAT A — Digest quotidien (existant, upgrade léger « v2.1 »)

Reste terse/extractif (radar). UN ajout :

- **LECTURE DU JOUR** : 1 paragraphe, 120-180 mots MAX, en tête. Le fil narratif
  qui relie les top-signaux du jour aux questions ouvertes (Q1-Q4), mécanisme
  d'abord, chaque chiffre avec provenance [#id]. Jours creux → « Journée sans
  lecture — n signaux mineurs » (L3 : court quand c'est court).
- Chiffres chaînés (règle 2 du guide) dans les annotations top_n existantes.
- AUCUN changement aux sections déterministes (REACTIONS, catalysts, POINTS DE
  DÉCISION) ni aux guards.

## 2. FORMAT B — SYNTHÈSE HEBDO (nouveau)

**Cadence** : cron dimanche 18h (avant l'ouverture asiatique). **Longueur** :
1 200-1 800 mots — MAIS règle no-padding : semaine mince = texte court, la borne
basse n'est pas un objectif (L3).

**Structure fixe** (template L17, déclaratif) :
1. La question de la semaine (1 §, choisie par le LLM parmi les questions
   ouvertes touchées par ≥2 signaux).
2. Ce que les FAITS ont prouvé (prints + signaux de la semaine, chiffres [#id],
   table REACTIONS de la semaine intégrée en prose).
3. Ce que ça change pour Q1-Q4 (par question : avancée / recul / inchangé —
   avec le marqueur touché).
4. La carte des régimes (Q2 discriminant, liquidité, politique — mécanismes).
5. Perspective (analogie historique AUTORISÉE ici, taggée « perspective »).
6. TLDR (5 points).
7. Rendez-vous (catalysts table à venir, déterministe).

**Sources d'entrée** : signals scorés de la semaine (7j) + reactions + events +
book_context() + open_questions.yaml. RIEN d'autre — le LLM ne « sait » rien
que le payload ne contient (analogies historiques exceptées, cf guard 3).

## 3. GUARDS (non négociables, hérités + nouveaux)

1. **T13 intégral** : prompt durci + `_t13_guard` mécanique post-rendu. Le style
   narratif AUGMENTE le risque d'impératifs (« il faut hiérarchiser ») — le test
   T13 tourne sur CHAQUE synthèse. Informer, jamais ordonner.
2. **Provenance** : tout chiffre porte [#id] ou [print TICKER date]. Test
   mécanique : regex nombres-sans-provenance → WARN visible en fin de texte
   (jamais de censure silencieuse).
3. **Analogies = perspective** : section 5 uniquement, préfixe « Perspective — ».
   Interdites dans les sections 2-3 (les faits ne se mélangent pas au décor).
4. **No-padding L3** : si <N signaux matériels dans la semaine, sections 2-4
   rétrécissent, le TLDR le dit (« semaine mince »).
5. **Timeout** : tier="enrich" + streaming + max_tokens dimensionné (~2 800) —
   leçon du timeout digest 29/07.
6. **Fail-closed L15** : payload vide/DB en échec → mail « SYNTHÈSE INDISPONIBLE
   (incident) », jamais un essai fabriqué.

## 4. Implémentation (mission Claude Code)

- `intelligence/weekly_synthesis.py` : `build_weekly_payload()` (signals 7j +
  reactions + events + book_context + open_questions) → `render_weekly()` (prompt
  template) → `_t13_guard` + `_provenance_guard` → mail/fichier.
- Template prompt : `docs/templates/weekly_synthesis_prompt.md` (le guide de voix
  §0 y est VERBATIM — c'est le contrat de style).
- Cron : APScheduler dimanche 18:00 Europe/Paris, sur la VM (source).
- Tests (`tests/test_weekly_synthesis.py`) : T13 sur fixtures avec impératifs ·
  provenance guard (chiffre nu → WARN) · no-padding (payload 1 signal → texte
  court) · fail-closed (payload vide → INDISPONIBLE) · TLDR présent · analogie
  hors section 5 → WARN.
- LECTURE DU JOUR (Format A v2.1) : ajout dans `digest.py` au moment de
  l'enrichissement top_n, 180 mots hard-cap, mêmes guards.

## 5. Attente honnête (à dire au gérant)

Le texte-cible a été co-écrit humain+LLM avec jugement dans la boucle. La version
automatisée visera ~80 % de la structure ; la passe d'édition du gérant reste le
dernier 20 %. On mesure après 4 semaines : si les synthèses partent à la poubelle
sans lecture, on tue le format (règle simplicité — soustraire avant d'ajouter).
