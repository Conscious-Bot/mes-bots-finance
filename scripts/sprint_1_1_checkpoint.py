#!/usr/bin/env python3
"""Sprint 1.1 equivalence checkpoint.

Proves behavior preservation pre/post handler extraction via cryptographic
hashing of top-level function bodies (AST-canonicalized) plus structural counts
and tooling gates (import / ruff / mypy / pytest).

Workflow per chunk N:
    1. Snapshot baseline BEFORE extraction:
         python scripts/sprint_1_1_checkpoint.py snapshot N "pre-<domain>"
    2. Do the cut-paste of handlers from bot/main.py into bot/handlers/<domain>.py
    3. Verify equivalence AFTER extraction:
         python scripts/sprint_1_1_checkpoint.py verify N [--expect-changed f1,f2]
    4. Require VERDICT: PASS before commit.

STRICT mode default: any unexpected function body hash change = FAIL.
Use --expect-changed to allowlist intentional changes (e.g. _append_log_entry
which changes from `parent.parent` to `parents[2]` in chunk 1).
"""

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINES_DIR = REPO_ROOT / "baselines"
BOT_MAIN = REPO_ROOT / "bot" / "main.py"
HANDLERS_DIR = REPO_ROOT / "bot" / "handlers"

PYTEST_EXPECTED_MIN = 119
MYPY_BASELINE = 2


def hash_node(node: ast.AST) -> str:
    """SHA256 (16 hex) of canonicalized source via ast.unparse.

    AST canonicalization strips comments + normalizes whitespace, so cut-paste
    of a function from one file to another preserves the hash. Decorators and
    the def signature are included.
    """
    return hashlib.sha256(ast.unparse(node).encode()).hexdigest()[:16]


def list_source_files() -> list[Path]:
    files = []
    if BOT_MAIN.exists():
        files.append(BOT_MAIN)
    if HANDLERS_DIR.exists():
        files.extend(sorted(HANDLERS_DIR.glob("*.py")))
    return files


def extract_function_hashes(files: list[Path]) -> dict[str, str]:
    """Walk top-level FunctionDef/AsyncFunctionDef in each file. Return {name: hash}.

    Top-level only (tree.body), not ast.walk, to avoid nested/method noise.
    Duplicates across files raise a warning (should not happen in a clean refactor).
    """
    result: dict[str, str] = {}
    locations: dict[str, str] = {}
    for fp in files:
        try:
            tree = ast.parse(fp.read_text())
        except SyntaxError as e:
            print(f"SYNTAX ERROR in {fp.relative_to(REPO_ROOT)}: {e}", file=sys.stderr)
            raise
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in result:
                    print(
                        f"WARN: duplicate top-level def '{node.name}' "
                        f"(first in {locations[node.name]}, also in {fp.relative_to(REPO_ROOT)})",
                        file=sys.stderr,
                    )
                result[node.name] = hash_node(node)
                locations[node.name] = str(fp.relative_to(REPO_ROOT))
    return result


def count_regex_in_main(pattern: str) -> int:
    if not BOT_MAIN.exists():
        return 0
    return len(re.findall(pattern, BOT_MAIN.read_text()))


def count_handler_registrations() -> int:
    return count_regex_in_main(r"CommandHandler\s*\(")


def count_scheduler_jobs() -> int:
    return count_regex_in_main(r"\.add_job\s*\(")


def count_cmd_defs() -> int:
    """Count cmd_* top-level defs across bot/main.py + bot/handlers/*.py."""
    n = 0
    for fp in list_source_files():
        tree = ast.parse(fp.read_text())
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("cmd_"):
                n += 1
    return n


def main_loc() -> int:
    return len(BOT_MAIN.read_text().splitlines()) if BOT_MAIN.exists() else 0


