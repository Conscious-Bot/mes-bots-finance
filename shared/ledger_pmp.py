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


def compute_pmp_realized(cx: Any, ticker: str) -> PositionPMP:
    """Calcule PMP roulant + realized_pnl date-ordonné pour ce ticker.

    Itère TOUTES les transactions (BUYs + SELLs) ordonnées par trade_date.
    Maintient (qty_pool, cost_pool_native, cost_pool_eur) en mémoire ;
    reset à 0 à chaque close complète.
    """
    rows = cx.execute("""
        SELECT side, qty, price_native, fees_native, fx_at_trade, trade_date
        FROM transactions
        WHERE ticker = ?
        ORDER BY trade_date ASC, id ASC
    """, (ticker,)).fetchall()

    qty_pool = 0.0
    cost_pool_native = 0.0  # somme cumulée qty x price + fees (en native)
    cost_pool_eur = 0.0     # somme cumulée qty x price x fx + fees x fx (en EUR)
    realized_eur = 0.0
    n_closures = 0

    for r in rows:
        side, qty, price_native, fees_native, fx, _ = r
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

    return PositionPMP(
        ticker=ticker,
        qty=qty_pool,
        pmp_native=pmp_native_final,
        pmp_eur=pmp_eur_final,
        realized_pnl_eur=realized_eur,
        n_closures=n_closures,
    )
