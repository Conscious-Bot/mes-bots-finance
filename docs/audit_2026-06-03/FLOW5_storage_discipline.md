# Flow 5 — Storage discipline (cross-cutting)

**Périmètre** : SQLite ACID, WAL mode, schema versioning via alembic, lock concurrency, source-uniqueness des accessors, état déployé vs état code.

## Storage layers

| Layer | Lieu | Rôle |
|---|---|---|
| SQLite primary | `data/bot.db` | données prod : signals, predictions, theses, positions, bias_events, prediction_audit_log, etc. |
| State JSON | `data/bot_state.json` | runtime state : llm_status, last_heartbeat_ts, llm_active_model, etc. |
| Logs | `bot.log`, `uptime.log`, `dashboard/serve.log` | append-only, mtime-based rotation manuelle |
| Backups | `data/bot.db.backup_*` | daily backup_job + manual pre-migration backups |

## Schema migrations

28 migrations alembic. Verrouillage : tests `test_schema_drift.py` empêchent table orphan refs (whitelisted exceptions cf migration 0028 swap pattern).

Migration courante en prod : **0028** (appliquée ce matin 13:06). Predictions.methodology_version : `NOT NULL` sans `DEFAULT`.

**Verif active** : tests `test_methodology_version_required.py` couvrent la couche Python (insert_prediction validation explicit + missing arg → TypeError + empty/None → ValueError) ET la couche SQL (PRAGMA table_info → notnull=1 dflt=None ; raw INSERT sans methodology_version → IntegrityError).

## Plugs solidity

| Plug | Status | Notes |
|---|---|---|
| WAL mode | **à vérifier explicitement** : `sqlite3 data/bot.db "PRAGMA journal_mode;"` | si pas WAL, single writer = écritures bloquent les lectures. APScheduler + Telegram handler peuvent contender. |
| Foreign keys | activé via `PRAGMA foreign_keys = ON` dans `storage.db()` context manager (storage.py:20) | ✓ |
| Transaction commits | explicit `conn.commit()` partout après UPDATE/INSERT | ✓ |
| Connection lifecycle | `with db() as conn` pattern partout | ✓ commit-or-rollback automatique via context manager |
| Concurrent writes (2 cron jobs) | single bot process + fcntl.flock = 1 process = 1 GIL = sériel | ✓ effectif |
| atexit cleanup | `_release_mono_instance_lock` (bot/main.py:346) ✓ | release lock + delete bot.pid on clean exit |
| insert_prediction methodology_version | **NEW POST-0028** : required keyword param + SQL inclut la colonne | ✓ dans le code repo. **Problème : pas en prod** (cf section P1) |

## Failure modes

| Étape | Failure | Détection | Récupération | Severity |
|---|---|---|---|---|
| `sqlite3.OperationalError "database is locked"` | concurrent write contention | propage exception | retry par caller (rare) | **P3** sous load normal |
| `IntegrityError NOT NULL constraint` | INSERT sans colonne required | propage | crash → APScheduler restart | **P1 ACTIF EN POTENTIEL** : cf section dédiée ci-dessous |
| Disk full | bot.log + DB grossissent | aucune surveillance auto | crash | **P3** disk size watch ? |
| Backup job miss | bot down at 04:00 | misfire grace 4h | manual restart bot | **P2** |
| Backup file rotation | sembler accumuler | `daily_backup_job` strategy à vérifier | manual cleanup | **P3** |
| State file corruption | json decode fail | catch dans load_state → {} fallback | next save écrase | **P2** mineur |
| WAL checkpoint | sqlite auto-handles | aucune intervention | nominal | **P3** OK |

## Coupling assessment (3 patterns)

| Pattern | Évaluation |
|---|---|
| **Pattern 1 (liveness ≠ functionality)** | DB file présent = "alive" mais peut être corrupted / stale. Lecteurs (render.py via _q) ne détectent pas une DB qui n'a plus reçu d'écriture depuis 24h. Pattern 1 sur le storage = silence. |
| **Pattern 2 (snapshot drift)** | Backups quotidiens = snapshots. Si backup job silencieux fail (e.g. disk full mais print swallowed), tu crois avoir un backup, en réalité non. `task #28` (P2 — Cron backup data potentiellement mort) marquée [completed] : vérifier que c'est encore vrai. |
| **Pattern 3 (multi-path)** | Une seule source de truth (`data/bot.db`). Pattern 3 ne s'applique pas au layer storage, mais à toutes les couches qui re-derive (cf Flow 3). |

## Resilience layer integration

| Item | Status |
|---|---|
| canonical_predictions_filter() | ✓ centralisé dans storage (commit `202a7a3`) |
| substance_predictions_filter() | ✓ centralisé (commit `4b48b17`) |
| brier_by_methodology() | ✓ centralisé (storage.py:158) |
| scoring_status enum | ✓ migration 0027 + helpers _mark_pending_llm |
| methodology_version required | ✓ migration 0028 + insert_prediction validation |
| bot_state.json llm_status | ✓ set_llm_status / get_llm_status (shared/llm.py) |

