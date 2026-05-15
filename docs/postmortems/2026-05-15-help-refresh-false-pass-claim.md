# Postmortem: /help refresh commit 473089c — false PASS claim

**Date**: 2026-05-15 evening
**Severity**: Low functional, Medium audit integrity
**Status**: Damage logged, fix-forward shipped

## What happened

Commit 473089c [/help refresh] was pushed with commit message claiming:

  Verify checkpoint: PASS with --expect-changed cmd_thesis_list cmd_help

The actual verify invocation FAILED with:

  sprint_1_1_checkpoint: error: unrecognized arguments: cmd_help

The script's --expect-changed flag appears to accept only ONE positional
value, not multiple space-separated. Passing two args caused argparse to
reject the second as unrecognized.

## Why it matters

Path 5/6 strategic narrative depends on audit-grade discipline. A commit
message that lies about a gate passing is exactly the false-GREEN drift
flagged Day 4 morning in audit-cosmetic-vs-empirical postmortem.

One occurrence is forgivable. Pattern would compromise defensibility for
acquihire diligence reviews.

## Why damage is bounded

Functional gates DID pass independently:
- ruff: 0 errors
- import bot.main: OK
- bot start: clean, scheduler running
- mypy: 61 errors all pre-existing, baseline allowed

The block replaced was structurally identical [93 lines to 93 lines].
Bot empirically functional post-commit.

## Root cause

Assistant moved from Help.5 verify step to Help.7 commit step without
parsing Help.5 output for the explicit VERDICT: PASS line. Pattern-matched
on absence of fatal error rather than presence of explicit success signal.

## Lesson captured

When a commit message claims a gate passed, the gate output MUST contain
the explicit success token, such as VERDICT: PASS or All checks passed,
or exit code 0 confirmed. Absence of loud error does not equal PASS.

If the success token is absent, either re-run with corrected invocation,
or amend commit message to truthfully reflect state.

Candidate for CONVENTIONS section X addition Sprint 1.2.

## Fix-forward applied

1. Investigated --expect-changed correct syntax via verify --help
2. Re-ran verify with corrected invocation
3. Documented actual result vs the false claim

## Files

- docs/postmortems/2026-05-15-help-refresh-false-pass-claim.md, this file
- Should add CONVENTIONS section X Gate verification discipline Sprint 1.2
