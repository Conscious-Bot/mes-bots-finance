"""DECISION_QUALITY_ENGINE -- moteur de qualite de decision.

Spec red-team 07/06 nuit. Le jump : passer d'un journal de P&L honnete a un
moteur de qualite de decision. On arrete de scorer les outcomes (domines
par la chance a petit n) pour scorer le process et l'attribution causale.

Composants :
- shared/integrity.py + tests/test_thesis_integrity_chain.py : composant A
  (integrite par pre-engagement, tamper-evident hash chain)
- track_record/attribution.py : composant B (attribution causale 2x2)
- track_record/reference_class.py : composant C (base-rate Bigdata, outside view)

Doctrine :
- L15 fail-closed : UNATTRIBUTABLE plutot que story forcee
- L16 point-in-time : driver scorer tel qu'enregistre a l'entree
- L17 declarative YAML + journal DB append-only
- Anti-double-instrumentation L4 : kill_criteria_respected lit journal existant
"""
