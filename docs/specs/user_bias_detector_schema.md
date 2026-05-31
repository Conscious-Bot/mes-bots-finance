# User Bias Detector — schéma canonique

> Spec user 31/05/2026 (close-session). **Schéma data-first** : une fois le flux d'événements posé, le panneau (Pile 1.1) et le compteur coût-de-biais tombent tout seuls — ils ne font que lire `bias_events`.

## Principe central : convention bidirectionnelle, **une seule somme signée**

`delta_signed = value_taken − value_avoided`, **toujours « positif = bonne décision »**.

- `acted_on_bias` : chemin pris = le biais. Si le biais a coûté, `delta_signed < 0` = coût matérialisé.
- `resisted` : chemin pris = la discipline. Si elle a payé, `delta_signed > 0` = valeur bankée.

Compteur du panneau = `SUM(delta_signed)` sur résolus, décomposable en deux moitiés :
1. Coût d'avoir cédé (somme des `acted_on_bias`)
2. Dividende d'avoir résisté (somme des `resisted`)

**Un seul nombre, bidirectionnel, qui dit littéralement ce que ta discipline vaut en euros.**

## Table canonique

Conventions respectées : UTC interne · JSON sorted keys · status lowercase_snake · erreurs explicites.

```sql
CREATE TABLE bias_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at          TEXT NOT NULL,        -- UTC ISO 8601
    ticker              TEXT,                 -- UPPERCASE, NULL = niveau portefeuille
    bias                TEXT NOT NULL,        -- lock_in | fomo_greed | other
    action              TEXT NOT NULL,        -- acted_on_bias | resisted
    decision_json       TEXT NOT NULL,        -- ce que la discipline disait vs ce que tu as fait
    counterfactual_json TEXT NOT NULL,        -- les deux chemins + ancre prix/horizon
    resolution_json     TEXT,                 -- NULL jusqu'à résolution (comme outcome_json)
    status              TEXT NOT NULL DEFAULT 'open',  -- open | resolved | void
    source              TEXT NOT NULL,        -- telegram_tap | auto_detected | manual
    thesis_id           INTEGER,              -- FK theses (nullable)
    prediction_id       INTEGER,              -- FK predictions (nullable)
    note                TEXT,                 -- le "j'ai résisté ici", contexte libre
    resolve_at          TEXT NOT NULL         -- UTC ISO, quand mesurer le coût
);
CREATE INDEX idx_bias_events_open ON bias_events(status, resolve_at);
CREATE INDEX idx_bias_events_bias ON bias_events(bias, action, created_at);
```

## Sous-schémas JSON

### decision_json — capture la divergence

```json
{
  "conviction": 4,
  "discipline_said": {"action": "hold", "ref": "rule:rightsize_c4", "target_size_pct": 6.0},
  "price_at_event": 181.2,
  "user_did": {"action": "trim", "size_pct_after": 3.0}
}
```

### counterfactual_json — fige les deux chemins à mesurer plus tard

```json
{
  "anchor_price": 181.2,
  "horizon_days": 30,
  "path_avoided": "discipline",
  "path_taken": "user",
  "shares_delta": -40
}
```

### resolution_json — rempli par le cron resolve

```json
{
  "delta_signed": -890.0,
  "measured_at": "2026-07-10T07:00:00+00:00",
  "price_at_horizon": 203.5,
  "summary": "trim NVDA à 181 = -890€ vs hold discipline",
  "value_avoided": 8140.0,
  "value_taken": 7250.0
}
```

## Capture — un tap, sinon ça ne vit pas

### Auto-détecté

`intelligence/bias_tagger.auto_tag_biases` **existe déjà** (10 biais classifiés par Haiku : anchoring, recency_bias, confirmation_bias, fomo, narrative_capture, loss_aversion, regret_avoidance, overconfidence, sunk_cost, availability_heuristic).

