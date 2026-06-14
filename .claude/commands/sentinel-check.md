---
description: Fact-check Bigdata.com pré-pose sentinelles (doctrine OBLIGATOIRE) — vérifie qu'aucune ne s'est déjà déclenchée publiquement avant pose
---

# /sentinel-check — Fact-check pré-pose Bigdata.com

**Pourquoi** : memory `feedback_no_probability_anchoring` (session 13/06) — 2/10 sentinelles posées en G2 étaient déjà publiquement déclenchées au moment de la pose. Doctrine : **fact-check Bigdata.com pré-pose OBLIGATOIRE**. Sinon le track-record commence avec un cadeau (sentinelle pre-déclenchée + crédit Brier indu).

**Quand l'invoquer** : juste AVANT toute pose de sentinelles (G2/G3/cure batch). Skip aucun cas, même "evidente". Le coût est de quelques minutes Bigdata.

## Etapes

1. **Inventaire** : lire la liste des sentinelles à poser (généralement fournie dans le prompt, ou dans `scripts/seed_sentinels_<date>.py` draft). Pour chaque sentinelle, identifier :
   - `claim_text` (le texte exact de la prédiction)
   - `claim_type` (event/data/price)
   - `target_date` (deadline)
   - `ticker` si applicable
   - `expected_trigger` (qu'est-ce qui ferait que la prédiction se déclenche)

2. **Pour chaque sentinelle, Bigdata search** (UNE focus par appel, voir MCP Bigdata.com instructions) :
   - Query naturelle reformulant l'event/claim attendu
   - Période adaptée au lookback : si déjà annoncé dans les 30 derniers jours, c'est mort
   - Discipline : language naturel, pas keyword list

3. **Verdict par sentinelle** :
   - **RED FLAG** : event/data déjà publiquement annoncé → NE PAS POSER, retirer du batch
   - **YELLOW** : signaux partiels ou rumeurs → noter, ajuster claim_text si trop vague
   - **GREEN** : aucun signe de déclenchement public → safe to pose

4. **Cross-check** (optionnel mais recommandé) : pour sentinelles ticker-bound, vérifier earnings calendar ou events calendar via `bigdata_events_calendar` (besoin rp_entity_id via `find_securities`).

5. **Report final** au user :
   - Tableau sentinelle → verdict (RED/YELLOW/GREEN)
   - Liste GREEN à conserver pour pose
   - Liste RED + justification (lien Bigdata source)
   - Action recommandée : "pose N green seulement" ou "revoir K yellow"

6. **Update doc** si applicable : si RED trouvée, noter dans SESSION_STATE et dans le seed script (commentaire #SKIPPED_BY_SENTINEL_CHECK + URL source).

## Anti-patterns

- ❌ Skip Bigdata "parce que c'est évident pas encore arrivé" → c'est exactement le mode où on cadeauise
- ❌ Mix multi-topics dans une seule query Bigdata → split obligatoire (cf MCP instructions)
- ❌ Inventer une date specific dans la query si user a dit "récemment" → préserver wording user
- ❌ Poser RED sentinelle même "petite" → corrompt la track record dès le départ

## Reference

- Doctrine : memory `feedback_no_probability_anchoring` (4 cas distincts, amendée 13/06)
- Cas fondateur : G2 cure 13/06 (`scripts/seed_sentinels_2026-06-13.py`)
- MCP : `mcp__claude_ai_Bigdata_com__bigdata_search` + `bigdata_events_calendar`
- Branding output : "Bigdata.com" + lien https://bigdata.com (MCP instructions)
