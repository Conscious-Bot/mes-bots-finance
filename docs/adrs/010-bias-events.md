# ADR 010 — bias_events : instrumentation de la boucle comportementale

**Statut** : Accepted (01/06/2026, après v1 mécanique posée + v2.a/v2.b implémentés)
**Vocabulaire** : conforme à [docs/GLOSSARY.md](../GLOSSARY.md) v1.0
**Migration** : 0023

## Contexte

La boucle comportementale (User Bias Detector) est la mission même de PRESAGE — et la pièce sous-instrumentée face à toute la machinerie de forecasting. Deux biais documentés à mesurer :

- **lock-in** (`lock_in`) — vendre les gagnants trop tôt.
- **FOMO / avidité** (`fomo_greed`) — tenir au-delà du top.

**Contrainte fondatrice** : cet instrument mesure quelqu'un qui a intérêt à ce que le chiffre soit beau — l'utilisateur lui-même. Tout point de discrétion laissé à l'agent biaisé contamine la mesure. Tout ce qui peut être non-discrétionnaire (auto-détecté, piloté par règle, horizon figé) **doit l'être**.

## Décision

### 1. Un événement de biais = une prédiction sur un contrefactuel

Réutilise la boucle resolve des prédictions : événement loggé à `t` avec une ancre, résolu à l'horizon, coût mesuré objectivement. Pas de nouvelle machinerie.

### 2. Compteur bidirectionnel signé

`delta_signed = value_taken − value_avoided`, convention « positif = bonne décision » :

- `acted_on_bias` → `delta_signed < 0` = coût d'avoir cédé.
- `resisted` → `delta_signed > 0` = valeur bankée par la discipline.

Compteur du panneau = somme signée des résolus, décomposable en deux moitiés (**coût du biais / valeur de la discipline**).

### 3. Capture non-discrétionnaire (le point critique)

- `discipline_said` est capturé à l'instant `t` depuis une règle déterministe, jamais reconstruit à la résolution — sinon tautologie (cf. fix `/asymmetry`). Tracé par `captured_at_event: true`.
- `resisted` est **auto-détecté** : la discipline a recommandé une action, aucun `position_event` correspondant à l'horizon → `resisted` auto-loggé. **Indispensable** : sans ça la capture est asymétrique (auto pour céder, manuel pour résister) et le compteur sous-compte la discipline.
- `acted_on_bias` auto-détecté via `bias_tagger` sur `/position_buy|sell`.
- Le tap manuel (`/resisted`) existe en secours, **pas comme voie primaire**.

### 4. Horizon = horizon de la thèse, jamais post-hoc

Le coût d'un biais est horizon-sensible (cherry-pickable). On fige l'horizon sur la thèse liée (sinon défaut `SIGNAL_TYPE_HORIZONS`), **à la création**. Optionnel v2 : mesurer aussi à 30/90 j (distribution), comme le CLV.

### 5. Contrefactuel — v1 simple et flaggée, v2 redéploiement

- **v1 (ship)** : `counterfactual_method: "cash_idle"` — suppose le cash libéré oisif. EUR FX-cohérent aux deux dates (event + horizon) via `get_close_on_in_eur` — non déferré, c'est une condition de justesse, pas un raffinement.
- **v2 (différé)** : `counterfactual_method: "redeployment"` — trace ce que le cash a réellement fait. Déclenché si v1 tourne et qu'il y a raison d'affiner.

`counterfactual_method` est stocké → toute lecture sait sous quelle hypothèse le coût est calculé.

### 6. Taux, pas somme brute

Le panneau montre **coût par événement + % de décisions où le biais l'emporte + tendance**. La somme nue sans dénominateur est ininterprétable (vanité ou honte).

### 7. Lifecycle explicite

`status : open | resolved | void`. Transitions définies :

- thèse invalidée avant `resolve_at` → `void`
- position ré-entrée avant résolution → `void` + nouvel événement
- prix manquant au resolve → `MissingDataError` (jamais de default silencieux, cf. CONVENTIONS.md §6)

> **Note d'implémentation 01/06** : la migration 0023 expose un enum status plus large (`open | resolved | void | thesis_invalidated | reentered | missing_data`). Pragmatique : permet de distinguer les causes de non-résolution sans pénalité (l'observateur sait pourquoi un event n'a pas résolu). À collapse vers les 3 ADR si l'enrichissement ne sert pas. `MissingDataError` reste l'exception canonique et est captée par `resolve_due_bias_events` qui marque `status='missing_data'` explicit — pas silencieux.

## Schéma — migration 0023

Cf. `scripts/alembic/versions/0023_bias_events.py`.

Divergences mineures vs ADR :
- Status enum élargi (6 vs 3) — pragmatique, voir note §7.
- Pas de colonne `note_tag` séparée pour le moment (le `note` libre suffit en v1, le tag structuré arrive si pattern de tags émergent post-données).

## Shapes JSON (sorted keys, cf. CONVENTIONS.md §3)

```jsonc
// decision_json
{ "captured_at_event": true,
  "conviction": 4,
  "discipline_said": { "action": "hold", "ref": "rule:rightsize_c4", "target_size_pct": 6.0 },
  "price_at_event": 181.2,
  "user_did": { "action": "trim", "size_pct_after": 3.0 } }

// counterfactual_json
{ "anchor_price_eur": 167.4,
  "counterfactual_method": "cash_idle",
  "horizon_days": 30,
  "path_avoided": "discipline",
  "path_taken": "user",
  "shares_taken": 60,
  "shares_avoided": 100 }

// resolution_json (rempli par le cron resolve)
{ "delta_signed_eur": -890.0,
  "measured_at": "2026-07-10T07:00:00+00:00",
  "price_at_horizon_eur": 187.6,
  "summary": "trim NVDA = -890€ vs hold (cash_idle)",
  "value_avoided_eur": 8140.0,
  "value_taken_eur": 7250.0 }
```

## Conséquences

- **Active** : panneau discipline (#10, le second lead) + compteur coût-de-biais. Une fois ce flux posé, le panneau et le compteur ne font que **lire** `bias_events`.
- **Orthogonalité** : ne pas confondre avec le track record de prédiction (mesures distinctes — justesse de prévision vs coût du comportement). Éviter le double-comptage P&L au panneau.
- **Différé** : redeployment (v2).
- **Dépendances** : `bias_tagger` (hook), cron resolve, `prices.py` (EUR), `theses` (horizon).

## Implémentation (Claude Code)

- [x] Migration 0023 (DDL bias_events) — commit `6d3a487`
- [x] `resolve_due_bias_events()` — clone de `resolve_due_predictions`, calcule `delta_signed_eur` via `get_close_on_in_eur` aux deux dates — commit `212155f`
- [x] `MissingDataError` exception — commit `212155f`
- [x] Tests invariants v2 (formule 4 directions + transitions lifecycle) — 14 verts
- [ ] Auto-détection : `acted_on_bias` (hook `bias_tagger`) + `resisted` (recommandation sans `position_event` à l'horizon) — **v2.c à venir**
- [ ] Handler `/resisted` (tap de secours, prérempli prix + thèse) — **v2.d à venir**
- [ ] Alignement counterfactual_json shape `counterfactual_method` (le rename arrive avec v2.c) — **TODO immédiat**

## Statut

**Accepted** 01/06/2026 après v1 mécanique + v2.a/v2.b avec tests. Prochains items : auto-détection (v2.c) + handler `/resisted` (v2.d).
