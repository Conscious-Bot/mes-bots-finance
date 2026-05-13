# ADR 001 — Point-in-Time Bitemporal Credibility Ledger

**Status**: Proposed
**Date**: 2026-05-13
**Decision-makers**: Olivier Legendre
**Context**: Phase Solidification post-marathon Day 2, Path 5/6 strategic mode

---

## 1. Context — Pourquoi cette décision

### 1.1 Symptôme observé

Le credibility ledger (`sources.credibility`), le materiality score (`signals.impact_magnitude / reversibility / time_to_realization`), et les half-life metrics sont **overwritten en place** à chaque update.

Concrètement :
```sql
UPDATE sources SET credibility = MAX(0, MIN(1, credibility + ?)) WHERE id = ?
```

Ce pattern est correct pour l'opérationnel courant mais **détruit toute trace historique**.

### 1.2 Questions impossibles à répondre aujourd'hui

1. **Backtest** : "Quelle était la credibility de SemiAnalysis le 1er juin 2026 ?" → impossible
2. **Audit Path 5/6** : "Montre-moi l'évolution mesurée de la calibration de mes 5 Tier S sur 12 mois" → impossible
3. **Drift detection** : "Le composite materiality de Chamath a-t-il drifté progressivement ou step-changed après un model upgrade ?" → impossible
4. **What-if** : "Si j'avais utilisé le credibility recalibré tel qu'il était à T-90j, mes décisions auraient-elles été différentes ?" → impossible
5. **Reconciliation** : "Quand exactement le credibility de cette source est-il passé de 0.5 à 0.6 ?" → impossible

### 1.3 Blocage critique pour Path 5/6

**Path 5 (acquihire)** : un acquéreur scrute `git log` + database history. "Voici l'évolution traçable de mon jugement sur 18 mois" >> "voici ma table de current state".

**Path 6 (Substack)** : la calibration plot publique requiert des snapshots de credibility/Brier across time, pas just current values. Sans bitemporality, le track record narrative est plat.

### 1.4 Pression empirique immédiate

- KPI #2 timer J+28 commence le 10 juin avec 40 resolutions batch
- KPI #3 Brier rolling 90d ne peut être calculé proprement sans snapshots de prédictions à différents temps de leur cycle
- credibility recalibration cron mensuel (`brier_recal 1st 6h`) overwrite sources.credibility chaque 1er du mois → on perd la trajectoire mensuelle

---

## 2. Decision

Adopter un **modèle bitemporal append-only** pour les entités critiques au track record :

### 2.1 Entités candidates (priority order)

| Entité | Pourquoi bitemporal | Volume écriture estimé |
|---|---|---|
| `sources.credibility` | Path 5/6 calibration narrative | ~30 sources × 1 update/mois = 360/an |
| `sources.half_life_days` | Source decay calibration drift | ~30 × quarterly = 120/an |
| `signals` materiality rubric | LLM model drift detection | ~60/jour × 365 = 22K/an |
| `theses.conviction` | Decision audit (where conviction was when sold) | ~10/mois = 120/an |
| `predictions.brier_score` | Already append-only (resolved_at) | déjà ok |

### 2.2 Bitemporal schema pattern

Pour chaque entité versionnée, deux colonnes temporelles :

```sql
CREATE TABLE sources_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    
    -- Snapshot data (mirror of mutable columns)
    credibility REAL NOT NULL,
    n_signals INTEGER,
    n_correct INTEGER,
    half_life_days REAL,
    
    -- Bitemporal columns
    valid_from TEXT NOT NULL,         -- when this value became true in the world
    valid_to TEXT,                    -- when this value stopped (NULL = current)
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,  -- transaction time (when we learned/wrote)
    
    -- Metadata
    change_reason TEXT,               -- 'brier_recal', 'manual_override', 'auto_increment', 'backfill'
    
    UNIQUE(source_id, valid_from)
);

CREATE INDEX idx_sources_history_lookup ON sources_history(source_id, valid_from, valid_to);
CREATE INDEX idx_sources_history_current ON sources_history(source_id) WHERE valid_to IS NULL;
```

### 2.3 Two-time semantics rigoureuses

- **`valid_from` / `valid_to`** : le temps DU MONDE. "Cette credibility était vraie entre T1 et T2."
- **`created_at`** : le temps DE LA TRANSACTION. "On a écrit cette ligne à T3, qui peut être après T1 (backfill)."

