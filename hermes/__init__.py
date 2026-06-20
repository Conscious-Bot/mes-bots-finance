"""Hermes — majordome PRESAGE (audit doctrine SAS 20/06/2026).

Deux tiers de capacite :

Tier R (Read-only) — inspector, observer, courses de recherche.
    Aucune ecriture d'etat, aucune edition de fichier. Freeze-safe par
    construction. Active maintenant.

Tier P (Propose) — write-gate via table proposals + APScheduler drain +
    doctrine_gate. AUTO commit ou TAP user notify. NOT INSTALLED.
    Gate sur KPI #2 canonical >= 5 resolved 28d (currently 2, breach).

Doctrine inspecteur, pas renovateur :
- Diagnostic libre, intervention interdite
- Aucune affirmation 'mort' sans preuve outil determinist (3 lentilles)
- Doctrine-aware : grace-period dépréciation, versioning archive, exclusions
- Sortie = backlog priorise pour ton jugement, jamais auto-applique
"""

__version__ = "0.1.0"
