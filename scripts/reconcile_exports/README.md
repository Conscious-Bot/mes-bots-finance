# Reconcile Exports

Dépose ici les exports CSV des brokers pour reconcilier le book DB contre la réalité broker.

## Format CSV attendu

```
ticker,qty,avg_cost_eur,wrapper
ASML.AS,3.5,950.50,PEA
TSM,18.5,140.20,CTO
```

Champs :
- `ticker` : symbole yfinance (`.AS` `.PA` `.T` `.KS` etc)
- `qty` : quantité réelle au broker (float, fractionnel OK)
- `avg_cost_eur` : prix moyen d'acquisition en EUR
- `wrapper` : `PEA` | `CTO` | `AVUS` | autre

## Workflow

1. Export depuis broker (Trade Republic, Boursorama, etc.)
2. Convertir au format canonique ci-dessus (mapping ticker yahoo + EUR)
3. Sauvegarder dans ce dossier (`broker_YYYY-MM-DD.csv`)
4. Lancer :

```bash
python3 -m intelligence.reconcile scripts/reconcile_exports/broker_2026-05-29.csv
```

5. Le rapport sort en stdout. 4 catégories :
   - **ok** : qty + cost match < 1% — pas d'action
   - **drift_minor** : 1-5% — vérifier si normal (arrondi, frais)
   - **drift_major** : >5% — corriger manuellement
   - **missing_in_db** : présent broker, absent DB → ajouter
   - **phantom_in_db** : présent DB, absent broker → fermer

6. Pour appliquer les corrections : `/position_buy`, `/position_sell` via Telegram bot (pas d'auto-apply ici pour audit trail).

## Pourquoi pas d'auto-apply ?

Pour cette première version, le reconciler **rapporte** mais ne **touche pas** la DB. Raisons :
- Audit trail explicit : chaque correction passe par une décision user
- Détection de bugs broker (ex: split non répliqué, ticker mismatch) avant qu'ils contaminent la DB
- Trust à accumuler avant d'autoriser writes automatiques

Auto-apply viendra quand le format CSV des deux brokers principaux sera validé sur ≥3 cycles de reconcile manuels sans drift surprise.

## Note

Ce dossier est dans `.gitignore` (les exports broker contiennent des données financières personnelles). Seul le `README.md` est commité.
