# hermes — majordome PRESAGE

Agent SAS pour la maison Presage. Deux tiers de capacité strictement séparés.

## Doctrine

> Inspecteur, pas rénovateur. Bloc-notes, jamais marteau. Diagnostic libre, intervention interdite.

Audit code = lecture seule. Aucune édition de fichier, ni d'état. Le verdict reste au maître de maison.

## Tiers

### Tier R — Read-only ([`hermes.inspector`](inspector/))

**Statut** : ✓ installé (20/06/2026)

5 lentilles. Les 3 premières en triangulation (1/3 → WATCH, 3/3 → DEAD). Les 2 dernières sont des lectures directes (violations canoniques, état infra).

| Lens | Source | Cible |
|---|---|---|
| `lens_static` | `ruff` + `vulture` (AST) | symbols dead-by-syntax |
| `lens_runtime` | telemetry `handler_calls` + `scheduler_runs` (via `storage.db_ro`) | handlers/crons 0 appel sur fenêtre |
| `lens_decision` | DB `signals` + `predictions` + `ticker_meta` (read-only) | sources/tickers 0 matter / 90j |
| `lens_doctrine` | grep code vs ADRs + LESSONS L1-L25 | violations doctrine canonique |
| `lens_ci` | `gh run list` + `gh run view --log-failed` | CI failures + tests récurrents |

Triangulation strict :
- 1 lens KO  →  **WATCH** (à regarder)
- 2 lens KO  →  **CANDIDATE** (confiance moyenne)
- 3 lens KO  →  **DEAD** (haute confiance, candidat suppression)

**Doctrine-aware** : avant de promouvoir un candidat, vérifie exclusions :
- CONVENTIONS §13 : v0/v1 archives intentionnels (comparaison cohort)
- CONVENTIONS §15 : grace-period 1 mois après marker DEPRECATED
- `KNOWN-GAP:` markers
- Shadow scorer ADR 014 (pendant migration)
- Variables `_xxx` prefix (RUF059 dummy convention)

### Tier P — Write-gate (table `proposals` + drain + `doctrine_gate`)

**Statut** : ✗ NOT INSTALLED. Gated sur KPI #2 ≥ 5 résolved 28j canonical (FICHE_TECHNIQUE NON-NEG, currently 2/5 → breach).

## Usage CLI

```bash
# Full scan, écriture report markdown dans docs/
python -m hermes.inspector --since 90d

# Cible spécifique
python -m hermes.inspector --target dashboard/ --since 90d

# Une seule lens
python -m hermes.inspector --lens static --since 30d

# Dry-run (affiche summary, n'écrit rien)
python -m hermes.inspector --since 90d --dry-run

# Vulture moins strict (plus de candidats)
python -m hermes.inspector --min-confidence 60
```

## Output

`docs/AUDIT_HERMES_YYYY-MM-DD.md` — backlog priorisé. Format :

```markdown
## DEAD (3/3) — haute confiance
### `cmd_foo` [handler]
  - static  : [vulture/vulture-function] bot/handlers/foo.py:42 (100%)
  - runtime : last_call=NEVER (window=90d)
  - decision: 0 signal / 0 prediction / 90d
  → candidat suppression. **Verdict : toi.**
```

Aucune affirmation 'mort' n'est un verdict. Chacune est un candidat pour le jugement humain.

## Boundary

Ce qui est **interdit** au code agent (gravé) :
- Édition d'un fichier `.py` / `.md` / `.css` / `.html` (hors `docs/AUDIT_HERMES_*.md`)
- Écriture DB (toute connexion = `mode=ro` strict)
- Commit / push git
- Re-exécution de scripts externes (sauf `ruff` et `vulture` en read)

Si le code agent essaye de muter quelque chose, c'est un bug à fixer immédiatement.
