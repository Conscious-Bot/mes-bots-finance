#!/bin/bash
# PRESAGE trial — bootstrap one-command. À lancer depuis la racine du package.
#   ./setup.sh
# Crée le venv, installe les deps figées, monte le schéma DB, prépare .env.
set -euo pipefail
cd "$(dirname "$0")"

echo "=== 1/4 venv (Python 3.14 requis) ==="
python3 --version
python3 -m venv venv

echo "=== 2/4 dépendances (requirements figées de l'instance source) ==="
./venv/bin/pip install --quiet --upgrade pip
./venv/bin/pip install --quiet -r requirements.txt

echo "=== 3/4 schéma DB (alembic upgrade head → data/bot.db vide et complète) ==="
mkdir -p data
./venv/bin/python -m alembic upgrade head

echo "=== 4/4 .env ==="
if [ -f .env ]; then
  echo ".env existe déjà, laissé intact."
else
  cp .env.example .env
  echo ".env créé depuis .env.example (toutes clés optionnelles pour le dashboard)."
fi

echo ""
echo "✅ Prêt. Ensuite :"
echo "   1. édite  book.csv        (copie book.example.csv, mets tes lignes + thèses)"
echo "   2. seed   ./venv/bin/python import_book.py book.csv"
echo "   3. lance  ./venv/bin/python -m dashboard.serve"
echo "      → http://127.0.0.1:8000/dashboard.html"
