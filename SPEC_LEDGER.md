# Spec — Ledger transactions append-only + positions VIEW dérivée

> Extension de `SPEC_MONEY_INVARIANT` à la **couche transaction**. Le money invariant a typé les baselines (Datum[Monetary], write-once entry) ; il n'a jamais empêché qu'`avg_cost_eur` / `realized_pnl` / `qty` se désynchronisent du broker après une vente partielle, parce que ce sont des **champs dérivés-stockés mutés à la main**. Cette spec rend **structurellement impossible** la classe de bug *« le broker import met à jour qty cosmétiquement mais ne recalcule jamais cost basis / realized_pnl »* — découverte 09/06 nuit++ sur 5 positions (SK Hynix, ALAB, MU, CCJ, 6920.T). Hérite de `SPEC_SOCLE` (Datum + derive), `SPEC_MONEY_INVARIANT` (M1 baselines, write-once entry), `QUALITY_BAR` (M1), `LESSONS` L27 (cohérence mécanique > vigilance).

## 0. La maladie, nommée une seule fois

Tous ces symptômes sont **un seul bug** :

| Symptôme | Champ pourri | Cause racine |
|---|---|---|
| SK Hynix panneau "+37% > target +23%" | `avg_cost_eur=1085` (vs réel 1060) | broker import a réduit `qty` sans recalcul `avg_cost` post-vente partielle |
| `realized_pnl=77.88` ≠ ground truth 98.37 | `realized_pnl` stocké | aucun handler ne recalcule sur événement vente |
| Note `qty_aligned_to_broker_2026-05-29` | `qty` patché à la main | symptôme du pansement humain, pas une cure |
| 5/26 positions désynchronisées | tous les champs dérivés | toute vente partielle non-Brier-loggée pourrit silencieusement |

> **La maladie : `avg_cost_eur`, `realized_pnl`, `qty` sont des dérivés stockés qui pourrissent parce qu'aucun handler ne les recalcule sur l'événement déclencheur (vente partielle).** C'est exactement `price_asof` figé et `eur_value`-dans-notes qu'on a tués. La cure n'est PAS un `partial_close handler` (pansement à ne-pas-oublier) — c'est **transformer ces champs en vues dérivées d'un ledger immuable**. Store-inputs-derive-outputs, L27 socle appliqué à la couche transaction. Cf `CANONICAL_MAP.md` §2 : *transactions = record immuable, positions = état dérivé*.

## 1. Cure #1 — `transactions` est append-only avec 3 gardes structurelles

```sql
CREATE TABLE transactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    side            TEXT NOT NULL,           -- 'BUY' | 'SELL' (V0). TEXT, pas ENUM : extensible 'SPLIT'/'ADJUST' (futur)
    qty             REAL NOT NULL CHECK(qty > 0),
    price_native    REAL NOT NULL,           -- prix d'exécution brut, datum pur (frais EXCLUS)
    fees_native     REAL NOT NULL DEFAULT 0, -- frais broker séparés (capitalisés au PRU en BUY, déduits du proceeds en SELL)
    currency        TEXT NOT NULL,           -- devise de cote (KRW / JPY / EUR / USD), source = prices.get(ticker).currency
    fx_at_trade     REAL NOT NULL,           -- currency → EUR au jour J. 1.0 si EUR.
    fx_is_derived   INTEGER NOT NULL DEFAULT 0,  -- 0 = back-out du EUR débité TR (autoritatif), 1 = fallback fx_history (marqué)
    trade_date      TEXT NOT NULL,
    broker_trade_id TEXT UNIQUE,             -- identifiant TR (capture OBLIGATOIRE pour ingestion broker), NULL pour anchors/manual
    source          TEXT NOT NULL,           -- 'TR_export_<date>' | 'anchor_snapshot_<date>' | 'manual_<context>'
    is_anchor       INTEGER NOT NULL DEFAULT 0,  -- 1 = trade synthétique d'ancrage back-fill
    notes           TEXT
);

-- Garde #1 : write-once via UPDATE-impossible
CREATE TRIGGER transactions_writeonce_update BEFORE UPDATE ON transactions
BEGIN
    SELECT RAISE(ABORT, 'transactions append-only : UPDATE interdit. Corriger via entrée compensatoire (ADJUST).');
END;

-- Garde #2 : write-once via DELETE-impossible
CREATE TRIGGER transactions_writeonce_delete BEFORE DELETE ON transactions
BEGIN
    SELECT RAISE(ABORT, 'transactions append-only : DELETE interdit. Corriger via entrée compensatoire (ADJUST).');
END;

-- Garde #3 : idempotence structurelle via broker_trade_id UNIQUE (déjà déclarée colonne). Re-INSERT même trade TR → DB reject.
```

