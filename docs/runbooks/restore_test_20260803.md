# Runbook — Test de restauration DB (preuve ACT-009 / H9-H9c)

**Date :** 2026-08-03 · **Opérateur :** session Claude Code · **Résultat : ✅ PASS**

## Contexte
ACT-009 exige une restauration **testée** (pas seulement un backup qui tourne).
Découvert le 03/08 : `presage-backup.service` échouait depuis le 31/07 sur
`No space left on device` — **disque VM 100% plein (36G/38G)**, racine physique
probable de plusieurs échecs silencieux de la nuit (writes tronqués à 0 : token
Gmail, sync, backup vault). Emergency résolue : purge des vieux backups accumulés
(19G → 2,2G), disque 100% → 55%. Backup + push offsite restaurés.

## Le test — restauration DEPUIS l'offsite (disaster recovery réel)
Source : **Hetzner Storage Box** `u608897-sub1@u608897-sub1.your-storagebox.de:presage-backups`
(port 23), PAS la copie locale VM. Environnement jetable : `/tmp/restore_test.db`.

Procédure (reproductible) :
```bash
# sur la VM
set -a; . ~/.config/presage/backup.env; set +a
rsync -e "ssh -p ${BACKUP_REMOTE_PORT} -i ${BACKUP_SSH_KEY} -o BatchMode=yes" \
  "$BACKUP_REMOTE_HOST:$BACKUP_REMOTE_PATH/bot.db.<TS>" /tmp/restore_test.db
sqlite3 /tmp/restore_test.db "PRAGMA integrity_check;"                 # -> ok
sha256sum /tmp/restore_test.db ~/backups/mes-bots-finance/bot.db.<TS>  # -> identiques
PRESAGE_DB_PATH=/tmp/restore_test.db venv/bin/python -c "..."          # smoke: le code lit
rm -f /tmp/restore_test.db
```

## Preuve (fichier `bot.db.20260803_184519`, 441M)
| Critère | Cible | Mesuré | Statut |
|---|---|---|---|
| RTO (durée restore depuis offsite) | ≤ 24h | **7 s** | ✅ |
| Intégrité SQLite | `ok` | `ok` | ✅ |
| Checksum offsite == backup local | identique | `1f5acac1b810ab70ae8c66a3171428a2fddb04c9713e735a50ca038f08e021bf` (les deux) | ✅ |
| Smoke — le code opère sur les données restaurées | lisible + tables cohérentes | positions=37 · decisions=96 · theses=57 · transactions=224 · storage import OK | ✅ |
| Nettoyage jetable | supprimé | `/tmp/restore_test.db` supprimé | ✅ |

## Conclusion
**H9 / H9c : vérifié avec preuve datée.** Un backup restaurable en 7s depuis un
offsite indépendant (Storage Box ≠ VM ≠ Mac), bit-identique, sur lequel le code
tourne. C'est plus que la plupart des systèmes en prod.

## Reste ouvert (durable, hors ce test)
- **Réduire la rétention** : `backup.sh` garde 14 jours ; à ~1 Go/jour sur un disque
  38G (dont repo 8,8G), ça re-remplit en ~2 semaines → le disque plein RÉCIDIVERA.
  Réduire à ~5-7 backups OU purger les tarballs projet (619M chacun, redondants
  avec git). **Le vrai fix anti-récidive.**
- **Dead-man's-switch avec `df`** : le disque plein n'a crié qu'après coup. Un check
  d'espace disque dans le heartbeat aurait intercepté toute la cascade en amont.
