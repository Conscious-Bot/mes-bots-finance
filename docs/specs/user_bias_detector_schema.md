# User Bias Detector — schéma canonique

> Spec user 31/05/2026 (close-session, 2 itérations critiques). **Schéma data-first** : une fois le flux d'événements posé, le panneau (Pile 1.1) et le compteur tombent tout seuls.

## Cadre — la condition de validité

**Cet instrument mesure quelqu'un qui a intérêt à ce que le chiffre soit beau — l'user lui-même.** Donc chaque point de discrétion laissé à l'agent biaisé contamine la mesure. Tout ce qui peut être **non-discrétionnaire** (auto-détecté, piloté par règle, horizon figé) **doit l'être**.

Cette règle force 3 conséquences architecturales :
1. `discipline_said` est capturé **au moment** de l'événement, **depuis une règle déterministe** (pas reconstruit à la résolution = tautologie).
2. `resisted` doit être **auto-détectable**, pas seulement auto-déclaré (sinon capture asymétrique → compteur biaisé).
3. `horizon` est **fixé sur la thèse** (principe), jamais choisi post-hoc.

## Convention bidirectionnelle, **une seule somme signée**

`delta_signed = value_taken − value_avoided`, **toujours « positif = bonne décision »**.

- `acted_on_bias` : chemin pris = le biais. Si le biais a coûté, `delta_signed < 0` = coût matérialisé.
- `resisted` : chemin pris = la discipline. Si elle a payé, `delta_signed > 0` = valeur bankée.

## Métrique honnête : taux, pas somme

**"-2400 € sur 3 décisions ou 300 ?"** Le panneau montre :
- **Coût par événement** (`delta_signed / N`)
- **% décisions où le biais l'a emporté** (`COUNT(acted_on_bias) / COUNT(*)`)
- **Distribution + tendance** (comme le pattern CLV existant)

**Pas de somme brute en hero** = vanité ou honte. Le taux est la métrique honnête.

## Table canonique

Conventions : UTC interne · JSON sorted keys · status lowercase_snake · erreurs explicites + `MissingDataError` jamais de default silencieux.

```sql
CREATE TABLE bias_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at          TEXT NOT NULL,        -- UTC ISO 8601
    ticker              TEXT,                 -- UPPERCASE, NULL = niveau portefeuille
    bias                TEXT NOT NULL,        -- lock_in | fomo_greed | other
    action              TEXT NOT NULL,        -- acted_on_bias | resisted
    decision_json       TEXT NOT NULL,        -- discipline déterministe AU MOMENT
    counterfactual_json TEXT NOT NULL,        -- les deux chemins + ancre + horizon thèse
    resolution_json     TEXT,                 -- NULL jusqu'à résolution
    status              TEXT NOT NULL DEFAULT 'open',
        -- enum strict : open | resolved | void | thesis_invalidated | reentered | missing_data
    source              TEXT NOT NULL,        -- auto_detected | telegram_tap | manual
    thesis_id           INTEGER,              -- FK theses (nullable, mais préféré)
    prediction_id       INTEGER,              -- FK predictions (nullable)
    note_tags_json      TEXT,                 -- tags STRUCTURÉS (pas texte libre)
    horizon_days        INTEGER NOT NULL,     -- copié de la thèse, jamais ad-hoc
    resolve_at          TEXT NOT NULL         -- UTC ISO, = created_at + horizon_days
);
CREATE INDEX idx_bias_events_open ON bias_events(status, resolve_at);
CREATE INDEX idx_bias_events_bias ON bias_events(bias, action, created_at);
```

## Sous-schémas JSON — capture déterministe

### decision_json — capture la divergence AU MOMENT

```json
{
  "conviction": 4,
  "discipline_said": {
    "action": "hold",
    "ref": "rule:rightsize_c4",
    "captured_at_event": true,
    "target_size_pct": 6.0
  },
  "price_at_event_native": 181.20,
  "price_at_event_eur": 154.45,
  "currency": "USD",
  "user_did": {"action": "trim", "size_pct_after": 3.0}
}
```

**`captured_at_event: true`** est l'invariant de falsifiabilité. Si false → reconstruit a posteriori → tautologie → compteur invérifiable.