Les 3 gardes sont **structurelles** (DB), pas applicatives (code) : impossible de les oublier, conformes L27.

## 1.5 La frontière d'ingestion — un trade entre par broker_trade_id, ou ne naît pas

> Sans `broker_trade_id` capturé, le dedup retombe sur du composite (ticker, date, side, qty, price) qui est fragile (deux trades légitimes identiques le même jour collisionnent → dédupliqués à tort, donnée perdue). Le `broker_trade_id` UNIQUE est la SEULE défense structurelle d'idempotence.

1. **TR export** doit exposer un identifiant unique par exécution (ordre/fill ID). Capture obligatoire. Si TR ne l'expose pas via une voie quelconque (CSV, API, UI export) → KNOWN-GAP documenté à l'ingestion, dedup composite fallback bruyant (warn explicite).
2. **Anchors** (back-fill 21 propres) et trades **manuels** (corrections rares) ont `broker_trade_id=NULL` par construction — UNIQUE permet plusieurs NULL en SQLite.
3. **`fx_at_trade`** : préférence absolue = **back-out depuis l'EUR débité TR** (`fx = eur_debited / (qty × price_native)`). C'est le fx réellement appliqué, spread TR inclus. Si EUR débité indisponible → fallback `fx_history@trade_date` avec `fx_is_derived=1` (provenance honnête).
4. **`currency` dérivée du ticker via `prices.get(ticker).currency`**, jamais saisie ni supposée EUR. Source unique cohérente avec money invariant §1.5.

## 2. Cure #2 — `positions` devient une VUE dérivée + `positions_meta` slim pour le déclaré

### 2.1 Séparation dérivé / déclaré (verify-before-patch fait 09/06 nuit++)

26 colonnes `positions` énumérées. Classification :

| Type | Colonnes | Vit dans |
|---|---|---|
| **Dérivées** (19) | `qty`, `avg_cost`, `avg_cost_eur`, `avg_cost_native`, `avg_cost_currency`, `avg_cost_value`, `avg_cost_asof`, `fx_at_purchase`, `realized_pnl`, `opened_at`, `last_updated`, `last_price_native`, `last_price_eur`, `last_price_currency`, `price_asof`, `price_source`, `fx_rate_to_eur`, `fx_asof`, `fx_source` | VIEW `positions` (calc depuis `transactions` + `prices.get`) |
| **Déclarées** (5) | `ticker`, `notes`, `status`, `account`, `wrapper` | TABLE `positions_meta` (slim, jointe à la VUE) |

`status` reste **déclaré** (label sémantique : `active`/`superseded`/`review`/`closed`), pas dérivé de `qty=0` qui est un fait. Ne pas conflater fait et label.

### 2.2 La VUE

