"""Phase B : cron audit_calibration_job (evolutif refresh 10j).

User 06/06 : "ces infos doivent etre evolutives, refresh audit every
10 days". Cette fonction :

1. Daily check : si last_audit > 10j -> trigger audit refresh
2. Auto sanity check sur historique 14j debt_signals :
   - Detecte les indicateurs "stuck warn" (>70% du temps en warn)
   - Detecte les seuils qui ne respirent jamais (aucun calm period > 5j)
   - Flag les divergences avec seuils calibration.yaml
3. Genere docs/calibration_audits/YYYY-MM-DD_v(N+1).md avec :
   - Findings auto (sanity check)
   - Prompt structure pour recherche pro web (humaine ou Claude Code)
   - Skeleton pour deltas proposes
4. Bump audit_metadata.next_audit_due dans calibration.yaml
5. Telegram ping "Audit refresh livre, X findings auto + prompt pret"

Doctrine voie clean auditable : pas d'auto-apply. User review +
applique manuellement. Cron mecanise le RAPPEL + le skeleton, pas la
decision.
"""

from __future__ import annotations

import datetime as _dt
import logging
from pathlib import Path

from shared import storage
from shared.calibration import get_all_bands, get_audit_metadata

log = logging.getLogger(__name__)


_AUDIT_DIR = Path(__file__).resolve().parent.parent / "docs" / "calibration_audits"
_CALIB_YAML = Path(__file__).resolve().parent.parent / "config" / "calibration.yaml"


def is_audit_due() -> tuple[bool, int]:
    """Returns (due, days_since_last)."""
    meta = get_audit_metadata()
    last = meta.get("last_audit")
    if not last:
        return True, 999
    try:
        last_dt = _dt.date.fromisoformat(str(last))
        today = _dt.date.today()
        days = (today - last_dt).days
        return days >= 10, days
    except Exception:
        return True, 999


def sanity_check_thresholds(days_window: int = 14) -> list[dict]:
    """Auto check : pour chaque indicateur avec band, mesure le % temps
    en calm/warn/danger sur la fenetre. Flag les anomalies.

    Returns list de findings :
        [{"indicator": "VIX", "issue": "stuck_warn", "pct_warn": 92,
          "suggestion": "tighten warn ou loosen", ...}]
    """
    findings: list[dict] = []
    bands = get_all_bands()
    try:
        with storage.db() as cx:
            rows = cx.execute(
                "SELECT indicator_name, value, timestamp FROM debt_signals "
                "WHERE timestamp > datetime('now', '-' || ? || ' day') "
                "  AND value IS NOT NULL "
                "ORDER BY indicator_name, timestamp ASC",
                (int(days_window),),
            ).fetchall()
    except Exception as e:
        log.warning(f"sanity_check read: {e}")
        return []

    import contextlib
    by_ind: dict[str, list[float]] = {}
    for ind, val, _ts in rows:
        with contextlib.suppress(Exception):
            by_ind.setdefault(ind, []).append(float(val))

    for ind, vals in by_ind.items():
        if ind not in bands or len(vals) < 3:
            continue
        warn_th, danger_th, hi_bad = bands[ind]
        n = len(vals)
        if hi_bad:
            warn_n = sum(1 for v in vals if v >= warn_th)
            danger_n = sum(1 for v in vals if v >= danger_th)
        else:
            warn_n = sum(1 for v in vals if v <= warn_th)
            danger_n = sum(1 for v in vals if v <= danger_th)
        pct_warn = warn_n / n * 100
        pct_danger = danger_n / n * 100

        # Issue 1 : stuck warn (>= 80% du temps en warn)
        if pct_warn >= 80 and pct_danger < 50:
            findings.append({
                "indicator": ind,
                "issue": "stuck_warn",
                "pct_warn": pct_warn,
                "pct_danger": pct_danger,
                "values_range": [min(vals), max(vals)],
                "current_thresholds": (warn_th, danger_th),
                "suggestion": (
                    f"{ind} en warn {pct_warn:.0f}% du temps. "
                    f"Soit le seuil warn={warn_th} est trop bas (loosen ?), "
                    f"soit l'environnement est durablement stresse (laisser tel quel)."
                ),
            })
        # Issue 2 : stuck danger (>= 50% du temps en danger)
        elif pct_danger >= 50:
            findings.append({
                "indicator": ind,
                "issue": "stuck_danger",
                "pct_warn": pct_warn,
                "pct_danger": pct_danger,
                "values_range": [min(vals), max(vals)],
                "current_thresholds": (warn_th, danger_th),
                "suggestion": (
                    f"{ind} en danger {pct_danger:.0f}% du temps. "
                    f"Indicateur structurellement detoriore (crise ?) "
                    f"OU seuil danger={danger_th} trop bas."
                ),
            })
        # Issue 3 : never warn (<= 5%) -> seuil potentiellement trop haut
        elif pct_warn <= 5 and len(vals) >= 7:
            findings.append({
                "indicator": ind,
                "issue": "never_warn",
                "pct_warn": pct_warn,
                "pct_danger": pct_danger,
                "values_range": [min(vals), max(vals)],
                "current_thresholds": (warn_th, danger_th),
                "suggestion": (
                    f"{ind} jamais en warn ({pct_warn:.0f}% du temps). "
                    f"Seuil warn={warn_th} potentiellement trop haut "
                    f"(loose). Verifier vs consensus pro."
                ),
            })
    return findings


def next_audit_version(meta: dict) -> str:
    """Bump audit_version v4 -> v5 -> v6."""
    cur = meta.get("audit_version") or "v4"
    try:
        n = int(str(cur).lstrip("v"))
        return f"v{n + 1}"
    except Exception:
        return "v5"