def git_commit() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=REPO_ROOT, timeout=5,
        )
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def run_check(cmd: list[str], timeout: int = 180) -> tuple[bool, str]:
    """Returns (ok, combined_output)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT, timeout=timeout)
        return (r.returncode == 0, r.stdout + r.stderr)
    except FileNotFoundError as e:
        return (False, f"command not found: {cmd[0]} ({e})")
    except subprocess.TimeoutExpired:
        return (False, f"timeout after {timeout}s")
    except Exception as e:
        return (False, str(e))


def cmd_snapshot(args: argparse.Namespace) -> int:
    BASELINES_DIR.mkdir(exist_ok=True)
    files = list_source_files()
    if not files:
        print(f"ERROR: no source files found (looked in {BOT_MAIN}, {HANDLERS_DIR})", file=sys.stderr)
        return 2

    snap = {
        "chunk": args.chunk,
        "label": args.label,
        "captured_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
        "main_py_lines": main_loc(),
        "handler_registration_count": count_handler_registrations(),
        "cmd_def_count": count_cmd_defs(),
        "scheduler_jobs_count": count_scheduler_jobs(),
        "files_scanned": [str(f.relative_to(REPO_ROOT)) for f in files],
        "function_hashes": extract_function_hashes(files),
    }

    fp = BASELINES_DIR / f"sprint-1.1-chunk-{args.chunk}.json"
    fp.write_text(json.dumps(snap, indent=2, sort_keys=True))

    print(f"Snapshot: {fp.relative_to(REPO_ROOT)}")
    print(f"  label: {snap['label']}")
    print(f"  git: {snap['git_commit']}")
    print(f"  files scanned: {len(files)} ({', '.join(f.name for f in files)})")
    print(f"  functions hashed: {len(snap['function_hashes'])}")
    print(f"  handler registrations: {snap['handler_registration_count']}")
    print(f"  cmd_* defs: {snap['cmd_def_count']}")
    print(f"  scheduler jobs: {snap['scheduler_jobs_count']}")
    print(f"  bot/main.py LOC: {snap['main_py_lines']}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    fp = BASELINES_DIR / f"sprint-1.1-chunk-{args.chunk}.json"
    if not fp.exists():
        print(f"ERROR: no baseline at {fp.relative_to(REPO_ROOT)}", file=sys.stderr)
        print("Run snapshot first: python scripts/sprint_1_1_checkpoint.py snapshot N LABEL", file=sys.stderr)
        return 2

    base = json.loads(fp.read_text())
    expected_changed = {s.strip() for s in args.expect_changed.split(",") if s.strip()}

    print(f"=== Verify chunk {args.chunk} ===")
    print(f"Baseline: {base['label']} @ {base['git_commit']} ({base['captured_at']})")
    print(f"Expect-changed allowlist: {sorted(expected_changed) or '(none)'}")
    print()

    failures: list[str] = []
    warnings_: list[str] = []

    cur = extract_function_hashes(list_source_files())
    base_h = base["function_hashes"]
    base_names = set(base_h.keys())
    cur_names = set(cur.keys())

    missing = base_names - cur_names
    added = cur_names - base_names
    common = base_names & cur_names

    unchanged = [n for n in common if base_h[n] == cur[n]]
    changed = [n for n in common if base_h[n] != cur[n]]

    print(f"Functions: {len(unchanged)}/{len(base_names)} unchanged")

    if missing:
        print(f"  MISSING ({len(missing)}): {sorted(missing)}")
        failures.append(f"Functions disappeared: {sorted(missing)}")

    if added:
        print(f"  NEW ({len(added)}): {sorted(added)}")

    if changed:
        unexpected = sorted(n for n in changed if n not in expected_changed)
        expected = sorted(n for n in changed if n in expected_changed)
        if expected:
            print(f"  CHANGED-expected ({len(expected)}): {expected}")
            warnings_.append(f"{len(expected)} expected body change(s) acknowledged")
        if unexpected:
            print(f"  CHANGED-UNEXPECTED ({len(unexpected)}): {unexpected}")
            failures.append(
                f"Unexpected body changes: {unexpected} "
                f"(use --expect-changed if intentional)"
            )

    print()

    count_checks = [
        ("handler registrations", base["handler_registration_count"], count_handler_registrations()),
        ("cmd_* defs", base["cmd_def_count"], count_cmd_defs()),
        ("scheduler jobs", base["scheduler_jobs_count"], count_scheduler_jobs()),
    ]
    print("Structural counts:")
    for name, b, c in count_checks:
        if b == c:
            print(f"  OK   {name}: {b} == {c}")
        else:
            print(f"  FAIL {name}: {b} -> {c}")
            failures.append(f"{name} count mismatch: {b} -> {c}")

    cur_loc = main_loc()
    delta = cur_loc - base["main_py_lines"]
    print(f"  INFO bot/main.py LOC: {base['main_py_lines']} -> {cur_loc} (delta {delta:+d})")

    print()
    print("Tooling gates:")

    ok, out = run_check([sys.executable, "-c", "import bot.main"])
    print(f"  {'OK  ' if ok else 'FAIL'} import bot.main")
    if not ok:
        failures.append(f"import bot.main failed: {out[:300]}")

    ok, out = run_check(["ruff", "check", "."])
    print(f"  {'OK  ' if ok else 'FAIL'} ruff")
    if not ok:
        failures.append(f"ruff errors:\n{out[:500]}")

    ok, out = run_check(["mypy", "."])
    lines = out.strip().splitlines()
    last_line = lines[-1] if lines else ""
    m = re.search(r"Found (\d+) error", last_line)
    if m:
        mypy_errs = int(m.group(1))
    elif ok:
        mypy_errs = 0
    else:
        mypy_errs = -1
    if 0 <= mypy_errs <= MYPY_BASELINE:
        print(f"  OK   mypy ({mypy_errs} <= {MYPY_BASELINE} baseline)")
    elif mypy_errs < 0:
        print("  FAIL mypy (did not run)")
        failures.append(f"mypy did not produce error count: {out[:300]}")
    else:
        print(f"  FAIL mypy ({mypy_errs} > {MYPY_BASELINE} baseline)")
        failures.append(f"mypy regression: {mypy_errs} > {MYPY_BASELINE}")

    ok, out = run_check(["pytest", "-q", "--no-header"], timeout=300)
    m_pass = re.search(r"(\d+) passed", out)
    m_fail = re.search(r"(\d+) failed", out)
    passed = int(m_pass.group(1)) if m_pass else 0
    failed = int(m_fail.group(1)) if m_fail else 0
    if failed == 0 and passed >= PYTEST_EXPECTED_MIN:
        print(f"  OK   pytest ({passed} passed, 0 failed)")
    else:
        print(f"  FAIL pytest ({passed} passed, {failed} failed, expected >= {PYTEST_EXPECTED_MIN})")
        failures.append(f"pytest: {passed}/{PYTEST_EXPECTED_MIN} passed, {failed} failed")

    print()
    if failures:
        print(f"VERDICT: FAIL ({len(failures)} issue(s))")
        for f in failures:
            print(f"  - {f}")
        if warnings_:
            print(f"  ({len(warnings_)} warning(s) acknowledged)")
        return 1
    print("VERDICT: PASS")
    if warnings_:
        print(f"  ({len(warnings_)} warning(s) acknowledged)")
    return 0


CHUNKS_PLAN = [
    (0, "baseline",       "absolute pre-Sprint-1.1 reference (no extraction)"),
    (1, "anti_erosion",   "cmd_log_value, cmd_log_friction, _append_log_entry"),
    (2, "observability",  "/health, /handler_stats, /llm_costs, /cost_trajectory, /kpi_status"),
    (3, "admin",          "/start, /help, /mode_switch, /version, /sources etc"),
    (4, "positions",      "/position_buy, /position_sell, /portfolio, /pnl"),
    (5, "sources",        "/sources_brier, /promote, /tiers, source admin"),
    (6, "signals",        "/signals_by_type, /materiality_debug, /recent_8k, /insider_buy_cluster_stats"),
    (7, "thesis",         "/thesis, /thesis_premortem, /analyze, /analyze_debate, /risk_check"),
    (8, "ritual",         "/brief, /digest"),
    (9, "analytics",      "/asymmetry, remaining analytics"),
    (10, "cleanup",       "tests + final smoke"),
]


def cmd_list_chunks(_args: argparse.Namespace) -> int:
    print("Planned Sprint 1.1 chunks (taxonomy DRAFT — validate at pre-flight):\n")
    for n, name, sample in CHUNKS_PLAN:
        baseline_fp = BASELINES_DIR / f"sprint-1.1-chunk-{n}.json"
        status = "captured" if baseline_fp.exists() else "—"
        print(f"  {n:2d}. {name:14s}  [{status:8s}]  {sample}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        prog="sprint_1_1_checkpoint",
        description="Equivalence checkpoint for Sprint 1.1 handler extraction.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("snapshot", help="Capture pre-extraction baseline.")
    s.add_argument("chunk", type=int)
    s.add_argument("label", type=str)

    v = sub.add_parser("verify", help="Verify post-extraction state.")
    v.add_argument("chunk", type=int)
    v.add_argument(
        "--expect-changed", default="",
        help="Comma-separated function names whose body change is intentional "
             "(e.g. '_append_log_entry' in chunk 1).",
    )

    sub.add_parser("list-chunks", help="List planned chunks and baseline status.")

    args = p.parse_args()
    if args.cmd == "snapshot":
        return cmd_snapshot(args)
    if args.cmd == "verify":
        return cmd_verify(args)
    if args.cmd == "list-chunks":
        return cmd_list_chunks(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
