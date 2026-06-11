"""Cron jobs package — split par fréquence Phase C (21/05/2026).

Sous-modules :
- bot.jobs.daily : jobs daily/weekly/monthly (21 jobs)
- bot.jobs.intervals : jobs interval/hourly + heartbeat (9 jobs)
- bot.jobs.periodic : jobs weekly/monthly de track-record et calibration (9 jobs)
- bot.jobs.thesis_alpha_resolver : resolver cron pour thesis_predictions (storage-only)
- bot.jobs.j_day, integrity_anchor, sequences, etc. : modules individuels

Pas de ré-exports au package-level (cure #128 12/06/2026) : les ré-exports
eager tiraient pandas/yfinance/google/data_sources via le big import-tree
de daily/intervals/periodic, cassant la storage-only-ness de tout sous-
module storage-only (resolver pièce 4, aggregator pièce 5, E2E pièce 6).

Tout consommateur importe son job DEPUIS LE SOUS-MODULE qui le définit :
    from bot.jobs.daily import daily_backup_job
    from bot.jobs.thesis_alpha_resolver import resolve_due_thesis_predictions

Source de vérité unique = la définition. Pas de 2e registre nom→sous-module
à maintenir.
"""
