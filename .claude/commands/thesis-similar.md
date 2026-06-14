---
description: RAG-retrieve K thèses passées similaires depuis ton track record (Voyage finance-2 + Chroma local) — miroir disciplinaire
---

# /thesis-similar — RAG sur ton track record

**Pourquoi** : memory `business_path_6_acted` = "wedge = discipline mécanisée pas alpha prédictif". Cet outil mécanise la discipline en miroir : quand tu prépares une thèse, **le système retrieve K thèses passées avec setup ressemblant + leur outcome**. Tu vois ton propre comportement passé sur des situations similaires. Anti-FOMO, anti-lock_in via comparaison historique.

Anti-pattern visé : "je sens que SNOW va monter parce qu'IA narrative" → le RAG sort 5 fois où tu as eu ce sentiment → 3 fois c'était lock_in piège, 2 fois ça a fonctionné. Tu calibres TON track record, pas l'opinion.

## Usage

```
/thesis-similar SNOW IA infrastructure rally entry conv c3
/thesis-similar AAPL hardware refresh cycle horizon 90j
/thesis-similar macro rate cut 50bps semi sector
```

Free-form text. Le système embed via Voyage `voyage-finance-2` (32k context, finance-domain trained), retrieve K=5 par cosine similarity dans `data/thesis_chroma/` (Chroma SQLite local).

## Etapes

1. **Validate setup** : `from shared.thesis_library import collection_stats ; print(collection_stats())`. Si `count=0` → demander bootstrap.

2. **Bootstrap (one-shot first call)** :
   ```python
   from shared.thesis_library import bootstrap_from_db
   bootstrap_from_db()  # indexe toutes predictions (manual + auto)
   ```
   Output : `{indexed: N, skipped: M, total_rows: T}`. Coût Voyage : ~$0.001 lifetime pour 300 theses.

3. **Query** :
   ```python
   from shared.thesis_library import find_similar
   results = find_similar(query_text, k=5, filter_meta={"outcome": "loss"})  # optionnel filter
   ```
   Returns list[dict] avec `similarity`, `metadata.pid`, `metadata.ticker`, `metadata.outcome`.

4. **Report au user** :
   - Tableau : sim score, pid, ticker, outcome, created_at, claim_type
   - **Pattern analysis** : si K/5 résultats ont outcome=loss → "Sur des setups similaires, ton historique = N/K losses. Calibration : reduce conviction or skip."
   - **Outcome distribution** : breakdown gain/loss/pending pour mesurer le edge réel de TOI sur ce setup
   - Highlight si toutes les K theses ont même bias (e.g. all bull) → potential confirmation bias

5. **Update memory** si finding non-trivial : ajouter ligne tail SESSION_STATE.md "Thesis similar query <text> : <K/K loss pattern>".

## Filter examples

```python
find_similar(text, k=5, filter_meta={"ticker": "NVDA"})  # only NVDA history
find_similar(text, k=10, filter_meta={"outcome": "loss"})  # only past losses
find_similar(text, k=5, filter_meta={"origin": "manual"})  # only manual sentinels
```

## Anti-patterns

- ❌ Trust RAG comme prédiction. C'est miroir disciplinaire, pas oracle.
- ❌ Skip si K<5 résultats → low data = utile, signale que c'est un setup inédit (à investiguer)
- ❌ Re-embed même text à chaque query → upsert utilise même id pour overwrite, mais query embed à chaque appel (intentional, paramètres peuvent varier)
- ❌ Filtrer trop agressivement → can retourner 0 résultats. Élargir si stricte filter vide.

## Doctrine fit

- ✅ Memory `feedback_no_probability_anchoring` : RAG ne suggère pas de chiffre, juste contexte historique
- ✅ Memory `feedback_instrumentation_vs_decision` : instrument N=300 theses (sample suffisant)
- ✅ Memory `barrier_held_without_human` : système peut surfacer pattern même contre user bias

## Reference

- Wrapper : `shared/thesis_library.py`
- Voyage docs : https://docs.voyageai.com/
- Chroma local : `data/thesis_chroma/` (SQLite-backed, no remote)
- Bootstrap source : DB `predictions` table
