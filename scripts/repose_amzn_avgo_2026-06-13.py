"""Repose AMZN + AVGO niveaux — 13/06/2026.

Pourquoi : flags 'dying' edge<5% etaient des targets stales (poses dans
regime plus bas, atteints pendant le run), pas des theses erodees. Plan
Olivier : reposer depuis ancres consensus, ne pas laisser le flag
declencher une vente du nom le moins cher du book.

AMZN (id=45) :
- Ancre : PT consensus $307/315 vs spot $244 = +28% upside (le plus gros du book)
- Target mid PT $311 = €269 (fx live USD/EUR)
- Stop $200 = €173 (sous precedent low ~$207)

AVGO (id=33) :
- Ancre : PT $490/495 vs spot $392 = +25%, backlog >$110Md, print 03/09
- Target mid PT $492 = €425
- Stop $325 = €281 (ATR-anchored)
- 4 invalidation_triggers gravees :
  * S10 dual-sourcing TPU (bear-claim core)
  * S11 backlog growth flat 2Q consecutifs
  * S12 hyperscaler capex revision -10% YoY
  * S13 print 03/09 miss revenue -5% OR margin -200bps

Currency : EUR direct (pattern SPCX). Pas de conversion fx applied a
target/stop. Entry restent en USD natif writeonce trigger 0054.

Effet smoke live post-update :
- AMZN dying -> alive (edge +21.4%, consensus delta -14% BEAR)
- AVGO dying -> alive (edge +14.8%, consensus delta -18.6% BEAR)
- stats : dying 4 -> 3, alive 22 -> 23

DB backup : data/bot.db.backup_pre_repose_amzn_avgo_<timestamp>
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

from shared import prices, storage as s


def main():
    today_iso = datetime.now(UTC).date().isoformat()
    fx_usd_eur = prices.get_fx_rate_on("USD", "EUR", today_iso)
    if not fx_usd_eur or fx_usd_eur <= 0:
        raise RuntimeError(f"FX USD/EUR indispo : {fx_usd_eur}")

    # AMZN ancres : PT consensus $307/315, stop sous low ~$200
    amzn_target_eur = round(311.0 * fx_usd_eur, 2)
    amzn_stop_eur = round(200.0 * fx_usd_eur, 2)

    # AVGO ancres : PT consensus $490/495, stop ATR-anchored ~$325
    avgo_target_eur = round(492.0 * fx_usd_eur, 2)
    avgo_stop_eur = round(325.0 * fx_usd_eur, 2)

    avgo_triggers = [
        "S10 dual-sourcing TPU (bear-claim core) : si GOOGL annonce TPU v6/v7 "
        "produit par MRVL ou AMD = AVGO ASIC revenue at risk -> 25-35% du backlog "
        "$110Md depend du custom silicon hyperscaler",
        "S11 backlog growth flat 2 quarters consecutifs (vs $110Md baseline) : "
        "pricing power de la franchise ASIC tested, premium consensus disparait",
        "S12 hyperscaler capex revision -10% YoY (Meta/MSFT/GOOG/AMZN earnings) : "
        "demande ASIC dependante du capex AI direct, revision baissier = direct hit",
        "S13 print 03/09 miss : revenue < consensus -5% OR margin compression "
        "> 200bps = rupture de l'hypothese 'priced for beats', re-rating consensus",
    ]

    with s.db() as cx:
        cur = cx.execute("""
            UPDATE theses SET
                target_full=?, target_full_value=?,
                target_full_currency='EUR', target_full_asof=?,
                stop_price=?, stop_value=?,
                stop_currency='EUR', stop_asof=?,
                notes=COALESCE(notes,'') || ?
            WHERE id=45
        """, (
            amzn_target_eur, amzn_target_eur, today_iso,
            amzn_stop_eur, amzn_stop_eur, today_iso,
            f"\n\n[13/06/2026 REPOSE AMZN]\nTarget repose ancre consensus "
            f"$307/315 mid = €{amzn_target_eur}. Stop €{amzn_stop_eur} sous low precedent.",
        ))
        if cur.rowcount != 1:
            raise RuntimeError(f"AMZN rowcount={cur.rowcount}")

        cur = cx.execute("""
            UPDATE theses SET
                target_full=?, target_full_value=?,
                target_full_currency='EUR', target_full_asof=?,
                stop_price=?, stop_value=?,
                stop_currency='EUR', stop_asof=?,
                invalidation_triggers=?,
                notes=COALESCE(notes,'') || ?
            WHERE id=33
        """, (
            avgo_target_eur, avgo_target_eur, today_iso,
            avgo_stop_eur, avgo_stop_eur, today_iso,
            json.dumps(avgo_triggers, ensure_ascii=False),
            f"\n\n[13/06/2026 REPOSE AVGO + bear-claim S10]\nTarget €{avgo_target_eur} "
            f"(PT mid $492). Stop €{avgo_stop_eur} (~$325 ATR). 4 triggers S10-S13.",
        ))
        if cur.rowcount != 1:
            raise RuntimeError(f"AVGO rowcount={cur.rowcount}")
        cx.commit()
        print(f"✓ UPDATE AMZN + AVGO OK")


if __name__ == "__main__":
    main()