```sql
CREATE TABLE positions_meta (
    ticker  TEXT PRIMARY KEY,
    notes   TEXT,
    status  TEXT,
    account TEXT,
    wrapper TEXT
);

CREATE VIEW positions AS
WITH buys AS (
    SELECT ticker,
           SUM(qty)                                                            AS sum_qty_buy,
           SUM(qty * price_native + fees_native)                               AS cost_native_total,
           SUM(qty * price_native * fx_at_trade + fees_native * fx_at_trade)   AS cost_eur_total,
           MIN(trade_date)                                                     AS opened_at
    FROM transactions
    WHERE side='BUY'
    GROUP BY ticker
),
sells AS (
    SELECT s.ticker,
           SUM(s.qty)                                                          AS sum_qty_sell,
           SUM(
               s.qty * s.price_native * s.fx_at_trade
             - s.fees_native * s.fx_at_trade
             - s.qty * (
                 SELECT SUM(b.qty * b.price_native * b.fx_at_trade + b.fees_native * b.fx_at_trade)
                      / SUM(b.qty)
                 FROM transactions b
                 WHERE b.ticker = s.ticker
                   AND b.side = 'BUY'
                   AND b.trade_date < s.trade_date
               )
           )                                                                    AS realized_pnl_eur
    FROM transactions s
    WHERE s.side='SELL'
    GROUP BY s.ticker
)
SELECT m.ticker,
       COALESCE(b.sum_qty_buy, 0) - COALESCE(s.sum_qty_sell, 0)            AS qty,
       b.cost_native_total / NULLIF(b.sum_qty_buy, 0)                      AS pru_native,
       b.cost_eur_total    / NULLIF(b.sum_qty_buy, 0)                      AS pru_eur,
       COALESCE(s.realized_pnl_eur, 0)                                     AS realized_pnl,
       b.opened_at,
       m.notes, m.status, m.account, m.wrapper
FROM positions_meta m
LEFT JOIN buys  b USING(ticker)
LEFT JOIN sells s USING(ticker);
```

Subtilité **`realized_pnl` temporellement ordonné** : sous-requête corrélée sur les buys **strictement antérieurs** à la vente. La vente ne se mange pas elle-même dans son propre PRU. SQL natif, VUE self-contained, byte-identité du swap propre.

### 2.3 PRU = moyenne pondérée, frozen-at-buy (décision fermée)

