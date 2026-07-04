---
description: Politique de rétention + drill de restore (DB + vault) — répété à froid, semestriel
---

# /backup-drill — Le backup qu'on n'a jamais restauré n'existe pas

**Pourquoi** : PRESAGE a vécu 3 corruptions DB et n'a JAMAIS répété la restore à
froid ; le vault Obsidian (le cerveau non-régénérable) n'était couvert par aucun
backup avant le 04/07. Un backup non-testé est une croyance, pas une garantie.

**Quand** : semestriel (et après tout changement du chemin de backup). ~30 min.

## Ce qui est sauvegardé (inventaire)

| Substrat | Mécanisme | Régénérable ? | Rétention |
|---|---|---|---|
| Repo (code) | `scripts/backup.sh` tarball | oui (git) | daily×14 |
| DB `bot.db` | `.backup` + integrity_check | **partiellement** (resync VM) | daily×14 |
| **Vault Obsidian** | `scripts/backup_vault.py` (REST export) | **NON — irrécupérable** | daily×14 + monthly×6 |

Offsite : rsync vers `BACKUP_REMOTE_HOST` (Hetzner Storage Box) si configuré.

## Politique de rétention (QUALITY_BAR axe 3 : « 17 backups → 1 politique »)

- **DB / repo** : 14 derniers jours (rotation `find -mtime +14` dans backup.sh).
- **Vault** : 14 daily + 6 premiers-du-mois (rotation `_rotate` dans backup_vault.py).
- **Backups nominatifs** (`backup_close_*`, `bot.db.pre_*`, `snapshot_pre_*`) :
  gitignorés, à purger manuellement une fois le mois vérifié — ce ne sont pas
  la politique, ce sont des filets ad hoc d'un chantier précis.

## Le drill (à FAIRE, pas à lire)

```bash
source venv/bin/activate
DRILL=/tmp/presage_restore_drill && rm -rf "$DRILL" && mkdir -p "$DRILL"

# --- 1. DB : restaurer le dernier snapshot vers une cible neuve + intégrité ---
LAST_DB=$(ls -t "$HOME/backups/mes-bots-finance"/bot.db.* 2>/dev/null | head -1)
echo "restore DB depuis : $LAST_DB"
cp "$LAST_DB" "$DRILL/bot.db"
# WAL/SHM : ne JAMAIS copier ceux d'origine (cf sqlite_wal_shm_cleanup memory) —
# un .backup est déjà consolidé, la cible n'a pas de sidecar.
sqlite3 "$DRILL/bot.db" "PRAGMA integrity_check;"          # attendu : ok
sqlite3 "$DRILL/bot.db" "SELECT count(*) FROM transactions;"  # attendu : > 0
PRESAGE_DB_PATH="$DRILL/bot.db" python3 -c "from shared import storage; print('positions VUE:', len(storage.get_open_positions()))"

# --- 2. Vault : restaurer le dernier tar + compter les notes ---
LAST_VAULT=$(ls -t "$HOME/presage_vault_backups"/PRESAGE_vault_*.tgz 2>/dev/null | head -1)
echo "restore vault depuis : $LAST_VAULT"
tar xzf "$LAST_VAULT" -C "$DRILL"
cat "$DRILL/vault/_BACKUP_MANIFEST.txt"                    # notes listées/exportées
find "$DRILL/vault" -name '*.md' | wc -l                   # doit ≈ manifeste
# sanity : les notes cornerstone existent
for n in "PRESAGE.md" "Grille de Conviction.md"; do
  [ -f "$DRILL/vault/$n" ] && echo "✓ $n" || echo "✗ MANQUE $n — backup incomplet"
done

# --- 3. Nettoyage ---
rm -rf "$DRILL"
```

## Lecture du verdict

- **DB** : `integrity_check` = `ok`, `count(transactions) > 0`, la VUE positions
  dérive (> 0). Un `ok` sur une DB à 0 transaction = backup d'une DB vide → creuser.
- **Vault** : `find *.md | wc -l` ≈ le `exported OK` du manifeste (écart = notes
  illisibles au moment du backup, à investiguer) ; les notes cornerstone présentes.
- **Si un `✗` apparaît** : le backup ne couvre pas ce qu'on croit — c'est
  précisément ce que le drill existe pour attraper, AVANT la vraie perte.

## Anti-pattern

- Lire cette procédure sans l'exécuter : le drill est un test d'EXÉCUTION.
- Restaurer par-dessus la vraie DB/vault : le drill écrit dans `/tmp`, jamais en place.
- Copier les sidecars WAL/SHM d'origine lors d'une restore DB (rowid out of order,
  cf memory `sqlite_wal_shm_cleanup_post_sync`).

## Référence

- `scripts/backup.sh` (repo + DB + vault + offsite) · `scripts/backup_vault.py`
  (export REST + rotation) · memory `sqlite_wal_shm_cleanup_post_sync`,
  `single_source_vm_acted_2026-06-23`, `project_obsidian_vault_primary_substrate`.
