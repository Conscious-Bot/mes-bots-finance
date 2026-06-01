# mes-bots-finance (PRESAGE)

> **La vérité dans le bruit. / Truth in the noise.**

Closed-loop personal finance intelligence: Telegram bot (`@Hawk_Dove_bot`) + Claude. Self-learning thesis tracker with bidirectional discipline enforcement.

**Le bot ne trade pas.** Il mécanise la discipline pré-commit. Deux biais empiriquement documentés (cf [`docs/glossary.md` § Biais documentés](docs/glossary.md)) : **`lock_in`** (vendre les winners trop tôt) = biais #1, raison d'être de PRESAGE — **non instrumenté à ce jour**, chemin prévu Surface 2 ADR-010 §2 ; **biais #2 historique** (anti-FOMO crypto aux tops) dormant ortho (stock-only depuis 26/05). L'enum technique `fomo_greed` (acception large = « pas réduit/sorti quand la discipline le disait ») est mécanisé sur 2 canaux (`kill_criteria` actif, `over_cap` en veille phase construction) — distinct du biais #2 crypto-tops. Boucle : ingestion → process LLM → décision → prédiction (horizon mesurable) → outcome → calibration → réinjection contexte.

## État (30/05/2026)

- **414 tests verts** (+ 4 slow network-dependent, `pytest -m slow`)
- **Bot** : Python 3.14 / SQLite WAL / APScheduler / cascade Anthropic Haiku-Sonnet-Opus
- **Privé** : repo `Conscious-Bot/mes-bots-finance`. Going public différé post-août (cf calibration V2 wired).
- **Mode** : High Standard / Solidification. Phase A du PLAN_ACQUIHIRE.

## Parcours de lecture (selon profondeur)

**Quick read (~15 min)** : qu'est-ce que c'est et où on en est
1. `docs/AGENT_HANDOFF.md` — manuel de reprise pour agent IA, contrat de travail + 5 pièges connus + leçons cardinales
2. `FICHE_TECHNIQUE.md` — mission + stack + KPIs + résumé dernière session

**Medium read (~1h)** : ajouter le pourquoi + les invariants
3. `PHILOSOPHY.md` — High Standard Mode + boucle décision-outcome-rétrospection
4. `CONVENTIONS.md` — naming + structure + Lessons 1-41 + règle DB_PATH (§5)
5. `docs/adrs/README.md` — index des Architecture Decision Records (12 ADRs)
6. `docs/decision_logs/01_calibration_unanchored.md` — arc V2 calibration 10 itérations (30/05)

**Deep read (~3h)** : voir le code en action
7. `intelligence/signal_scorer_v2.py` — élicitation probabiliste 3 étapes (canonique)
8. `intelligence/edgar_signal_wire.py` — wire SEC primary forward-only
9. `shared/storage.py` — passerelle DB unique (sauf modules-domaine, cf CONVENTIONS §5)
10. `posts/post_01_calibration_unanchored.md` — narratif publishable de l'arc

## Stack contraintes

- Python 3.14, SQLite **WAL mode**, APScheduler, embeddings BGE-small-en-v1.5 locaux
- Cascade Anthropic : Haiku (volume) / Sonnet (enrich) / Opus (raisonnement)
- Dashboard read-only : `dashboard/render.py` (static-gen → dashboard.html) + `dashboard/serve.py` (stdlib, 127.0.0.1:8000)
- **INTERDITS** : FastAPI / Postgres / Redis / LangGraph. Local MacBook Pro, pas de cloud.

## Tests

```bash
venv/bin/pytest tests/ -q                # 414 tests rapides (~2 min)
venv/bin/pytest tests/ -m slow           # 4 tests reseau-dependants
venv/bin/ruff check .                    # lint
```

## Path 5/6 strategic mode

Acquihire (18-24mo) **ou** Substack/prosumer subscription (24-36mo). Cf `PLAN_ACQUIHIRE.md` pour l'arc 6 mois (Phase A fondations / Phase B publication / Phase C distribution). Track record vérifiable = l'asset central.

## Documents canoniques

| Fichier | Rôle |
|---|---|
| `docs/AGENT_HANDOFF.md` | **Premier doc à lire**. Manuel de reprise + pièges + leçons |
| `FICHE_TECHNIQUE.md` | Mission + stack + KPIs runtime + dernière session |
| `PLAN_ACQUIHIRE.md` | Arc 6 mois strategic (Phase A/B/C) |
| `PHILOSOPHY.md` | High Standard Mode + boucle |
| `CONVENTIONS.md` | Naming + structure + Lessons 1-41 |
| `TODO.md` | Backlog actionnel courant |
| `SESSION_STATE.md` | Handoff de session (tail = état courant) |
| `docs/adrs/` | 12 Architecture Decision Records |
| `docs/decision_logs/` | Decision logs longs (`01_calibration_unanchored.md` = arc V2) |
| `posts/` | Posts canoniques bilingues FR+EN (publication différée) |

Aucun chemin caché : tout est traçable depuis `AGENT_HANDOFF.md`.