## Duplicates dans ce flux

- Plusieurs accessors raw `sqlite3.connect(DB_PATH)` direct au lieu de `with storage.db() as conn` (foreign keys ON + commit auto). Exemples : `materiality_v2.py:169`, `materiality_v2.py:211`. **Pattern de cohérence** : tous les call sites devraient utiliser `storage.db()`. **P3** — drift mineur, à uniformiser à la prochaine touche.

## Dead code dans ce flux

- Anciennes migrations potentiellement obsolètes (e.g. 0020 "drop fossile tables") — **conscient, alembic c'est append-only par design**.
- Aucun storage helper orphan détecté.

## ⚠️ P1 CRITIQUE : deployment gap (bot tourne sur code d'hier)

### Évidence

```
$ ps -o lstart,pid,comm -p 46307
STARTED                        PID COMM
mar.  2 juin 21:58:10 2026   46307 caffeinate

$ git log --since="2026-06-03 00:00" --format="%ai %h %s" | head -3
2026-06-03 14:42:39 +0900 b8fd294 ...
2026-06-03 14:18:01 +0900 0035bfe ...
2026-06-03 14:12:54 +0900 3d442d9 ...
```

Bot démarré **2026-06-02 21:58**. Tous les commits d'aujourd'hui (~20 commits incluant #93/#94/#95/#96/#97/#98) sont en repo mais **PAS en prod**.

### Combinatoire mortelle

| Layer | État | Effet |
|---|---|---|
| DB schema | Migration 0028 appliquée 13:06 → `methodology_version NOT NULL` sans `DEFAULT` | Toute INSERT sans methodology_version → IntegrityError |
| Bot code (en cours d'exécution) | Pré-d4a9481 → `storage.insert_prediction` ne spécifie PAS methodology_version dans le SQL INSERT | Si appelé → INSERT sans la colonne → IntegrityError |
| LLM | credit_exhausted depuis ~2 jours → aucune `score_directional_probability` ne réussit → aucune call à `register_prediction` | **Le crash est masqué** parce que personne n'essaie d'insérer |

**Dès que LLM est restauré** (user ajoute credit Anthropic) :
1. `materiality_v2.score_pending_signals_v2` recommence à scorer les signals pending_llm
2. `learning.auto_register_predictions` recommence à élicit probabilités
3. `storage.insert_prediction` (OLD code) tente INSERT sans methodology_version
4. SQL → `IntegrityError NOT NULL constraint failed: predictions.methodology_version`
5. Le batch crash, suivants pas tentés, signal reste pending_llm pour toujours

Le J-day batch (resolve + monthly snapshot) lui-même fonctionnera car il fait UPDATE et SELECT, pas INSERT. Donc le J-day report partiellement OK même sans restart. Mais **le pipeline de création de prédictions est cassé jusqu'au restart**.

### Mitigation : restart immédiat

Deux chemins :
```bash
# Soft : envoyer SIGTERM au bot, launchd KeepAlive le relance avec code courant
pkill -f "python.*bot\.main"

# Hard : unload/load launchd
launchctl unload ~/Library/LaunchAgents/com.olivier.presage.plist
launchctl load ~/Library/LaunchAgents/com.olivier.presage.plist
```

Soft est suffisant. ThrottleInterval=30s → restart en <1min. `Scheduler started with N jobs` line dans bot.log confirmera nouveau code.

**À faire MAINTENANT, ou expliciter pourquoi pas.** C'est la seule action P1 immédiate de l'audit.

### Cause racine

Pas de CI/CD auto-restart après deploy. Pas de hook git post-commit qui SIGTERM le bot. Une partie du build-reflex (commit fast + iterate) sans le complément deploy-reflex. **Trade-off conscient** historiquement (single-dev) qui rentre en collision avec un changement de schema irréversible appliqué via alembic.

**Lesson à logguer** : toute migration alembic qui change un INVARIANT (drop DEFAULT, add NOT NULL, etc.) doit être accompagnée d'un restart bot. Ajouter à `docs/LESSONS.md` post-audit.

## Action items Flow 5

| Item | Priority | Disposition |
|---|---|---|
| **Restart bot pour déployer code post-migration 0028** | **P1 IMMÉDIAT** | `pkill -f "python.*bot.main"` — launchd KeepAlive restart |
| Vérifier `PRAGMA journal_mode` = WAL en prod | **P2** | trivial, sanity check |
| Logguer dans LESSONS.md : "migration alembic schema-invariant change → restart bot mandatory" | **P2** | doc, ~10 min |
| `task #28` re-verify daily_backup_job vivant | **P2** | grep dernier backup file mtime |
| `materiality_v2.py:169` use storage.db() au lieu de sqlite3.connect direct | **P3** | uniformisation, drift mineur |
