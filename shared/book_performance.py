"""SOCLE canonique : performance réelle du book — source unique (L1).

POURQUOI CE MODULE EXISTE (audit 03/08/2026)
--------------------------------------------
Le 29/07, `portfolio_snapshots.pnl_pct` affichait **−1,1 %**. Le book était à
**+23,3 %**. Écart : 24 points, sur la métrique de performance du système.

Cause : ce champ mesure le LATENT sur les seules lignes TENUES. Il ignore
7 221 € de réalisé (64 % du P&L de vie du book) et ne connaît pas le capital
réellement injecté. C'est un agrégat partiel présenté comme un total — L31.
Le défaut est passé inaperçu des mois ; il a trompé un lecteur averti en moins
d'une heure. Un chiffre faux et plausible est pire qu'une absence de chiffre.

CE QUE CE MODULE GARANTIT
-------------------------
1. **Une seule lecture du ledger** — via `ledger_pmp.normalized_transactions`.
2. **Réconciliation vérifiée À CHAQUE APPEL** :

       valeur_marché − capital_net_injecté  ==  réalisé + latent

   Si l'égalité casse au-delà de la tolérance, la fonction renvoie
   `status="error"` et **aucun pourcentage**. Le système a le droit de dire
   « je ne sais pas » ; jamais celui de publier une performance qui ne se
   réconcilie pas (QUALITY_BAR M1, L15 fail-closed).
3. **Provenance déclarée** — un capital reconstitué depuis un PRU seedé n'est
   pas la même preuve qu'un fill broker. `provenance` le dit, toujours.
4. **Couverture déclarée** — une ligne sans prix rend le total INCOMPLET.
   Le pourcentage n'est alors pas rendu (L31 : un agrégat partiel est un faux,
   pas une approximation).

CE QUE CE MODULE NE FAIT PAS
----------------------------
Il n'écrit rien. Aucune valeur dérivée n'est stockée comme vérité (A8) : la
performance est TOUJOURS recalculée depuis le ledger. Le journal quotidien
(`erosion_alerts`) est un capteur de pente et un cache — jamais une source.
En cas de divergence journal/socle, le socle gagne.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── Constantes déclarées (A3 : aucun seuil muet) ─────────────────────────────

#: Tickers de smoke-test présents dans le ledger de PRODUCTION (constaté
#: 03/08/2026 : sources `smoke_test_126` / `smoke_test_cleanup_2026-06-09`).
#: Ils injectent ~+187 € de P&L fabriqué. Exclus ICI et DÉCLARÉS dans le
#: résultat — jamais retirés en silence. Correctif de fond : cure append-only
#: du ledger, hors périmètre de ce socle.
LEDGER_TEST_TICKERS: frozenset[str] = frozenset({
    "SMOKE126",
    "SMK126_1780976099",
    "SMK126_1780976181_EUR",
})

#: Sources de transactions qui NE SONT PAS des fills broker : positions
#: reconstituées à partir d'un PRU au moment de la migration. Le montant est
#: exact (PRU × qty = coût réel), mais la DATE est fictive et l'historique
#: antérieur est absent. Toute lecture temporelle (période de détention,
#: rendement time-weighted) est invalide sur ces lignes.
SEEDED_SOURCES: frozenset[str] = frozenset({"migration_anchor_2026-06-09"})

#: Tolérance de réconciliation. 1 € sur un book à cinq chiffres : assez serré
#: pour attraper une divergence de méthode, assez lâche pour absorber les
#: arrondis flottants. L'écart de 26 € constaté avant le refactor du
#: 03/08 (overrides ADJUST ignorés côté capital) aurait été attrapé ici.
RECONCILIATION_TOL_EUR: float = 1.0


@dataclass(frozen=True)
class BookPerformance:
    """Performance du book à un instant. Tous les montants en EUR.

    `status` :
      - "ok"      : réconcilié, couverture complète — les % sont publiables.
      - "partial" : au moins une ligne sans prix. Montants indicatifs,
                    `total_return_pct` est None. La couverture est déclarée.
      - "error"   : la réconciliation a échoué. AUCUN chiffre n'est publiable.
    """

    asof: str
    status: str

    capital_net_eur: float          # Σ achats (frais inclus) − Σ produits de vente nets
    market_value_eur: float         # lignes tenues, prix × fx as-of
    realized_pnl_eur: float         # via ledger_pmp — source unique
    unrealized_pnl_eur: float
    total_pnl_eur: float            # realized + unrealized
    total_return_pct: float | None  # None si couverture incomplète (L31)

    n_lines_held: int
    n_lines_closed: int
    n_lines_priced: int
    missing_price_tickers: tuple[str, ...] = ()

    # ── Provenance (M1 : valeur, as-of, source) ──
    provenance: str = ""
    seeded_tickers: tuple[str, ...] = ()
    excluded_test_tickers: tuple[str, ...] = ()
    oldest_price_asof: str | None = None
    ledger_first_trade: str | None = None

    reconciliation_gap_eur: float = 0.0
    error: str | None = None

    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_publishable(self) -> bool:
        """Un pourcentage ne s'affiche que si le book se réconcilie ET est couvert."""
        return self.status == "ok" and self.total_return_pct is not None


