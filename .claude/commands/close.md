---
description: Rituel de clôture de session (5 min) — handoff vivant pour la session suivante
---

# /close — Rituel de clôture de session

**Pourquoi** : cf `docs/LESSONS.md` L6 — cinq minutes en fin de session épargnent ~30 minutes de re-onboarding la session suivante. Meilleur ratio investissement/retour du projet.

**Quand l'invoquer** : à la fin de toute session non-triviale (livrable substantiel, audit complet, sweep architectural). Pas obligatoire pour les sessions exploratoires courtes.

## Étapes (à exécuter dans l'ordre)

1. **Append une section `## Close YYYY-MM-DD` au tail de `SESSION_STATE.md`** avec :
   - **Livre** : ce qui a été commité aujourd'hui (commits référencés par hash, par chantier — pas du copier-coller du git log brut). Pour chaque chantier, 1 ligne par sous-livrable substantiel.
   - **Audit** (si fait) : findings observés + tri P0/P1/P2/P3.
   - **Cleanup session post-audit** (si applicable) : tâches résolues + faux positifs identifiés.
   - **Outils ajoutés** (si applicable) : skills, MCPs, slash-commands installés.
   - **Entry next session** : 2-4 bullets concrets — qu'est-ce qu'on regarde en priorité au prochain démarrage, quels événements externes pourraient déclencher une intervention immédiate, quelles dates calendaires comptent.

2. **Update `TODO.md`** :
   - Header `**Refresh** : <date>` à jour
   - Section `## 🟢 ÉTAT SYSTÈME (<date>)` rafraîchie : tests verts, alembic head, bot status, cron sains, LLM cost, livrables clés, backlog ouvert
   - Tâches complétées de la session intégrées à `## ✅ DÉJÀ FAIT` (date + chantier court)

3. **Vérifier que tout est commité** :
   - `git status --short` : working tree clean (sauf fichiers pré-session intentionnellement non-touchés)
   - `git log --oneline -<N>` : N commits aujourd'hui visibles, messages cohérents

4. **Commit de clôture si nécessaire** :
   - Si SESSION_STATE et TODO viennent d'être updaté → un commit dédié `session <date> close` ou inclus dans le commit final du chantier (selon contexte). Préfère commit dédié pour traçabilité.

5. **Sanity check final** : full test suite (`source venv/bin/activate && pytest -q --tb=no | tail -3`). Si rouge, fix avant de fermer.

6. **Audit canonical drift** (L25) : `python3 scripts/audit_canonical_drift.py | tail -20`. Reporte par SPEC le ratio référence-code / orphelin + doublons candidats. Si exit code 1 (SPEC sans footer Implementation Status) → noter dans SESSION_STATE comme dette doctrinale (pas blocker du close, mais visible pour la session suivante).

## Anti-pattern à éviter

- Skipper le rituel "parce que la session est courte" → 2 sessions plus tard, le SESSION_STATE est stale et la friction de re-onboarding revient.
- Recopier le `git log` brut dans SESSION_STATE — pas un handoff, juste un dump. Le handoff dit *ce qui a été livré et pourquoi*, pas *quels commits ont été faits*.
- Ne pas mettre l'**entry next session** — c'est la partie qui sauve le plus de temps : elle permet de reprendre sans réfléchir aux 3 minutes de "où en étions-nous ?".

## Référence rapide

- Format du SESSION_STATE close : cf entries `## Close 2026-06-01` (most recent canonical example).
- L6 : `docs/LESSONS.md` § L6 (la règle elle-même).
- Pourquoi commit dédié `session close` plutôt que dans le commit final : permet de bisecter — un futur `git log --oneline | grep close` donne la chronologie des sessions sans bruit.