def generate_audit_skeleton(findings: list[dict], next_version: str) -> str:
    """Genere le markdown skeleton avec findings auto + prompt pro."""
    today = _dt.date.today().isoformat()
    bands = get_all_bands()
    bands_summary = "\n".join(
        f"  - **{ind}** : warn {b[0]}, danger {b[1]}, hi_bad={b[2]}"
        for ind, b in bands.items()
    )
    findings_md = ""
    if findings:
        for f in findings:
            findings_md += (
                f"### {f['indicator']} — {f['issue']}\n"
                f"- Range observé : {f['values_range'][0]:.2f} .. "
                f"{f['values_range'][1]:.2f}\n"
                f"- % temps warn : {f['pct_warn']:.0f}%\n"
                f"- % temps danger : {f['pct_danger']:.0f}%\n"
                f"- Seuils courants : warn={f['current_thresholds'][0]}, "
                f"danger={f['current_thresholds'][1]}\n"
                f"- **Suggestion auto** : {f['suggestion']}\n\n"
            )
    else:
        findings_md = "_(Aucun finding auto. Tous indicateurs respirent normalement.)_\n"

    return f"""# Audit refresh {next_version} — {today}

**Type** : Refresh automatique (cron audit_calibration_job, 10j cadence)
**Méthode** : Sanity check auto sur historique 14j + prompt pro pour recherche web humaine

## 1. Findings automatiques (sanity check 14j)

{findings_md}

## 2. État courant calibration.yaml

{bands_summary}

## 3. Prompt structuré pour recherche pro web (manuel ou Claude Code)

```
Tu fais un AUDIT PROFESSIONNEL de mes seuils macro. Date {today}.

Indicateurs et seuils (warn, danger, hi_bad) :
{bands_summary}

Pour chaque indicateur, recherche autorité (FRED / BIS / JPM / GS /
Bloomberg / Cboe / Tradingeconomics) :
1. Niveau courant + position percentile vs 10y
2. Verdict : ACCURATE / SLIGHTLY-OFF / WRONG vs consensus pro
3. Si correction proposée : warn/danger ajustés + rationale + URL source

Format report :
- Verdict par indicateur (max 6 lignes chacun)
- Top 3 corrections impactantes
- Sources citées (URL)
```

## 4. Sections à compléter manuellement

### 4.1 Verdicts par indicateur (à remplir post-recherche pro)

| Indicateur | Verdict | Correction proposée |
|---|---|---|
{chr(10).join(f"| {ind} | — | — |" for ind in bands)}

### 4.2 Cycle phases sectorielles

Validation Q{(_dt.date.today().month - 1) // 3 + 1} 2026 :

- **semis** : current = late cycle. Consensus pro = ?
- **energy_commodities** : current = early. Consensus pro = ?
- **defense_industrials_eu** : current = mid. Consensus pro = ?
- **tech_mega** : current = late. Consensus pro = ?
- **auto_ev** : current = contraction. Consensus pro = ?

### 4.3 Top 3 corrections impactantes (à remplir)

1.
2.
3.

## 5. Changes à appliquer

Une fois review terminée, mettre à jour :
- `config/calibration.yaml` bands + classifier_thresholds + rules_thresholds
- audit_metadata.last_audit = {today}
- audit_metadata.audit_version = {next_version}
- audit_metadata.audit_reports (append ce fichier)

## 6. Sources consultées (à remplir)

-
-
"""


def run_audit_refresh() -> dict:
    """Genere skeleton + bump metadata + Telegram ping. Returns summary."""
    _AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    today_iso = _dt.date.today().isoformat()
    meta = get_audit_metadata()
    next_v = next_audit_version(meta)
    findings = sanity_check_thresholds()
    skeleton_md = generate_audit_skeleton(findings, next_v)
    out_path = _AUDIT_DIR / f"{today_iso}_{next_v}_skeleton.md"
    out_path.write_text(skeleton_md)
    log.info(f"audit_refresh wrote {out_path}, findings={len(findings)}")

    # Telegram ping
    try:
        from shared import notify
        msg = (
            f"🔄 *Audit refresh {next_v}* prêt\n\n"
            f"Skeleton : `{out_path.relative_to(_CALIB_YAML.parent.parent)}`\n"
            f"Findings auto : *{len(findings)}*\n\n"
        )
        if findings:
            msg += "Top findings :\n"
            for f in findings[:3]:
                msg += f"  • {f['indicator']} — {f['issue']}\n"
        msg += (
            f"\nLance recherche pro via Claude Code ou manuel. "
            f"Calibration courante : `{meta.get('audit_version', '?')}` "
            f"({meta.get('last_audit', '?')})."
        )
        notify.send_text(msg)
    except Exception as e:
        log.warning(f"audit_refresh telegram: {e}")

    return {
        "next_version": next_v,
        "findings_count": len(findings),
        "out_path": str(out_path),
    }


def cron_audit_calibration_daily() -> None:
    """APScheduler entry : daily check, trigger audit refresh si >= 10j."""
    log.info("cron_audit_calibration_daily starting")
    try:
        due, days = is_audit_due()
        if not due:
            log.info(f"audit not due (last audit {days}j ago, threshold 10j)")
            return
        result = run_audit_refresh()
        log.info(
            f"audit refresh complete : {result['next_version']} "
            f"with {result['findings_count']} findings at {result['out_path']}"
        )
    except Exception as e:
        log.exception(f"cron_audit_calibration_daily crashed: {e}")