Pour le bot personnel, les deux coïncident généralement (on apprend en temps réel). Mais :
- Backfill historique (e.g. recompute credibility from past predictions) → `valid_from < created_at`
- Correction de bug retroactive → idem

### 2.4 Query "as of date T"

```sql
-- Credibility de source X à instant T
SELECT credibility FROM sources_history
WHERE source_id = ?
  AND valid_from <= ?
  AND (valid_to IS NULL OR valid_to > ?)
ORDER BY valid_from DESC LIMIT 1;

-- Évolution credibility d'une source sur 12 mois
SELECT valid_from, valid_to, credibility, change_reason
FROM sources_history
WHERE source_id = ?
  AND valid_from >= datetime('now', '-12 months')
ORDER BY valid_from;
```

### 2.5 Write pattern (Python helper)

```python
def update_credibility_versioned(source_id, new_value, change_reason, valid_from=None):
    """Append-only update: close previous row, insert new row."""
    valid_from = valid_from or datetime.now().isoformat()
    with db() as conn:
        # Close previous current row
        conn.execute(
            "UPDATE sources_history SET valid_to = ? "
            "WHERE source_id = ? AND valid_to IS NULL",
            (valid_from, source_id)
        )
        # Insert new current row
        conn.execute(
            "INSERT INTO sources_history (source_id, credibility, valid_from, change_reason) "
            "VALUES (?, ?, ?, ?)",
            (source_id, new_value, valid_from, change_reason)
        )
        # Also update the canonical sources table (for fast "current" reads)
        conn.execute(
            "UPDATE sources SET credibility = ? WHERE id = ?",
            (new_value, source_id)
        )
```

Note : on garde `sources.credibility` comme **cache de la current value** pour éviter de JOIN à chaque lecture chaude. Le history est la source-of-truth, le current est l'index.

---

## 3. Consequences

### 3.1 Bénéfices

| Bénéfice | Path 5/6 value |
|---|---|
| Backtest credibility ledger possible | Validation rigoureuse du système |
| Calibration plot dynamique (credibility vs time, par source) | Path 6 publishable artifact |
| Drift detection automatique (step vs smooth change) | Engineering credibility |
| Audit "decisions consistent with credibility at T" | Path 5 acquéreur due diligence |
| Reconcile manual overrides vs auto updates | Operational hygiene |
| Replay scenarios "if I'd had today's info at T" | Counterfactual analysis |

### 3.2 Coûts

| Coût | Mitigation |
|---|---|
| Schema complexity ×2 tables pour entités tracked | Confiner à 3-4 entités critiques, pas all |
| Storage growth proportionnel aux writes | 22K rows/an signals_history = ~10MB/an, négligeable |
| Code complexity dans update paths | Wrapper helper functions centralisées |
| Migration des données existantes | One-shot script avec valid_from = now() |
| Risk de désynchronisation cache-vs-history | Tests + invariants (history.current row credibility == sources.credibility) |

### 3.3 Risques résiduels

- **Backfill ambiguity** : si je recalibre credibility à T0 avec données jusqu'à T1, quel valid_from utiliser ? T0 (when world value was first true) ou T1 (when computed) ?
  - Convention proposée : `valid_from = T0` (world time), `created_at = T1` (transaction time). Différenciation explicite.

- **Concurrent writes** : deux process updatent credibility simultanément → race. Mitigé par SQLite WAL + transaction atomique (already implemented).

- **Trigger temptation** : SQLite triggers automatiques pour mirror sources → sources_history seraient élégants mais cachés. Préférer Python helpers explicites pour traçabilité.

---

## 4. Alternatives considered

### Alt A — Generic audit_log table

```sql
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY,
    table_name TEXT, row_id INTEGER,
    column_name TEXT, old_value TEXT, new_value TEXT,
    changed_at TEXT
);
```

**Pros** : généralise pour any table, simple schema unique.
**Cons** : 
- Query "credibility at T" requiert joins/aggregations complexes
- Pas de bitemporal (valid time vs transaction time confondus)
- Denormalized (everything stringified)

**Rejected** : trop générique pour les use cases prioritaires (calibration plot, drift detection).

