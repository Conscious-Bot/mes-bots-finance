.PHONY: test test-cov backup test-restore test-restore-db test-restore-tarball help

help:
	@echo "Available targets:"
	@echo "  test          - Run all unit tests (pytest)"
	@echo "  test-cov      - Run tests with coverage report"
	@echo "  backup        - Run backup script manually"
	@echo "  test-restore  - Validate latest backup can be restored (DB + tarball)"
	@echo "  help          - Show this help"

test:
	pytest tests/ -v

test-cov:
	pytest tests/ \
		--cov=shared.math_helpers \
		--cov=intelligence.materiality_v2 \
		--cov=intelligence.asymmetry \
		--cov-report=term-missing

backup:
	bash scripts/backup.sh

test-restore-db:
	@echo "=== Test restore: DB snapshot"
	@LATEST_DB=$$(ls -t ~/backups/mes-bots-finance/bot.db.* 2>/dev/null | head -1); \
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
