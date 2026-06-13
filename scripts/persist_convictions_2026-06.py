"""Fige les convictions/targets/stops re-placees (rubric 5-facteurs, 12/06/2026).

Ecrit dans theses (lu par le bot : kill_criteria, sizing, gauges). UPDATE cible
par id (1 ligne/ticker verifie). Ne touche PAS les champs entry (write-once).
Passerelle L17 (shared.storage.db). Read-back de verification.

Changements :
- TSLA (id42) : conv 4->5, target 468->1075, stop 335->280, invalidation definie
  (FSD/Optimus fin 2027). Le c5 devient falsifiable, plus de la foi.
- SNPS (id29) : target NULL->700, stop NULL->388 (conv deja 5). Variant bull.
- TSM  (id27) : target 495.23->495, stop 305->375 (conv deja 5). Variant bull.
- ASML/Shin-Etsu/CCJ : inchanges (c5-hold / deja 4/4), rien a ecrire.
"""
from shared.storage import db

ASOF = "2026-06-12"
TSLA_INVAL = ('["FSD/robotaxi non-scale commercialement fin 2027",'
              '"Optimus zero traction commerciale fin 2027",'
              '"marges auto Tesla s effondrent (moteur cash du flywheel)",'
              '"Musk dilue activement les porteurs Tesla (deal SpaceX defavorable)"]')

UPDATES = [
    {"ticker": "TSLA", "id": 42, "conviction": 5, "target": 1075.0, "stop": 280.0, "inval": TSLA_INVAL},
    {"ticker": "SNPS", "id": 29, "conviction": 5, "target": 700.0,  "stop": 388.0, "inval": None},
    {"ticker": "TSM",  "id": 27, "conviction": 5, "target": 495.0,  "stop": 375.0, "inval": None},
]

for u in UPDATES:
    sets = ("conviction=?, target_full=?, target_full_value=?, target_full_currency='USD', "
            "target_full_asof=?, stop_price=?")
    params = [u["conviction"], u["target"], u["target"], ASOF, u["stop"]]
    if u["inval"] is not None:
        sets += ", invalidation_triggers=?"
        params.append(u["inval"])
    params.append(u["id"])
    try:
        with db() as cx:
            cur = cx.execute(f"UPDATE theses SET {sets} WHERE id=?", params)
            rc = cur.rowcount
        print(f"{u['ticker']:6} UPDATE rowcount={rc} {'OK' if rc==1 else 'ANOMALIE'}")
    except Exception as e:
        print(f"{u['ticker']:6} UPDATE FAILED -> {type(e).__name__}: {e}")

print("\n=== READ-BACK (verify-after-write) ===")
with db() as cx:
    for u in UPDATES:
        r = cx.execute("SELECT ticker,conviction,target_full,target_full_currency,stop_price,"
                       "invalidation_triggers FROM theses WHERE id=?", (u["id"],)).fetchone()
        d = dict(r)
        d["invalidation_triggers"] = (str(d["invalidation_triggers"])[:60] + "...") if d["invalidation_triggers"] else None
        print("  ", d)
