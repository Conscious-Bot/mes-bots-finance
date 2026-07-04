---
description: Crash-test mensuel fail-closed — panne yfinance simulée, vérifier que tout dit « je ne sais pas »
---

# /crash-test — Panne simulée mensuelle (L15/L31)

**Pourquoi** : les fail-closed posés le 04/07 (snapshot REFUSÉ, digue gel-hold,
kill aveugle notifié) ne valent que s'ils tiennent ENCORE dans six mois. Le seul
moyen de le savoir : simuler la panne et regarder le système. Un chemin qui
fabrique un nombre sous panne = régression L31 à corriger séance tenante.

**Quand** : 1×/mois (~1h), et après tout chantier touchant prices/snapshot/digue/kill.

## Mécanisme

`PRESAGE_SIMULATE_YF_DOWN=1` fait raise `SimulatedOutage` au chokepoint unique
`shared/prices._yf_ticker` → chaque caller traverse son chemin d'erreur RÉEL.
Zéro appel réseau sous flag.

## Exécuter

```bash
source venv/bin/activate

# 1. La suite automatisée du flag (rapide, CI-safe)
python3 -m pytest tests/test_crash_test_flag.py -q

# 2. Regen dashboard SOUS PANNE — lire l'écran ensuite
PRESAGE_SIMULATE_YF_DOWN=1 PYTHONPATH=. python3 -c "from dashboard.render import render; print(render())"

# 3. Snapshot book sous panne — DOIT raise « REFUSÉ » (pas de row fabriquée)
PRESAGE_SIMULATE_YF_DOWN=1 PYTHONPATH=. python3 -m intelligence.snapshot || echo "OK: refus attendu"

# 4. État digue sous panne (lit la DB, dernière row complète = normal si fraîche)
PRESAGE_SIMULATE_YF_DOWN=1 PYTHONPATH=. python3 -m intelligence.digue_monitor
```

## Lecture du verdict (checklist honnêteté)

- **Dashboard (étape 2)** : les prix/valeurs affichés doivent venir du cache/stale
  MARQUÉ (panneau Data health « Stale prix n/N », chips as-of) — AUCUN panneau ne
  doit afficher un nombre frais inventé. Panneaux vides > panneaux faux.
- **Snapshot (étape 3)** : RuntimeError « snapshot book REFUSÉ » = comportement
  correct. Une row écrite sous panne totale = RÉGRESSION L31.
- **Digue (étape 4)** : si la dernière row complète est fraîche → état normal
  (correct, la panne date de maintenant). Pour tester le gel-hold complet :
  cf tests/test_digue_monitor.py::test_gel_hold_when_signal_lost_during_active_gel.
- **Kill_switch** : couvert par tests/test_kill_switch_smoke.py (snapshot refusé
  + notify + staleness). Sur la VM, une vraie panne se lit dans scheduler_runs
  (kill_snapshot_job FAIL) + le Telegram d'aveuglement.

## Anti-pattern

- Lancer le flag puis ne pas LIRE le dashboard : le crash-test est un test de
  LECTURE (est-ce que l'écran ment ?), pas juste un test de non-crash.
- Oublier d'unset : le flag ne persiste pas (env par commande ci-dessus), mais ne
  JAMAIS l'exporter dans .env / launchd.

## Référence

- Chokepoint : `shared/prices._yf_ticker` + `SimulatedOutage`.
- Doctrine : docs/LESSONS.md L31 (agrégat partiel ≠ total), L15 (fail-closed).