### counterfactual_json — fige les deux chemins

```json
{
  "anchor_price_native": 181.20,
  "anchor_price_eur": 154.45,
  "horizon_days": 30,
  "horizon_source": "thesis:NVDA-2026-04",
  "path_avoided": "discipline",
  "path_taken": "user",
  "shares_delta": -40,
  "cash_redeployment": {
    "amount_eur": 7250.0,
    "destination": "cash_oisif"
  }
}
```

**`cash_redeployment`** est obligatoire pour les trims : le vrai contrefactuel inclut **ce qui a été fait du cash**. Options enum : `cash_oisif | reinvested:{ticker} | other_position:{ticker}`.

### resolution_json — rempli par cron, EUR FX-cohérent aux 2 dates

```json
{
  "delta_signed_eur": -890.0,
  "measured_at": "2026-07-10T07:00:00+00:00",
  "price_at_horizon_native": 203.50,
  "price_at_horizon_eur": 178.20,
  "value_avoided_eur": 8140.0,
  "value_taken_eur": 7250.0,
  "summary": "trim NVDA à 181 USD = -890€ vs hold discipline",
  "fx_rate_at_event": 1.1655,
  "fx_rate_at_horizon": 1.1420
}
```

**Tout en EUR via `get_current_price_in_eur` + FX cohérent aux 2 dates.** Sinon dérive FX (JPY/KRW/USD) entre event et horizon pollue le coût (leçon FX wave 9 appliquée).

## Capture symétrique — `resisted` aussi auto-détectable

**Asymétrie tue le compteur** : si `acted_on_bias` auto-détecté (fiable) mais `resisted` seulement auto-déclaré (décroît avec mémoire) → sous-compte dividende résister, sur-montre coût céder.

**Règle d'inférence canonique** : 
- À `resolve_at`, regarder s'il y a eu un `position_event` (buy/sell/trim) sur le ticker entre `created_at` et `resolve_at`.
- Si discipline a dit `trim` et **AUCUN position_event de type sell/trim** → `action='resisted'` automatique, `source='auto_detected'`.
- Si discipline a dit `hold` et **AUCUN position_event** → `action='resisted'` automatique.

**Le tap (`/resisted`) reste utile** pour le cas où user veut tagger un événement non-couvert par la règle d'inférence. Mais il **n'est plus le primary path** — il est le complément.

## Horizon = fixé sur la thèse, jamais post-hoc

**"Vendre NVDA tôt a coûté 890 € à 30 j ; à 7 j ça a peut-être sauvé."** Horizon unique cherry-pickable.

**Règle stricte** :
1. `horizon_days` est **copié de la thèse** liée (`thesis_id → horizon`).
2. Si pas de thèse : horizon par défaut **figé en config** (30 j), jamais discrétionnaire.
3. Bonus : sortir le panneau avec **distribution multi-horizon (30 j / 90 j)** quand N suffisant — pattern CLV.

## Note structurée, pas texte libre

Notes "j'ai résisté ici" = données les plus précieuses **mais inexploitables si en texte libre**.

```json
{
  "trigger": "discipline_reminder|telegram_alert|self_initiated|other",
  "what_pulled_me": ["fomo_chart", "macro_fear", "twitter_thread", "thesis_fragility"],
  "what_held_me": ["rule:rightsize_c4", "memory_past_bias", "user_friction.md_note"]
}
```

Tag enum strict (max ~6 valeurs par champ). Évite verbatim de l'user (impossible à agréger).

## Lifecycle status enum strict

`open | resolved | void | thesis_invalidated | reentered | missing_data`

Transitions explicites :
- `open → resolved` : `resolve_at <= now` et prix dispo et thèse encore active.
- `open → thesis_invalidated` : thèse fermée/invalidée avant `resolve_at` → événement n'a plus de référentiel.
- `open → reentered` : user a re-entered la position entre `created_at` et `resolve_at` → contrefactuel cassé.
- `open → missing_data` : prix au resolve indisponible (`MissingDataError`) → **jamais default silencieux**, status explicit.
- `* → void` : marquage manuel rare (erreur de capture, doublon).

Le cron `resolve_due_bias_events` **crashe ou marque missing_data**, ne ment jamais.

## Câblage à l'existant — vérifié

