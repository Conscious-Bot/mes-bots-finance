# ADR 011 — probability_at_creation: stale-read fix, fail-loud, backfill

**Status**: Accepted (27/05/2026)
**Related**: ADR 007 (credibility single authority + Brier), ADR 009 (conviction soft tiers)

## Context

KPI #3 (Brier rolling 90d) est l'actif central du narratif Path-6 ("comment je sais
que mes convictions sont calibrees"). Audit du pipeline de resolution (27/05): les
154 predictions du ledger portaient probability_at_creation = 0.5 (145) / 0.53 (8) /
NULL (1). Un prior constant a 0.5 donne Brier = (0.5 - outcome)^2 = 0.25 quel que
soit le resultat => KPI #3 mecaniquement fige, zero information de calibration,
retroactivement invalide. Track record invendable.

Root cause (etablie empiriquement, pas par hypothese): insert_prediction
(shared/storage.py) re-requetait signals.score au moment de l'insert. Or
auto_register_predictions filtre sur le score present EN MEMOIRE dans le dict digest,
tandis que l'ecriture DB de la colonne score (materiality_v2) lag par rapport a
l'enregistrement. La ligne lue avait donc score=NULL => estimate_probability(None,...)
-> plancher 0.50. Les 8 a 0.53 = signaux dont signal_type/impact_magnitude etaient
deja ecrits (bonus +0.03) mais pas le score. Le NULL unique = un
except Exception -> prob=None silencieux (violation CONVENTIONS #6).

La formule estimate_probability est saine: nourrie des vrais inputs (meme requete
jouee post-hoc -> 0.596 / 0.628 / 0.660 +bonus, differencie). Defaut de plomberie
(lecture d'une ligne pas encore ecrite), pas de modele.

## Decision

1. Thread, ne re-requete pas. auto_register passe score (deja en main, >=6 garanti
   par son propre filtre) a travers register_prediction jusqu'a insert_prediction,
   avec signal_type/impact_magnitude. insert_prediction ne re-requete plus que
   credibility (propriete de la SOURCE, stable a l'insert, aucun timing).

2. Fail-loud, jamais de plancher silencieux. Si score is None a l'insert: log error +
   return None (prediction NON enregistree). Mieux vaut une prediction manquante
   qu'un prior factice a 0.50 qui pollue le Brier. Supprime la violation CONVENTIONS #6.

3. Backfill du ledger existant. Les 153 non-resolues recomputees via
   estimate_probability depuis la donnee signal desormais persistee. Table
   predictions_bak_probfix (snapshot in-DB) = rollback. Pic plat 0.5 -> spread
   0.576-0.658 differencie.

## Defensibilite (due-diligence Path-5/6)

- Pas de look-ahead. Les 153 etaient TOUTES non-resolues au backfill
  (resolved_at IS NULL). Le prior recompute n'utilise que des features de CREATION
  (score, type, impact, credibility), jamais l'outcome. Reconstruction du prior
  voulu, pas un fit a posteriori.
- Proxy honnete. Le backfill lit la donnee signal ACTUELLE comme meilleur proxy de
  la donnee a la creation. Drift mineur possible si un score a ete re-ajuste
  (materiality_boost) apres creation. Acceptable a N=153.
- Honnetete temporelle. Le ledger Brier AVANT le 27/05 etait decoratif. Le track
  record exploitable demarre 27/05. Toute presentation publique (Substack,
  acquihire) doit le dire: ne jamais revendiquer un Brier pre-27/05.

## Consequences

- KPI #3 devient porteur de signal a mesure que les 153 se resolvent (28j).
- Verification: gates ruff/mypy/import green; smoke end-to-end (DB temp, yfinance
  bypass) -> 25 predictions, toutes >0.5, probs differenciees 0.576-0.652.
- Bug trouve a J+15, pas J+360. L'economie du "bon audit".

## Open / deferred

- Fork de design (CENTRAL, pas cosmetique): auto-register une prediction depuis
  CHAQUE signal score>=6 (5 tickers x N signaux -> predictions correlees, meme prior,
  meme direction) gonfle N mais avec des outcomes correles. Le Brier sur 153 telles
  predictions sur-estime massivement la taille d'echantillon effective (les 5 tickers
  d'un meme signal AI-infra bougent ensemble = ~1 pari independant). "153 predictions
  resolues" est trompeur si c'est ~30 paniers correles. A trancher avant toute
  revendication statistique de track record.
- Bande de l'estimateur: sortie bornee 0.50-0.72, jamais <0.50 (prend toujours le
  sens du signal a >=50%). A confronter aux outcomes: bien calibree ou
  sur/sous-confiante ? Question post-resolution, pas un bug.
- predictions_bak_probfix: drop apres quelques jours de confiance.
