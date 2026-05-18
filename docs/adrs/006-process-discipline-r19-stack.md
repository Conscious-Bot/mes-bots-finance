# ADR 006 — Process Discipline: R19 v2-v5 Stack for Bash Shipping

**Status**: Accepted (Day 12, 18 May 2026)
**Author**: Olivier Legendre (with Claude as code partner)
**Cross-references**: CONVENTIONS.md Section 16; failure_modes.md FM-9/10/11/12; ADR 004 USD canonical migration.

---

## Context

mes-bots-finance ships substantive technical work via long-running bash subshells executed in **zsh** (macOS interactive session). Day 11+12 marathon (~15h cumulative across two days, 22 commits + this ADR) revealed multiple instances where naive bash shipping patterns silently produced broken state. Each violation became a durable system improvement.

### Empirical failures Day 11+12

**Failure 1 — FM-9 zsh subshell pipefail unreliability (Day 11, dfd9e0e)**
Pattern `(set -eo pipefail; cmd | tail) || echo "abort"` was expected to abort on pipeline non-zero exit. Empirically did not — the subshell continued and `|| echo` never fired. Root cause: zsh `pipefail` interaction with `()` subshell did not propagate intermediate command failure reliably.

**Failure 2 — R14 v2 substring contamination (Day 12 Step 1, 094f33d)**
Check `if 'currency=Currency.USD' in src` returned true after the first patch in a batch, causing subsequent patches in the same bash to skip with false-positive "already done" status. Root cause: global `in src` matched substrings from sibling patches in the same bash transaction.

**Failure 3 — Step 2A silent partial failure (Day 12 a9c3adf)**
A bash applying 4 portfolio_views.py patches printed "WARNING: pattern not matched" for 3 of them, then continued to gates (which passed on unchanged source), then committed. Net: commit landed with 1 of 4 patches actually applied. Root cause: AST verify section observed marker count = 0 but only printed, did not raise.

**Failure 4 — FM-12 zsh set-e bypass on python3 heredoc (Day 12 c4eb24e)**
Bash with `(set -eo pipefail; python3 << PYEOF ... raise SystemExit(1) ... PYEOF; later_cmd; commit)` did not abort on python3 non-zero exit. Section B raised SystemExit on pattern mismatch; Section C raised on R19 v4 gate failure. Bash continued through D/E/F, committed 2ef6c73 with ONLY R19 v4 codification — the patches it was supposed to land still missing. Root cause: zsh `set -e` does not reliably propagate non-zero exit from heredoc commands in subshells.

**Failure 5 — Pattern matching brittleness (Day 12 Step 2A)**
Heredoc patches used Unicode escape sequences (typed as backslash + U + hex codepoint) for emoji chars while file source contained the literal emoji UTF-8 bytes (📊, 🎯). Pattern bytes did not match file bytes; str.replace returned source unchanged. R17 codified: live-read file lines via Path.read_text + splitlines, use the live line as str.replace pattern.

**Failure 6 — Display-layer coupling miss (Day 11)**
Centralized formatter refactor (display.py kwarg extension) was started before consumer audit. Day 11 audit caught that `CANONICAL_FINANCE=EUR` constant + explicit migration doctrine meant Batch 4A/4B USD values passed to `format_finance` would render with EUR symbol on restart. R20 codified: display-layer forensic before centralized refactor.

### Compounded effect

Six discipline violations Day 11+12. Each could have shipped a commit with broken state (display anomaly, false-positive completion, lost patches). Without systematic gates, the marathon would have shipped multiple compromised commits requiring forensic rollback. With each violation, the system hardened. Day 11+12 closed with `day12-close` tag on:

- 270 tests passing (Hypothesis property-based + smoke + integration)
- 0 mypy errors on 16 strict-typed modules
- 0 ruff errors codebase-wide
- ADR 004 daily-usage scope complete with empirical smoke verification
- 12 failure modes codified (FM-1 to FM-12)
- R19 stack v2 through v5 + R14 v2 + R17 + R20 codified in CONVENTIONS.md

