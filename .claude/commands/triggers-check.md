---
description: Tour systématique invalidation_triggers méthode #135 sur 26 thèses actives — Bigdata.com fact-check par conviction décroissante + rewrite measurables
---

# /triggers-check — Tour systématique invalidation_triggers (hebdomadaire)

**Pourquoi** : session 17/06/2026 a établi le rituel — test systématique des 90 triggers sur 26 thèses actives via Bigdata.com méthode #135 (3 colonnes : instrument / ancre externe live / ressenti). Catch les régime shifts AVANT que le marché les price, force la rigueur measurable (criteria flou → seuils chiffrés + baselines), détecte les violations doctrine (price-only, audience off-target, terminologie inexistante).

**Quand l'invoquer** : chaque lundi matin (rappel launchd `com.olivier.presage-weekly-triggers`), OU avant toute action portfolio (lock_in / over_cap / rebalance) majeure, OU après earnings call majeur d'un anchor (NVDA/MSFT/META/TSM/AMZN).

**Cadence** : full 26 thèses chaque semaine. ~45 min - 1h30 selon état (devrait décroître à mesure que les triggers deviennent mesurables).

## Étapes

1. **Inventaire** : récupère liste de toutes les thèses `status='active'` ordonnées conviction DESC :
   ```python
   import sqlite3, json
   from shared.storage import DB_PATH
   cx = sqlite3.connect(DB_PATH)
   rows = cx.execute("SELECT ticker, conviction, invalidation_triggers FROM theses WHERE status='active' ORDER BY conviction DESC, ticker").fetchall()
   ```
   Notebooke le total : 26 thèses, ~90 triggers attendus (varie 2-5 par thèse).

2. **Par ticker (conviction décroissante c5 → c4 → c3 → c2)** :

   a. **Fetch triggers actuels** depuis DB.

   b. **Bigdata.com queries** (2-3 par ticker, UNE focus par query, language naturel) :
      - Earnings Q1 2026 / dernière période disponible : revenue/segment/margin/guidance
      - Question spécifique à 1-2 triggers les plus à risque ("le pivot fondateur")
      - Industrie context si pertinent (e.g., concurrent dynamics, regulatory)
      - **N'INVENTE PAS de dates spécifiques** : préserve "Q1 2026", "récemment", "dernier quarter"
      - Discipline : éviter mix multi-topics dans une query

   c. **Pour chaque trigger** :
      - Verdict : **STRONG SAFE / SAFE / AT_RISK monitor / FIRED**
      - Si AT_RISK ou FIRED : justifier avec citation Bigdata.com
      - Si STRONG SAFE opposé MASSIF : noter (anchor structurel)
      - Si wording vague / non-mesurable : **rewrite** avec seuil chiffré + baseline Q1 2026

   d. **Cross-ref check** via `shared.invalidation_triggers.get_trigger_status_per_thesis()` :
      - Si le mécanisme fired une sentinelle résolue côté trigger, **vérifie cohérence avec verdict Bigdata** (cas AVGO #1 16/06 = false-positive S10 corrigé après fact-check)

3. **Rewrites applicable** (si wording vague détecté) :

   ```python
   triggers[idx] = "<NEW wording mesurable avec baseline Q1 2026>"
   cx.execute("UPDATE theses SET invalidation_triggers = ? WHERE ticker = ?", (json.dumps(triggers, ensure_ascii=False), ticker))
   cx.commit()
   ```

   Anti-pattern : **ne PAS introduire de nouveaux codes `S{N}` dans les triggers** (sentinelles fictives = faux positifs cross-ref). Si trigger référence sentinelle, vérifier qu'elle existe dans table predictions.

4. **Doctrine compliance** :
   - **Memory `currency_native_invariant`** : aucun trigger price-only (kill criteria valuation banni). Si rewrite introduit price → fundamental GM/op margin.
   - **Memory `feedback_no_probability_anchoring`** : aucune suggestion de probabilité, criteria binaires mesurables only.
   - **L21 fail-closed** : triggers mesurables avec seuils chiffrés + baselines récentes.

5. **Audit-trace script** : si rewrites appliqués, créer `scripts/trigger_rewrites_<batch>_<date>.py` idempotent (pattern `trigger_rewrites_c5_2026-06-17.py` ou `trigger_rewrites_c4_c3_c2_2026-06-17.py`).

6. **Report final** au user :
   - Tableau : ticker → conviction → n_fired / n_triggers → n_rewrites
   - Highlights : triggers FIRED actuels (action requise), anchors structurels MASSIFS confirmés
   - Side-flags : reanchor candidates (target_full < current px), financial monitors hors-thèse
   - Total : X/Y triggers fired across 26 active theses

7. **Update SESSION_STATE** : append `## Triggers check YYYY-MM-DD` avec sommary.

8. **Commit cumulatif** : `docs(thesis): weekly triggers-check round <date> + rewrites batch`.

## Pattern méthode #135 (3 colonnes)

Pour chaque ticker en cas d'AT_RISK ou trigger ambigu :

| Colonne 1 (Instrument) | Colonne 2 (Ancre externe live) | Colonne 3 (Ressenti) |
|---|---|---|
| current px, conviction, target_partial/full, stop, value | Bigdata.com earnings/news/regulatory dernière période | Validation user (re-anchor / hold / trim / exit) |

## Anti-patterns

- ❌ Skip Bigdata sur thèse "évidente" → c'est exactement où on rate le pivot
- ❌ Rewrite avec criteria vague à nouveau (e.g., "pricing pressure" sans seuil chiffré)
- ❌ Introduire `S{N}` dans triggers (sentinelles fictives = faux positifs cross-ref)
- ❌ Trigger price-only (valuation, P/E forward) — banni par doctrine
- ❌ Audience trigger mal ciblée (e.g., "hyperscaler" pour MP qui sert EV/defense/Apple)
- ❌ Wording terminologique inexistant (e.g., "Sabine Pass Stage 3" qui n'existe pas — c'est CCL)

## Reference

- **Cas fondateur** : session 17/06/2026 — 26 thèses testées, 31 rewrites appliqués, 0/90 fired
- **Audit-trace scripts** : `scripts/trigger_rewrites_c5_2026-06-17.py` + `scripts/trigger_rewrites_c4_c3_c2_2026-06-17.py`
- **Cross-ref module** : `shared/invalidation_triggers.py` (commit `05c8d22` 16/06)
- **launchd** : `com.olivier.presage-weekly-triggers.plist` (lundi 09h)
- **Doctrine memory** : `weekly_triggers_check_ritual.md`, `currency_native_invariant`, `feedback_no_probability_anchoring`
- **MCP** : `mcp__claude_ai_Bigdata_com__bigdata_search` (UNE focus par query, language naturel, ne pas inventer dates)
- **Branding output** : "Bigdata.com" + lien https://bigdata.com (MCP instructions)
