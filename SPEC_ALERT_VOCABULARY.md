# Spec — Vocabulaire d'alerte canonique (le substrat sémantique)

> Extension de `docs/GLOSSARY.md` à la couche alerte/signal. Un registre déclaratif de « mots d'alerte » canoniques dont **tous les panels composent** — au lieu d'inventer leur propre langue. C'est ce qui permet aux panels d'**évoluer à l'infini sans dérive sémantique** : un nouveau panel *compose* le substrat, il n'étend pas le langage. Hérite de `PLAN_REFONTE_ALERTES`, `CALIBRATION_DOCTRINE`.

## 0. Le principe keystone

> Un panel ne **fabrique** jamais une alerte ad-hoc. Il **compose** des mots canoniques. La doctrine d'alarme (gagnée, delta-pas-état, défaut-calme) et la calibration sont définies **une fois sur le mot**, héritées par tout panel qui l'emploie.

## 1. Les 4 classes (orthogonales — ne jamais mélanger)

| Classe | Rôle | Attire l'œil ? |
|---|---|---|
| **STATE** | décrit où une chose *est* (contexte) | **NON** — descriptif, défaut calme |
| **STEER** | conclut quoi *faire* | seulement les act-class (pas HOLD/WATCH) |
| **FLAG** | condition qui *contraint* la lecture | OUI quand actif |
| **EVENT** | un *delta* — quelque chose vient de changer | **OUI** — l'alarme légitime par nature |

**La règle structurelle qui encode la doctrine d'alarme :**
> L'attention (poids visuel, l'œil qui accroche) provient **UNIQUEMENT** de `{EVENT} ∪ {FLAG actif} ∪ {STEER act-class}`. **Un STATE n'attire jamais l'attention** — il est contexte. Les états *décrivent* (calme) ; les deltas/conditions/conclusions *alarment* (gagné). C'est la doctrine delta-pas-état, gravée dans la structure du vocabulaire.

## 2. Le vocabulaire de départ (canonique, orthogonal, ~30 mots)

**STATE** (descriptif, calme) :
`CYCLE_EARLY|MID|LATE|CONTRACTION|TROUGH|RECOVERY` · `THESIS_INTACT|ERODING|BROKEN|UNREVIEWED` · `FRESH_LIVE|NEAR|STALE` · `TYPE_STRUCTURAL|PRICED|TACTICAL` · `CONV_C1..C5`

