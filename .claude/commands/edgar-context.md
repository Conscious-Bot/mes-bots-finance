---
description: Pull 10-Q context (financials snapshot + Risk Factors + income statement) pour thesis review d'un ticker
---

# /edgar-context — 10-Q context pour thesis review

**Pourquoi** : `shared/edgar.py` couvre Form 4 + 8-K + insider clusters mais PAS le contenu 10-Q. Quand tu prepares/reviews une thesis sur un ticker, le 10-Q est la source primaire pour :
- Risk Factors (Item 1A) — risques nouveaux materiels declares par la company
- Financials snapshot (revenue, net income, total assets)
- Sections disponibles pour drill-down (Items 1-8)

`shared/edgar_client.py` wraps edgartools pour ces 3 angles, value-add net new.

**Quand l'invoquer** :
- Avant ouverture position (thesis prep) : lire Risk Factors pour identifier risques connus
- Apres release 10-Q d'une position (cron event ?) : diff vs Risk Factors precedent
- Sanity-check : verifier que yfinance .info financials matchent SEC declaratif

## Usage

```
/edgar-context AAPL
/edgar-context NVDA
```

## Etapes

1. **Validate ticker** : check existe dans la DB book ou watchlist. Si pas, demander confirm.

2. **Fetch 10-Q context** :
   ```python
   from shared.edgar_client import thesis_enrichment
   data = thesis_enrichment(ticker)
   ```
   3 sections : `tenq_context` (snapshot 729-2000 chars), `risk_factors_10q` (jusqu'a 6000 chars), `income_statement_10q` (preview tabulaire).

3. **Surface au user** :
   - **Header** : filing_date + accession (lien SEC : https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-','')}/)
   - **Snapshot** : tenq_context (Revenue, Net Income, Total Assets)
   - **Risk Factors** : si > 1000 chars = risques materiels declares (lire attentif), si < 500 chars = "no material changes" (low signal)
   - **Income statement** : preview tabulaire (3 derniers periods si dispo)

4. **Cross-checks** (optionnel mais valeur) :
   - Cas `risk_factors_10q.text_chars_full > 10k` : signaler "10-Q avec risk factors materiellement etoffes — investigation requise"
   - Cas tenq_context contient new section nom inhabituel : surfacer (e.g. "Cybersecurity Incidents")

5. **Update memory** (si finding non-trivial) : ajouter ligne tail SESSION_STATE.md "Thesis review {TICKER} 10-Q : <finding court>".

## Anti-patterns

- ❌ Re-fetch 10-Q every minute → SEC rate limit 10 req/s. Cache en mémoire 1h pour repeat queries
- ❌ Truncate Risk Factors trop court (< 1000 chars) → perd les changes materiels
- ❌ Considerer "no material changes" comme rien à voir → c'est une déclaration explicite, à noter
- ❌ Ignorer le filing_date → un 10-Q stale 6 mois est moins pertinent qu'un fresh

## Reference

- Wrapper : `shared/edgar_client.py` (edgartools-based, MIT)
- API doc : https://edgartools.readthedocs.io/
- Complement : `shared/edgar.py` existant pour Form 4 + 8-K + insider clusters
- Doctrine : memory `business_path_6_acted` (discipline mecanisee, contexte > signal)
