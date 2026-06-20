"""hermes.inspector — Tier R audit triangulation 3-lentilles.

3 lentilles independantes, jamais une seule pour declarer 'mort' :
- lens_static    : ruff F-rules + vulture (dead symbol detector AST)
- lens_runtime   : telemetry handler_calls / cron_runs (0 calls / 90d)
- lens_decision  : signal -> prediction -> decision matter (matérialité)

Triangulation : 1 lens KO = a regarder ; 3 lens KO = haute confiance suppression.
Jamais verdict, jamais auto-action — sortie = backlog markdown pour
jugement humain.

Usage CLI :
    python -m hermes.inspector --lens all --since 90d
    python -m hermes.inspector --lens static --target dashboard/
    python -m hermes.inspector --deltas-only   # diff vs dernier passage
"""

__all__ = ["doctrine", "lens_decision", "lens_runtime", "lens_static", "report", "runner"]