def _fx_map(cx: Any, asof: str | None) -> dict[str, float]:
    """Taux <base>→EUR les plus récents (≤ asof si fourni). EUR→EUR = 1.0."""
    if asof:
        rows = cx.execute(
            "SELECT base, rate FROM fx_history WHERE quote='EUR' AND asof<=? "
            "AND id IN (SELECT max(id) FROM fx_history WHERE quote='EUR' AND asof<=? GROUP BY base)",
            (asof, asof),
        ).fetchall()
    else:
        rows = cx.execute(
            "SELECT base, rate FROM fx_history WHERE quote='EUR' "
            "AND id IN (SELECT max(id) FROM fx_history WHERE quote='EUR' GROUP BY base)"
        ).fetchall()
    out = {str(b): float(r) for b, r in rows}
    out["EUR"] = 1.0
    return out


def _last_price(cx: Any, ticker: str, asof: str | None) -> tuple[float, str, str] | None:
    """(prix natif, devise, as-of) le plus récent ≤ asof. None si aucun prix."""
    if asof:
        row = cx.execute(
            "SELECT price_native, currency, asof FROM price_history "
            "WHERE ticker=? AND asof<=? ORDER BY asof DESC LIMIT 1",
            (ticker, asof),
        ).fetchone()
    else:
        row = cx.execute(
            "SELECT price_native, currency, asof FROM price_history "
            "WHERE ticker=? ORDER BY asof DESC LIMIT 1",
            (ticker,),
        ).fetchone()
    if not row or row[0] is None:
        return None
    return float(row[0]), str(row[1]), str(row[2])


