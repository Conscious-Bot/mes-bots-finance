# Failure Modes Registry — Top 5

**Updated**: 13 May 2026
**Methodology**: Likelihood × impact ranking. Each entry: scenario / detection / impact / mitigation / recovery.

## Why this matters

Path 5/6 requires demonstrating not just "ça marche" but "je sais quand ça casse". Cette registry est la **liste exhaustive des failures probables** qu'un acquéreur ou subscriber Substack scrutera. Mieux vaut documenter 5 scénarios honnêtement que 50 superficiellement.

---

## #1 — LLM API outage / cost spike

**Likelihood**: HIGH (API providers ont des incidents mensuels) × **Impact**: HIGH (digest/materiality/risk_check tous bloqués)

### Scénarios
- Anthropic API 5xx errors prolonged (>30min)
- Rate limit 429 sur burst de crons (debate + materiality_v2 simultanés)
- Coût spike: erreur prompt qui boucle (debate infini), changement pricing modèle, oubli max_tokens
- Budget mensuel >$50 breaché (cible: $8-15/mo)

### Detection
- `SELECT COUNT(*), SUM(cost_usd) FROM llm_calls WHERE created_at >= datetime('now', '-1 hour') AND status='error'` — si >10 errors/h → alert
- `SELECT SUM(cost_usd) FROM llm_calls WHERE created_at >= datetime('now', '-1 day')` — si >$3/jour → alert
- Heartbeat 1h cron silencieux → bot.log grep "anthropic" errors

### Mitigation préventive
- Cascade LLM en place: Haiku volume / Sonnet curation / Opus uniquement raisonnement structuré
- Timeouts explicites sur chaque appel API
- Token limits enforced
- Pas de boucle d'appels LLM sans break condition

### Recovery runbook
1. `tail -50 bot.log | grep -i anthropic` → identifier nature erreur
2. Si rate limit: pause crons gourmands (debate, risk_check, materiality_v2) via `pkill -USR1` ou edit bot/main.py temporaire
3. Si cost spike: `SELECT * FROM llm_calls WHERE cost_usd > 0.10 ORDER BY created_at DESC LIMIT 20` → identifier le runaway
4. Si Anthropic outage: fallback Haiku-only mode, désactiver Opus jobs temporairement

---

## #2 — DB corruption / lock cascade

**Likelihood**: LOW post-WAL × **Impact**: CATASTROPHIC (perte journal + theses + credibility)

### Scénarios
- Hardware fail / disk full pendant write → bot.db corruption
- `database is locked (5)` cascade malgré WAL (concurrent writes > checkpoint freq)
- bot.db-wal grows unbounded (checkpoint cron absent)
- File system corruption (rare sur APFS mais possible)

### Detection
- `PRAGMA integrity_check;` au backup quotidien — si != "ok" → alert
- Heartbeat cron 1h détecte si DB inaccessible
- bot.log grep "database is locked" — si répété → investigate
- `ls -la data/bot.db-wal` >100MB → WAL non checkpointé

