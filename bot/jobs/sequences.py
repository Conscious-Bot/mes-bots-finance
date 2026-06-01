"""Soudure ④ brief : crons séquencés (X fini ⟹ Y peut tourner).

Diagnostic user :
> "Tes 22 crons sont planifies par l'heure, pas par dependance. APScheduler
>  declenche par horloge, pas par 'X fini donc Y peut tourner'. Donc rien
>  ne garantit que le digest (7h) tourne apres l'ingestion, ni que resolve
>  tourne apres le refresh des prix. 22 reveils independants != une boucle
>  ordonnee. C'est une fragilite de course classique."

Avant : 35+ add_job individuels par heure -> race conditions silencieuses
(buy_cluster_scan a 6h20 PEUT tourner avant insider_refresh a 6h00 si
APScheduler skip ou retard).

Maintenant : 3 chaines explicites async :
- morning_chain() : 5h-9h pipeline d'apprentissage du jour
- evening_chain() : 23h snapshot + grade + counterfactual
- weekly_chain() : sam/dim synthèses hebdomadaires

Chaque étape await la précédente. Si une étape crash, on log mais on
continue (best-effort). L'ordre est garanti, pas l'aboutissement.

Les jobs autonomes (heartbeat, ingest_gmail, price_monitor) restent
individuels -- pas de dependance fonctionnelle.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


async def _safe_run(label: str, coro_factory):
    """Wrap une coroutine pour la chaine : log start/end, swallow exceptions.

    On veut que le crash d'une etape NE bloque PAS les suivantes (sinon
    une etape boguee tue tout le pipeline du jour). Best-effort + log.
    """
    log.info(f"chain step start : {label}")
    try:
        result = coro_factory()
        if hasattr(result, "__await__"):
            await result
        log.info(f"chain step OK : {label}")
        return True
    except Exception as e:
        log.error(f"chain step FAILED : {label}: {type(e).__name__}: {e}")
        return False


# ─────────────────────── Morning chain (5h-9h) ─────────────────────────────


async def morning_chain():
    """Pipeline d'apprentissage matinal -- ordre garanti.

    Etape 1 : Pré-requis (events, insiders, filings)
    Etape 2 : Scoring (signaux pending, materialite, clusters)
    Etape 3 : Digest book-anchored
    Etape 4 : Monitors (kill_criteria, risk_signal)
    Etape 5 : Resolutions (decisions, predictions, returns)
    """
    from bot.jobs.daily import (
        daily_decision_anniversary_job,
        daily_digest_job,
        daily_kill_criteria_check_job,
        daily_over_cap_check_job,
        daily_resolve_job,
        daily_risk_signal_monitor_job,
        resolve_copilot_interventions_30d_job,
        resolve_journal_decisions_job,
        scheduled_8k_scan_job,
        scheduled_buy_cluster_scan_job,
        scheduled_insider_refresh_job,
        scheduled_resolve_buy_cluster_returns_job,
    )
    from bot.jobs.intervals import (
        score_pending_signals_job,
        update_echo_clusters_job,
    )

    log.info("morning_chain start")

    # 1. Pré-requis : events / insiders / SEC filings
    # (calendar refresh est isolé à 5h, déjà tourné)
    await _safe_run("insider_refresh", scheduled_insider_refresh_job)
    await _safe_run("buy_cluster_scan", scheduled_buy_cluster_scan_job)
    await _safe_run("8k_scan", scheduled_8k_scan_job)

    # 2. Scoring : signaux ingérés pendant la nuit doivent être scorés
    #    AVANT que le digest les lise (sinon digest = signaux non scorés)
    await _safe_run("score_pending_signals", score_pending_signals_job)
    await _safe_run("update_echo_clusters", update_echo_clusters_job)

    # 3. Digest book-anchored (lit signaux scorés + book canonique)
    await _safe_run("daily_digest", daily_digest_job)

    # 4. Monitors (utilisent les signaux digérés et le book)
    await _safe_run("kill_criteria_check", daily_kill_criteria_check_job)
    await _safe_run("over_cap_check", daily_over_cap_check_job)
    await _safe_run("risk_signal_monitor", daily_risk_signal_monitor_job)
    await _safe_run("decision_anniversary", daily_decision_anniversary_job)

    # 5. Résolutions (a besoin de prix frais ET de décisions matures)
    await _safe_run("resolve_journal_decisions", resolve_journal_decisions_job)
    await _safe_run("daily_resolve", daily_resolve_job)
    await _safe_run("resolve_copilot_interventions_30d", resolve_copilot_interventions_30d_job)
    await _safe_run("resolve_buy_cluster_returns", scheduled_resolve_buy_cluster_returns_job)

    log.info("morning_chain end")


# ─────────────────────── Evening chain (23h) ───────────────────────────────


async def evening_chain():
    """Snapshot + grade + counterfactual resolve.

    Etape 1 : Snapshot du portfolio (etat figé J)
    Etape 2 : Grade calculé sur le snapshot
    Etape 3 : Counterfactual J+30 résolu (besoin de prix frais)
    """
    from bot.jobs.daily import (
        daily_counterfactual_resolve_job,
        daily_portfolio_grade_job,
    )
    from intelligence.snapshot import daily_snapshot_job

    log.info("evening_chain start")
    await _safe_run("snapshot", daily_snapshot_job)
    await _safe_run("portfolio_grade", daily_portfolio_grade_job)
    await _safe_run("counterfactual_resolve", daily_counterfactual_resolve_job)
    log.info("evening_chain end")


# ─────────────────────── Weekly chain (sat/sun) ────────────────────────────


async def weekly_chain_saturday():
    """Samedi : clusters de données (préparation des synthèses dimanche)."""
    from bot.jobs.daily import weekly_data_clusters_synthesis_job

    log.info("weekly_chain_saturday start")
    await _safe_run("data_clusters", weekly_data_clusters_synthesis_job)
    log.info("weekly_chain_saturday end")


async def weekly_chain_sunday():
    """Dimanche : synthèses hebdomadaires en chaîne.

    Conceptions → portfolio_narrative → user_profile → cost_summary → kpi_status
    """
    from bot.jobs.daily import (
        weekly_bot_conceptions_synthesis_job,
        weekly_portfolio_narrative_synthesis_job,
        weekly_user_profile_refresh_job,
    )
    from bot.jobs.periodic import (
        refresh_source_half_lives_job,
        weekly_cost_summary_job,
        weekly_handler_stats_job,
        weekly_kpi_status_job,
    )

    log.info("weekly_chain_sunday start")
    # Pré-requis : refresh des half-lives sources
    await _safe_run("refresh_source_half_lives", refresh_source_half_lives_job)
    # Synthèses dans l'ordre des dépendances
    await _safe_run("bot_conceptions", weekly_bot_conceptions_synthesis_job)
    await _safe_run("portfolio_narrative", weekly_portfolio_narrative_synthesis_job)
    await _safe_run("user_profile", weekly_user_profile_refresh_job)
    # Reporting (lit les synthèses)
    await _safe_run("cost_summary", weekly_cost_summary_job)
    await _safe_run("kpi_status", weekly_kpi_status_job)
    await _safe_run("handler_stats", weekly_handler_stats_job)
    log.info("weekly_chain_sunday end")
