# Gabarit — Nouveau monitor type kca / over_cap

**Version 1.0** (figé 01/06/2026). Pattern canonique pour ajouter un nouveau monitor qui : (a) détecte une transition d'état sur un objet du book, (b) notifie l'utilisateur à l'instant T du franchissement, (c) ouvre un candidat bias_event observable. Cf `LESSONS.md` L4.

**Précédents** :
- `intelligence/kill_criteria_monitor.py` — état stocké dans `kill_criteria_alerts`, transition `dormant/at_risk/triggered` par thèse, wire fomo_greed sur transition `→ triggered`.
- `intelligence/over_cap_monitor.py` — état stocké dans `over_cap_alerts`, transition `dormant/over` par position, wire fomo_greed sur transition `dormant_to_over`.

---

## Composants obligatoires

### 1. Table journal d'événements append-only (migration alembic)

**Pattern** :
```sql
CREATE TABLE <name>_alerts (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at         TEXT NOT NULL DEFAULT (datetime('now')),
    <key>              TEXT NOT NULL,                      -- ticker, thesis_id, etc.
    status             TEXT NOT NULL CHECK(status IN (...)), -- enum des états
    <metrics>          REAL NOT NULL,                       -- weight_pct, confidence...
    notified           INTEGER NOT NULL DEFAULT 0,
    transition         TEXT CHECK(transition IN ('...', NULL)),
    bias_event_id      INTEGER REFERENCES bias_events(id)
);
CREATE INDEX idx_<name>_<key> ON <name>_alerts(<key>, created_at);
CREATE INDEX idx_<name>_status ON <name>_alerts(status, created_at);
```

**Règles** :
- `created_at` avec **DEFAULT** (sinon les cure-rows MODE B échouent).
- `notified` 0/1 pour distinguer transitions qui ont déclenché notify.
- `transition` nullable (= no_change row vs vraie transition).
- `bias_event_id` FK pour lier audit ↔ candidat ouvert.
- **JAMAIS de DELETE** dans le code applicatif (append-only strict). Cure = append ligne `dormant` avec colonnes neutralisées (cf L4 cure MODE B).

### 2. Helper storage dans `shared/storage.py`

```python
def insert_<name>_alert(
    key: str, status: str, metric: float, ...,
    notified: bool = False,
    transition: str | None = None,
    bias_event_id: int | None = None,
) -> int | None:
    """Insert audit row. Toujours append. Retour lastrowid ou None on error."""

def get_latest_<name>_per_key(key: str) -> dict | None:
    """Last evaluation row pour key, source de vérité prev_status."""
```

### 3. Module monitor dans `intelligence/<name>_monitor.py`

```python
def classify_<obj>(<obj>, ...) -> dict | None:
    """Source de vérité UNIQUE pour la classification.

    Retourne None si non-classifiable LÉGITIMEMENT (pas dans périmètre,
    règle métier non applicable).

    Raise MissingDataError si donnée critique manquante pour un <obj>
    qui DEVRAIT être classifiable. Le caller catche et compte en errors.
    JAMAIS de silent drop dans None.
    """
    # Distinguer strictement :
    # - non-classifiable légitime → return None
    # - donnée manquante critique → raise MissingDataError

def _prev_status_for_<name>(key) -> str:
    """Lit derniere row du journal. Default 'dormant' si jamais évalué.
    DÉCOUPLE du cycle bias_events (cf L4)."""
    row = storage.get_latest_<name>_per_key(key)
    return row["status"] if row else "dormant"

def check_all_<name>_transitions() -> dict:
    """Pour chaque obj, classify + détecte transition + notify+wire+audit.
    
    Returns: {checked, <state>, transitions, notified, wired, errors}
    """
    for obj in <objs>:
        try:
            try:
                cls = classify_<obj>(obj, ...)
            except MissingDataError as md:
                log.warning(f"<name> {obj.key}: missing data: {md}")
                stats["errors"] += 1
                continue
            if cls is None:
                continue  # non-classifiable légitime

            new_status = cls["status"]
            prev_status = _prev_status_for_<name>(obj.key)
            transition = _classify_transition(prev_status, new_status)

            notified_flag = False
            bias_event_id = None
            if transition == "<actionable_transition>":
                # 1. Notify Telegram (l'instant T fidèle, wrap try/except)
                try:
                    notify.send_text(...)
                    notified_flag = True
                    stats["notified"] += 1
                except Exception as e:
                    log.warning(f"<name> notify {obj.key} failed: {e}")

                # 2. Wire bias_events (fail-safe interne mais wrap par sécurité)
                try:
                    r = wire_bias_trigger([{...}])
                    stats["wired"] += r.get("opened", 0)
                    # Récupère bias_event_id pour lien audit
                    bias_event_id = _get_latest_open_bias_id(obj.key)
                except Exception as e:
                    log.error(f"<name> wire raised on {obj.key}: {e}")

            # 3. Audit row à CHAQUE évaluation (no_change inclus)
            storage.insert_<name>_alert(
                key=obj.key, status=new_status, metric=cls["metric"],
                notified=notified_flag, transition=transition,
                bias_event_id=bias_event_id,
            )
        except Exception as e:
            log.warning(f"<name>: {obj.key} failed: {e}")
            stats["errors"] += 1
            continue
    return stats
```