---

## Decision

Adopt the **R19 v2-v5 stack** as the canonical bash shipping pattern for all discipline-critical work. zsh `set -e` is never trusted to propagate failure. Every gate captures rc explicitly.

### R19 stack definition

**R19 v2 — pytest + mypy gates (Day 11, FM-9 mitigation)**

```bash
pytest -q > /tmp/pt 2>&1 && rc=0 || rc=$?
if [ "$rc" -ne 0 ]; then
    tail -15 /tmp/pt
    echo "===== ABORT — pytest ====="
    exit 1
fi
echo "  pytest GREEN"

mypy <typed_modules> > /tmp/mypy 2>&1 && rc=0 || rc=$?
err_count=$(grep -cE 'error:' /tmp/mypy 2>/dev/null)
err_count=${err_count:-0}
if [ "$err_count" -gt 0 ]; then tail -10 /tmp/mypy; exit 1; fi
echo "  mypy GREEN: 0 errors"
```

**R19 v3 — ruff added (Day 12 Step 1.5)**

Same explicit rc pattern for ruff lint. Order: ruff (cheap, fast) → pytest → mypy.

```bash
ruff check . > /tmp/ruff 2>&1 && rc=0 || rc=$?
if [ "$rc" -ne 0 ]; then cat /tmp/ruff; exit 1; fi
echo "  ruff GREEN"
```

**R19 v4 — AST function-scoped marker count gate (Day 12 Step 2A.5)**

After any batch of pattern-replace patches, an AST gate asserts expected marker count per function. Mismatch = explicit `sys.exit(1)`.

```python
expectations = {
    'function_to_patch_1': expected_marker_count,
    'function_to_patch_2': expected_marker_count,
    'function_intentionally_not_patched': 0,  # explicit declaration
}
failures = []
tree = ast.parse(src)
for fn, expected in expectations.items():
    found = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn:
            body = '\n'.join(src.splitlines()[node.lineno-1:node.end_lineno])
            actual = body.count(MARKER)
            if actual != expected:
                failures.append(f"{fn}: expected {expected}, got {actual}")
            found = True
            break
    if not found:
        failures.append(f"{fn}: function not found")
if failures:
    sys.exit(1)
```

Functions intentionally not patched MUST declare `expected=0` — DECLARATION of intent, not silent default. Multi-marker variant possible (present/absent assertions per function — see Day 12 Step 2B morning_brief retrofit).

**R19 v5 — explicit rc check for ALL commands incl. python3 heredocs (Day 12 c4eb24e, FM-12 mitigation)**

Every discipline-critical command — including python3 heredocs and the R19 v4 gate itself — uses the explicit pattern:

```bash
cmd > /tmp/out 2>&1 && rc=0 || rc=$?
if [ "$rc" -ne 0 ]; then
    cat /tmp/out
    echo "===== ABORT — context (rc=$rc) ====="
    exit 1
fi
```

This is the **terminating rule** of the R19 stack. Apply to every command whose failure should abort the bash.

### Supporting rules (Section 16 CONVENTIONS.md)

**R14 v2** — Function-scoped AST check for "already patched" detection. Replace global `if marker in src` with AST function-scoped check via `ast.walk` + line range. Prevents substring contamination from sibling patches in same bash transaction.

**R17** — Live-read file content for fragile patterns. When pattern includes Unicode/emoji literals or formatting that may differ between forensic dump and file source, read the line via `Path.read_text() + splitlines()` and use the live line as str.replace pattern.

**R20** — Display-layer forensic before centralized formatter refactor. Audit every consumer call site before refactoring a centralized formatter (e.g. display.py format_finance). Refactor must preserve backward compat (default kwarg) and explicitly migrate consumers via separate commits.

### Guarantees

