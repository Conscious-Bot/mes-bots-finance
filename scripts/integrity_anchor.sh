#!/usr/bin/env bash
# scripts/integrity_anchor.sh -- ancrage TRUSTLESS du chain-head via OpenTimestamps.
#
# Catch red-team 07/06 nuit++ : git tag prive + push origin NE SUFFISENT PAS pour
# un operateur solo avec repo prive. Tu controles le repo, tu peux git tag -d /
# push --force / reecrire historique. Un tag signe prouve QUI l'a fait, pas qu'il
# n'a pas ete refait. Les seuls ancrages reellement trustless dans cette position :
# - OpenTimestamps (ancrage Bitcoin) -- gratuit, sans compte, sans tiers a qui faire
#   confiance. Le bon choix par defaut.
# - Publier le hash la ou tu ne peux pas le reecrire et ou d'autres l'observent
#   (repo public, post horodate, service de commitment).
#
# Ce script utilise OTS comme ancre primaire + git comme audit secondaire.
#
# Cron daily suggere user crontab :
#   0 6 * * * cd /path/to/presage && /path/to/scripts/integrity_anchor.sh
#
# Verification post-hoc (apres ~quelques heures pour confirmation Bitcoin) :
#   ots upgrade integrity_anchors/<date>.txt.ots
#   ots verify integrity_anchors/<date>.txt.ots

set -euo pipefail

# Requires OTS installed : pip install opentimestamps-client
command -v ots >/dev/null || {
    echo "FATAL: opentimestamps-client absent (pip install opentimestamps-client)" >&2
    exit 1
}

cd "$(dirname "$0")/.."

# 1. Build artefact auditable depuis la chain DB (export jsonl git-trackable)
#    Catch red-team : bot.db est gitignored -> table seule n'est PAS auditable par tiers.
#    Solution : export ledger en jsonl git-tracke + .ots sidecar.
LEDGER="integrity_anchors/predictions_ledger.jsonl"
mkdir -p integrity_anchors

# Export via Python helper (utilise shared.integrity verify d'abord, refuse export sur chain cassee)
python3 -c "
import json
from shared import storage
from shared.integrity import verify_chain

chain = storage.get_thesis_integrity_chain()
if not chain:
    raise SystemExit('chain vide, rien a ancrer')
ok, broken = verify_chain(chain)
if not ok:
    raise SystemExit(f'CHAIN VERIFY FAILED at seq={broken} -- ANCHOR ABORT (L15)')

with open('$LEDGER', 'w') as f:
    for row in chain:
        # canonical primitive types only (catch #1 footgun fix)
        line = {
            'seq': row['seq'],
            'thesis_id': row['thesis_id'],
            'captured_at': row['captured_at'],
            'payload_json': row['payload_json'],
            'prev_hash': row['prev_hash'],
            'chain_hash': row['chain_hash'],
        }
        f.write(json.dumps(line, sort_keys=True, separators=(',', ':')) + '\n')
print(f'wrote {len(chain)} rows -> $LEDGER')
"

# 2. OTS stamp le ledger public (cree predictions_ledger.jsonl.ots)
#    C'est LA preuve trustless : Bitcoin ancre le hash, irreproductible pour
#    l'operateur solo.
ots stamp "$LEDGER"

# 3. commit ledger + recipt OTS dans git (1ere couche : history visible)
git add "$LEDGER" "$LEDGER.ots"
git commit -m "[integrity] anchor chain-head $(date -u +%FT%TZ)" || echo "rien a committer (ledger inchange)"

# 4. push (2e couche, best-effort) -- NE remplace PAS l'OTS comme preuve
git push origin main 2>&1 || echo "WARN push echec -- OTS reste la preuve trustless"

echo "OK -- attestation Bitcoin en cours (asynchrone, ~quelques heures pour confirmation)"
echo "Verification differee : ots upgrade $LEDGER.ots && ots verify $LEDGER.ots"
