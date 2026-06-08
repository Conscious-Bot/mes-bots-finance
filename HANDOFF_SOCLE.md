# Handoff SOCLE — la fondation données (urgent, avant tout cornerstone book-facing)

> Le socle est cassé *maintenant* (eur_value figé J-15, incohérence 0,5× vs 1,80×, deux chemins de valorisation) et le cornerstone (gouverneur, position-card, fragilité) est sur le point d'atterrir dessus. **On le pose AVANT que son poids ne tombe dessus.** Consolide `OPERATIONAL_READINESS` (base_health) + la discussion structure-données. Exécution ordonnée par dépendance. Rien de spéculatif — que de la plomberie de grounding.

## Ordre (dépendance dure)

```
S0 (parallèle, immédiat, IRRÉVERSIBLE) : OTS anchor cron live
S1 (keystone)                          : prices.get() → triple M1 + price_history/fx_history + gate CI yfinance
S2 (dépend S1)                         : migration positions (tuer eur_value-dans-notes) + value_eur() dérivée
S3 (dépend S1+S2)                      : base_health vert sur Positions-vérité + Fraîcheur
```

---

## S0 — OTS anchor opérationnel (fais-le EN PREMIER, c'est minuscule et irréversible)

La provabilité est le seul actif strictement gaté par le temps : chaque jour de prédictions sans ancrage est un jour de track-record non-prouvable *pour toujours*. La chaîne existe ; il manque le cron.

- Vérifier `scripts/integrity_anchor.sh` (déjà écrit) : `ots stamp` du ledger + commit + push.
- **Wire en cron daily** (APScheduler ou crontab). Lancer **une fois maintenant à la main** → la tête de chaîne courante ancre tout l'historique jusqu'à aujourd'hui.
- **DoD S0** : un `.ots` existe pour le ledger courant, committé. `ots verify` (différé, ~quelques heures pour la confirmation Bitcoin).
- *Demi-heure de travail, valeur irréversible. Ne le repousse pas.*

## S1 — `prices.get()` retourne le triple M1 (le keystone : tout lit les prix par ici)

```python
# shared/prices.py
def get(ticker: str) -> PriceQuote:        # JAMAIS un float nu
    # PriceQuote = (price_native: float, currency: str, asof: str, source: str)
    # fetch throttlé → APPEND price_history → retourne le triple
def fx(base: str, quote: str) -> FxQuote:  # (rate, asof, source)
```

Tables append-only (servent fraîcheur ET attribution future) :
```sql
CREATE TABLE price_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticker TEXT NOT NULL, asof TEXT NOT NULL,
  price_native REAL NOT NULL, currency TEXT NOT NULL, source TEXT NOT NULL);
CREATE INDEX idx_px_ticker_asof ON price_history(ticker, asof DESC);
CREATE TABLE fx_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  base TEXT NOT NULL, quote TEXT NOT NULL, rate REAL NOT NULL,
  asof TEXT NOT NULL, source TEXT NOT NULL);
```

Gate CI (rend le single-source réel — tue le SPOF des 19 bypass) :
```bash
# yfinance / yf. hors shared/prices.py = build rouge (même niveau que la gate sqlite)
rg -n 'import yfinance|yfinance\.|yf\.' --glob '!shared/prices.py' bot shared intelligence dashboard && exit 1 || exit 0
```

SLA fraîcheur déclaratif (`config/freshness.yaml`, L17) :
```yaml
price: { green_sec: 900, amber_sec: 3600 }   # 15min / 1h
fx:    { green_sec: 3600, amber_sec: 14400 }
```

## S2 — Migration positions : tuer `eur_value`-dans-`notes`, dériver la valeur live

Principe : **stocke les inputs datés, dérive les outputs.** Ne stocke JAMAIS une valeur fonction d'un prix.

```sql
ALTER TABLE positions ADD COLUMN avg_cost_ccy TEXT;     -- devise du PRU
-- notes redevient texte libre. Script one-shot : retirer eur_value=/pru=/qty= des notes existants.
-- NE PAS ajouter market_value_eur (c'est dérivé).
```

Fonction de valorisation (pas une colonne) :
```python
# shared/book.py (ou positions)
def value_eur(position) -> Valuation:
    # Valuation = (value_eur, price_native, price_asof, fx_rate, fx_asof,
    #              effective_asof = min(price_asof, fx_asof), staleness)
    px = prices.get(position.ticker)          # triple S1
    fx = prices.fx(px.currency, "EUR")
    return qty * px.price_native * fx.rate, effective_asof, staleness   # dérivé MAINTENANT
```

Dashboard / governor / card lisent **`value_eur()`**, jamais `notes`. Une seule vérité par grandeur (M1).

## S3 — `base_health.py` vert sur les deux ROUGES

```python
# scripts/base_health.py — exit non-zéro si un RED
checks = {
  "Positions vérité": all(no eur_value in notes; toute ligne ouverte a avg_cost_ccy;
                          value_eur() dérive de price_history, pas de notes),
  "Fraîcheur data":   prices.get retourne le triple; 0 yfinance hors prices.py (gate);
                      as-of le plus vieux du book < SLA amber,
  "Chaîne intègre":   verify_chain OK + dernier ancrage OTS < 25h (lien S0),
}
# GREEN/AMBER/RED + raison une ligne par dim.
```

---

## Seams à vérifier (verify-before-patch, AVANT de patcher)

- `shared/prices.py` : forme actuelle (`_cached_price_eur`, `_PX_CACHE`, `_PX_TTL`) — `get()` retourne un float aujourd'hui ; les 19 sites de bypass yfinance à rapatrier.
- `positions` table : confirmer les colonnes + où `eur_value=`/`pru=`/`qty=` sont écrits dans `notes` (le parsing regex à tuer).
- `scripts/integrity_anchor.sh` : confirmer qu'il tourne (`ots` installé ? push configuré ?) — le cron est-il wiré ou juste le script existe ?
- Tout consommateur actuel de `eur_value` (dashboard, governor, factor_exposures) : les rerouter vers `value_eur()`.

## Tests verrouillants

- `prices.get()` retourne le triple, jamais un float (assert sur le type).
- **grep gate** : aucun parsing `eur_value=` dans `notes` nulle part (build rouge).
- `value_eur()` dérive du dernier `price_history`, pas de `notes` (assert).
- gate yfinance hors `prices.py` = build rouge.
- `base_health` : fixture stale → RED ; fixture propre → GREEN (transition testable).
- S0 : l'ancrage produit un reçu `.ots` + ledger committé (assert).

## Definition of Done (le socle est posé)

1. **`base_health` vert** sur « Positions vérité » ET « Fraîcheur data ».
2. **`prices.get()` retourne le triple** partout ; gate yfinance active.
3. **`eur_value`-dans-`notes` mort** ; valeur dérivée live, une seule source.
4. **OTS anchor a tourné au moins une fois** (tête de chaîne ancrée).

> Tant que ces 4 ne sont pas verts, **on ne ship aucune partie book-facing du cornerstone** (gouverneur, position-card, fragilité) — elles liraient une base cassée et steeraient faux avec assurance. Le socle d'abord, le poids ensuite.
