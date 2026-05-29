"""PRESAGE — Point d'ingestion unique book vs export courtier (directive #5).

Probleme adresse : "Sinon ton book canonique sera stale dans deux semaines --
exactement comme SESSION_STATE (Day 2 alors que tu es Day 17). Tes
RECONCILE_FLAGS manuels ne tiendront pas. Une source (export courtier) ->
reconcile -> book. Rends la derive structurellement impossible, pas
patchee a la main."

Format CSV canonique attendu (un fichier par broker, ou un fichier merge) :

    ticker,qty,avg_cost_eur,wrapper
    ASML.AS,3.5,950.50,PEA
    TSM,18.5,140.20,CTO

Champs :
  - ticker : symbole yfinance (.AS .PA .T .KS etc)
  - qty : quantite reelle au broker (float, peut etre fractionnel)
  - avg_cost_eur : prix moyen d'acquisition en EUR (taux change applique
    au moment de l'achat, pas du jour)
  - wrapper : PEA | CTO | AVUS | autre

Export depuis brokers :
  - Trade Republic : Portfolio -> Settings -> Export to CSV
  - Boursorama : Mon Portefeuille -> Telecharger Excel -> sauve en CSV
    Convertir colonnes : Code Yahoo, Quantite, PRU EUR, Compte=PEA

L'user depose les CSV dans scripts/reconcile_exports/ et lance :
    python3 -m intelligence.reconcile scripts/reconcile_exports/<file>.csv

Output : rapport des divergences (qty mismatch, manquant en DB, fantome
en DB). PAS d'auto-apply pour cette version -- l'user valide les corrections
a la main (audit trail). Auto-apply viendra apres trust accumule.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path

from shared import storage

log = logging.getLogger(__name__)


@dataclass
class ReconcileLine:
    ticker: str
    csv_qty: float | None = None
    csv_avg_cost: float | None = None
    csv_wrapper: str | None = None
    db_qty: float | None = None
    db_avg_cost: float | None = None
    db_wrapper: str | None = None

    @property
    def in_csv(self) -> bool:
        return self.csv_qty is not None

    @property
    def in_db(self) -> bool:
        return self.db_qty is not None

    @property
    def qty_mismatch_pct(self) -> float | None:
        if self.csv_qty is None or self.db_qty is None or self.db_qty == 0:
            return None
        return abs(self.csv_qty - self.db_qty) / self.db_qty * 100

    @property
    def avg_cost_mismatch_pct(self) -> float | None:
        if self.csv_avg_cost is None or self.db_avg_cost is None or self.db_avg_cost == 0:
            return None
        return abs(self.csv_avg_cost - self.db_avg_cost) / self.db_avg_cost * 100

    @property
    def status(self) -> str:
        if self.in_csv and not self.in_db:
            return "missing_in_db"  # broker tient une position que la DB ignore
        if self.in_db and not self.in_csv:
            return "phantom_in_db"  # DB tient une position que le broker ignore (sortie ?)
        # Both sides present
        qm = self.qty_mismatch_pct or 0
        cm = self.avg_cost_mismatch_pct or 0
        if qm < 1.0 and cm < 1.0:
            return "ok"
        if qm < 5.0 and cm < 5.0:
            return "drift_minor"
        return "drift_major"


@dataclass
class ReconcileReport:
    lines: list[ReconcileLine] = field(default_factory=list)
    csv_path: str = ""

    @property
    def by_status(self) -> dict[str, list[ReconcileLine]]:
        out: dict[str, list[ReconcileLine]] = {}
        for ln in self.lines:
            out.setdefault(ln.status, []).append(ln)
        return out

    def format_text(self) -> str:
        by = self.by_status
        out = [f"=== RECONCILE REPORT : {self.csv_path} ===\n"]
        ok = len(by.get("ok", []))
        out.append(f"  OK (qty + cost match < 1%) : {ok} lignes")
        for status in ("drift_minor", "drift_major", "missing_in_db", "phantom_in_db"):
            lns = by.get(status, [])
            if not lns:
                continue
            out.append(f"\n  {status.upper()} ({len(lns)} ligne(s)) :")
            for ln in sorted(lns, key=lambda x: x.ticker):
                if status in ("drift_minor", "drift_major"):
                    out.append(
                        f"    {ln.ticker:<12s} qty broker={ln.csv_qty} vs db={ln.db_qty} "
                        f"(ecart {ln.qty_mismatch_pct:.1f}%)  cost broker={ln.csv_avg_cost:.2f} "
                        f"vs db={ln.db_avg_cost:.2f} (ecart {ln.avg_cost_mismatch_pct:.1f}%)"
                    )
                elif status == "missing_in_db":
                    out.append(
                        f"    {ln.ticker:<12s} broker={ln.csv_qty} @ {ln.csv_avg_cost:.2f}€ "
                        f"({ln.csv_wrapper}) -- a ajouter en DB"
                    )
                else:  # phantom_in_db
                    out.append(
                        f"    {ln.ticker:<12s} db={ln.db_qty} @ {ln.db_avg_cost:.2f}€ "
                        f"({ln.db_wrapper}) -- a fermer en DB (sortie chez broker)"
                    )
        out.append("")
        out.append("Action : valide chaque divergence manuellement avant correction DB.")
        out.append("Auto-apply pas active dans cette version (audit trail prioritaire).")
        return "\n".join(out)


def _load_csv(csv_path: Path) -> dict[str, dict]:
    """Charge le CSV en {ticker: {qty, avg_cost_eur, wrapper}}."""
    out: dict[str, dict] = {}
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            tk = (row.get("ticker") or "").strip().upper()
            if not tk:
                continue
            try:
                qty = float(row.get("qty", 0) or 0)
                avg = float(row.get("avg_cost_eur", 0) or 0)
            except ValueError:
                log.warning(f"CSV row {tk} : qty/avg_cost not numeric, skip")
                continue
            out[tk] = {
                "qty": qty,
                "avg_cost_eur": avg,
                "wrapper": (row.get("wrapper") or "CTO").strip().upper(),
            }
    return out


def _load_db_positions() -> dict[str, dict]:
    """Positions DB ouvertes -> {ticker: {qty, avg_cost, wrapper}}."""
    out: dict[str, dict] = {}
    with storage.db() as cx:
        rows = cx.execute(
            "SELECT ticker, qty, avg_cost, wrapper FROM positions "
            "WHERE status='open' AND qty > 0"
        ).fetchall()
        for r in rows:
            out[r[0].upper()] = {
                "qty": r[1] or 0,
                "avg_cost": r[2] or 0,
                "wrapper": (r[3] or "CTO").upper(),
            }
    return out


def reconcile_from_csv(csv_path: str | Path) -> ReconcileReport:
    """Reconcilie un export broker CSV contre la DB.

    Returns: ReconcileReport avec lignes par status (ok, drift_minor,
    drift_major, missing_in_db, phantom_in_db).
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV introuvable : {csv_path}")
    csv_data = _load_csv(csv_path)
    db_data = _load_db_positions()

    all_tickers = set(csv_data) | set(db_data)
    lines = []
    for tk in sorted(all_tickers):
        csv_p = csv_data.get(tk) or {}
        db_p = db_data.get(tk) or {}
        lines.append(ReconcileLine(
            ticker=tk,
            csv_qty=csv_p.get("qty"),
            csv_avg_cost=csv_p.get("avg_cost_eur"),
            csv_wrapper=csv_p.get("wrapper"),
            db_qty=db_p.get("qty"),
            db_avg_cost=db_p.get("avg_cost"),
            db_wrapper=db_p.get("wrapper"),
        ))
    return ReconcileReport(lines=lines, csv_path=str(csv_path))


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 -m intelligence.reconcile <path_to_csv>")
        print("Format CSV : ticker,qty,avg_cost_eur,wrapper")
        sys.exit(1)
    report = reconcile_from_csv(sys.argv[1])
    print(report.format_text())
