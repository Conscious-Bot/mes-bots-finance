.PHONY: test test-slow test-cov backup test-restore test-restore-db test-restore-tarball help db-bootstrap db-current db-history db-migrate db-revision

help:
	@echo "Available targets:"
	@echo "  test          - Run fast unit tests (skip slow = network/LLM)"
	@echo "  test-slow     - Run ONLY slow tests (network SEC + Claude API)"
	@echo "  test-cov      - Run fast tests with coverage report"
	@echo "  backup        - Run backup script manually"
	@echo "  test-restore  - Validate latest backup can be restored (DB + tarball)"
	@echo "  db-bootstrap  - Create fresh DB from migrations (CI/new install)"
	@echo "  db-current    - Show current alembic revision"
	@echo "  db-history    - Show full alembic migration history"
	@echo "  db-migrate    - Apply pending alembic migrations (upgrade head)"
	@echo "  db-revision   - Generate empty migration (MSG=desc required)"
	@echo "  help          - Show this help"

test:
	pytest tests/ -v -m "not slow"

test-slow:
	pytest tests/ -v -m slow

test-cov:
	pytest tests/ -m "not slow" \
		--cov=shared.math_helpers \
		--cov=intelligence.materiality_v2 \
		--cov=intelligence.asymmetry \
		--cov-report=term-missing

backup:
	bash scripts/backup.sh

test-restore-db:
	@echo "=== Test restore: DB snapshot"
	@LATEST_DB=$$(ls -t ~/backups/mes-bots-finance/bot.db.* 2>/dev/null | grep -v -- '-shm' | grep -v -- '-wal' | head -1); \
	if [ -z "$$LATEST_DB" ]; then \
		echo "FAIL: no DB backups in ~/backups/mes-bots-finance/"; exit 1; \
	fi; \
	echo "  Latest DB: $$LATEST_DB"; \
	cp "$$LATEST_DB" /tmp/test_restore.db; \
	if ! sqlite3 /tmp/test_restore.db "PRAGMA integrity_check;" | grep -q "ok"; then \
		echo "  FAIL: integrity check"; rm -f /tmp/test_restore.db; exit 1; \
	fi; \
	echo "  ✓ Integrity OK"; \
	SIGNALS=$$(sqlite3 /tmp/test_restore.db "SELECT COUNT(*) FROM signals"); \
	THESES=$$(sqlite3 /tmp/test_restore.db "SELECT COUNT(*) FROM theses"); \
	DECISIONS=$$(sqlite3 /tmp/test_restore.db "SELECT COUNT(*) FROM decisions"); \
	echo "  signals=$$SIGNALS theses=$$THESES decisions=$$DECISIONS"; \
	rm -f /tmp/test_restore.db; \
	echo "  ✓ DB restore test PASS"

test-restore-tarball:
	@echo "=== Test restore: tarball"
	@LATEST_TAR=$$(ls -t ~/backups/mes-bots-finance/snapshot_*.tar.gz 2>/dev/null | head -1); \
	if [ -z "$$LATEST_TAR" ]; then \
		echo "FAIL: no tarball backups"; exit 1; \
	fi; \
	echo "  Latest tarball: $$LATEST_TAR"; \
	TMPDIR=/tmp/test_restore_$$$$ && rm -rf $$TMPDIR && mkdir -p $$TMPDIR; \
	tar xzf "$$LATEST_TAR" -C $$TMPDIR/ 2>/dev/null; \
	for f in bot/main.py config.yaml intelligence/digest.py shared/math_helpers.py shared/storage.py; do \
		if [ ! -f "$$TMPDIR/mes-bots-finance/$$f" ]; then \
			echo "  FAIL: missing critical file $$f"; rm -rf $$TMPDIR; exit 1; \
		fi; \
	done; \
	echo "  ✓ Critical core files present"; \
	for f in TODO.md PHILOSOPHY.md ARCHITECTURE.md SESSION_STATE.md; do \
		if [ ! -f "$$TMPDIR/mes-bots-finance/$$f" ]; then \
			echo "  WARN: missing doc $$f (non-blocking)"; \
		fi; \
	done; \
	echo "  ✓ Critical files present in tarball"; \
	rm -rf $$TMPDIR; \
	echo "  ✓ Tarball restore test PASS"

test-restore: test-restore-db test-restore-tarball
	@echo ""
	@echo "✅ FULL RESTORE TEST PASS"

db-bootstrap:
	@echo "=== Bootstrap fresh DB from migrations"
	@python3 -c "from shared.storage import bootstrap_schema; bootstrap_schema(); print('OK schema bootstrapped to head')"

db-current:
	@alembic current

db-history:
	@alembic history

db-migrate:
	@alembic upgrade head

db-revision:
	@if [ -z "$(MSG)" ]; then echo "Usage: make db-revision MSG=\"description\""; exit 1; fi
	@alembic revision -m "$(MSG)"