def compute_book_performance(cx: Any, asof: str | None = None) -> BookPerformance:
    """Performance complète du book — réalisé INCLUS. Source unique (L1).

    Args:
        cx   : connexion sqlite3 (doctrine : pas d'import sqlite3 hors storage).
        asof : borne temporelle ISO, ou None pour « maintenant ».

    Returns:
        BookPerformance. Ne lève jamais : toute erreur devient `status="error"`
        avec un message — un appelant ne doit jamais recevoir un nombre muet.
    """
    from shared.ledger_pmp import compute_pmp_realized, normalized_transactions

    try:
        txs = normalized_transactions(cx, upto=asof)
    except Exception as exc:  # ledger illisible → état explicite
        return BookPerformance(
            asof=asof or "", status="error",
            capital_net_eur=0.0, market_value_eur=0.0, realized_pnl_eur=0.0,
            unrealized_pnl_eur=0.0, total_pnl_eur=0.0, total_return_pct=None,
            n_lines_held=0, n_lines_closed=0, n_lines_priced=0,
            error=f"ledger illisible : {exc}",
        )

    tickers_all = sorted({t.ticker for t in txs} - {""})
    excluded = tuple(sorted(t for t in tickers_all if t in LEDGER_TEST_TICKERS))
    tickers = [t for t in tickers_all if t not in LEDGER_TEST_TICKERS]

    # ── 1. Capital net injecté (même lecture que le réalisé) ──
    capital = 0.0
    seeded: set[str] = set()
    first_trade: str | None = None
    seed_ids = {
        int(r[0])
        for r in cx.execute(
            "SELECT id FROM transactions WHERE source IN ({})".format(
                ",".join("?" * len(SEEDED_SOURCES))
            ),
            tuple(SEEDED_SOURCES),
        ).fetchall()
    } if SEEDED_SOURCES else set()

    for t in txs:
        tk = t.ticker
        if not tk or tk in LEDGER_TEST_TICKERS:
            continue
        if first_trade is None or t.trade_date < first_trade:
            first_trade = t.trade_date
        if t.tx_id in seed_ids:
            seeded.add(tk)
        gross = t.qty * t.price_native * t.fx_at_trade
        fees = t.fees_native * t.fx_at_trade
        capital += (gross + fees) if t.side == "BUY" else -(gross - fees)

    # ── 2. Réalisé + positions tenues (helper canonique) ──
    realized = 0.0
    held: list[tuple[str, float, float]] = []  # (ticker, qty, pmp_eur)
    n_closed = 0
    for tk in tickers:
        p = compute_pmp_realized(cx, tk, upto=asof)
        realized += p.realized_pnl_eur
        if p.qty > 1e-6 and p.pmp_eur is not None:
            held.append((tk, p.qty, p.pmp_eur))
        else:
            n_closed += 1

    # ── 3. Valeur de marché + latent ──
    fx = _fx_map(cx, asof)
    market_value = 0.0
    unrealized = 0.0
    missing: list[str] = []
    oldest_px: str | None = None
    for tk, qty, pmp_eur in held:
        px = _last_price(cx, tk, asof)
        if px is None or px[1] not in fx:
            missing.append(tk)
            continue
        price_native, cur, px_asof = px
        val = qty * price_native * fx[cur]
        market_value += val
        unrealized += val - qty * pmp_eur
        if oldest_px is None or px_asof < oldest_px:
            oldest_px = px_asof

    total_pnl = realized + unrealized
    gap = (market_value - capital) - total_pnl

    # ── 4. Invariant de réconciliation — fail-closed ──
    if missing:
        status = "partial"
        ret: float | None = None
        err = None
    elif abs(gap) > RECONCILIATION_TOL_EUR:
        status = "error"
        ret = None
        err = (
            f"réconciliation KO : (valeur {market_value:,.2f} − capital {capital:,.2f}) "
            f"= {market_value - capital:,.2f} ≠ réalisé+latent {total_pnl:,.2f} "
            f"(écart {gap:+,.2f} €, tolérance {RECONCILIATION_TOL_EUR} €)"
        )
    else:
        status = "ok"
        ret = (total_pnl / capital * 100.0) if capital > 0 else None
        err = None

    notes: list[str] = []
    if excluded:
        notes.append(
            f"{len(excluded)} ticker(s) de smoke-test exclus du ledger de prod : "
            + ", ".join(excluded)
        )
    if seeded:
        notes.append(
            f"{len(seeded)} ligne(s) reconstituées depuis un PRU au 15/05/2026 "
            f"({', '.join(sorted(seeded))}) : montants exacts, DATES fictives — "
            "toute lecture temporelle (durée de détention, rendement time-weighted) "
            "est invalide sur ces lignes, et leurs cessions antérieures sont absentes."
        )
    if missing:
        notes.append(
            f"{len(missing)} ligne(s) sans prix : {', '.join(sorted(missing))} — "
            "total INCOMPLET, pourcentage non rendu (L31)."
        )

    prov = "broker+manuel"
    if seeded:
        prov = "broker+manuel+PRU seedé"

    return BookPerformance(
        asof=asof or (oldest_px or ""),
        status=status,
        capital_net_eur=capital,
        market_value_eur=market_value,
        realized_pnl_eur=realized,
        unrealized_pnl_eur=unrealized,
        total_pnl_eur=total_pnl,
        total_return_pct=ret,
        n_lines_held=len(held),
        n_lines_closed=n_closed,
        n_lines_priced=len(held) - len(missing),
        missing_price_tickers=tuple(sorted(missing)),
        provenance=prov,
        seeded_tickers=tuple(sorted(seeded)),
        excluded_test_tickers=excluded,
        oldest_price_asof=oldest_px,
        ledger_first_trade=first_trade,
        reconciliation_gap_eur=gap,
        error=err,
        notes=tuple(notes),
    )


def format_headline(p: BookPerformance) -> str:
    """Une ligne honnête pour l'écran. Jamais un nombre nu (A8).

    Le libellé nomme sa base : « sur capital net injecté » — pour qu'aucun
    lecteur ne puisse le confondre avec le latent sur lignes tenues, qui est
    précisément la confusion à l'origine de ce module.
    """
    if p.status == "error":
        return f"⚠ PERFORMANCE NON RÉCONCILIÉE — {p.error}"
    pct = f"{p.total_return_pct:+.1f} %" if p.total_return_pct is not None else "—"
    base = f"{p.total_pnl_eur:+,.0f} € ({pct} sur capital net injecté {p.capital_net_eur:,.0f} €)"
    detail = f" · réalisé {p.realized_pnl_eur:+,.0f} € · latent {p.unrealized_pnl_eur:+,.0f} €"
    flag = "" if p.status == "ok" else f" · ⚠ couverture {p.n_lines_priced}/{p.n_lines_held}"
    return base + detail + flag
