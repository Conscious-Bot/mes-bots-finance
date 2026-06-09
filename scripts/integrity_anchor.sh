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
LEDGER_PREDICTIONS="integrity_anchors/predictions_ledger.jsonl"
LEDGER_THESES="integrity_anchors/theses_ledger.jsonl"
mkdir -p integrity_anchors

# Export DEUX chains DISTINCTES (catch architecture red-team) :
# - predictions = commit-reveal HIDING (hash chain seul, payload PRIVE jusqu'au reveal)
# - theses = narratif transparent (payload publique OK)
python3 -c "
import json
from shared import storage
from shared.integrity import verify_chain

# --- Chain PREDICTIONS (commit-reveal HIDING) ---
chain_p = storage.get_prediction_integrity_chain()
if chain_p:
    ok, broken = verify_chain(chain_p)
    if not ok:
        raise SystemExit(f'PREDICTIONS CHAIN VERIFY FAILED at seq={broken} -- ANCHOR ABORT (L15)')
    with open('$LEDGER_PREDICTIONS', 'w') as f:
        for row in chain_p:
            # HASH SEUL : pas de payload_json (preserve hiding)
            line = {
                'seq': row['seq'],
                'prediction_id': row['prediction_id'],
                'captured_at': row['captured_at'],
                'prev_hash': row['prev_hash'],
                'chain_hash': row['chain_hash'],
            }
            f.write(json.dumps(line, sort_keys=True, separators=(',', ':')) + '\n')
    print(f'predictions: {len(chain_p)} rows -> $LEDGER_PREDICTIONS (hash chain seul, hiding preserve)')
else:
    print('predictions chain vide')

# --- Chain THESES (transparent) ---
chain_t = storage.get_thesis_integrity_chain()
if chain_t:
    ok, broken = verify_chain(chain_t)
    if not ok:
        raise SystemExit(f'THESES CHAIN VERIFY FAILED at seq={broken} -- ANCHOR ABORT (L15)')
    with open('$LEDGER_THESES', 'w') as f:
        for row in chain_t:
            line = {
                'seq': row['seq'],
                'thesis_id': row['thesis_id'],
                'captured_at': row['captured_at'],
                'payload_json': row['payload_json'],
                'prev_hash': row['prev_hash'],
                'chain_hash': row['chain_hash'],
            }
            f.write(json.dumps(line, sort_keys=True, separators=(',', ':')) + '\n')
    print(f'theses: {len(chain_t)} rows -> $LEDGER_THESES (transparent)')
else:
    print('theses chain vide')
"

# 2. OTS stamp les ledgers (preuve trustless Bitcoin)
# Note : ots stamp refuse si .ots existe deja -- on retire l'ancien d'abord.
# L'attestation precedente reste valide dans le git log + reste verifiable via
# `git show <commit>:<ledger>.ots` ; ce n'est pas une perte de preuve, c'est le
# remplacement de l'attestation chain-head du jour par celle d'aujourd'hui.
if [ -f "$LEDGER_PREDICTIONS" ]; then
    rm -f "${LEDGER_PREDICTIONS}.ots"
    ots stamp "$LEDGER_PREDICTIONS"
fi
if [ -f "$LEDGER_THESES" ]; then
    rm -f "${LEDGER_THESES}.ots"
    ots stamp "$LEDGER_THESES"
fi

# 3. commit ledgers + receipts OTS (1ere couche audit history)
git add integrity_anchors/*.jsonl integrity_anchors/*.ots 2>/dev/null || true
git commit -m "[integrity] anchor chain-head $(date -u +%FT%TZ)" || echo "rien a committer (ledger inchange)"

# 4. push (2e couche, best-effort) -- NE remplace PAS l'OTS comme preuve
git push origin main 2>&1 || echo "WARN push echec -- OTS reste la preuve trustless"

echo "OK -- attestation Bitcoin en cours (asynchrone, ~quelques heures pour confirmation bloc)"
echo "Verification differee : ots upgrade integrity_anchors/*.ots && ots verify integrity_anchors/*.ots"