### 4. Job daily dans `bot/jobs/daily.py`

```python
async def daily_<name>_check_job():
    """Cron quotidien : détection transitions + notify + wire."""
    log.info("Daily <name> check starting")
    try:
        from intelligence import <name>_monitor as _m
        out = _m.check_all_<name>_transitions()
        log.info(f"<name>_check : {out}")
    except Exception as e:
        log.error(f"daily_<name>_check failed: {e}")
```

### 5. Intégration `bot/jobs/sequences.py` étape 4 monitors

```python
await _safe_run("<name>_check", daily_<name>_check_job)
```

---

## Tests obligatoires (~7 tests minimum)

Dans `tests/test_<name>_monitor.py` :

1. **Transition actionable** : nouvelle transition → 1 notify, 1 wire, 1 audit row avec bias_event_id.
2. **État stable** : 2e cycle avec même état → 1 audit row `no_change`, 0 notify, 0 wire.
3. **Transition retour à dormant** : audit row seulement, pas de notify (rien à annoncer).
4. **TEST CRITIQUE L4** : bias_event force à `resolved` (simule +30j), position toujours dans l'état déclenché → no_change, **pas de re-fire spurieux**. C'est le test qui démontre le découplage.
5. **Cas dégénéré** : aucun objet en périmètre → stats vides, 0 audit, 0 wire.
6. **Fail-safe** : 1 ligne buggée (raise MissingDataError) → comptée en `errors`, les autres lignes continuent.
7. **classify pure** : missing data → raise MissingDataError (jamais None), non-classifiable légitime → None.

Et dans `tests/test_<name>_wire.py` ou intégré :
- Wire post-notify : transition → ouvre 1 candidat bias_event avec bon ref stable.
- Idempotence cross-cycle : 2 appels même `(obj, action, ref)` → kept, pas supersede.
- Fail-safe : `wire_bias_trigger` mocked-to-raise → caller survit.

---

## Checklist pré-PR

- [ ] Migration alembic créée (numéro suivant) + `created_at DEFAULT`
- [ ] Helpers `insert_<name>_alert` + `get_latest_<name>_per_key` dans storage
- [ ] `classify_<obj>` raise MissingDataError sur missing data critique (jamais None silencieux)
- [ ] `_prev_status_for_<name>` lit le journal dédié, **pas** bias_events
- [ ] Audit row inserted à chaque évaluation (no_change inclus, pas seulement transitions)
- [ ] Wire post-notify dans le bloc transition (instant T fidèle)
- [ ] Ref stable choisi avec discernement (cf L1 : pas paramétré sur valeur volatile)
- [ ] 7 tests minimum dont le **TEST CRITIQUE L4** (résolu-mais-toujours-déclenché)
- [ ] Job daily + intégration sequences.py
- [ ] Module ajouté à `ALLOWED_FILES` du `test_db_write_discipline.py` si écrit DB
- [ ] Smoke test manuel : lancer le job sur le vrai book, observer 1er notify