- **`intelligence/bias_tagger.auto_tag_biases`** existe (10 biais Haiku). À mapper vers le triplet user `lock_in / fomo_greed / other` via dict canonique.
- **`shared/prices.get_current_price_in_eur`** existe + FX-coherent via `get_fx_rate` live (commit `ead47c3`).
- **`resolve_due_bias_events()`** = clone exact de `resolve_due_predictions()` (post fix wrong-day close `bce5a58` + monkey-patch native `0730c1a`).
- **Pile 1.1 panneau discipline** = lecture seule sur `bias_events` agrégés.

## Orthogonalité prédiction / biais — pas de double-comptage

**Deux mesures distinctes** :
- **Track record** = "ma prévision était-elle juste ?"
- **Coût-de-biais** = "mon comportement m'a-t-il coûté ?"

**Si un événement bias partage ticker + horizon avec une prédiction** : risque de double-comptage du P&L dans les panneaux. **Garde-les visuellement séparés** :
- Track record en haut (mesure prédiction)
- Discipline panneau en bas ou orthogonal (mesure comportement)

Pas de KPI agrégé qui mélange les deux.

## Pré-requis avant 10/06 (pas dans la panique du jour)

Checklist J-3 (07/06) :
1. Test `recalib_map.fit_calibration_map()` avec mock n=30+ v1 → `CalibrationMap is not None`
2. Vérif `_track_record_panel()` disparaît N>=10 (commit `bd932d8`)
3. `_distribution_health_panel()` reflète live
4. Hero portefeuille au bar
5. **Audit complet `methodology_version != 'v0'` sur TOUS les sites de lecture predictions** (cf leçon FX : un seul site oublié = fausse mesure). Sites confirmés post-31/05 fix : calibration_audit ×2 / portfolio_grade / morning_brief ×4 / observability / v2_vigilance / recalib_map / outcome_context / base_rates. Sites restant à voir : `user_profile.py:367` (cas usage profile, peut-être acceptable).
6. **Tests invariants** : test KPI #2 exclut neutrals + test scaffolds retournent None à N<MIN_N_FIT.

## Cap de la frame statique — geste perfectionniste maintenant

**La frame HTML figée a un plafond de fidélité.** Continuer à polir ne trouvera plus la vraie classe de bugs (ergonomie, focus clavier, états vides sur vraie donnée).

**Le geste perfectionniste maintenant** = **un seul panneau LIVE sur data v0-filtrée, testé en interaction**. Pas une 18e itération statique.

**Où NE PAS être perfectionniste** :
- Structure JSON de `bias_events` à N minuscule = correcte, n'y touche pas
- Grain papier, responsive 680px = corrects
- Normaliser/indexer bias_events à l'échelle de la donnée actuelle = gold-plating

## À réconcilier avant figer

**Termes employés dans le panneau** (`cible`, `fiabilité`, `résolution`) **n'ont pas eu la passe terminologie**. À aligner sur le glossaire canonique 5 axes user (Solidité / Pari / Doublon / Santé / Calibrage + Construction / Fragilité) **avant de figer le panneau**.

## Séquencement strict (user spec close-session)

**Profondeur, pas largeur :**

```
0. Mode advisory deepening      ──  condition qualité data
0bis. Passe terminologie        ──  réconciliation glossaire AVANT panneau
1. Pile 2.1 : bias_events + cron + capture symétrique auto
2. Pile 1.1 : panneau discipline live sur data v0-filtrée
3. Pré-requis J-3/07-06         ──  audit v0 complet + tests invariants
4. 10/06 : observation + 1er point
5. Pile 1.2-1.4 : héritage après 1.1 stable
```

**Tooling découpé** (pas de yak-shave) :
- Live-reload + Geist auto-hosted : **FIRST** (30 min, accélère tout)
- Plot/uPlot : **quand graphes** (pas avant)
- Playwright : **dernier**

## Ce qui n'est pas dans cette spec

- **Publier #01** : déjà fait (commit `1c42026` + tag).
- **Calibration map / base rates / outcome context** : scaffoldés (commit `d607085`), s'activent N>=30 auto post-10/06.
- **bias_tagger.auto_tag_biases** : existe (`intelligence/bias_tagger.py`).
