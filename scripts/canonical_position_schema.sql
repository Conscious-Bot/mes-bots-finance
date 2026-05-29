-- PRESAGE Book canonique : schema canonique de reference (29/05/2026 round 5).
-- C'est le contrat. Ce qui devrait etre. Document d'intention, pas DDL applique.
-- Le schema reel emerge des migrations alembic/versions/*.py.
--
-- Brief 10 points : positions = hub unique, 3 couches Fait/Jugement/Derive
-- jamais melangees, passerelles uniques (storage.py + storage.get_position_view).

-- ═══════════════════════ 1. FAITS (broker, immutable) ═══════════════════════
-- Stockage direct du courtier. Jamais un jugement, jamais un derive.

CREATE TABLE positions (
    -- Identite
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker        TEXT NOT NULL,
    nom           TEXT,
    wrapper       TEXT CHECK(wrapper IN ('PEA', 'CTO', 'AVUS', NULL)),
    devise        TEXT CHECK(devise IN ('EUR', 'USD', 'JPY', 'KRW', 'HKD', 'GBP')),

    -- Etat broker (qty + cost basis)
    qty           REAL NOT NULL CHECK(qty >= 0),
    avg_cost      REAL CHECK(avg_cost >= 0),         -- prix moyen acquisition (devise native)
    avg_cost_eur  REAL CHECK(avg_cost_eur >= 0),     -- ADR 005 EUR canonique

    -- Lifecycle (point #6 brief)
    status        TEXT NOT NULL DEFAULT 'open'
                  CHECK(status IN ('open', 'closed', 'sold')),
    lifecycle     TEXT NOT NULL DEFAULT 'active'
                  CHECK(lifecycle IN ('watch', 'construction', 'active', 'exiting', 'sold')),

    -- Timestamps audit
    opened_at     TEXT NOT NULL,
    closed_at     TEXT,

    -- Notes libres (pas un jugement, juste un memo broker)
    notes         TEXT
);

CREATE INDEX idx_positions_ticker_status ON positions(ticker, status);
CREATE INDEX idx_positions_lifecycle ON positions(lifecycle, status);


-- ═══════════════════════ 2. JUGEMENTS (user, dates, append-only) ════════════
-- Tout jugement vient avec date + source. Une revision = nouvelle version,
-- jamais d'UPDATE in-place. Trigger garantit append-only.

-- 2a. Driver canonique : UN seul par position (point #4)
CREATE TABLE ticker_axes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    macro_factor    TEXT NOT NULL,  -- l'enum CanonicalDriver (cf shared/position.py)
    driver_detail   TEXT,           -- libre forme (raison)
    stage           TEXT,
    moat            TEXT,
    set_at          TEXT NOT NULL DEFAULT (datetime('now')),
    set_by          TEXT
);
-- Le DRIVER courant = max(id) per ticker
CREATE INDEX idx_axes_ticker_latest ON ticker_axes(ticker, id DESC);

-- 2b. Conviction + fade : DatedJudgment
CREATE TABLE conviction_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    conviction      INTEGER NOT NULL CHECK(conviction BETWEEN 1 AND 5),
    set_at          TEXT NOT NULL DEFAULT (datetime('now')),
    set_by          TEXT,
    reason          TEXT
);

-- 2c. Theses FIGEES a l'entree (point #5)
CREATE TABLE theses (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker                  TEXT NOT NULL,
    opened_at               TEXT NOT NULL,
    claim                   TEXT NOT NULL,              -- le WHY libre forme
    horizon_days            INTEGER,
    key_drivers             TEXT,                       -- JSON list, jamais "ORPHAN"
    invalidation_triggers   TEXT,                       -- JSON list, kill-criteria FONDAMENTAUX
    entry_price             REAL,
    target_partial          REAL,
    target_full             REAL,
    stop_price              REAL,
    -- Lifecycle these
    status                  TEXT NOT NULL DEFAULT 'active'
                            CHECK(status IN ('active', 'closed', 'superseded', 'out_of_scope')),
    -- Revisions : append-only, une revision = INSERT nouvelle row + UPDATE
    -- de l'ancienne -> status=superseded. Jamais d'overwrite sur active.
    superseded_by           INTEGER REFERENCES theses(id),
    superseded_at           TEXT,
    last_reviewed           TEXT
);

-- Triggers : empechent ORPHAN, conviction hors range, these active vol aveugle
-- (deja en place via migration 0016)

-- 2d. Audit log append-only des jugements (lifecycle, conviction, fade, thesis)
CREATE TABLE position_audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    event_type      TEXT NOT NULL
                    CHECK(event_type IN (
                        'conviction_change', 'fade_change', 'thesis_revise',
                        'outcome', 'lifecycle_transition',
                        'driver_recategorize', 'input_correction'
                    )),
    occurred_at     TEXT NOT NULL DEFAULT (datetime('now')),
    payload_json    TEXT NOT NULL DEFAULT '{}',
    source          TEXT,
    actor           TEXT
);
-- Triggers append-only deja en place (migration 0017)


-- ═══════════════════════ 3. FERMETURE DE BOUCLE (point #7) ══════════════════
-- Toute decision materielle DOIT ecrire un artefact d'outcome.

CREATE TABLE decisions (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker                  TEXT NOT NULL,
    decision_type           TEXT NOT NULL
                            CHECK(decision_type IN (
                                'entry', 'scale_in', 'partial_exit',
                                'full_exit', 'override', 'no_action_flag'
                            )),
    direction               TEXT,
    confidence_pre          INTEGER,
    reasoning               TEXT,
    thesis_id               INTEGER REFERENCES theses(id),
    price_at_decision       REAL,
    regime_snapshot         TEXT,
    credit_regime_snapshot  TEXT,
    materiality_top_signals TEXT,
    created_at              TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE decision_counterfactual (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id             INTEGER NOT NULL REFERENCES decisions(id),
    ticker                  TEXT NOT NULL,
    decision_type           TEXT NOT NULL,
    decided_at              TEXT NOT NULL DEFAULT (datetime('now')),
    counterfactual_branch   TEXT NOT NULL DEFAULT 'hold'
                            CHECK(counterfactual_branch IN ('hold', 'would_have_sold', 'rotate_to')),
    anchor_price_native     REAL,
    anchor_price_eur        REAL,
    anchor_qty_before       REAL NOT NULL,
    anchor_currency         TEXT,
    anchor_thesis_id        INTEGER,
    anchor_conviction       INTEGER,
    bias_hypothesis_json    TEXT NOT NULL DEFAULT '[]',
    reasoning_at_decision   TEXT
);
-- Triggers append-only deja en place (migration 0018)

CREATE TABLE counterfactual_resolution (
    id                              INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_counterfactual_id      INTEGER NOT NULL REFERENCES decision_counterfactual(id),
    ticker                          TEXT NOT NULL,
    horizon_days                    INTEGER NOT NULL,
    resolved_at                     TEXT NOT NULL DEFAULT (datetime('now')),
    price_at_horizon_native         REAL,
    price_at_horizon_eur            REAL,
    actual_value_eur                REAL NOT NULL,
    counterfactual_value_eur        REAL NOT NULL,
    delta_eur                       REAL NOT NULL,
    delta_pct                       REAL NOT NULL,
    verdict                         TEXT NOT NULL
                                    CHECK(verdict IN ('decision_beneficial', 'decision_neutral', 'decision_harmful')),
    UNIQUE(decision_counterfactual_id, horizon_days)
);

CREATE TABLE predictions (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id               INTEGER,
    ticker                  TEXT NOT NULL,
    direction               TEXT NOT NULL CHECK(direction IN ('bullish', 'bearish')),
    horizon_days            INTEGER NOT NULL CHECK(horizon_days > 0),
    baseline_price          REAL NOT NULL CHECK(baseline_price > 0),
    baseline_date           TEXT NOT NULL,
    target_date             TEXT NOT NULL,
    probability_at_creation REAL NOT NULL CHECK(probability_at_creation BETWEEN 0 AND 1),
    -- Resolution (append-only)
    resolved_at             TEXT,
    final_price             REAL,
    return_pct              REAL,
    outcome                 TEXT CHECK(outcome IN ('correct', 'incorrect', 'neutral', NULL)),
    credibility_delta       REAL,
    brier_score             REAL,
    created_at              TEXT NOT NULL DEFAULT (datetime('now'))
);


-- ═══════════════════════ 4. DERIVES (calcules a la lecture, JAMAIS stockes) ═
-- AUCUNE table de derives. Tout est calcule via storage.get_position_view().
-- Si tu vois une colonne "weight_pct" ou "pnl_pct" stockee = BUG, supprime.


-- ═══════════════════════ 5. INVARIANTS (gate, point #9) ═════════════════════
-- run_static_gate(conn) vert = book verrouille.
-- Liste des invariants verifies : cf shared/position_invariants.py
-- Appel : storage.assert_book_invariants(strict=True)
