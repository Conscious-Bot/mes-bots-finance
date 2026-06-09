# Swap 0048 — Prérequis colonnes VUE (audit pré-DROP)

> Document d'audit pour décider la stratégie d'implémentation de la VUE
> `positions` post-DROP TABLE. Cf SPEC_LEDGER §5 (étape 0048) + red-team
> Olivier 09/06 ("complétude schéma de la VUE — gate-valeur ne couvre PAS").

## Constat

La VUE minimale du SPEC_LEDGER §2.2 expose `qty`, `pru_native`, `pru_eur`,
`realized_pnl`, `opened_at` + 5 colonnes meta. Mais le code prod consomme
**~50 refs sur 9 colonnes market-live** qui ne sont **pas dérivables des
transactions** :

| Colonne | Refs | Source primitive |
|---|---|---|
| `last_price_native` | 14 | `price_history` (cron yfinance) |
| `last_price_currency` | 5 | `price_history.currency` |
| `last_price_eur` | 0 | dérivé `native × fx` (déjà unused) |
| `price_asof` | 17 | `price_history.asof` |
| `price_source` | 3 | `price_history.source` |
| `fx_rate_to_eur` | 8 | `fx_history` (cron yfinance) |
| `fx_asof` | 10 | `fx_history.asof` |
| `fx_source` | 4 | `fx_history.source` |
| `last_updated` | 1 | déprécié (asof granulaire par champ) |

Le gate `check_ledger_view_equivalence.py` prouve la justesse des valeurs
ledger-dérivées. Il ne prouve PAS la complétude du schéma VUE vs consumers.

## Options de stratégie

### Option A — VUE étendue avec JOIN price_history + fx_history

VUE complète qui reproduit le comportement actuel de `positions` (qui cachait
le dernier tick yfinance). Pseudo-SQL :

```sql
CREATE VIEW positions AS
WITH buys_agg AS (...),  -- cf SPEC §2.2
     sells_agg AS (...),
     latest_price AS (
       SELECT p1.ticker, p1.price_native AS last_price_native,
              p1.currency AS last_price_currency,
              p1.asof AS price_asof, p1.source AS price_source
       FROM price_history p1
       WHERE p1.id = (
         SELECT MAX(p2.id) FROM price_history p2 WHERE p2.ticker = p1.ticker
       )
     ),
     latest_fx AS (
       SELECT pair, rate, asof, source FROM fx_history
       WHERE id IN (SELECT MAX(id) FROM fx_history GROUP BY pair)
     )
SELECT m.ticker,
       COALESCE(b.qty_buy,0) - COALESCE(s.qty_sell,0) AS qty,
       b.pru_native AS avg_cost_native,
       b.pru_eur AS avg_cost_eur,
       COALESCE(s.realized_pnl_eur, 0) AS realized_pnl,
       b.opened_at,
       lp.last_price_native, lp.last_price_currency, lp.price_asof, lp.price_source,
       fx.rate AS fx_rate_to_eur, fx.asof AS fx_asof, fx.source AS fx_source,
       lp.last_price_native * fx.rate AS last_price_eur,
       m.notes, m.status, m.account, m.wrapper
FROM positions_meta m
LEFT JOIN buys_agg b USING(ticker)
LEFT JOIN sells_agg s USING(ticker)
LEFT JOIN latest_price lp ON lp.ticker = m.ticker
LEFT JOIN latest_fx fx ON fx.pair = lp.last_price_currency || '/EUR'
;
```

**Avantages** :
- Compat code existant 100% : `SELECT * FROM positions` continue à fonctionner
- Swap minimal — pas de refactor des ~50 callsites

**Désavantages** :
- VUE complexe (4 sous-requêtes, 4 JOIN) — coût query
- Re-introduit la dualité `price_history` (cron) vs `prices.get()` live qu'on a passé hier à unifier
- Suppose que `fx_history.pair` existe sous forme `'KRW/EUR'`. À vérifier.

### Option B — VUE ledger-only + refactor consumers vers `shared.book.BookLine`

VUE minimal (SPEC §2.2 strict). Tous les consumers qui lisaient
`positions.last_price_*` ou `positions.fx_*` doivent passer par
`shared.book.get_held_lines()` qui compose ledger + market live via
`prices.get()`.

**Avantages** :
- Single source of truth : `prices.get()` est le seul accès market (cohérent SOCLE Phase 1)
- VUE simple, performante
- Pas de dualité cron/live

**Désavantages** :
- Refactor ~50 callsites (~ 9 colonnes × 5-10 refs moyenne)
- Risque régression à chaque consumer migré
- Plus long à shipper

### Option C — VUE étendue (A) **maintenant**, refactor B en différé

Pragmatique : ship A pour débloquer le swap aujourd'hui (compat préservée),
puis migration B itérative par module pour aller vers single source. La
table `positions_meta` et `transactions` restent inchangées.

## Reco

**Option C**, mais conditionnée à la validation Olivier — car même VUE A
exige (a) vérifier le schéma `fx_history` (pair format ?), (b) tests
exhaustifs après création VUE (smoke dashboard + intelligence/* contre VUE),
(c) backup avant DROP.

## Décisions pendantes (à trancher avant 0048)

1. **Option A vs B vs C** ?
2. Si A/C : confirmer schéma `fx_history` (pair `'KRW/EUR'` ou colonnes `from`/`to` séparées ?)
3. Si A/C : décider sort de `last_updated` (déprécié, drop colonne ou expose NULL ?)
4. Si A/C : `fx_at_purchase` actuellement = 1.0 partout (depuis cure money), à exposer ou drop ?
5. Smoke plan : quel test reproduit le rendu dashboard depuis la VUE pour valider compat avant DROP irréversible ?

## État courant (09/06 matin)

- Migration 0046 : appliquée (`alembic_version=0046`)
- 21 anchors + 21 trades TR ingérés (42 transactions)
- `positions_meta` : 30 rows back-fillées
- Gate `check_ledger_view_equivalence.py` : **EXIT 0 GREEN**
- Table `positions` : encore présente (coexistence)
- Backup pré-#121 : `data/bot.db.backup_pre_121_*`

**Pas d'urgence au swap**. KNOWN-GAP des 5 réconcilié dans le ledger.
La table `positions` continue à servir le code prod jusqu'à 0048.
