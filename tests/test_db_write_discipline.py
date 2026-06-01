"""Fitness function: la surface des writers DB est explicite et gelee.

CONVENTIONS §5: les writes DB sont possedes par-table par un ensemble
sanctionne de modules. Un NOUVEAU module qui execute du SQL d'ecriture fait
echouer ce test expres -- ajouter un writer doit etre un choix conscient.

Detection AST (pas grep texte): on ne flague que le SQL d'ecriture passe en
litteral a .execute/.executemany/.executescript/query(). Docstrings et
commentaires ignores. Limite connue: du SQL stocke dans une variable puis
execute (sql = "INSERT..."; cur.execute(sql)) n'est pas detecte -- rare.
"""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ALLOWED_FILES = {
    "shared/storage.py",  # tables coeur (theses, predictions, signals via insert_raw_signal, sources...)
    "shared/positions.py",  # positions + position_events
    "shared/ticker_names.py",  # cache ticker_names
    "shared/llm.py",  # telemetrie llm_calls
    "intelligence/price_monitor.py",  # MAJ prix/clv/triggers theses (cron)
    "intelligence/materiality_v2.py",  # MAJ scores materialite signals (cron)
    "intelligence/debt_monitor.py",  # debt_signals / debt_composite (cron)
    "intelligence/insider_digest.py",  # insider_snapshots (cron)
    "intelligence/analyze.py",  # table analyses
    "intelligence/calendar.py",  # events (catalysts)
    "intelligence/self_loop.py",  # boucle-de-soi V0 : decision_counterfactual + counterfactual_resolution (tables dediees append-only, triggers SQL bloquent UPDATE/DELETE)
    "intelligence/bias_events.py",  # User Bias Detector v2.c (01/06) : open_candidate / resolve_due_bias_events / wire_bias_trigger / backfill_resolved_observations -- table dediee bias_events, cron. Pattern identique a price_monitor / debt_monitor.
    "intelligence/lock_in_detector.py",  # Surface 2 lock_in v2.c.6 (01/06) : detect_winner_sell hook positions.add_sell (L7 post-commit), update bias_events.position_event_id FK. Cron-equivalent (declenche par add_sell, pas par scheduler).
    "bot/main.py",  # telemetrie handler_calls
    "bot/handlers/misc.py",  # edition champs these
}
ALLOWED_PREFIXES = ("scripts/", "tests/")
SKIP_DIRS = {"venv", ".venv", ".backups", "__pycache__", ".git", "build", "dist", "data"}
EXEC_FUNCS = {"execute", "executemany", "executescript", "query"}
WRITE_SQL = re.compile(
    r"\b(INSERT\s+(OR\s+\w+\s+)?INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|REPLACE\s+INTO)\b",
    re.IGNORECASE,
)


def _str_of(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
    if isinstance(node, ast.BinOp):
        return _str_of(node.left) + _str_of(node.right)
    return ""


def _writes_db(path):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name in EXEC_FUNCS and any(WRITE_SQL.search(_str_of(a)) for a in node.args):
                return True
    return False


def _iter_py():
    for p in ROOT.rglob("*.py"):
        if not any(part in SKIP_DIRS for part in p.parts):
            yield p


def test_db_write_surface_is_frozen():
    violations = sorted(
        rel
        for p in _iter_py()
        if (rel := p.relative_to(ROOT).as_posix()) not in ALLOWED_FILES
        and not rel.startswith(ALLOWED_PREFIXES)
        and _writes_db(p)
    )
    assert not violations, (
        "Writer DB hors allowlist (CONVENTIONS §5). Route via storage.py, "
        "ou ajoute a ALLOWED_FILES avec une raison:\n  " + "\n  ".join(violations)
    )
