#!/bin/bash
# Assemble le dossier PRESAGE trial sendable dans dist/presage-trial/.
#
# SÉCURITÉ (leçon 30/06) — DEUX couches :
#   1. `git archive` = uniquement les fichiers TRACKÉS → aucun gitignoré
#      (secrets, .env*, credentials.json, data, backups, *.db, logs) par construction.
#   2. ALLOWLIST = on ne recopie QUE les 6 packages de code que l'app importe
#      + config + alembic. Tout le sprawl du repo (hermes, markets, posts, docs,
#      track_record, tests…) est exclu par non-inclusion, pas par denylist.
#   3. Scan secret dur en fin = échoue si quoi que ce soit traîne.
#
# Lancer depuis la racine du repo :  bash packaging/trial/build_package.sh
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$REPO/dist/presage-trial"
TRIAL="$REPO/packaging/trial"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Packages locaux réellement importés par dashboard/bot/intelligence (vérifié)
KEEP_DIRS=(bot dashboard data_sources intelligence risk shared config)
KEEP_FILES=(alembic.ini pyproject.toml config.yaml pytest.ini)

echo "=== git archive HEAD → tmp (tracked-only) ==="
git -C "$REPO" archive --format=tar HEAD | tar -x -C "$TMP"

echo "=== nettoyage $OUT ==="
rm -rf "$OUT" && mkdir -p "$OUT"

echo "=== copie ALLOWLIST ==="
for d in "${KEEP_DIRS[@]}"; do
  [ -d "$TMP/$d" ] && cp -R "$TMP/$d" "$OUT/$d" && echo "  dir  $d"
done
for f in "${KEEP_FILES[@]}"; do
  [ -f "$TMP/$f" ] && cp "$TMP/$f" "$OUT/$f" && echo "  file $f"
done
# alembic (schéma) : uniquement le sous-dossier, pas les scripts one-off perso
mkdir -p "$OUT/scripts"
cp -R "$TMP/scripts/alembic" "$OUT/scripts/alembic" && echo "  dir  scripts/alembic"

echo "=== requirements figées ==="
if [ -x "$REPO/venv/bin/pip" ]; then
  "$REPO/venv/bin/pip" freeze > "$OUT/requirements.txt"
  echo "  $(wc -l < "$OUT/requirements.txt") deps"
fi

echo "=== injection artefacts trial ==="
cp "$TRIAL/import_book.py" "$TRIAL/book.example.csv" "$TRIAL/.env.example" \
   "$TRIAL/setup.sh" "$TRIAL/README.md" "$OUT/"
chmod +x "$OUT/setup.sh"

echo "=== SCAN SECRET DUR ==="
PAT='AIza[0-9A-Za-z_-]{20}|sk-ant-|xox[baprs]-|-----BEGIN|"private_key"|"client_secret"|[0-9]{8,10}:[A-Za-z0-9_-]{35}'
HITS=$(grep -rlEI "$PAT" "$OUT" 2>/dev/null | grep -v '/.env.example$' || true)
NAMES=$(find "$OUT" \( -name '.env' -o -name '.env.*' ! -name '.env.example' \
        -o -name 'credentials*.json' -o -name '*.db' -o -name '*.log' \) 2>/dev/null || true)
if [ -n "$HITS$NAMES" ]; then
  echo "  ⛔ FUITE — NE PAS ENVOYER :"
  [ -n "$HITS" ] && echo "$HITS" | sed 's/^/    contenu: /'
  [ -n "$NAMES" ] && echo "$NAMES" | sed 's/^/    fichier: /'
  exit 1
fi
echo "  ✅ aucun secret, aucun fichier sensible"
echo ""
echo "✅ Package SAIN : $OUT  ($(du -sh "$OUT" | cut -f1))"
echo "   Zip : (cd \"$REPO/dist\" && zip -rq presage-trial.zip presage-trial)"