### Alt B — Version column + is_current flag

```sql
ALTER TABLE sources ADD COLUMN version INTEGER DEFAULT 1;
ALTER TABLE sources ADD COLUMN is_current INTEGER DEFAULT 1;
-- New row per update with version++, set previous is_current=0
```

**Pros** : single table, simple to query "current" (`WHERE is_current=1`).
**Cons** :
- "As-of T" requires sorting by version + filtering
- Pas de valid_from/to → temps flou
- Joints aux signaux/predictions deviennent fragiles (FK to which version?)

**Rejected** : pas de temporal semantics rigoureuse.

### Alt C — Event sourcing total

Stocker uniquement les EVENTS (credibility_delta_applied, source_recalibrated, ...) et reconstruire current state on-the-fly.

**Pros** : log d'événements pur, replay native.
**Cons** :
- Reconstruction state cher pour every read
- Migration depuis schéma actuel = rewrite total
- Overkill pour un bot solo

**Rejected** : surcomplique le bot personnel-scale.

### Alt D — Status quo (overwrite in place)

**Pros** : simple, fast.
**Cons** : ce qui motive cet ADR.

**Rejected** par définition.

---

## 5. Implementation plan (phased, non-blocking)

### Phase 1 — Schema + helpers (~2h)
- Create `sources_history` table
- Implement `update_credibility_versioned(source_id, new_value, change_reason)`
- Implement `get_credibility_as_of(source_id, timestamp)`
- Add Hypothesis tests for "current row == canonical sources.credibility" invariant

### Phase 2 — Migration (~30min)
- Migration script: pour chaque source actuelle, insert 1 row dans sources_history avec valid_from = sources.created_at, credibility = current value, change_reason = 'migration_baseline_2026-05-13'

### Phase 3 — Production wiring (~1h30)
- Replace `storage.update_credibility(source_id, delta)` calls to use versioned wrapper
- Add to `recalibrate_source_credibility_from_brier` (cron mensuel)
- Add to `apply_feedback(signal_id, rating)` (intelligence/credibility.py)

### Phase 4 — Extension aux signals materiality (~2h)
- Schema `signals_materiality_history` (impact_magnitude, reversibility, time_to_realization snapshots)
- Wire dans materiality_v2.persist_breakdown

### Phase 5 — Query helpers + reporting (~1h)
- `/credibility_trajectory SOURCE` handler : credibility evolution chart ASCII
- Weekly cron : detect anomalous drift (step change >0.05 in 7d)

### Phase 6 — Calibration plot prep (~2h, post J+90)
- Build SQL for "credibility distribution over time"
- Export to Substack-publishable format

**Total estimated effort** : ~10h sur 4-6 semaines. Non bloquant, ship par phases.

---

## 6. Trigger d'activation

Lancer **Phase 1+2** quand au moins une des conditions est vraie :
- KPI #2 satisfait (≥5 predictions résolues, premier batch Brier exploitable)
- Premier credibility recalibration mensuel cron tourné (1er juin)
- Manual override de credibility appliqué (signal qu'on perd info utile)

Pour now (13 mai) : **ADR adopté, implementation déferrée à juin** pour ne pas créer de complexity prématurément.

---

## 7. Success criteria

ADR considéré "implémenté avec succès" quand :
- `/credibility_trajectory SemiAnalysis` retourne 6+ data points sur 90 jours
- Calibration plot publique générable from `sources_history` join `predictions`
- Audit "decisions cohérentes avec credibility at T" runnable
- Drift detection cron alert sur step changes >0.05

---

## 8. References

- Bitemporal data modeling, Snodgrass C.J. (academic reference)
- AWS Aurora bi-temporal queries (similar pattern in managed DBs)
- Mémoire entry #7 : "PIT absent bloque backtest" — was flagged as P1 dette le 13 mai matin

---

## 9. Decision log

| Date | Décision | Rationale |
|---|---|---|
| 2026-05-13 | ADR drafted, status=Proposed | Critique Day 2 marathon a identifié l'absence de PIT comme dette critique #3 |
| 2026-05-13 | Implementation deferred to juin 2026 | Pas de pressing need avant premier batch resolution (J+28 = 10 juin) |
| (future) | Phase 1 launch | Trigger: KPI #2 satisfait OU 1er recal mensuel cron |