### Mitigation préventive
- WAL mode activé (PRAGMA journal_mode=WAL) — P0 #3.5 ✅
- Backup quotidien 04:00 + integrity check enforced — P0 #2 ✅
- 14j rotation backups (rollback possible jusqu'à 2 semaines)

### Recovery runbook
1. **Si bot ne démarre pas**: stop bot, `cp ~/backups/mes-bots-finance/bot.db.LATEST data/bot.db`, restart
2. **Si integrity check FAIL**: `sqlite3 data/bot.db ".recover" > recovered.sql && sqlite3 new.db < recovered.sql`
3. **Si WAL >50MB**: `sqlite3 data/bot.db "PRAGMA wal_checkpoint(TRUNCATE);"`
4. **Si tout est cassé**: restore depuis last good backup (`make test-restore` confirms ce qui marche)

---

## #3 — Gmail OAuth token expiry / refresh fail

**Likelihood**: HIGH (Google rotation tokens régulière) × **Impact**: MEDIUM (newsletters bloqués, le reste marche)

### Scénarios
- `token.json` refresh expire silencieusement (default 7j si pas refresh, mais peut être révoqué)
- Google révoque app si pas vérifiée OAuth (limite 7 jours pour testing apps)
- Scope changement Gmail API force re-consent
- credentials.json rotated chez Google Cloud Console

### Detection
- `SELECT COUNT(*) FROM signals WHERE type='newsletter' AND timestamp >= datetime('now', '-2 days')` — si 0 sur 48h → alert
- bot.log grep "gmail_fetch" errors
- `gmail_fetch_job` returns n_fetched=0 sur >3 runs consécutives

### Mitigation préventive
- credentials.json + token.json backupés (NOT committed — .gitignore)
- OAuth scope minimal (gmail.readonly + labels.read seulement)

### Recovery runbook
1. `rm data/token.json` (force re-auth)
2. Stop bot
3. `python -m intelligence.gmail_auth` (CLI flow s'affiche)
4. Browser flow: copier code, paste, token.json regénéré
5. Restart bot, `tail bot.log | grep gmail` confirms

---

## #4 — yfinance API change / rate limit

**Likelihood**: MEDIUM (Yahoo silently modifie l'API ~1x/an) × **Impact**: HIGH (prices, asymmetry, crypto_zone tous cassés)

### Scénarios
- Yahoo modifie schéma JSON → yfinance.Ticker(x).history() retourne empty DataFrame
- IP-level rate limit (rare mais possible si bot poll 215 tickers trop souvent)
- yfinance package incompatibility avec nouvelle API (gap entre Yahoo change et package update)
- Ticker delisting silencieux → yfinance retourne NaN

### Detection
- `-- DEPRECATED: positions.current_price column doesn't exist. Real price fetched live via yfinance. Use bot_health_check.sh for price coverage diagnosis.` — si >5 tickers NULL → alert
- bot.log grep "price fetch" warnings >10/h
- /asymmetry retourne "price fetch failed" pour core tickers
- price_monitor_job logs "fetched 0/215"

### Mitigation préventive
- Try/except autour de chaque yfinance call (déjà en place dans _get_current_price)
- Logging warning sur fetch failures (log.warning(f"price fetch {ticker}: {e}"))
- Roadmap: FMP $14/mo comme fallback prêt à activer

### Recovery runbook
1. `pip install --upgrade yfinance` (souvent fix package version mismatch)
2. Si toujours cassé après upgrade: activer FMP fallback (config.yaml flag)
3. Edge case: ajouter alphavantage gratuit comme triple fallback
4. Pour tickers spécifiques cassés: vérifier ticker still listed (delisting)

---

## #5 — KPI #2 violation: Brier resolution stuck

**Likelihood**: MEDIUM (premier risque réel à J+28) × **Impact**: CREDIBILITY-BREAKING (track record Path 5/6 invalide)

### Scénarios
- <5 predictions résolues à J+28 → KPI #2 trigger STOP BUILD 5 jours
- Predictions stuck à `resolved_at IS NULL` malgré timestamp_created > 28j
- Resolve cron failure silencieux (yfinance down + retry pas implémenté)
- Auto-resolve logic bug (baseline_price NULL, ticker delisted, etc.)

### Detection
- Hebdo: `SELECT COUNT(*) FROM predictions WHERE resolved_at IS NULL AND created_at < datetime('now', '-28 days')` — si >0 → investigate
- Dashboard KPI #2: predictions résolues J+28 = N. Si N < 5 → stop build
- bot.log grep "resolve_predictions" pour errors

### Mitigation préventive
- resolve cron 9:00 Paris quotidien (déjà en place)
- Backfill manuel via `/resolve_prediction <id>` Telegram handler
- baseline_price stocké à creation pour éviter divergence

### Recovery runbook
1. Run manuel: `python -c "from intelligence import learning; learning.resolve_predictions()"`
2. `SELECT * FROM predictions WHERE resolved_at IS NULL ORDER BY created_at` — investigate cas par cas
3. Si bug systémique: stop 5j build, audit resolve logic
4. **KPI #2 violation trigger automatique**: zéro nouvelle thèse jusqu'à backfill complet

---

## Failure modes secondaires (non-top-5, à monitorer)

| Mode | Likelihood | Impact | Mitigation status |
|---|---|---|---|
| Disk full (log/DB unbounded) | LOW | HIGH | ⏳ Log rotation à ajouter (P1) |
| Telegram token revoked | LOW | HIGH | Restart manual via @BotFather |
| Position desync (manual trades) | MEDIUM | MEDIUM | Manual /position_set, weekly reconcile |
| Materiality_v2 prompt drift | MEDIUM | MEDIUM | Version pin model + prompt (P2 backlog) |
| FRED/EDGAR rate limit | LOW | LOW | Already gracefully degraded |
| Echo cluster BGE model drift | LOW | LOW | Pin model version, retrain quarterly |

## Review cadence

- **Mensuel 1er**: parcourir chaque failure mode, vérifier mitigation toujours active
- **Post-incident**: ajouter learnings, mettre à jour likelihood
- **Quarterly**: re-rank top 5 selon incidents réels observés



## #6 — APScheduler scheduler thread hangs silently (added 2026-05-14)

### Symptoms
- Process alive (`pgrep -if` finds it)
- bot.log shows no new entries for >1h despite hourly crons
- All scheduled jobs (heartbeat, gmail_ingest, materiality_v2, etc.) silently stop firing
- Telegram handlers may still respond (asyncio polling loop unaffected)
- Often preceded by "Run time of job X was missed by Y" warnings in log

### Detection
- `bot_health_check.sh` → `heartbeat_fresh FAIL` (>60min threshold)
- Secondary: `signal_ingest_freshness WARN` (>180min threshold)
- Manual: `tail bot.log` shows no recent entries despite alive process

### Cause hypotheses
1. ThreadPoolExecutor saturation (default max_workers=10, gmail_ingest ~20s blocking)
2. Job exception killing worker thread without propagation to main
3. APScheduler internal deadlock on event loop

### Runbook
cp bot.log HOME/backups/mes-bots-finance/bot.log.scheduler_hang_
(date +%Y%m%d_%H%M%S).log
pgrep -if "python.*bot.main" | xargs kill -9
sleep 30
pgrep -ifl "python.*bot.main"
nohup python -m bot.main > bot.log 2>&1 &
head -10 bot.log
./scripts/bot_health_check.sh

**Important**: do NOT use `pkill -f "python.*bot.main"` (case-sensitive on macOS where bin is `Python` capital P — see CONVENTIONS §16, §19). Use `pgrep -if | xargs kill -9` pattern instead.

Heartbeat_fresh will mechanically remain FAIL for ~1h post-restart until first cron fires. That's expected behavior, not a re-occurrence.

### References
- Postmortem: `docs/post-mortems/2026-05-14-apscheduler-hang-restart-cascade.md`
- CONVENTIONS §19 (macOS process targeting, Python.app launcher gotchas)
- CONVENTIONS §16 (detector validation, case-sensitivity trap origin)

### Open follow-ups (P2, post-J+28)
- APScheduler config tuning (max_workers, coalesce, executor type)
- Internal APScheduler INFO logging for stuck worker detection
- Consider multiprocessing executor for long-running gmail/LLM jobs
