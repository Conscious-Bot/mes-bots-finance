-- KLAC split 10:1 cure — 2026-06-23 (documented post-hoc)
-- ============================================================
--
-- CONTEXTE
-- KL Tencor (KLAC) a subi un split 10:1 le 12/06/2026 (real corporate event,
-- pas un bug yfinance). Trace en DB :
--   tx152 BUY  1.259 sh  @ $1588 USD  date=2026-05-15  (pre-split)
--   tx206 BUY 11.335 sh  @     $0    date=2026-06-12  source=split_klac_10to1_20260612
--
-- BUG
-- Pendant le split mid-thesis, la logique de trigger_partial / trigger_full
-- / trigger_stop a compare des prix scaled differemment (pre-split vs post-
-- split) et fire les 3 a tort sur 06/06, 09/06, 12/06.
--
-- En plus, le NEW schema (entry_value / target_*_value / stop_value en USD)
-- n'a pas ete ÷10 ajuste au moment du split, alors que le OLD schema
-- (entry_price / target_full / stop_price) l'a ete.
--
-- ETAT REEL (verifie 23/06)
-- KLAC live $269.16, position 12.594 sh, avg_cost ~$158, PnL +70% USD.
-- Winner sain dans Semi equipment, pas un stop ni target hit.
--
-- CURE APPLIQUEE
-- (1) NULL les triggered_*_at (artefacts du split)
-- (2) Sync target_*_value + stop_value /= 10 vers OLD schema post-split
-- (3) Update last_price live ($269.16) + last_price_at
-- (4) Note datee dans notes column
--
-- entry_value RESTE 1626.22 (pre-split USD) car L28 + SPEC_MONEY_INVARIANT §3
-- imposent immutability (trigger DB enforce). C'est OK semantically :
-- 1626 USD pre-split × 1.259 sh = 2047 USD ≈ €1814 cost basis original.
-- Post-split equivalent serait 162.62 USD × 12.594 sh = 2048 USD (consistent).
--
-- BACKUP : data/bot.db.backup_klac_cure_20260623_093939
--
-- ============================================================

BEGIN TRANSACTION;

UPDATE theses
SET
    triggered_partial_at = NULL,
    triggered_full_at    = NULL,
    triggered_stop_at    = NULL,
    target_partial_value = 178.884550618808,
    target_full_value    = 200.025550618808,
    stop_value           = 143.108,
    last_price           = 269.16,
    last_price_at        = datetime('now') || '+00:00',
    notes                = COALESCE(notes, '') || char(10) ||
                           '[2026-06-23] split 10:1 (12/06) cure : ' ||
                           'triggered_*_at reset (artefacts split-migration), ' ||
                           'target_*_value + stop_value /= 10 sync OLD post-split, ' ||
                           'last_price refresh live. entry_value=1626.22 reste ' ||
                           'immutable per L28 (= pre-split USD, semantic preserved).'
WHERE ticker = 'KLAC';

-- Assert exactly 1 row touched
SELECT
    CASE WHEN changes() = 1 THEN 'OK'
         ELSE 'ABORT: expected 1 row, got ' || changes()
    END AS verdict;

COMMIT;
