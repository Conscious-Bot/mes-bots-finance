# User Bias Detector — schéma data-first

> Spec user 31/05/2026 (close-session) : "schéma d'abord. Définis l'événement-biais. Une fois ce flux d'événements posé, le panneau et le compteur coût-de-biais en tombent tout seuls."

## Principe

**Donnée avant surface.** Le panneau discipline/biais (Pile 1.1) est la *surface* de cette instrumentation (Pile 2.1). On ne surface pas ce qu'on n'a pas mesuré.

**Strict** : si le bot fait flic, le user l'utilise moins → moins de data comportementale → instrumentation creuse. **Alléger le policing avant ou avec la mise en route** est une *condition de qualité de la donnée*, pas un confort. Cf charter §7 / wave 10 mode advisory, à approfondir.

## L'événement-biais (atomique)

```sql
CREATE TABLE bias_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Type canonique : seuls 3 patterns mesurables en J0
    bias_type TEXT NOT NULL CHECK(bias_type IN (
        'vend_tot',       -- biais #1 : winners vendus trop tôt (mécanisé du bot)
        'tient_trop',     -- biais #2 : crypto pas vendu aux tops (dormant, code conservé)
        'resiste'         -- POSITIVE : user a résisté à un biais (donnée la plus précieuse)
    )),
    -- Lien à la décision concernée (NULL accepté si résisté hors décision formelle)
    decision_id INTEGER REFERENCES decisions(id),
    thesis_id INTEGER REFERENCES theses(id),
    ticker TEXT,

    -- Tag libre (raison-courte user-tapée, max ~80 chars)
    tag TEXT,

    -- Ancre contrefactuelle : ce qui se serait passé si le biais s'était exprimé.
    -- Ex : "j'ai gardé AVGO malgré +18% (= biais vend_tôt résisté). Si vendu : aurait
    --      raté +X% sur les Y jours suivants."
    counterfactual_anchor TEXT,            -- description humaine
    counterfactual_price REAL,              -- prix au moment de l'événement (NATIVE)
    counterfactual_currency TEXT,           -- USD/JPY/etc (cf currency_native_invariant)

    -- Résolution : quand peut-on calculer le coût-de-biais réel ?
    resolution_date TEXT NOT NULL,          -- target_date pour comparer counterfactual_price
    resolved_at TEXT,                       -- rempli quand prix résolu (cf resolve_due_predictions pattern)
    final_price REAL,                       -- prix à resolution_date (NATIVE)
    cost_pct REAL,                          -- (final - counterfactual) / counterfactual * 100
                                            -- signe : positif = biais aurait COÛTÉ (résisté à raison)
                                            --         négatif = biais aurait gagné (résisté à tort)

    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    source TEXT,                            -- 'telegram_tap' | 'web_one_click' | 'cron_inferred' | 'manual'
    methodology_version TEXT NOT NULL DEFAULT 'v1'  -- cf migration 0021 quarantine v0
);
CREATE INDEX idx_bias_event_type ON bias_event(bias_type, created_at);
CREATE INDEX idx_bias_event_resolution ON bias_event(resolution_date, resolved_at);
```

## Capture : un tap (la donnée la plus précieuse)

User spec : **"logger un 'j'ai résisté ici' doit être un tap — c'est ta donnée la plus précieuse."**

**Telegram canonique** (Pile 1.4 + le tap) :
- `/resiste {ticker} {tag-court}` → INSERT bias_event(type='resiste', ticker, tag, counterfactual_price=current_price, resolution_date=now+30d).
  Réponse bot : "✓ résisté noté · résolution {date} · coût-de-biais calculé alors."
- `/vendu_tot {ticker} {tag}` → biais survenu (raté), pour faire saigner le compteur honnêtement.
- `/tient_trop {ticker} {tag}` → idem pour biais #2.

**Web one-click** : sur chaque ligne position du dashboard, un mini-bouton "✋ résisté" (icône main fermée). Click → modal léger 1 champ tag → INSERT. Pas de formulaire long.

## Calcul du coût-de-biais

```python
def resolve_due_bias_events():
    """Cron daily 9h CEST. Pour chaque bias_event WHERE resolution_date <= today
    AND resolved_at IS NULL : fetch get_close_on(ticker, resolution_date) NATIVE,
    compute cost_pct, UPDATE row. Pattern identique a resolve_due_predictions."""
```

**Coût-de-biais cumulé** = `SUM(cost_pct * weight)` sur événements résolus, par type.
- Cohorte 'resiste' : positif moyen = user résiste à raison (gain évité par discipline).
- Cohorte 'vend_tot' : positif moyen = chaque vente précoce a coûté X% en moyenne (matérialise le biais).

## Panneau discipline/biais (Pile 1.1) — surface

Une fois la table peuplée, hérite du pattern Track record :
- **Compteur coût-de-biais** : "+12.3% cumulé évité par résistance · -4.1% perdu par vente précoce" (Geist Mono, axes primitive).
- **État honnête-tôt** : si N < 10 résolus → `INSUFFISANT — N<10` (charter §12).
- **Top frictions récentes** : 5 dernières lignes bias_event résolues, axe stop→cible adapté (coût matérialisé sur axe).
- **Filets fins, motion épistémique** au load.

## Pré-requis avant 10/06 (pas dans la panique du jour)

User spec : "vérifier avant le jour que les scaffolds s'activent bien sur les vraies résolutions (filtrées v0), pas dans la panique du jour."

Checklist J-3 (07/06) :
1. Tester `recalib_map.fit_calibration_map()` en passant un mock-cohorte n=30+ v1 → vérifier qu'une CalibrationMap est retournée (pas None).
2. Vérifier que `_track_record_panel()` disparaît bien quand N>=10 (charter §12 + commit `bd932d8`).
3. Tester `_distribution_health_panel()` reflète live les nouvelles résolutions.
4. Hero portefeuille doit être au bar (Pile 1.2 héritage) — sinon le 1er vrai point tombe dans une frame vide.

## Séquencement strict (user spec)

```
Profondeur, pas largeur :

1. Alléger policing (mode advisory deepening)  ──  condition qualité donnée
2. Pile 2.1 : table bias_event + cron resolve + Telegram /resiste
3. Pile 1.1 : panneau discipline/biais surface (hérite du pattern)
4. Pré-requis J-3/07-06 : vérif scaffolds + hero au bar
5. 10/06 : observation activation auto + 1er point réel
6. Pile 1.2-1.4 : héritage du pattern sur hero / évidence / Telegram (après 1.1 stable)

Tooling decoupé :
- Live-reload + Geist auto-hosted : FIRST (30 min, accélère tout)
- Plot/uPlot : QUAND on construit les graphes du panneau (pas avant)
- Playwright : DERNIER (régression sur design qui bouge = gaspillage)
- PAS de yak-shave outils qui repousse le vrai travail
```

## Ce qui n'est pas dans cette spec

- **Publier #01** : déjà fait 31/05 (commit `1c42026` + tag `publish-post-01-20260531`). Ne dépend d'aucun autre item.
- **Calibration map / base rates / outcome context** : déjà scaffoldés (commit `d607085`), s'activent N>=30 auto post-10/06.
