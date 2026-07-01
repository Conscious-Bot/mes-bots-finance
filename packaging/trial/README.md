# PRESAGE — trial

Instance autonome de PRESAGE (dashboard) à faire tourner localement avec **ton
propre book**. Tu rentres tes lignes + thèses dans un CSV, tout se met en place.

> Ceci est le **dashboard-only** (visualisation de ton book : positions,
> concentration, risque, thèses, track record). Le bot Telegram + le scoring LLM
> continu + les crons sont un étage séparé, non inclus dans le trial.

## Prérequis

- **Python 3.14** (`python3 --version`)
- macOS ou Linux
- Aucune clé API obligatoire pour démarrer (les prix viennent de yfinance).

## Démarrage (4 étapes)

```bash
./setup.sh                                   # venv + deps + schéma DB + .env
cp book.example.csv book.csv                 # puis édite book.csv avec tes lignes
./venv/bin/python import_book.py book.csv    # seed + backfill des prix
./venv/bin/python -m dashboard.serve         # http://127.0.0.1:8000/dashboard.html
```

## Le fichier `book.csv`

Une ligne = une position **+ sa thèse (optionnelle)**. Colonnes :

| Colonne | Oblig. | Exemple | Sens |
|---|---|---|---|
| `ticker` | ✅ | `AAPL`, `MC.PA`, `ASML.AS` | symbole yfinance (suffixe marché : `.PA` Paris, `.AS` Amsterdam, `.T` Tokyo…) |
| `qty` | ✅ | `10` | quantité détenue |
| `avg_price_native` | ✅ | `180.50` | prix de revient moyen, en devise native |
| `currency` | ✅ | `USD`, `EUR` | devise native du titre |
| `trade_date` | ✅ | `2025-11-15` | date d'entrée (YYYY-MM-DD) |
| `conviction` | — | `1`–`5` | si présent → crée une thèse |
| `direction` | — | `long` | |
| `entry_price` / `target_partial` / `target_full` / `stop_price` | — | | niveaux de la thèse (devise native) |
| `thesis` | — | texte | résumé de la thèse |
| `account` / `wrapper` | — | `PEA` / `CTO` | libellés d'affichage |

Ré-import idempotent : un ticker déjà importé est sauté.

## Clés API (optionnelles)

Édite `.env` (créé par `setup.sh`). Chaque clé absente = composant en veille, jamais un crash. Voir `.env.example` pour ce que chacune débloque.

## Limitations connues du trial

- **Prix EUR non-EUR approximatifs** : le FX native→EUR au moment du seed est best-effort ; pour un book multi-devises, les valeurs EUR peuvent être approximatives tant que l'historique FX n'est pas backfillé. Les prix natifs et les % sont corrects.
- Pas de bot, pas d'alertes, pas de scoring LLM continu (étage 2).
- La config de gouvernance (`config.yaml`) porte des défauts ; les règles par-ticker spécifiques (grille de conviction SOCLE) ne s'appliquent qu'à leurs tickers.