À câbler : quand `bias_tagger` détecte un pattern correspondant à `lock_in` (loss_aversion + sunk_cost) ou `fomo_greed` (fomo + narrative_capture + overconfidence) sur `/position_buy` ou `/position_sell` → INSERT `bias_events` avec `source=auto_detected`, `discipline_said` préremplie depuis la règle violée, `user_did` depuis le `position_event` correspondant.

### Auto-déclaré (le plus précieux)

`/resisted NVDA` → handler Telegram qui :
1. Récupère le prix courant via `prices.get_current_price(ticker)` NATIVE
2. Trouve la thèse ouverte liée (`thesis_id` via positions/theses join)
3. INSERT avec `action='resisted'`, `source='telegram_tap'`, `bias` inféré du contexte ou demandé en réplique
4. Demande une ligne de note (un tap supplémentaire OK pour la donnée la plus précieuse)

## Câblage à l'existant

### Cron `resolve_due_bias_events()`

Calque exact de `resolve_due_predictions()` (cf commit `bce5a58` après fix wrong-day close) :
- Filtre `WHERE status='open' AND resolve_at <= now`
- Prix via `prices.get_close_on(ticker, resolve_at)` NATIVE (FX-invariant)
- Écrit `resolution_json` avec `delta_signed`, `value_avoided`, `value_taken`, `price_at_horizon`
- Passe `status='resolved'`

Cron schedule : `daily 9h CEST` (même famille que resolve_predictions).

### Panneau discipline (Pile 1.1)

- **Hero du panneau** : compteur bidirectionnel `SUM(delta_signed)` en Geist Mono, axe primitive de gauche-coût → droite-valeur. Hérite du pattern Track record.
- **Journal** : flux des `bias_events` résolus, langage visuel du registre / axe.
- **État honnête-tôt** : si N résolus < 10 → `INSUFFISANT — N<10` (charter §12).
- Filets fins, motion épistémique.

## Pré-requis avant 10/06 (pas dans la panique du jour)

Checklist J-3 (07/06) :
1. Test `recalib_map.fit_calibration_map()` avec mock n=30+ v1 → CalibrationMap pas None
2. Vérif `_track_record_panel()` disparaît bien N>=10 (charter §12 + commit `bd932d8`)
3. `_distribution_health_panel()` reflète live les nouvelles résolutions
4. Hero portefeuille au bar (Pile 1.2) — sinon le 1er point tombe dans frame vide

## Séquencement strict (user spec close-session)

**Profondeur, pas largeur :**

```
0. Mode advisory deepening      ──  condition qualité data (si bot flic, user désengage)
1. Pile 2.1 : table bias_events + cron resolve + Telegram /resisted
2. Pile 1.1 : panneau discipline/biais surface (hérite Track record)
3. Pré-requis J-3/07-06       ──  vérif scaffolds + hero au bar
4. 10/06 : observation activation auto + 1er point réel
5. Pile 1.2-1.4 : héritage pattern (hero / évidence / Telegram) ─ après 1.1 stable
```

**Tooling découpé** (pas de yak-shave) :
- Live-reload + Geist auto-hosted : **FIRST** (30 min, accélère tout)
- Plot/uPlot : **quand graphes** (pas avant)
- Playwright : **dernier** (régression sur design qui bouge = gaspillage)

## Ce qui n'est pas dans cette spec

- **Publier #01** : déjà fait 31/05 (commit `1c42026` + tag `publish-post-01-20260531`). Ne dépend d'aucun autre item, ne re-plaide pas, juste fait.
- **Calibration map / base rates / outcome context** : déjà scaffoldés (commit `d607085`), s'activent N>=30 auto post-10/06.
- **bias_tagger.auto_tag_biases** : existe déjà (`intelligence/bias_tagger.py`), 10 biais classifiés par Haiku. À mapper vers le triplet canonique `lock_in / fomo_greed / other` pour cohérence.
