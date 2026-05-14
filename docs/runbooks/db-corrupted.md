# SQLite database corruption

## Symptoms

- Queries raise `sqlite3.DatabaseError: database disk image is malformed`
- `PRAGMA integrity_check` returns anything other than `ok`
- Bot fails to start with "unable to open database"
- WAL file (`data/bot.db-wal`) larger than 100 MB and not checkpointing

## Triage (2 min — do this BEFORE writing anything else)

1. **STOP** the bot immediately:
```bash
   pkill -f "python.*bot.main"
```
2. Do NOT delete WAL or SHM files. They may contain recoverable data.
3. Run integrity check:
```bash
   sqlite3 data/bot.db "PRAGMA integrity_check;"
```
4. Verify backup recency:
```bash
   ls -lat data/backups/data_*.tar.gz | head -3
```
5. Estimate data loss window: time between last good backup and now.

## Recovery

### Mild corruption (integrity_check reports specific page errors)
Try sqlite's own recovery:
```bash
cp data/bot.db data/bot.db.corrupt_$(date +%Y%m%d_%H%M%S)
sqlite3 data/bot.db ".recover" > /tmp/recovered.sql
mv data/bot.db data/bot.db.before_recover
sqlite3 data/bot.db.new < /tmp/recovered.sql
sqlite3 data/bot.db.new "PRAGMA integrity_check;"
# If ok: mv data/bot.db.new data/bot.db
```

### Severe corruption (database header damaged, .recover fails)
Restore from backup:
```bash
cp data/bot.db data/bot.db.corrupt_$(date +%Y%m%d_%H%M%S)
LATEST=$(ls -1t data/backups/data_*.tar.gz | head -1)
echo "Restoring from: $LATEST"
tar xzf "$LATEST" -C /tmp/
mv data/bot.db data/bot.db.replaced_$(date +%Y%m%d_%H%M%S)
cp /tmp/data/bot.db data/bot.db
sqlite3 data/bot.db "PRAGMA integrity_check;"
sqlite3 data/bot.db "PRAGMA journal_mode=WAL;"
```
Document data loss in `docs/post-mortems/YYYY-MM-DD-db-corruption.md`: gmail since backup time will be re-ingested naturally (dedup by gmail_id); insider/8-K data since backup time will need re-scan via cron.

### Bot back up
```bash
nohup python -m bot.main > bot.log 2>&1 &
sleep 5
pgrep -fl "python.*bot.main"
```

## Prevention hooks

- Daily backup at 04:00 (already shipped — `scripts/backup.sh`)
- 14-day rotation (already shipped)
- Integrity check in backup.sh (already shipped — aborts backup if source DB is malformed)
- WAL mode reduces corruption risk vs rollback journal (already shipped)
- Consider: monthly off-machine backup copy (e.g., iCloud or external drive)

## References

- `scripts/backup.sh` — daily backup automation
- `Makefile:db-bootstrap` — fresh DB bootstrap via Alembic
- `shared/storage.py:bootstrap_schema` — programmatic schema setup
- ADR-005 — Alembic schema versioning