**STEER** (conclusion ; act-class en gras = attire l'œil) :
**`TRIM`** · **`RIGHTSIZE`** · **`EXIT`** · **`REVIEW`** · **`SET_TARGET`** · `HOLD` · `WATCH` · `ADD`

**FLAG** (condition, attire si actif) :
`OVER_CAP` · `UNDER_CAP` · `BIAS_OPEN` · `FAIL_CLOSED` · `DEGRADED` · `NO_STOP` · `NO_TARGET` · `UNVALIDATED` · `NO_EDGE` (avec le consensus)

**EVENT** (delta — le cœur des alarmes gagnées) :
`INVALIDATION_HIT` · `TARGET_HIT` · `EROSION_DETECTED` · `ASYM_COMPRESSION` · `CROWDING_SPIKE` · `REGIME_SHIFT` · `STRESS_RISING` · `DEMOTED`

## 3. Le schéma d'un mot (registre déclaratif `config/alert_vocabulary.yaml`)

```yaml
EROSION_DETECTED:
  class: event
  earns_attention: true
  meaning: "un driver de thèse s'érode au-delà du seuil"
  calibration_contract:       # comment il gagne le droit de tirer
    trigger: "moteur érosion : net driver ≤ seuil"
    delta_based: true          # sur le changement, pas l'état
    outcome_validated: "érosion → sous-perf forward ? (Brier)"
  render: { color: warning, icon: trending-down, weight: high }
  action_hint: "REVIEW · re-justifie ou allège"
```

Tout mot porte : `class`, `earns_attention`, `meaning`, `calibration_contract` (le *delta* + la validation outcome), `render` (visuel canonique hérité par TOUS les panels), `action_hint`.

## 4. Gouvernance (ce que le substrat débloque)

- **Cohérence** : `EROSION_DETECTED` veut dire et *s'affiche* pareil sur la ligne positions, la card, le panel thèses. Une vérité, un rendu.
- **Calibration centralisée** : le seuil/validation d'un EVENT est défini une fois sur le mot, pas re-litigué par panel.
- **Crying-wolf globalement auditable** : `count(mots attention-earning actifs / total)` à travers TOUS les panels. **>20% → calibration cassée, system-wide** (la règle de `PLAN_REFONTE_ALERTES`, enfin enforceable globalement parce que le vocabulaire est partagé).
- **Extensibilité infinie** : un nouveau panel = une nouvelle *composition* de mots existants. Pas de nouvelle langue → pas de dérive. Ajouter un mot est un acte délibéré (comme une entrée GLOSSARY), pas un panel qui improvise.

## 5. Anti-pattern à bannir (test verrouillant)

- **Aucune alerte hard-codée dans un panel** : grep — pas de couleur/label d'alarme littéral hors du registre (gate CI, comme « pas de `weight=<float>` »).
- **STATE n'attire jamais l'œil** : un panel qui rend un STATE en couleur-alarme = build rouge.
- **EVENT sans `calibration_contract`** = refusé (un delta non-calibré n'est pas un mot, c'est du bruit).
- **>20% attention-earning** sur un panel donné = build rouge (défaut calme).

## 6. Architecture code

```
config/alert_vocabulary.yaml         # le registre (~30 mots, déclaratif L17)
shared/alert_vocabulary.py
  load_vocabulary() -> VocabularyRegistry      # parse + Pydantic frozen, extra='forbid'
  get_word(name) -> AlertWord                  # discriminated union sur `class`
  attention_earning(word) -> bool              # règle structurelle §1
  render_token(word) -> RenderSpec             # color/icon/weight canonique
```

- `AlertWord` Pydantic frozen avec discriminator sur `class`.
- `EventWord` exige `calibration_contract` non-null (validator).
- `StateWord.earns_attention` forcé à `False` par validator.
- Tous les panels (`render.py`, position-card, thèses, cornerstone) consomment via `get_word` + `render_token` — **jamais de littéral d'alerte**.

## 7. Gate CI (le verrou opérationnel)

```bash
# scripts/check_no_hardcoded_alerts.sh
# Tout panel qui code en dur une couleur d'alarme hors du registre = build rouge
rg -n '"#[a-fA-F0-9]{6}"' dashboard/render*.py | rg -i '(alert|warning|danger|critical|erosion|invalidation)' \
    && exit 1 || exit 0
```

Au même niveau que la gate « `yfinance` hors `prices.py` » (cf master §5 fondation). Wire dans CI : tout match = build rouge sauf via `shared/alert_vocabulary.render_token`.

## 8. Build sequence

1. **`config/alert_vocabulary.yaml`** : poser les ~30 mots avec schéma complet (EVENT ont `calibration_contract` ; STATE explicitement `earns_attention: false`).
2. **`shared/alert_vocabulary.py`** : loader + Pydantic frozen + 6 tests verrouillants (4 classes orthogonales, EVENT sans contract refusé, STATE.earns_attention forcé false, mots non-déclarés refusés, ratio attention-earning per-panel auditable, classes mutuellement exclusives).
3. **Gate CI** : grep no-hardcoded-alerts wired dans CI workflow.
4. **Migration progressive** (type-quand-tu-touches, cf GLOSSARY) : remplacer dans `render.py` les littéraux d'alerte par `render_token(get_word("EROSION_DETECTED"))`. Pas de grand sweep — conforme le code neuf systématiquement, corrige l'ancien quand tu le touches.
5. Plug le compteur `attention_earning_ratio` per-panel + global → build rouge >20%.

## 9. Le fil

> Avant : des panels qui accrètent chacun leur langue → entropie, incohérence, crying-wolf ingérable. Après : un **substrat sémantique canonique** que les panels *rendent*. Le vocabulaire est la couche où vivent la cohérence, la calibration et la doctrine d'alarme — définies une fois, héritées partout. Les panels évoluent à l'infini parce qu'ils **composent le substrat, ils n'étendent pas le langage.**

C'est la couche qui manquait sous tout le reste :

```
QUALITY_BAR (les principes)
   └── CALIBRATION_DOCTRINE (la pondération)
         └── PLAN_REFONTE_ALERTES (l'alarme)
               └── SPEC_ALERT_VOCABULARY (le substrat sémantique)   ← cette spec
                     └── les panels (positions, card, cornerstone) qui ne font plus que rendre le substrat
```
