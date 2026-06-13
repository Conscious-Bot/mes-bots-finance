r"""Ajout position SPCX (Space Exploration Technologies) — IPO 12/06/2026.

Pourquoi : Olivier a achete 600 EUR de SPCX a l'IPO du 12/06 a 130 EUR/share
via TR. Position nouvelle, these basique posee meme jour.

Composants :
1. INSERT BUY ledger transactions (convention TR : price_native en EUR,
   currency='USD' tag, fx_at_trade=1.0, UUID broker_trade_id).
2. INSERT these (entry stocke en USD natif via fx live, target/stop en EUR
   direct decision Olivier 13/06).

Convention thesis SPCX :
- entry_price = 150.45 USD (= 130 EUR × fx live 1.1573, currency='USD' natif)
  /!\ Writeonce trigger 0054 : impossible a modifier post-INSERT.
- target_full = 500 EUR (direct, currency='EUR')
- stop_price = 50 EUR (direct, currency='EUR')
- Mismatch ccy interne entry vs target/stop assume (decision 13/06 update).

Variant explicite (cf L16 parameter-free) :
- Consensus yfinance : 3 analystes, target_mean 139.33 USD, recommendation Sell
- target_high analyste = 190 USD (le plus bullish)
- Target Olivier 500 EUR = 578 USD = 3.04x le high analyste
- Position ULTRA-divergente, variant explicite c5.

DB backup pre-INSERT : data/bot.db.backup_pre_spcx_<timestamp>
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from shared import positions, prices, storage as s


def main():
    today_iso = datetime.now(UTC).date().isoformat()
    fx_eur_usd = prices.get_fx_rate_on("EUR", "USD", today_iso)
    if not fx_eur_usd or fx_eur_usd <= 0:
        raise RuntimeError(f"FX EUR/USD indispo : {fx_eur_usd}")

    entry_eur = 130.0
    target_eur = 500.0
    stop_eur = 50.0
    qty = round(600.0 / entry_eur, 6)
    entry_usd = round(entry_eur * fx_eur_usd, 2)

    # 1. INSERT BUY ledger (convention TR EUR-as-USD)
    broker_id = str(uuid.uuid4())
    positions.add_buy(
        "SPCX", qty=qty, price=entry_eur, fees=0,
        currency="USD", fx_at_trade=1.0,
        broker_trade_id=broker_id,
        source="manual_add_buy",
        notes="SPCX IPO 12/06, +600 EUR a 130 EUR/share",
    )

    # 2. INSERT these (entry USD natif, target/stop EUR direct, substance gravee)
    import json as _json

    key_drivers = [
        "Starship reusability scale : cout/kg en orbite divise par 10-100",
        "Starlink revenue ramp : >$20B run-rate confirmed avant 2027",
        "Musk ecosystem cross-pollination (TSLA Optimus + FSD AI + SPCX manufacturing)",
        "Optionalite merger SPCX-TSLA : multiple expansion conglomerat post-deal",
    ]
    invalidation_triggers = [
        "Musk leadership crisis materielle (sante, controverse legale, exit)",
        "Starship echec scalable (3+ explosions consecutives v2/v3 ou abandon program)",
        "Antitrust block explicite du merger SPCX-TSLA (regulators US/EU)",
        "Starlink subscriber growth flat 2 quarters consecutifs",
    ]
    variant_perception = (
        "Merger SPCX-TSLA a terme. Musk ecosystem flywheel (Starship + Starlink + "
        "TSLA Energy/Optimus) value sous-evalue par la rue qui regarde SPCX comme un "
        "space-pure-play. Vraie valeur = optionalite d'integration multi-business Musk."
    )
    driver_epic = (
        "Convergence SPCX-TSLA en 18-36m : Starlink finance Starship, Optimus + FSD "
        "integrent l'ecosystem manufacturing, merger ouvre la valuation au niveau "
        "conglomerat (Berkshire-style)."
    )
    pre_mortem = (
        "Si je devais expliquer pourquoi cette these a echoue dans 18m : 1) Musk a "
        "perdu l'attention SPCX au profit de xAI/X/Politics, 2) Le merger est bloque "
        "par antitrust, 3) Une concurrence (Bezos/Blue Origin nouvelle gen + Chinese "
        "state) commoditise Starship economics avant scale."
    )

    with s.db() as cx:
        cur = cx.execute("""
            INSERT INTO theses (
                ticker, opened_at, conviction, direction, horizon, status,
                entry_price, entry_value, entry_currency, entry_asof,
                entry_fx_at_call, entry_fx_at_call_asof,
                target_full, target_full_value, target_full_currency, target_full_asof,
                stop_price, stop_value, stop_currency, stop_asof,
                position_type, conviction_at_entry,
                key_drivers, invalidation_triggers, variant_perception,
                driver_epic, pre_mortem,
                notes
            ) VALUES (
                'SPCX', ?, 5, 'long', '18m', 'active',
                ?, ?, 'USD', ?, ?, ?,
                ?, ?, 'EUR', ?,
                ?, ?, 'EUR', ?,
                'priced', 5,
                ?, ?, ?,
                ?, ?,
                ?
            )
        """, (
            datetime.now(UTC).isoformat(),
            entry_usd, entry_usd, today_iso, fx_eur_usd, today_iso,
            target_eur, target_eur, today_iso,
            stop_eur, stop_eur, today_iso,
            _json.dumps(key_drivers, ensure_ascii=False),
            _json.dumps(invalidation_triggers, ensure_ascii=False),
            variant_perception, driver_epic, pre_mortem,
            "IPO 12/06 conv c5 high-conviction variant explicite. "
            "Target/stop en EUR direct (decision Olivier 13/06). Entry stocke "
            f"en USD natif ({entry_usd} USD = 130 EUR × fx {fx_eur_usd:.4f}) "
            "writeonce par trigger 0054, mismatch ccy entry vs target/stop a noter. "
            "Variant explicite : consensus yfinance target_mean=139 USD reco=Sell, "
            "target_high analyste=190 USD, Olivier 500 EUR = 578 USD = 3x le high.",
        ))
        cx.commit()
        thesis_id = cur.lastrowid

    print(f"✓ SPCX inserted : tx + these id={thesis_id}")


if __name__ == "__main__":
    main()