After bash completes successfully under R19 v2-v5:
- All linting passes (ruff)
- All tests pass (pytest)
- All type checks pass (mypy strict-typed)
- All declared patches actually landed (AST marker count)
- No silent failures from zsh quirks (every command rc-checked)

After bash fails under R19 v2-v5:
- No commit was made (gates abort before `git commit`)
- The exact failure is visible (cat /tmp/out + abort message)
- No partial side effects from earlier steps need rollback

---

## Consequences

### Positive

1. **Reliability over verbosity**. Bash patterns are 3-5x longer than naive `set -e` reliance, but they reliably abort on any failure. Net: less time on forensic rollback after silent failures.

2. **Compound learning**. Six discipline violations Day 11+12 produced six durable system improvements (R19 v3, v4, v5 + R14 v2 reinforced + R17 + R20 + FM-9, FM-12 codification). Codebase grew stronger with each violation, not weaker.

3. **Path 5/6 defensibility**. An auditor reviewing the codebase sees systematic process discipline:
   - CONVENTIONS.md Section 16 with versioned rules R1-R20
   - failure_modes.md with 12 documented FMs and mitigations
   - This ADR explaining the rationale
   - Empirical commits showing each rule applied (c4eb24e, a25ed81, aa6976e use R19 v5 stack)
   
   Not vibe coding. Engineering discipline visible in artifact form.

4. **Reproducibility**. Future Claude+Olivier sessions ship under the same stack without re-deriving lessons. CONVENTIONS.md is canonical reference.

### Negative

1. **Verbosity**. Each discipline-critical bash 3-5x longer than naive form. Mitigated by codification — pattern is mechanical to apply once internalized.

2. **Cognitive overhead**. Five gates per ship. Mitigated by templates in CONVENTIONS.md.

3. **zsh-specific scope**. R19 stack is zsh-shipping-specific. CI uses bash with `set -euo pipefail` which works there; R19 stack is for local interactive zsh shipping.

---

## Alternatives considered

### 1. `#!/bin/bash` shebang on shipping bashes
**Rejected**. Olivier's interactive session is zsh. Switching shebang adds invocation friction (need `bash script.sh` vs paste-in-zsh). Local development should not depend on a specific shell selection at runtime.

### 2. Python orchestration script (scripts/ship.py)
**Rejected**. Increases scope (write + maintain harness), reduces visibility of individual steps in chat (output buffered through harness), harder to iterate. R19 stack achieves same reliability with native bash Olivier can read and modify in-flight.

### 3. Aggressive `set -euo pipefail` reliance
**Rejected — empirically falsified**. Day 11+12 proved zsh `set -e` unreliable for subshell heredoc commands (FM-12) and pipefail (FM-9). Explicit rc check is minimum-change maximum-reliability path.

### 4. Single-step bash per commit
**Rejected**. Many ships are intrinsically multi-step (diagnostic → patch → gate → commit). Forcing one-step-per-bash would require interleaved Olivier copy-paste, breaking flow.

The chosen path — multi-step bash with explicit rc gate at each step — preserves flow AND adds reliability.

---

## Migration

Already applied. All Day 12 commits c4eb24e onward use R19 v5 pattern. Backward-incompatible no-op for prior commits.

Forward: every new discipline-critical bash MUST follow R19 v5 stack. Reviewers (Olivier, Claude, future collaborators) reject bashes relying on `set -e` for propagation.

---

## References

- CONVENTIONS.md Section 16 (R1-R20)
- docs/failure_modes.md: FM-9 (pipefail), FM-10 (enrich_with_live currency mix), FM-11 (drift SQL aggregation), FM-12 (set-e heredoc bypass)
- ADR 004 USD canonical migration (parallel work, used R19 stack throughout Day 12)
- Day 11+12 commits: e8c81cf base → aa6976e day12-close
- HANDOFF.md Day 11 close + Day 12 close sections
