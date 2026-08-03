"""PMP roulant + realized_pnl date-ordonné — convention fiscale française stricte.

Cf rectification Olivier 09/06 : « PMP fiscal FR RESET le pool sur clôture
complète. Règle CGI : plus-value sur vente = (cession - PMP) x qty_vendue ;
PMP des titres restants inchangé. Mais quand on vend TOUT (qty → 0), le pool
est vide — un rachat ultérieur démarre un NOUVEAU PMP = le prix de rachat. »

La sous-requête corrélée VUE `Σ(buy.cost) / Σ(buy.qty) WHERE trade_date < sell`
est exacte UNIQUEMENT si le pool ne se vide jamais (Σ buys invariant aux ventes
simples). Tesla est le 1er ticker avec cycle full-close→rebuy → la simplif
SQL casse. Sortie en Python stateful : itération date-ordonnée, reset cost+qty
à 0 quand qty atteint 0, reconstruction au BUY suivant.

Convention :
  - PMP = poids pondéré des BUYs du pool ouvert (frais d'achat capitalisés)
  - SELL : qty -= sell.qty, cost_pool -= sell.qty x pmp_actuel,
           realized += sell.qty x (sell.price.eur - pmp.eur) - sell.fees.eur
  - Close (qty ≈ 0) : reset cost_pool=0, qty=0 (le PMP du nouveau pool sera le
    prix du prochain BUY)
  - Toujours fees + tax capitalisés (BUYs au cost, SELLs déduits du proceeds)

Garde régression : si AUCUN close-rebuy dans l'historique, ce helper donne
EXACTEMENT le même résultat que la sous-requête corrélée VUE (vérif par les
5 stale + 14 propres qui n'ont pas de close-rebuy).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any  # cx = sqlite3.Connection mais pas importé (doctrine sqlite3 hors storage.py)


@dataclass
class PositionPMP:
    ticker: str
    qty: float
    pmp_native: float | None  # avg du pool ouvert en native
    pmp_eur: float | None     # avg du pool ouvert en EUR (frozen-at-buy)
    realized_pnl_eur: float   # cumulé sur l'historique
    n_closures: int           # nombre de fois où le pool s'est vidé (audit)


_TOL_ZERO = 1e-6  # qty considérée nulle (close complète)


@dataclass(frozen=True)
class NormalizedTx:
    """Une transaction, overrides appliqués. Unité de lecture du ledger."""
    tx_id: int
    ticker: str
    side: str            # "BUY" | "SELL" (les ADJUST ont été absorbés)
    qty: float
    price_native: float
    fees_native: float
    fx_at_trade: float
    trade_date: str


def normalized_transactions(
    cx: Any, ticker: str | None = None, upto: str | None = None
) -> list[NormalizedTx]:
    """Flux de transactions NORMALISÉ — source unique de lecture du ledger (L1).

    Applique les overrides `ADJUST` (cure currency 14/06/2026) puis retire les
    lignes ADJUST du flux. Tout consumer du ledger — PMP, réalisé, capital net
    injecté — DOIT passer par ici : deux façons de lire une transaction
    produisent deux vérités.

    Origine (audit 03/08/2026) : le capital net injecté, calculé sans les
    overrides ADJUST, divergeait du réalisé de 26 € sur 48 207 €. Assez petit
    pour passer inaperçu pendant des mois, assez gros pour prouver qu'il
    existait deux lectures du même ledger.

    Args:
        cx     : connexion sqlite3 (doctrine : pas d'import sqlite3 hors storage)
        ticker : restreint à un ticker, ou None pour tout le ledger.
        upto   : borne HAUTE incluse (ISO). Indispensable à toute lecture
                 historique : sans elle, un calcul « as-of le 22/06 » compte
                 des ventes de juillet et fabrique un passé qui n'a jamais
                 existé. Les ADJUST sont bornés eux aussi — une correction
                 postérieure ne doit pas réécrire un état antérieur.

    Returns:
        Transactions ordonnées (trade_date, id), ADJUST appliqués et absorbés.
    """
    import json as _json

    cols = ("SELECT id, ticker, side, qty, price_native, fees_native, "
            "fx_at_trade, trade_date, notes FROM transactions")
    where, params = [], []
    if ticker is not None:
        where.append("ticker = ?")
        params.append(ticker)
    if upto is not None:
        where.append("trade_date <= ?")
        params.append(upto)
    sql = cols + (" WHERE " + " AND ".join(where) if where else "")
    rows_raw = cx.execute(sql + " ORDER BY trade_date ASC, id ASC", tuple(params)).fetchall()

    adjust_map: dict[int, dict[str, float]] = {}
    kept: list[tuple] = []
    for tx_id, tk, side, qty, price_native, fees_native, fx, trade_date, notes in rows_raw:
        if side == "ADJUST":
            try:
                notes_data = _json.loads(notes) if notes else {}
                target_id = notes_data.get("target_tx_id")
                if target_id is not None:
                    adjust_map[int(target_id)] = {
                        "price_native": float(price_native),
                        "fx_at_trade": float(fx),
                    }
            except (ValueError, TypeError, _json.JSONDecodeError):
                continue  # ADJUST mal formé -> ignore (fail-soft, cf original)
        else:
            kept.append((tx_id, tk, side, qty, price_native, fees_native, fx, trade_date))

    out: list[NormalizedTx] = []
    for tx_id, tk, side, qty, price_native, fees_native, fx, trade_date in kept:
        ov = adjust_map.get(tx_id)
        out.append(NormalizedTx(
            tx_id=int(tx_id),
            ticker=str(tk),
            side=str(side),
            qty=float(qty),
            price_native=float(ov["price_native"]) if ov else float(price_native),
            fees_native=float(fees_native),
            fx_at_trade=float(ov["fx_at_trade"]) if ov else float(fx),
            trade_date=str(trade_date),
        ))
    return out


def compute_pmp_realized(cx: Any, ticker: str, upto: str | None = None) -> PositionPMP:
    """Calcule PMP roulant + realized_pnl date-ordonné pour ce ticker.

    Itère TOUTES les transactions (BUYs + SELLs) ordonnées par trade_date.
    Maintient (qty_pool, cost_pool_native, cost_pool_eur) en mémoire ;
    reset à 0 à chaque close complète.

    ADJUST handling (cure currency bug 14/06/2026) : tx side='ADJUST' avec
    notes JSON `{"target_tx_id": N, ...}` override les fields price_native +
    fx_at_trade de la tx N. Permet correction sans UPDATE (append-only
    structural preserved) ni pansement reversal-BUY (qui pollue PMP
    path-dependent). Cf SPEC_LEDGER §1 "extensible 'SPLIT'/'ADJUST' (futur)".
    """
    iter_rows = [
        (t.tx_id, t.side, t.qty, t.price_native, t.fees_native, t.fx_at_trade)
        for t in normalized_transactions(cx, ticker, upto)
    ]

    qty_pool = 0.0
    cost_pool_native = 0.0  # somme cumulée qty x price + fees (en native)
    cost_pool_eur = 0.0     # somme cumulée qty x price x fx + fees x fx (en EUR)
    realized_eur = 0.0
    n_closures = 0

    for _tx_id, side, qty, price_native, fees_native, fx in iter_rows:
        # (overrides ADJUST déjà appliqués par normalized_transactions)
        qty = float(qty)
        price_native = float(price_native)
        fees_native = float(fees_native)
        fx = float(fx)

        if side == "BUY":
            # Ajout au pool : capitalise frais
            cost_pool_native += qty * price_native + fees_native
            cost_pool_eur += qty * price_native * fx + fees_native * fx
            qty_pool += qty

        elif side == "SELL":
            if qty_pool <= _TOL_ZERO:
                # SELL sur pool vide = erreur de données (n'arrive pas en théorie
                # car le CSV broker est cohérent). On log et skip pour ne pas
                # créer un realized fabriqué.
                continue

            # PMP courant du pool
            pmp_native = cost_pool_native / qty_pool if qty_pool > 0 else 0
            pmp_eur = cost_pool_eur / qty_pool if qty_pool > 0 else 0

            # Realized = proceeds_eur (net of sell fees) - cost_basis_eur sur ce qty vendu
            proceeds_eur = qty * price_native * fx - fees_native * fx
            cost_basis_eur = qty * pmp_eur
            realized_eur += proceeds_eur - cost_basis_eur

            # Retire du pool : qty et cost proportionnels
            qty_pool -= qty
            cost_pool_native -= qty * pmp_native
            cost_pool_eur -= qty * pmp_eur

            # Close complète : reset pool (pool vide = PMP n'existe plus,
            # prochain BUY redémarre un nouveau PMP)
            if qty_pool <= _TOL_ZERO:
                qty_pool = 0.0
                cost_pool_native = 0.0
                cost_pool_eur = 0.0
                n_closures += 1

    pmp_native_final = (cost_pool_native / qty_pool) if qty_pool > 0 else None
    pmp_eur_final = (cost_pool_eur / qty_pool) if qty_pool > 0 else None

    # LIVING GRAPH W0 (#110, SPEC §4) : publie pmp_eur dans concept_index pour
    # fork-detection au regen-end. Source canonique = "ledger_pmp" (ce helper).
    # Si une autre source (VUE SQL ex-helper, autre chemin) publie une valeur
    # différente au-delà de ε=0.001 pour ce ticker/jour → fork détecté = L29
    # mécanisé. Silent-miss L7 si living_graph DB indispo.
    if pmp_eur_final is not None and upto is None:  # jamais publier un état passé
        try:
            from shared.living_graph import register_concept
            register_concept(
                concept_key="pmp_eur",
                value=pmp_eur_final,
                source="ledger_pmp",
                ticker=ticker,
                op="rolling_fifo_french_cgi",
            )
        except Exception:
            pass  # silent-miss L7

    return PositionPMP(
        ticker=ticker,
        qty=qty_pool,
        pmp_native=pmp_native_final,
        pmp_eur=pmp_eur_final,
        realized_pnl_eur=realized_eur,
        n_closures=n_closures,
    )