- **Méthode comptable = moyenne pondérée** (PRU français). Fisc FR impose le prix moyen pondéré sur titres + cohérence avec le modèle existant (`avg_cost` = PRU). FIFO serait un mismatch fisc + modèle. **Décision fermée**, pas matrice à débattre.
- **`pru_eur` frozen-at-buy** : pondère le `fx_at_trade` de chaque BUY (figé au jour de l'achat), jamais le `fx` du jour. Cohérent `entry_fx_at_call` (SPEC_MONEY_INVARIANT §2). Tax-correct (plus-value FR) + invariant : `pru_eur` ne dérive pas dans le temps.
- **`pru_native`** : pondère sur les prix natifs, indépendant du fx. Permet panneau native-space (skill isolé du change) en parallèle.

### 2.4 `realized_pnl` = NET de frais (plus-value fiscale FR, ≠ affichage TR gross)

Formule canonique (cf §2.2) :

```
realized_pnl_eur = Σ_sell ( sell.qty × sell.price × sell.fx
                          − sell.fees × sell.fx
                          − sell.qty × PRU_eur_at_sell )
```

avec `PRU_eur_at_sell` incluant les frais d'achat capitalisés (cf §2.2 sous-requête corrélée).

**Conséquence : ledger.realized_pnl = TR.gain − sell_fees**. C'est **par design**, pas une erreur. Convention fiscale française :

> Plus-value = prix de cession **net** (après frais de vente) − **PRU** (frais d'achat inclus)

Validation back-fill #121 (sur les 5 stale) : Δ = exactement `−1.00€ × N_sells` par ticker (frais TR = 1€/trade), confirmant la formule.

| Ticker | TR gain | Ledger | Δ | N_sells |
|---|---|---|---|---|
| 6920.T | +22.08 | +21.08 | −1.00 | 1 |
| ALAB | +228.89 | +227.88 | −1.01 | 1 |
| CCJ | −11.27 | −12.27 | −1.00 | 1 |
| SK Hynix | +98.18 | +97.17 | −1.01 | 1 |
| MU | +910.19 | +904.19 | −6.00 | 6 |

**Le ledger est plus juste que l'affichage TR**. TR affiche le gain gross-of-sell-fee (proceeds bruts − coût). Le ledger calcule la vraie plus-value fiscale. **Ne pas re-paniquer sur un futur hand-check** qui verrait ce −1€ par sell : c'est la convention nette qu'on veut.

Garde de régression : tout futur consumer qui compare `realized_pnl` au "gain TR brut" doit ajouter `Σ sell.fees_native × fx` pour convertir en convention TR. Documenter en commentaire de code à chaque comparaison.

## 3. Cure #3 — back-fill couvre les 26, pas les 5 (Catch 1)

> Dès que `positions` devient VUE (étape 0048), toute position sans `transactions` sort à `qty=0`/`PRU=NULL` dans la VUE. Les 21 « propres » disparaîtraient. Donc **back-fill = 26**, pas 5.

### 3.1 Anchor synthétique pour les 21 propres

Un INSERT BUY par position, `is_anchor=1`, calé pour reproduire **exactement** `pru_native` ET `pru_eur` existants :

```python
INSERT INTO transactions (
    ticker, side, qty, price_native, fees_native, currency, fx_at_trade,
    trade_date, broker_trade_id, source, is_anchor, notes
) VALUES (
    ticker,
    'BUY',
    positions.qty,                                            -- qty actuelle (vérité courante connue-bonne)
    positions.avg_cost_native,                                -- price_native = PRU native existant
    0,                                                        -- pas de frais sur l'anchor (capitalisés en lump-sum)
    positions.avg_cost_currency,
    positions.avg_cost_eur / positions.avg_cost_native,       -- ASTUCE GATE : reproduit pru_eur ET pru_native exactement
    positions.opened_at,
    NULL,                                                     -- broker_trade_id NULL pour anchor
    'migration_anchor_2026-06-09',
    1,                                                        -- is_anchor=1
    'Migration ledger v0 : anchor depuis positions snapshot pré-VUE'
)
```

**Astuce gate** : `fx_at_trade = avg_cost_eur / avg_cost_native` garantit `price_native × fx_at_trade ≡ avg_cost_eur` → gate byte-identité (Cure #4) passe sur les 21.

### 3.2 N'anchore JAMAIS les 5 stale

Les 5 (SK Hynix, ALAB, MU, CCJ, 6920.T) ont des `avg_cost_eur` / `qty` faux. Anchorer depuis ces valeurs **coulerait la valeur fausse dans l'immuable** — et comme on ne peut ni UPDATE ni DELETE, on serait coincé à empiler des ADJUST compensatoires sur un anchor faux. Inversibilité perdue.

Règle dure : les 5 sont **réconciliées avec relevés broker autoritatifs** (TR export complet OU snapshot autoritatif daté + deltas). **Pas avant.** Si TR pas prêt → les 5 restent en KNOWN-GAP L3 honnête, swap 0048 différé.

## 4. Cure #4 — gate byte-identité avant swap (Catch 2)

`scripts/check_ledger_view_equivalence.py` est un **gate obligatoire** avant `DROP TABLE positions` (étape 0048) :

- Pour chaque ticker des 26, compare VIEW (`SELECT * FROM positions` après CREATE VIEW) vs ancienne table (`SELECT * FROM positions_legacy_snapshot`, capturée avant DROP) sur `(qty, pru_eur, realized_pnl)`.
- **Tolérance** : 1e-6 sur `qty`, 0.01€ sur `pru_eur` et `realized_pnl` (arrondis flottants).
- **Liste dure des 5 stale** : exclues du "must match" — leur écart est attendu (c'est la cure). Log avant/après pour hand-check.
- **21 propres** DOIVENT matcher. Si 20/21 → ABORT, diagnostique le 1 inattendu avant de DROP.

Sortie attendue :
```
OK 21/21 propres byte-identique
ÉCART ATTENDU 5/5 stale (réconciliés) :
  000660.KS  pru_eur  1084.83 → 1060.00  (Δ -24.83)  rPnL  77.88 → 98.37
  ALAB       ...
GATE GREEN — swap 0048 autorisé.
```

Si 0/0 propres matchent → la VUE est cassée, NE PAS DROP.

## 5. Ordre des opérations (figé)

```
0046    CREATE transactions + positions_meta + 3 triggers + tests serrures   [GO immédiat]
0047    back-fill positions_meta depuis positions (5 cols × 26)              [post-0046, one-shot idempotent]
0047b   anchor BUY × 21 propres (script idempotent NOT EXISTS guard)         [post-0047]
#121    back-fill réel × 5 stale avec relevés TR autoritatifs                [attente relevés Olivier]
GATE    scripts/check_ledger_view_equivalence.py — bloque tant que 21/21+5/5 KO
0048    DROP TABLE positions + CREATE VIEW positions                        [SEULEMENT si GATE green]
0049    sweep code legacy refs colonnes mortes (si reste)                    [post-0048]
```

**Règle dure de séquencement** : `#121` est **AVANT** `0048`, jamais après. Si on swap sans `#121`, les 5 stale sortent à `qty=0`/`PRU=NULL` dans la VUE — perdues. Si TR pas prêt → tout jusqu'au GATE sur les 21, coexistence maintenue (table `positions` reste), swap différé. **Aucune urgence** : le KNOWN-GAP est honnête, il peut attendre les vrais chiffres. C'est la seule étape patiente du plan.

## 6. KNOWN-GAPs documentés (V0)

- **Dividendes / DRIP** : hors scope `transactions` V0. DRIP = un BUY réel (déjà géré dans le pattern). Dividendes cash → ledger cash séparé (table `cash_flows` futur).
- **Splits / corporate actions** : aucun split post-2020 sur les 5 stale (vérifié 09/06 nuit++ via yfinance). Hook `side TEXT` extensible réservé pour ajout futur `SPLIT` / `ADJUST` en additif (pas ENUM bétonné). À ré-tester si watchlist étendue inclut tickers qui splittent.
- **Frais broker manquants** sur trades historiques anciens : si TR n'expose pas → INSERT `fees_native=0` + note KNOWN-GAP par trade. PRU sous-estime légèrement le coût réel, biais documenté.
- **`broker_trade_id` indisponible sur TR export ancien** : si pas exposé → dedup composite `(ticker, trade_date, side, qty, price_native, source)` fallback, warn bruyant. Ingestion future doit exiger l'ID.

## 7. Invariants porteurs (les tests serrures pour 0046)

1. **Append-only structurel** : UPDATE → RAISE, DELETE → RAISE. Les corrections passent par entrée compensatoire (ADJUST futur), jamais edit.
2. **Idempotence structurelle** : INSERT même `broker_trade_id` → UNIQUE constraint violation. Pas de dedup applicatif oubliable.
3. **`qty > 0` strict** : pas de quantité négative déguisée en BUY. Le signe est porté par `side`, jamais par `qty`.
4. **`fx_at_trade` NOT NULL** : aucun trade sans fx (même si EUR : `fx=1.0`). Pas de fallback silencieux.
5. **PRU reproductible deterministe** : fixture 2 BUY (100@10 + 100@20) → `pru_native=15.0` exact. Fixture 3 BUY + 1 SELL ordonnés → `realized_pnl` calculé sur PRU pré-vente, pas leak de la vente dans son propre PRU.

## 8. Ce que cette spec rend impossible (la classe morte)

- ❌ `avg_cost_eur` désynchronisé du broker après vente partielle → impossible, dérivé du ledger immuable.
- ❌ `realized_pnl` patché à la main → impossible, dérivé.
- ❌ `qty_aligned_to_broker` note humaine → impossible, qty = Σ(BUY) − Σ(SELL) automatique.
- ❌ Double-insert d'un trade TR → impossible, `broker_trade_id` UNIQUE.
- ❌ DELETE silencieux d'une transaction « pour corriger » → impossible, trigger RAISE. Correction = ADJUST loggué.
- ❌ Re-introduction de `partial_close handler` pansement → caduc, dérivation automatique.

## 9. Liens

- `SPEC_SOCLE` — Datum primitif + derive (les briques de base de ce ledger)
- `SPEC_MONEY_INVARIANT` — baselines monétaires Datum[Monetary] + write-once entry (couche au-dessus)
- `CANONICAL_MAP.md` §2 — *transactions = record immuable, positions = état dérivé* (principe directeur)
- `LESSONS` L27 — cohérence mécanique > vigilance humaine (la doctrine qui rend les pansements caducs)
- Audit log `position_audit_log` id=83 (tentative realign SK Hynix) + id=84 (rollback + rationale cure for-good) — l'origine vivante de cette spec
