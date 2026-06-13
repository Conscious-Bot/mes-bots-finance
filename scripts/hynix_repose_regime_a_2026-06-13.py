"""Repose 000660.KS SK Hynix en Régime A structural — 13/06/2026.

Pourquoi : le flag 'Dead' du stale_target_monitor sur Hynix etait le plus
dangereux du book — pas un bug de la these mais un misfire du framework.
Hynix est Régime A : un price-target y est une erreur de catégorie. Chaque
jour ou 'Dead' restait affiche, il chuchottait 'vends' au biais #1 lock_in
sur la conviction la MIEUX confirmee du book (beat +45.7%, marges pic 71%).

Cure :
- target_full / stop_price : supprimes (erreur categorie sur chokepoint structurel)
- position_type : 'priced' -> 'structural'
- structural_justification gravee
- 3 sentinelles installees dans invalidation_triggers :
  * S1 spread spot/contrat HBM
  * S2 CXMT subventions + capacity ramp
  * S3 DIO (Days Inventory Outstanding) memory peers
- Cap 6% groupe memoire : a acter au niveau book overlay (hors these)

Lecon methodologique gravee pour #135 doctrine :
Les flags 'dying/dead' mesurent la peremption des NIVEAUX, pas des THESES.
La methode 3-colonnes doit institutionnaliser : l'instrument calcule,
l'ancre externe situe, et aucun des deux ne vend a ta place.

DB backup pre-update : data/bot.db.backup_pre_hynix_repose_<timestamp>
"""
from __future__ import annotations

import json
from shared import storage as s


def main():
    structural_justification = (
        "Régime A : HBM chokepoint structurel. Beat +45.7%, marges pic 71%, "
        "demande IA dépasse capacité expansion 24-36m. Price-target = erreur "
        "de catégorie sur ce nom -- la valeur ne s'évalue pas par target prix "
        "mais par persistance du chokepoint. Cap groupe mémoire 6% reste le "
        "vrai garde-fou de taille (overlay book-level, hors thèse)."
    )
    invalidation_triggers = [
        "S1 spread spot/contrat HBM : si spread se compresse <10% pendant 2 "
        "quarters consecutifs = pricing power érodé, chokepoint fade",
        "S2 CXMT subs + capacity ramp : si subventions chinoises ou capacity "
        "public déclarée > x2 vs plan baseline = substitution menace credible <18m",
        "S3 DIO (Days Inventory Outstanding) memory peers : si DIO industry >90 "
        "jours 2 quarters consecutifs = cycle pivot bear confirmé, plus de pic 71%",
    ]
    notes_addendum = (
        "Repose 13/06/2026 Régime A : target_full et stop supprimés (erreur "
        "catégorie sur chokepoint). 3 sentinelles S1/S2/S3 installées (spread HBM, "
        "CXMT capacity, DIO industry). Cap 6% mémoire à acter au niveau book. "
        "Beat +45.7% & marges pic 71% confirment le chokepoint -- pas le moment "
        "de laisser un flag 'Dead' chuchoter 'vends' sur la conviction la mieux "
        "confirmée du book (biais #1 lock_in)."
    )

    with s.db() as cx:
        cur_notes = cx.execute(
            "SELECT notes FROM theses WHERE id=28",
        ).fetchone()[0] or ""
        cur = cx.execute("""
            UPDATE theses SET
                target_full=NULL, target_full_value=NULL,
                target_full_currency=NULL, target_full_asof=NULL,
                stop_price=NULL, stop_value=NULL,
                stop_currency=NULL, stop_asof=NULL,
                position_type='structural',
                structural_justification=?,
                invalidation_triggers=?,
                notes=?
            WHERE id=28
        """, (
            structural_justification,
            json.dumps(invalidation_triggers, ensure_ascii=False),
            f"{cur_notes}\n\n[13/06/2026 REPOSE RÉGIME A]\n{notes_addendum}",
        ))
        if cur.rowcount != 1:
            raise RuntimeError(f"rowcount={cur.rowcount}")
        cx.commit()
        print(f"✓ UPDATE thesis id=28 (000660.KS Hynix) -> structural Régime A")


if __name__ == "__main__":
    main()
