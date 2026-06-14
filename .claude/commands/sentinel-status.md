---
description: État courant des sentinelles pending — count, deadlines approchantes, claim_type breakdown, alertes deadline < 30j
---

# /sentinel-status — État pending sentinelles

**Pourquoi** : 10 sentinelles posées 13/06/2026 chantier #150 G2 (deadlines 199-564 jours). Audit régulier pour détecter (a) deadlines approchantes (action requise), (b) sentinelles déclenchées dans le réel (à résoudre), (c) drift entre intention pose et état réel.

**Quand l'invoquer** :
- Trigger hebdomadaire auto (launchd plist Mac → Telegram alert dimanche)
- On-demand quand curieux de l'état chantier #150

## Etapes

1. **Query DB** : récupérer toutes les sentinelles `origin='manual' AND outcome IS NULL` :
   ```python
   import sqlite3
   from datetime import datetime
   conn = sqlite3.connect('data/bot.db')
   cur = conn.execute('''
       SELECT id, ticker, claim_type, target_date, baseline_date,
              probability_at_creation, scoring_trace_json
       FROM predictions
       WHERE origin='manual' AND outcome IS NULL
       ORDER BY target_date
   ''')
   ```

2. **Compute** pour chaque sentinelle :
   - `days_remaining` = (target_date - today).days
   - `urgency` = RED si <30j, YELLOW si 30-90j, GREEN si >90j
   - `age` = (today - baseline_date).days

3. **Aggregates** :
   - Total pending
   - Distribution par claim_type (event / data / price)
   - Distribution par urgency (RED/YELLOW/GREEN)
   - Sum probabilities (sanity-check vs constraint sum<=1.5 mécanique)
   - Tickers covered vs no-ticker (macro/data sentinelles)

4. **Fact-check Bigdata.com** (memory `feedback_no_probability_anchoring` cure mécanique) :
   Pour chaque sentinelle RED ou YELLOW (deadline <90j), Bigdata search rapide :
   - "Has [claim_text] already occurred publicly?"
   - Si OUI → flag pour résolution immédiate
   - Si NON → status OK

5. **Output tableau** :
   ```
   pid | ticker | type  | deadline   | days | prob | urgency | bigdata_check
   ----+--------+-------+------------+------+------+---------+--------------
   294 |   -    | data  | 2026-12-31 |  199 | 0.70 | YELLOW  | not triggered
   ...
   ```

6. **Alerts** au user :
   - RED count + actions requises (résolution / extension / archive)
   - Sentinelles trouvées déclenchées via Bigdata (à résoudre dans la DB)
   - Sum probs hors mécanique (sanity-check)

7. **Update SESSION_STATE** : ajouter une ligne dans le tail si findings non-triviaux (sentinelle déclenchée, deadline RED).

## Anti-patterns

- ❌ Re-tirer probabilité (memory `feedback_no_probability_anchoring` : 4 cas distincts, jamais re-anchor Claude-side)
- ❌ Resolve sentinelles silently dans la DB → toujours commit explicite avec hash trace
- ❌ Ignorer sum_probs > 1.5 mécanique sans investiguer (peut être bug pose)

## Reference

- Memory : `feedback_no_probability_anchoring`, `barrier_held_without_human_2026-06-13`
- DB : `data/bot.db` table `predictions`
- Pose initiale : `scripts/seed_sentinels_2026-06-13.py` (pids 294-303)
- Doctrine : Path Q1 chantier #150 (research_brief handler Bigdata Q1 2027)
