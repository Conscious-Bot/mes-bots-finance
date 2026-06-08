# LESSONS — catches récurrents et règles de réflexe

**Version 1.0** (figé 01/06/2026). Ce fichier code la sagesse opérationnelle de PRESAGE : ce qu'on a appris à attraper *en cours de session*, pour ne plus le ré-attraper la prochaine fois. Source de vérité unique pour les règles transversales de décision qui dépassent le glossaire (vocabulaire) ou les ADR (architecture).

**Règle d'usage** : avant tout chantier non-trivial, relire la section pertinente. Avant tout commit qui touche une zone listée, vérifier que la règle est respectée. Si une nouvelle leçon émerge, l'ajouter ici plutôt que la disperser dans 4 commentaires.

---

## L1 — Source unique de vérité, sans exception

**Règle** : tout calcul ou définition fait à *deux* endroits différents est une dette de divergence future. Consolider à la source dès l'apparition du deuxième.

**Pourquoi** : la divergence ne se voit pas au moment du fork — elle apparaît 3 sessions plus tard quand on debugge un mismatch qui n'aurait jamais dû exister. Le coût de consolidation à l'instant 0 est négligeable ; le coût de réconciliation 3 sessions plus tard est massif.

**Cas concrets de PRESAGE** :
- `classify_position()` extrait dans `over_cap_monitor.py` comme **source unique** consommée à la fois par le monitor (production) et par le bloc baseline (audit). Avant l'extraction, un bloc baseline en `_q(...)` ré-implémentait la math — mismatch silencieux possible sur les orphelins (conv lookup). Le user 01/06 : *"ta confronte mismatchera pile sur les orphelins — et tu chasseras un non-bug, ou tu rubber-stamperas un vrai écart."*
- `docs/glossary.md` § Biais documentés comme **source unique** vs 4 docs publics (README, FICHE, CLAUDE, memory) qui re-formulaient chacune la sémantique des biais. Après désambiguïsation : 1 entrée glossaire + 4 renvois courts. *Plus jamais reformuler ailleurs.*
- `_DBA_CSS` constant unique pour le styling du panneau Discipline & Biais — pas de CSS dispersé inline ou dupliqué.

**Red flag à repérer immédiatement** :
- Tu écris une fonction `_compute_X` dans le module A puis tu vas écrire la même chose dans un test ou un script d'audit → **STOP**, extrait avant.
- Un libellé / un seuil / une règle métier apparaît dans plus d'un fichier → **STOP**, vérifie le glossaire ou crée l'entrée.
- Un panneau ré-dérive un état qu'un cron calcule déjà → **STOP**, fais consommer la même fonction.

---

## L2 — Ne bâtis pas l'affichage avant que la donnée existe

**Règle** : différer toute interface qui mocke un contenu qui ne sera réel qu'à T+N jours. Construire le hero contre la vraie densité, pas contre du synthétique.

**Pourquoi** : tu designes les choix visuels (lay-out, hiérarchie, libellés, échelle des chiffres, comportement état-vide) **contre les caractéristiques de la donnée**. Mocker = inventer ces caractéristiques. À T+N quand la vraie donnée arrive, elle ne correspond pas → refonte intégrale. C'est exactement le coût refactor que tu cherchais à éviter en démarrant tôt.

**Cas concrets de PRESAGE** :
- Pile 1.2-1.4 (heritage hero track record biais) **différée à ~J+30** — quand les premiers candidats fomo_greed se résolvent et qu'on a 3-5 lignes de delta_signed_eur réels à mettre en hero. Construire avant = recommencer après.
- Pile 1.1 panneau Discipline & Biais **construit après** v2.c.5 wire B2 livré → on connaît la forme exacte du contenu (état canal canonique 3 états, kca actif vs over_cap en veille vs lock_in non instrumenté). Le panneau est honnête dès jour 1.
- Site public presage.pro / modernisation interface (#24) **gated par** J-day track record + densité biais. Pas avant.

**Exception à la règle** : *l'état creux*. Une surface qui dit honnêtement "rien encore, et voici pourquoi (canal X actif mais 0 événement / canal Y dormant par décision / canal Z non instrumenté)" est **plus crédible** qu'une surface vide ou pleine de mock. L'état-creux n'est pas un mock — c'est la vraie photo de la mission à l'instant t.

---

## L3 — État honnête > contenu inventé

**Règle** : afficher "0 candidat, voici pourquoi" avec les 3 états canoniques (`actif` / `en veille (par décision)` / `non instrumenté`) plutôt qu'un blanc ou un placeholder. Un compteur à 0 sans état de canal lit faux (cf `docs/glossary.md` § État de canal d'instrumentation).

**Pourquoi** : la crédibilité d'un instrument se mesure à sa capacité d'**admettre** ce qu'il ne capture pas. La forme "0 par défaut" est ambiguë (bug ? pas implémenté ? rien à dire ?). La forme typée est non-ambiguë.

**Cas concrets** :
- Panneau Discipline & Biais affiche `lock_in NON INSTRUMENTÉ — chemin Surface 2` au lieu de cacher le biais #1.
- `over_cap EN VEILLE (PAR DÉCISION) — book 53k → 70k cible, condition de ré-activation explicite` au lieu d'omettre le canal.
- Brier handler refuse d'afficher une moyenne à N<10 (`"insuffisant N≥10"`) au lieu de mentir avec un chiffre bruit.
- Brier baseline 0.25 **nommé explicitement** (`vs 0.25 (prédicteur constante 0.5, baseline le plus faible)`) au lieu de laisser le lecteur croire que 0.25 = victoire.

---

## L4 — Anti-double-instrumentation : une seule reco par franchissement

**Règle** : pour tout détecteur de transition (over_cap, kca, futurs monitors), 1 événement = 1 franchissement = 1 prédiction sur 1 contrefactuel. Ne pas réutiliser bias_events.open comme proxy d'état (couplerait à la résolution → re-fire spurieux à +30j). État dédié dans une table journal append-only.

**Pourquoi** : si un candidat over_cap se résout à +30j alors que la position est toujours over, lire `bias_events.open` comme prev_status retournerait `dormant` → re-fire au cycle suivant. "Résolu-mais-toujours-over" deviendrait indistinguable de "jamais franchi". Le compteur se re-arme tout seul, l'orthogonalité défendue par ADR-010 est cassée.

**Pattern canon (cf `docs/templates/monitor_pattern.md`)** :
- Journal d'événements dédié (table `<name>_alerts`, append-only, migration alembic)
- `prev_status` lu depuis ce journal, **pas** depuis bias_events
- Transition `dormant_to_over` (et inverses) auditée à chaque évaluation (no_change inclus)
- Cure mode B = append `dormant` row (NE PAS DELETE — préserve audit trail)

---

## L5 — Fail-safe strict sur les effets de bord, jamais sur les vérifications

**Règle** : un wire (effet de bord : INSERT bias_events, notify Telegram, write file) doit être enveloppé `try/except` strict. Une erreur dedans ne casse JAMAIS le caller (brief, sizing, cron). Une erreur de **vérification** (MissingDataError, schema mismatch) doit au contraire **crasher visible**, pas se silenter.

**Pourquoi** : le brief matinal ou le sizing live sont la valeur de surface — un bug d'instrumentation ne peut pas les noircir. Mais une donnée critique manquante (qty None, prix None, schema drift) doit être détectée à temps, pas silencieusement absorbée en "IGNORED".

**Cas concrets** :
- `wire_bias_trigger(recommendations)` : chaque ouverture wrapée `try/except`, erreur compte en `stats["errors"]`, jamais raise vers le caller. Test : `test_open_candidate_failure_does_not_break_caller`.
- `classify_position` **raise MissingDataError** si qty ≤ 0 ou anchor_eur None — *jamais* return None silencieusement. Le caller catch et compte en `errors`, visible dans logs. La ligne ne va pas en IGNORED legit.
- `wire_bias_trigger` retourne `dict {opened, kept, superseded, errors}` — pas d'effet de bord caché.

---

## L6 — Le rituel de clôture vaut sa durée

**Règle** : en fin de chaque session non-triviale, 5 minutes pour : (a) appendre une section `## Close YYYY-MM-DD` au SESSION_STATE.md, (b) actualiser TODO.md (header + completed), (c) commit récap. Ces 5 minutes économisent ~30 minutes de re-onboarding la session suivante.

**Pourquoi** : le coût de redémarrage à froid (où en sommes-nous ? qu'est-ce qui vient d'être livré ? quels findings actifs ?) est asymétriquement élevé. Le SESSION_STATE/TODO datés de 2-3 semaines forcent une fouille forensique (`git log`, grep, ouvrir 4 fichiers). Cinq minutes en fin de session vs trente au démarrage = ratio temps × 6.

**Pattern canon (cf `.claude/commands/close.md`)** :
1. Append "Close YYYY-MM-DD" à SESSION_STATE.md (livrables + audit + entry next session)
2. Update TODO.md (header date + état système + completed tasks)
3. Commit dédié "session YYYY-MM-DD close" si pas déjà fait
4. **Ne pas skip** : c'est le meilleur ratio investissement / retour du projet.

---

## L7 — Side-effects analytiques après commit DB, avec acceptation explicite du failure mode « silent miss »

**Règle** : tout hook d'instrumentation (bias detection, observability, ledger enrichment) fire **après la transaction métier commitée**. Conséquence directe : si le hook échoue, l'événement métier reste valide mais l'observation analytique est perdue silencieusement (catch + log warning, **ne jamais re-throw**).

**Tradeoff explicite** :
- **Bénéfice principal** : un rollback métier ne laisse pas d'event analytique orphelin. Le journal de calibration / bias_events reste cohérent avec la vérité des transactions.
- **Coût accepté** : un crash entre commit et hook laisse l'analytique muette pour cet event. La transaction métier est OK, mais on a perdu l'opportunité d'observer.

**Quand abandonner ce pattern** : si l'analytique devient critique — par exemple, elle alimente un modèle de prediction en boucle fermée, ou un KPI non-récupérable (pas re-calculable depuis l'état actuel) — basculer vers un **transactional outbox** : insérer un marker dans la même transaction que l'event métier (atomicité garantie), puis le marker est consommé par un job séparé idempotent.

**Application courante** : `shared.positions.add_sell` → `intelligence.lock_in_detector.detect_winner_sell` (lock_in v2.c.6, juin 2026). Le hook fire après `cx.commit()`, wrapé `try/except Exception as e: log.warning(...); pass`. Si le détecteur lock_in crashe, la vente est enregistrée sans candidat bias — accepté car la mesure du biais est statistique (pas chaque event ne doit être capturé) et l'observation manquée est un coût acceptable face au risque d'un event analytique orphelin.

**Red flag** : si tu te retrouves à vouloir `raise` depuis le hook pour rollback la transaction métier, **stop** — c'est le signe que tu confonds analytique et critique. Soit le hook est analytique (= L7 pattern, silent miss accepté), soit il est critique (= transactional outbox, marker atomique).

---

## L8 — Les test fixtures DB ne sont pas le schéma de production

**Règle (cause structurelle)** : les fixtures DB des tests sont **clonées d'un état du schéma à un moment T**. Une fois la migration suivante posée (`ALTER TABLE`, nouvelle colonne, contrainte, index), les fixtures restent à T sauf régénération explicite. Tous les tests qui touchent cette table continuent de passer ✅ alors que le code, en condition réelle migrée, échoue.

**Mode de défaillance typique** : colonnes optionnelles ajoutées par migration récente que le code consomme mais que la fixture ne contient pas. Les writes/reads sur la colonne fail silencieusement (None retourné, INSERT qui ignore la colonne inexistante, ou crash décalé à la première vraie utilisation prod).

**Origine** : sprint v2.c.6 lock_in, hotfix `9a67e0c` (01/06/2026), J−9 avant batch KPI #2. La colonne `note_tags_json` ajoutée par migration 0023 n'avait jamais été propagée aux fixtures tests (qui contenaient `note TEXT`). `open_candidate` INSERT dans la colonne nommée `note` — le code prod silently failed à chaque tentative d'ouverture de candidat depuis Sprint 15 (kca) + Sprint 25 (over_cap). Non révélé parce que 0 transition réelle (kca tout dormant, over_cap dark par décision). **Le bug aurait pété au premier vrai trigger kca le 10/06**, en plein milieu de la batch résolution KPI #2 — exactement le mauvais moment pour découvrir qu'un hook silencieusement mort depuis 40 jours fait sauter l'intégrité du ledger. Sans le smoke E2E ajouté avant J-day, post-mortem garanti.

### Règle structurelle (le vrai fix, **shipped 01/06/2026**)

Les fixtures DB tests **sont dérivées de la migration head courante**, pas commitées comme snapshots statiques. Régénération automatique au CI via `alembic upgrade head` sur un volume éphémère + minimal seed.

**Livré** : fixture pytest `migrated_db` dans `tests/conftest.py`. Tout test qui ajoute `migrated_db` en argument reçoit une DB sqlite temp **avec le schéma head courant** + `storage.DB_PATH` monkeypatché. Le drift schéma-prod / fixture-test devient impossible par construction.

**Tests d'invariant** dans `tests/test_migrated_db_schema.py` : vérifie que les colonnes critiques (`bias_events.note_tags_json`, `bias_events.position_event_id`, status enum canonique, triggers append-only, `predictions.baseline_price`) sont présentes après `alembic upgrade head`. Toute migration future qui drop ou renomme une colonne critique fire un test.

### Règle tactique (palliatif en attendant la structurelle)

Tout code qui consume une colonne ajoutée par migration récente **embarque un smoke E2E contre une DB freshly-migrated**, distinct des tests unitaires fixtures. Le smoke crée une vraie position dans la vraie DB live, fait fire le chemin réel (ex. `positions.add_sell` → hook → INSERT bias_event), vérifie le row écrit, cleanup. 30 secondes d'écriture, attrape les drifts schema.

### Anti-pattern à interdire explicitement

❌ Ajouter une colonne par migration → écrire les tests sur fixture pré-migration → déclarer tests verts = code safe.

Le raisonnement fallacieux est : « tests verts donc code safe ». La vérité est : « tests verts contre le schéma de la fixture, indépendamment du schéma de la prod ». Si la fixture diverge de la prod, les tests verts ne disent rien sur la safety prod.

Quand la version structurelle (régénération fixtures CI) sera shippée, cette section "Règle tactique" devient un commentaire historique à l'intérieur de L8 — le smoke E2E par hook reste utile en complément, mais cesse d'être le filet de sécurité principal.

---

## L9 — Aucun comportement de production sur un modèle non backtesté. Démote, ne pas wire.

**Règle** : si un modèle produit une sortie qui pourrait piloter une décision opérationnelle (sizing, gating, throttling, alerting matériel), il **ne pilote rien** tant qu'il n'a pas été backtesté contre N régimes historiques connus. Si le backtest est bloqué par données manquantes, **démote le modèle à "exploratoire"** sur l'UI plutôt que de l'enrôler dans une décision.

### Le piège qui force la violation : pression de cohérence visible

Un modèle non-validé exposé sur l'UI crée souvent une **contradiction visible** avec une autre règle (cas v2.macro : "phase 2 stress" affiché à côté de "sizing ×1.0"). La pression psychologique à résoudre vite la contradiction pousse à wire le modèle non-validé sur la décision pour "rendre cohérent". **C'est l'erreur**. La bonne réponse est de **démote le modèle**, pas de **promouvoir la décision sur lui**.

Nommer la pression = la moitié de la résistance. Sans le nom, la pression sera ressentie comme légitime ("il faut bien rendre cohérent !"). Avec le nom, elle est identifiable comme biais cognitif et tu peux la refuser explicitement.

### Pattern de démote standard

Quand on identifie un modèle non backtesté affichant sur l'UI :

1. **Renommer la métrique** en "score exploratoire / non calibré / backtest en cours". Le label autoritaire (STABLE/STRESS/ALERTE/CRISE) devient un statut transparent.
2. **Neutraliser visuellement** : couleurs `steel`/`mute` (plus de `warn`/`bear`), retrait des labels décisionnels de l'échelle (stable/stress/alerte/crise → bas/haut neutres).
3. **Clarifier explicitement quelle règle réelle pilote** la décision (ex : "sizing : règle VIX seule"). Ne jamais laisser implicite que le modèle exploratoire pilote quoi que ce soit.
4. **Référencer la task de backtest** qui débloque la re-promotion (ex : "backtest en cours" + lien tâche).

### Trigger de re-promotion

Backtest validé contre **≥3 régimes historiques connus** (ex : COVID 2020, Q2 2022, SVB 2023) **et ≥2 périodes calmes confirmées** (2017, 2019). En-dessous de ce seuil, le modèle reste exploratoire indéfiniment.

### Coût asymétrique

Un faux signal en prod (cost-drag silencieux pendant N mois jusqu'à détection) excède de plusieurs ordres de grandeur le coût du backtest préalable. **Quel que soit l'impatience visuelle**. Pour PRESAGE sizing→phase : ~30% du rendement annualisé en faux positif "stress" en marché calme, contre 6-8h de FRED pulls. Ratio > 1000×.

### Origine

Sprint v2.macro sizing→phase, J−9 avant batch KPI #2 (01/06/2026). L'agent propose ordre A→B (câbler avant backtester) "pour débloquer vite la cohérence visuelle". User inverse en B→A. La séquence inverse codifie L9 comme invariant général plutôt que règlement de cas particulier. Commit démote : `f2eefbc`. Task de re-promote : #42.

### Anti-pattern à interdire explicitement

❌ « Wire le modèle en prod et observe son output pour valider » = **science à l'envers**. La validation se fait sur historique connu, pas par l'output en prod du modèle qu'on veut valider. C'est exactement le pattern que `PHILOSOPHY.md` "matière empirique > construction" interdit.

❌ « Rendre cohérent maintenant » comme justification pour wirer un modèle non-validé. La cohérence est un sous-produit de la validation, pas un substitut à elle.

---

## L10 — Biais de séquence : débloquer vite la friction visible avant la rigueur empirique différée

**Règle** : quand on propose une séquence d'exécution, le premier réflexe est souvent *« faisons d'abord ce qui débloque la friction visible immédiate »* plutôt que *« faisons d'abord ce qui valide empiriquement le sous-jacent »*. Cette préférence est **systématique** dans les propositions agent et doit être identifiée comme biais à corriger consciemment. La séquence empirique-d'abord est presque toujours la bonne, même quand elle coûte plus de temps initial.

**Pourquoi le coût est asymétrique** : raccourcir l'ordre revient à shipper du comportement de production basé sur un construct non-validé (cf L9). Le faux-positif silencieux qui en résulte (cost-drag, ledger pollué, débogage post-mortem en plein pic de charge) excède de plusieurs ordres de grandeur le temps initial gagné. La friction visible immédiate, elle, peut presque toujours être traitée par démote ou caveat plutôt que par câblage.

### Heuristique de détection (avant de proposer une séquence)

Trois questions explicites à se poser :

1. **La friction qui se débloque rapidement vient-elle d'une matière empirique validée OU d'un construct non-validé ?** Si construct non-validé, alarme.
2. **L'ordre proposé fait-il shipper un comportement prod basé sur un modèle dont le verdict de validation arrive après ?** Si oui, c'est le pattern L9 « wire et observe » — refuser.
3. **Une démote visuelle (étiquette "exploratoire / non calibré" + neutralisation des labels décisionnels) résoudrait-elle la friction visible sans engager la décision ?** Si oui, c'est presque toujours le bon move tactique en attendant la validation empirique.

Si une seule réponse est positive, **inverser la séquence avant de proposer**.

### Cas concrets observés (01/06/2026)

**Cas 1 — Sprint v2.c.6 Q2 lock_in gate** : proposition initiale "ship gate v1 absolu `pnl_pct ≥ 0.15 AND conviction ≥ 3`, simple, on shippe". User push-back : ship simple **mais** logger les 4 dimensions (`pnl_pct_progress`, `time_progress`, etc.) dans `counterfactual_json` pour permettre v2 data-driven post-90j sur prédicat relatif (`pnl_pct_progress < 0.6 AND time_progress < 0.5`). Sans le logging, v2 aurait nécessité de refaire 6 mois d'observation sur de nouvelles dimensions.

**Cas 2 — Sprint v2.macro sizing→phase** : proposition initiale A→B (câbler sizing sur composite phase avant le backtest) "pour débloquer vite la cohérence visuelle entre frise et sizing". User push-back : B→A, backtest empirique = **prerequisite** absolue. La friction visible (incohérence affichée) se résout par démote, pas par câblage à l'aveugle. Commit démote `f2eefbc`, task backtest #42.

### Anti-pattern à interdire explicitement

❌ « Pour livrer vite la valeur visible, on shippe maintenant et on validera ensuite. » Formulation qui semble pragmatique mais qui est exactement le pattern `PHILOSOPHY.md` « matière empirique > construction » interdit, déguisé en réalisme business.

❌ « La friction visible crée une pression à résoudre vite. » Pression légitime à ressentir, mais à canaliser vers démote (cf L9), pas vers raccourcissement de la séquence empirique.

❌ « Sans le câblage, l'utilisateur ne voit pas la valeur. » L'utilisateur voit déjà la valeur — la matière empirique solide à l'arrivée. L'attente initiale est largement compensée par l'absence de débogage post-mortem.

### Application

Avant de proposer une séquence d'exécution, vérifier explicitement les 3 questions de détection ci-dessus. Si un raccourcissement est tentant, **nommer le trade-off vitesse vs validation explicitement** dans la proposition, sans masquer sous une formulation "pragmatique". Le décideur (user) doit voir le coût asymétrique pour pouvoir refuser l'inversion.

### Origine

Deux occurrences identifiées 01/06/2026 dans la même session (v2.c.6 Q2 + v2.macro sizing→phase). Pattern reconnu comme récurrent (« souvent ») par user post-mortem. Codifié ici pour que les futures séquences d'exécution proposées soient automatiquement vérifiées contre le biais avant émission, plutôt qu'attendre le push-back utilisateur à chaque occurrence.

L10 est un invariant **anti-agent** au sens où elle code une discipline qui n'est pas naturelle dans les heuristiques d'optimisation typiques (« minimiser le temps jusqu'à valeur visible ») et qui doit être imposée externalement par la PHILOSOPHY.md PRESAGE (« matière empirique > construction »).

---

## L11 — Les anchors a priori sont une hypothèse à valider empiriquement, pas une vérité

**Règle** : quand on backteste une formule contre une liste d'anchors labellisés a priori (« 2017 = P1 calme », « SVB = P2 stress modéré »), la labellisation est elle-même une **hypothèse**, pas un référentiel absolu. Avant de conclure « formule cassée » sur un fail, vérifier empiriquement la qualité du label : tirer 2-4 indicateurs macro de la période réelle (VIX moyen, spreads, courbe taux, ISM) et confirmer que le régime étiqueté correspond bien à la réalité observée.

**Pourquoi le coût est asymétrique** : conclure « formule cassée » sur un anchor mal labellisé conduit à 3 erreurs en cascade : (1) on rejette une formule qui captait correctement le signal ; (2) on entreprend un redesign inutile ; (3) on perd la confiance dans le sous-jacent qui était valide. À l'inverse, vérifier 4 indicateurs macro coûte 30 minutes et tranche définitivement.

### Heuristique de détection (avant de conclure sur un fail d'anchor)

Avant d'écrire « anchor X échoue → formule cassée », répondre explicitement :

1. **Le label de l'anchor a-t-il été assigné après vérification empirique du régime macro de la période, OU sur réputation/narratif ?** Si « réputation », c'est une hypothèse de travail, pas un référentiel.
2. **Si la formule classe X plus stressé que prévu, quels 2-3 indicateurs macro indépendants (hors composite) confirment / infirment cette classification ?** VIX moyen 6m, spread HY OAS, courbe 10s-2s, ISM Manuf, etc.
3. **L'écart entre score formule et label attendu est-il cohérent avec un pré-stress latent qui n'avait pas été reconnu dans la labellisation initiale ?**

Si une seule réponse confirme la mauvaise labellisation, **relabel l'anchor avant de conclure sur la formule**.

### Cas concret observé (01/06/2026)

**Task #42 backtest macro composite** : labellisation initiale « 2017-06 = 2019-06 = P1 calme ». La formule V3 classait 2017-06 à 21 (P1) et 2019-06 à 45 (P2). Conclusion immédiate de l'agent : « formule cassée, baseline trop élevé, variance 24 points entre 2 calmes ». User push-back : « juin 2019 n'était pas un calme — courbe 10s-2s à l'inversion, Fed pivot dovish, ISM <50, trade war Chine pic ».

Sanity-check empirique sur 4 indicateurs :
- VIX moyen 2017 = **11.09** vs 2019 = **15.39** → 2019 plus stressé ✓
- 10s-2s juin 2017 = **84 bps** vs juin 2019 = **26 bps** + 3 jours d'inversion → 2019 pré-récession ✓
- IPMAN YoY juin 2017 = **+0.61%** vs juin 2019 = **-1.91%** → 2019 contraction industrielle ✓
- HY OAS juin 2017 < juin 2019 (rate-limit FRED, mais ordre évident)

Conclusion révisée : juin 2019 = vrai P2 (pré-stress latent), pas P1 calme. L'écart 24 points était du **signal correctement capté** par la formule, pas du bruit. Relabel 2019 → P2 → V3 passe 8/8 anchors a priori + 7/8 OOS + 5/5 fenêtres soutenues.

### Anti-pattern à interdire explicitement

❌ « L'anchor échoue, la formule est cassée. » Court-circuite la possibilité que ce soit l'anchor qui soit mal labellisé. Toujours vérifier les deux côtés.

❌ « La labellisation a été faite par un expert (humain ou agent), donc elle est fiable. » Les labellisations a priori reposent sur la réputation des événements (« COVID = crise », « 2017 = calme »), pas sur leur granularité macro. La granularité macro peut être contre-intuitive.

❌ « Tester 4 indicateurs prend du temps, on tranche sur le verdict actuel. » 30 minutes de sanity-check économisent typiquement plusieurs heures de redesign inutile + une perte de confiance dans la formule.

### Application

Avant tout backtest, **listing dual** : (1) anchors avec leur label attendu ; (2) sources empiriques de vérification pour chaque anchor (VIX moyen, courbe, spreads, ISM sur la fenêtre). Si une labellisation diffère de la formule par > 1 cran de phase, runner la vérification empirique avant de conclure sur la formule.

### Origine

Session 01/06/2026 task #42 backtest macro composite, V3 redesign BTC drawdown 180j + FedBalance YoY + MfgIP P4. Pattern reconnu par user après que l'agent eut conclu « formule cassée, baseline trop élevé » sur l'écart 2017/2019, alors que la réalité macro confirmait l'écart. Commit `715c7df` (CSV in-sample), commit V3 prod `7a43189`.

L11 est un complément de L9 et L10 : L9 dit « pas de prod sur modèle non backtesté » ; L10 dit « ne pas raccourcir la séquence empirique » ; L11 dit **« et le backtest lui-même doit reposer sur des anchors empiriquement vérifiés, pas labellisés au feeling »**.

---

## L12 — Devise native vs EUR : interdit mélanger dans une formule de %

**Règle** : tout prix-thèse (`stop_price`, `target_full`, `target_partial`, `entry_price`) est stocké en **NATIVE currency du ticker** (cf memory `currency_native_invariant`, ADR 005). Comparer un de ces prix à un prix courant en EUR produit des `%` absurdes (multiples de 100×). Passer **par le helper canonique** `_stop_distance_pct_native(ticker, stop_price)` (ou équivalent native-vs-native), jamais inline `(current_eur - stop_native) / current_eur`.

**Pourquoi** : la divergence n'éclate pas en EUR-only book (US tickers en USD ≈ EUR ordre de grandeur), elle éclate sur JPY (×150), KRW (×1400), HKD (×8.5). Le bug peut rester invisible pendant des semaines tant que le book reste US-only puis exploser à la première position asiatique.

**Cas concrets de PRESAGE** :
- `_theses()` ligne 3631 : pattern correct `current = _cached_price_native(tk) or last or entry` puis `(current - stop) / current * 100`. Commentaire de fix daté 31/05 (4063.T cible +23876%, 000660.KS cible +175408%).
- `_mauboussin_sizing()` ligne 1257 (avant 01/06 soir) : **bug**, mélangeait `ln.current_price_eur` et `ln.stop_price`. Produisait `stop −11089%` sur 4063.T (Shin-Etsu, JPY). Fix : extraction du helper canonique `_stop_distance_pct_native()`.
- `compute_portfolio_asymmetry()` : `asym_mod._get_current_price = _cached_price_native` au moment de l'appel render() (ligne 5891). Pattern par injection — l'asymmetry module reste agnostique du dashboard.

**Helper canonique** (dashboard/render.py) :
```python
def _stop_distance_pct_native(ticker, stop_price) -> float | None:
    if not stop_price or stop_price <= 0: return None
    current = _cached_price_native(ticker)
    if current is None or current <= 0: return None
    return (current - stop_price) / current * 100
```

**Red flag à repérer immédiatement** :
- Tout calcul `(X - stop_price) / X * 100` ou `(target_X - Y) / Y * 100` qui ne passe pas par un helper documenté native-only → **STOP**, utilise le helper ou ajoute-en un.
- `current_price_eur` apparaît dans la même expression qu'un champ `_price` issu de la table `theses` → **STOP**, currency mix.

**Sentinel canonique** : si `asymmetry_ratio == 999.0`, c'est `verdict = TARGET_HIT` (current ≥ target_full, upside = 0). Affichage `_asym_format()` doit rendre "cible ✓" / chèvron, **pas** "999.0×".

---

## L13 — Backtest rétrospectif : plafonné par construction quand l'instrument est plus jeune que les erreurs

**Règle** : un test honnête de détection comportementale exige une trace **timestampée AVANT** la décision, des **inputs PIT** (conviction / target / stop / thesis_status), et un **label posé indépendamment** du verdict. Si l'une des trois est absente, le rétrospectif ne teste rien — il fabrique ce qu'il prétend valider.

**Pourquoi** : les "signature errors" mémorables (les ventes qu'on regrette le plus) sont par construction les plus anciennes → les plus pré-instrument. Le track-record d'un bot ne peut pas rétroagir sur des trades antérieurs à sa propre existence. Toute reconstruction d'inputs à partir du souvenir = hindsight contamination en blouse blanche.

**Cas concret (TER, session 04/06/2026)** :
- Une ligne du backtest N=6 "TER c3, entry 306 → sold 328, PnL +7.2%, no_flag par 15% floor + out_of_scope" semblait propre.
- Triplement contaminée :
  - **(i) Tranche déguisée en événement** : le ledger broker révèle 7 ventes sur 18 mois, le partial_exit 2026-05-29 @328 n'était que la dernière de la campagne.
  - **(ii) Entry recalé à T-13j** : `thesis.entry_price=306` était le cost basis recalculé à l'ouverture thesis (2026-05-16), pas la vraie première entrée Dec 2024 (avg cost réel ≈ 110€).
  - **(iii) 5 ventes orphan ignorées** : 2025-11-03, 2026-01-27, 02-24, 04-17, 05-15 — toutes pré-thesis, sans PIT.
- Réalisé EUR sur le round-trip complet ≈ +93% (vs +7.2% sur la tranche isolée). Le "verdict no_flag" n'évaluait absolument pas la décision globale.

**Red flag à repérer immédiatement** :
- Tu construis un "cas test" rétrospectif → vérifie *avant tout autre chose* que la thèse était dans la table **avec timestamp antérieur** à la décision testée. Pas "à peu près à l'époque", pas "le bot a été créé après mais on peut reconstruire" — strictement antérieur.
- Tu observes un sell isolé → vérifie qu'il n'est pas la dernière d'une série dans le ledger broker. Sinon traite la **campagne**, pas l'événement (D1 round-trip, jamais D2 per-event quand fragmenté).
- Tu envisages de baisser un seuil détecteur "pour attraper le cas qui n'a pas flag" → STOP, c'est juste déplacer la contamination de la donnée vers la règle. Garde 1 : règle figée AVANT regard.

**Corollaire structurel** :
- SOFI/PLTR/NVDA et tout pré-instrument → **non testables**. Le rétrospectif rend P&L et regret-impressions, jamais validation détecteur.
- La seule voie auditable = forward-logging discipline : conviction/target/stop/asymétrie loggés AT entry, à partir du jour 0 d'instrumentation.
- ADR-001 bitemporal (valid_time + transaction_time) justifié pour les décisions futures, pas pour ressusciter le passé.

**Smoke-test associé** : `docs/smoke_test_lock_in_2026-06-04.md` documente le post-pivot après le constat L13 — N=5 brut → N=2 in-scope, 1 TN (ALAB) + 1 FP (SNOW), 1 levier structurel (#109 sell-UX radio status_change). Pas une preuve, un proof-of-discipline-sanity du dispositif.

---

## Politique d'évolution

Toute nouvelle leçon (catch récurrent qu'on attrape pour la 2ème fois) **doit** être ajoutée ici avec :
- numéro `Lk` séquentiel
- règle en 1 phrase imperative
- pourquoi (le coût qu'on évite)
- cas concrets observés (références au code)
- éventuel red flag détectable à l'instant 0

Référencer depuis `CLAUDE.md` § "À retenir sans chercher" — pas de re-formulation ailleurs.

---

## L14 — Anti-patterns frameworks LLM-trading 2026 (synthèse audit OSS 07/06)

Audit comparatif 19 repos OSS (qlib, TradingAgents, ai-hedge-fund, FinRL, QuantDinger, Kronos, OpenBB, FinceptTerminal, etc.). 9 anti-patterns confirmés. À reconnaître + rejeter lorsqu'ils reviennent te tenter sous une autre forme.

### Les 9

1. **Multi-agent persona debate** (TradingAgents, ai-hedge-fund 19 mentors, QuantDinger fast_analysis) → Bull/Bear/Aggressive personas qui débattent, judge LLM arbitre. **Zéro base rate, zéro calibration, le judge décide sur la rhétorique.** Antithèse de `signal_scorer_v2` base-rate-first. Si tu vois "AI agents that imitate Buffett/Druckenmiller" → fuir.

2. **Foundation model autoregressif sur OHLC seul** (Kronos) → transformer pré-entraîné sur K-line de 45 exchanges, prédit next bars. **Zéro causalité, ignore earnings/FDA/macro, overfit régime de pré-entraînement.** L'autoregression sur OHLC n'est pas un "langage des marchés", c'est de la projection de patterns sans cause.

3. **RL agent qui apprend la policy de trading** (FinRL : DRL on DOW30 2014-2025 → live 2026) → reward = pnl scaled, agent maximise pnl sans contrainte DD/lock_in/position size. **Reward hacking inévitable + survivorship bias DOW30 absolu.** Opposé de "discipline mécanisée prédéfinie".

4. **Backtest sans walk-forward + sans transaction costs réalistes + sans CI** (FinRL exemple 2026 : 2 mois OOS, 5 agents → pick best ; TradingAgents : N=3 tickers cherry-picked, T=3 mois bull-run, SR>5 flaggé par auteurs comme anomalie) → **overfitting déguisé en validation**. Bench réaliste = walk-forward sur ≥5 ans + transaction costs adversariaux + multi-seed + CI bootstrap sur Sharpe/Brier.

5. **LLM trend prediction multi-horizon** (QuantDinger `fast_analysis.py` : next_24h / 3d / 1w / 1m → BUY/SELL/HOLD avec strength) → **persona prediction LLM à plusieurs échelles temporelles simultanément**. Antithèse scorer V2 base-rate-first. Le LLM produit des outputs structurés mais le contenu est de la divination.

6. **Schema `z.any()` / type permissif sur champs LLM** (agentic-inbox confessait `// unvalidated — settings goes straight to AI`) → prompt injection trivial. **Tout champ utilisateur qui finit dans un system prompt doit traverser un schema strict + sanitization.**

7. **Stack multi-DB + Datadog/Sentry/ES** (nango : Postgres + ES + Redis + KvStore + DD-trace) → over-engineering. **Pour PRESAGE solo lifestyle, ce stack est ingérable.** Conserver SQLite WAL + APScheduler tant que < 100 users.

8. **Model zoo SOTA papers tournée best-of-N** (qlib HIST/TRA/TFT/ADD/ADARNN/TCTS…) → ~25 modèles "state-of-the-art" empilés. **Signature d'une plateforme qui empile sans valider rigoureusement chaque ajout.** Picking le meilleur modèle ex post sur le même test set = overfit garanti.

9. **RD-Agent intégration** (microsoft qlib partenaire, NeurIPS 2025, arxiv 2505.15155) → LLM-driven autonomous factor mining + model optimization en boucle fermée. Claims 2× ARR vs benchmark factor libs. **C'est de l'overfitting industrialisé** : un LLM cherche des factors qui ont marché in-sample, valide sur backtest peu profond, itère. Pour PRESAGE : **casserait la propriété auditable du Brier ledger** (mélange signal humain-typé + signal LLM-mined = impossible de séparer la contribution). **Ne PAS intégrer.**

### Règle pratique

Quand un repo OSS se présente comme "AI trading framework / multi-agent / foundation model / RL", appliquer le filtre L14 AVANT de lancer un audit code. Économise 4h de research par repo.

### Test contre soi-même

Les 9 anti-patterns ont en commun : **prédire l'avenir au lieu de mesurer le passé**. PRESAGE doctrine "discipline mécanisée, pas alpha prédictif" (`[[business-path-6-acted]]`) est l'antidote structurel. Toute proposition d'ajout au système doit passer le test : *"Est-ce que ça mesure une décision passée, ou est-ce que ça prédit un futur ?"* Si prédiction, refuser ou démote en exploratoire taggé.

### Référencer

Depuis `CLAUDE.md` § "À retenir sans chercher" + `TODO.md` section TECH DEBT AUDIT OSS. Pas de re-formulation ailleurs.

## L15 — Fail-closed scoring : pas de score arbitraire en mode dégradé

Phase 1.2 absorption_roadmap (07/06 soir). Doctrine héritée de l'audit `agentic-inbox` (workers/lib/ai.ts) + spec user 03/06 `degraded_restitution_contract`.

### La règle

Tout scorer LLM (`signal_scorer_v2`, `materiality_v2`, futurs) qui n'aboutit pas à un output structuré valide doit retourner `None` ou `raise LLMUnavailableError`, **jamais un score par défaut, jamais un fallback formule, jamais 0.5 "par sûreté"**. Le caller (orchestrator / `learning`) traite `None` comme `skip ce signal proprement, sans entrée au Brier ledger`.

### Les 4 chemins de sortie autorisés du scorer

| Cas | Sortie | Raison |
|---|---|---|
| LLM call OK + JSON parse OK + validation OK + direction ≠ watch | `dict` complet | scoring abouti, ledger consigne |
| LLM call OK + JSON parse OK + direction == watch (evidence none/weak) | `dict` avec `direction='watch'` | abouti mais non-falsifiable, caller skip ledger |
| LLM call OK + parse FAIL (JSONDecodeError / no JSON in text / prob hors [0,1]) | `None` + `log.warning` structuré | scoring crashé, JAMAIS de prob fabriquée |
| LLM call FAIL (rate_limit / credit_exhausted / overloaded) | `raise LLMUnavailableError` | upstream KO, caller marque `pending_llm` ou route vers `rule_v1_fallback` si flag ON |

### Ce qui est interdit (jamais à réintroduire)

- `prob = 0.5 if json_decode_fail else parsed_prob` — divine sous prétexte de robustesse, pollue le ledger
- `direction = "watch"` comme défaut quand parse échoue — masque le crash en non-action, perd l'audit
- `try / except: return default_dict` — fabriquer un dict "valide-en-apparence" pour ne pas casser la pipeline
- Score V1 (estimate_probability formule) en fallback de V2 — bug fondateur 30/05 : 40 predictions toutes [0.608, 0.658], mono-bucket. **V1 est demote, pas fallback.**

### Test contre soi-même

Si tu touches un scorer LLM et qu'un `return ...` en `except:` te tente : c'est un piège L15. Le bon réflexe : `log.warning` + `return None` + laisse le caller décider (`learning.py` skip propre, `orchestrator` route vers RuleScorer si flag ON).

### Test verrouillé

`tests/test_fail_closed_scorer.py` — vérifie pour `signal_scorer_v2.score_directional_probability` :
1. JSON malformed → `None`, jamais de dict avec `probability` arbitraire
2. JSON sans clé `probability` → `None`
3. `probability` hors `[0, 1]` → `None` (pas de clamp silencieux)
4. LLM call retourne `""` ou texte sans `{` → `None`
5. `LLMUnavailableError` → propage (pas swallow)

Si un de ces 5 cas régresse, c'est une violation L15.

### Pourquoi cette doctrine est dure

Tentation 1 : "Si je return None systématiquement, je perds 5-10% du batch — un fallback formule serait mieux." → Non. Un batch incomplet est honnête ; un batch complet avec 5-10% de scores fabriqués détruit la calibration Brier sur des centaines de buckets.

Tentation 2 : "Au moins logger en `info` la valeur fabriquée pour audit, c'est traçable." → Non. La règle anti-double-instrumentation (L4) interdit ça : l'audit n'a pas à reconstruire la prédiction post-hoc, le ledger doit être complet ou vide, jamais partiel-fabriqué.

### Référencer

Depuis `CLAUDE.md` § "À retenir sans chercher" (doctrine fail-closed). Test verrouillé `tests/test_fail_closed_scorer.py`. Pas de re-formulation ailleurs.

## L16 — Splits temporels stricts in-file (anti in-sample tuning)

Phase 1.4 absorption_roadmap (07/06 soir). Doctrine héritée de Kronos `finetune/config.py:28-32` + catch session 01/06 task #42 (cf memory `feedback_in_sample_tuning_validation`).

### Le piège

Quand tu introduis N degrés de liberté (thresholds, bumps, gates) contre M anchors (predictions historiques), la phrase « X/M valides » est tautologique tant que les anchors et le tuning vivent dans la même fenêtre temporelle. Tu fittes une fonction qui passe par les points et tu te félicites de ce qu'elle passe par les points.

Le pire : tu peux re-tuner « juste un peu » le soir même de l'audit, sans tracer, et personne (toi-même 3 mois plus tard inclus) ne peut le détecter.

### La règle

**Tout tuning de scorer / threshold / band doit dater train/val/oos dans le YAML versionné AVANT le tuning.** Ce qui veut dire :

1. Un bloc `temporal_splits` figure dans le fichier config tuné (ex `config/calibration.yaml audit_metadata.temporal_splits`).
2. Les fenêtres sont explicites : `train_window`, `val_window`, `oos_window` (vérifié post-hoc), `next_oos_window` (frozen, forward-only).
3. Une `rule:` libre énonce le délai de freeze + conditions qui débloquent un re-tune (drift détecté, misfire >X%, audit cron N jours).
4. Toute mise à jour de bands déclare son nouveau `next_oos_window` AVANT (commit séparé, ou ordre vérifiable dans `git log -p`).

### Ce qui est interdit

- Re-tune dans la fenêtre `next_oos_window` (in-sample par construction)
- Modifier `temporal_splits` et les bands dans le même commit (pas de séparation = re-tune masqué)
- Bands sans bloc `temporal_splits` du tout (signal de tuning intuitif non auditable)
- "OOS" qui couvre la même période que les anchors utilisés pour valider (cas pernicieux : tu déclares OOS 2026-Q2 mais les predictions resolved 2026-Q2 ont été incluses dans val)

### Test verrouillé

`tests/test_calibration_temporal_splits.py` :
1. Le bloc `audit_metadata.temporal_splits` existe + a les 5 clés requises
2. Les dates sont parsables (ISO ou format `YYYY-MM-DD .. YYYY-MM-DD`)
3. `oos_window` ≤ `next_oos_window` (chronologie cohérente)
4. `next_oos_window` ≥ `last_audit` (la fenêtre frozen commence après l'audit)

Régression sur un de ces 4 = violation L16, gate `assert` lors de la build.

### Pourquoi cette doctrine est dure

Tentation 1 : « Le marché a bougé, je dois adapter. » → Si tu n'as pas attendu la fin du `next_oos_window`, tu commits une violation. Adapter = légitime SEULEMENT si tu commits un nouveau split (split-update commit ≠ bands-update commit) avec justification écrite.

Tentation 2 : « Je vais juste ajuster ce seuil de 15 à 16, c'est rien. » → 1 seuil × 12 indicateurs × 4 fois par an = 48 micro-ajustements. Chacun isolé semble inoffensif, en agrégat ils repeignent les bands pour qu'elles « marchent toujours » sur l'historique récent. Anti-pattern qlib model zoo (L14 anti-pattern #8) à l'échelle thresholds.

### Référencer

Depuis `CLAUDE.md` § "À retenir sans chercher" (splits temporels). Helper `shared.calibration.get_temporal_splits()`. Test verrouillé `tests/test_calibration_temporal_splits.py`. Pas de re-formulation ailleurs.

## L17 — Declarative en YAML versionné, live state en DB, jamais mélanger

Phase 1.5 absorption_roadmap (07/06 soir). Découle de l'analyse de `scripts/risk_watch.json` : le fichier mélange (a) la déclaration user des risques (rang, ballast cible, tickers à surveiller, scénarios, mitigation plan) et (b) l'état live mis à jour par cron (`current_status`, `last_evaluated_at`, `last_eval_reason`, `last_eval_confidence`, `last_eval_evidence_ids`). Mélanger les deux casse plusieurs propriétés.

### Le piège

Un fichier qui sert à la fois de source-de-vérité-déclarative ET de scratchpad-cron a ces problèmes :
- **Git blame inutilisable** : chaque run cron modifie le fichier, le diff utile (« quand le user a changé le rang d'un risque ») est noyé.
- **Pas de comments YAML** : si tu veux comments inline pour audit humain, tu dois utiliser ruamel.yaml round-trip qui n'est pas robuste sur les structures profondes.
- **Conflits de concurrence** : si le user édite pendant un run cron, l'un des deux écrase l'autre. Pas de transaction.
- **Audit trail perdu** : la valeur `current_status='at_risk'` au moment T n'est plus consultable une fois écrasée par T+1.

### La règle

**Séparer dur les deux natures de données :**

| Nature | Storage | Mutation | Schema | Exemple |
|---|---|---|---|---|
| Déclarative (user-edited) | `config/<nom>.yaml` | User uniquement (jamais cron) | Pydantic strict, `_meta` block obligatoire | `config/target_allocation.yaml`, `config/calibration.yaml` |
| Live state (cron-edited) | Table SQLite append-only | Cron uniquement (jamais user direct) | Migration Alembic, indexes (ticker, timestamp) | `risk_signal_evaluations`, `macro_regime_alerts` |

Le déclaratif charge à boot et au reload. Le live state s'append à chaque évaluation cron, jamais d'UPDATE in-place. Pour le « current status », on fait `SELECT … ORDER BY created_at DESC LIMIT 1`.

### Anti-patterns

- **YAML que le cron écrit** : si la cron doit muter un YAML, c'est qu'on s'est trompé de couche. Soit on déplace la mutation côté DB, soit c'est en réalité du JSON live (pas du YAML déclaratif).
- **`current_status` dans le YAML déclaratif** : drift garanti. Le déclaratif dit « ce risque existe, voici sa cible ». Le live state dit « voici son évaluation à T ».
- **JSON sans `_meta` versionné** : pas de schema_version → impossible de faire une migration de format propre plus tard.
- **Lecture du YAML à chaque render** : le coût parse + valide n'est pas négligeable. Cache au boot, reset_cache pour les tests.

### Test contre soi-même

Si tu te retrouves à écrire `_RISK_WATCH_PATH.write_text(json.dumps(updated_data))` quelque part dans un cron : c'est une violation L17. La cron doit écrire dans une table DB append-only. Le fichier déclaratif est read-only par le bot, write-only par le user.

### Cas border-line : ce qui est légitime

- **Fichiers de catalog statique** (sectors.yaml, GLOSSARY refs) : pas de live state, pas besoin de `_meta` complet, juste un commit user à l'évolution.
- **DB lookup tables** (ex `ticker_meta` pré-rempli batch) : OK même si « écrites », tant que ce sont des batch loads explicites, pas des mutations cron implicites.

### Référencer

Depuis `CLAUDE.md` § "Catches récurrents" (pointage vers L17). Template canonical `docs/templates/workflow_yaml_pattern.md`. Test verrouillé `tests/test_target_allocation_yaml_schema.py`. Pas de re-formulation ailleurs.

## L18 — Munger latticework : meta-pattern cross-disciplinaire (M16 doctrine)

Phase M-B pillar (07/06). Doctrine pure : non-encodable en gate déterministe, mais critère explicite de qualité du raisonnement.

### Le pattern

Munger : "you have to have models in your head, and you have to array your experience — both vicarious and direct — onto this latticework of models". Une décision investissement de qualité s'appuie sur **plusieurs disciplines** (finance + biologie + psychologie + physique + histoire + ingénierie), pas une seule.

### Symptômes de violation L18

- Raisonnement mono-discipline (juste "P/E < 15 donc undervalued")
- Aucun reach pour analogies hors-finance (effet réseau biologique, théorie des jeux pour pricing, etc.)
- Décisions qui dépendent uniquement de l'expertise sectorielle sans cross-check structurel
- Conviction haute sur un secteur unique sans modèles d'évolution adjacents

### Pourquoi non-encodable

Aucun gate ne peut mesurer "cross-disciplinary depth of reasoning" — c'est une qualité du raisonnement, pas un fait observable. Encoder serait inventer une métrique fausse (compter mots-clés "psychology" / "biology" dans key_drivers = théâtre, pas signal).

### Application pratique

- Avant conviction 5 sur un secteur : forcer self-check "quelles disciplines ai-je consultées ?". Si la réponse est "juste finance + memo analyste", alarme.
- Dans `key_drivers` : encourager (pas enforcer) des drivers cross-disciplinaires explicites. Ex M5 Lynch clarity pattern peut implicitement capturer ça si le user formule en termes de "network effect" / "regulatory cycle" / "compounding returns to scale".
- En audit `/audit` : surface ratio drivers-secteur vs drivers-cross-discipline. Métrique optionnelle, pas gate.

### Référencer

CLAUDE.md "Catches recurrents" L18 pointer doctrine M16. Pas de test verrouillé (non-encodable). Pas de re-formulation ailleurs.

## L19 — Sophistication doit être justifiée par fondation, pas la précéder

Pivot 07/06 nuit (red-team auto-correction). Catch identifié après 27+ commits sur étage META (M-B mentor gates, Heimdall V3, ffn/bt wrappers) pendant que la fondation (pre-engagement integrity, attribution causale, base-rate externe) restait inexistante.

### La règle

**Aucune nouvelle couche scoring / calibration / monitoring tant que les 3 conditions suivantes ne sont pas remplies :**
1. **N_resolu >= 100** sur le bucket cible (sinon : calibration sur bruit)
2. **Pre-engagement tamper-evident** en place (sinon : revisions post-hoc indétectables, doctrine illusoire)
3. **Source-de-vérité figée** à l'entrée (driver structuré, benchmark, conviction PIT, kill_criteria)

Si une de ces conditions manque, l'effort doit aller vers la combler, pas vers une nouvelle couche de scoring.

### Symptômes de violation L19

- Ajouter un Nème gate / scorer / dashboard panel alors que le N statistique reste à 35
- Calibrer un modèle (isotonic / Platt / Beta shrinkage) avec n < 100 sur 1 bucket
- Construire une métrique 2ème ordre (Brier conditionnel au régime, IR rolling) avant que la métrique 1er ordre ait du signal
- Documenter une doctrine ("hook posté", "throttle single-gateway", "factor monitor wired") qui n'est pas réelle dans le code

### Pourquoi cette doctrine est dure

Tentation 1 : "le code est propre, ajoutons encore une couche pour le démontrer." → Mais le code propre sans fondation = instrument de mesure d'orfèvre pour une table dont les pieds porteurs ne sont pas posés.

Tentation 2 : "N atteindra 100 dans 18 mois, autant préparer la machinerie maintenant." → Non. La machinerie qui attend 18 mois de data accumule de la dette et drifte loin du besoin réel. Construis quand le N le justifie.

### Test contre soi-même

Avant chaque nouveau commit qui ajoute :
- Un scoring layer, calibration formula, Brier metric
- Un panel dashboard, chart, KPI
- Un gate de validation, monitor, alerte

**Pose-toi** : *"Cette couche calcule sur quel N ? Le N suffit pour qu'elle ne soit pas du bruit ? Si non — vais-je nourrir N en priorité ou ajouter cette couche en priorité ?"*

Si la réponse est "ajouter la couche", **stop**.

### Application pratique

- L19 surface dans `/audit` (TBD) : metric "doctrine sophistication ratio" = (nb_couches_scoring / log(N_resolu)). Si > seuil, alerte.
- CI gate possible : count fichiers `intelligence/*scoring*.py` + `intelligence/*calibration*.py`. Si croît sans N_resolu correspondant, fail.

### Référencer

CLAUDE.md "Catches récurrents" L19. Cf docs/DECISION_QUALITY_ENGINE.md pour la fondation requise. Pas de re-formulation ailleurs.

## L20 — Outcome-graded ne suffit pas, scorer la décision (attribution 2x2)

Pivot 07/06 nuit. Le mode d'échec central d'une machine à discipline calibrée sur outcomes seuls = **quadrant raison-fausse / outcome-juste = chance déguisée en talent**. Invisible à un Brier sur outcomes, indistinguable de SKILL.

### La règle

**Scorer une décision se fait en 2 axes orthogonaux, pas 1 :**
- Axe 1 : outcome (le résultat) — connu (excess return vs benchmark)
- Axe 2 : process / attribution causale — la **raison** déclarée à l'entrée correspond-elle au moteur dominant du return réalisé ?

|  | Outcome juste | Outcome faux |
|---|---|---|
| **Raison juste** | SKILL répétable (size ça) | SOUND_PROCESS (process sain, ne pas désapprendre) |
| **Raison fausse** | **LUCK** (chance déguisée — le quadrant qui ruine) | LEARNING (vrai apprentissage) |

+ 5ᵉ quadrant **UNATTRIBUTABLE** : si le résidu domine la décomposition (≥ 50% du sum abs), L15 fail-closed — pas de cause fabriquée.

### Mécanisation de "raison juste" (cf track_record/attribution.py)

Triple condition :
1. **Driver-hit test** : le KPI nommé dans `epic_driver` a bougé dans direction + magnitude prédites
2. **Channel dominant matche** : la décomposition return montre le canal nommé (`fundamental` vs `multiple`) comme dominant
3. **Kill-criteria respectés** : booléen depuis le journal monitoring (lecture, pas re-implémentation — L4)

Si une seule condition manque → reason_right = False → LUCK ou LEARNING selon outcome.

### Symptômes de violation L20

- Conclure "j'ai du skill" sur une série de outcomes positifs sans vérifier attribution
- Désapprendre une thèse après un outcome négatif sans vérifier si reason_right
- Réviser une conviction post-hoc en disant "je savais que..." (anti-L16 et anti-L20)
- Présenter un Brier impeccable sans présenter `luck_share` (= part LUCK / (SKILL + LUCK))

### Pourquoi cette doctrine est dure

Tentation 1 : "Mon Brier est à 0.18, c'est largement mieux que 0.25 baseline." → Mais sans attribution 2x2, tu ne sais pas combien de tes outcomes positifs sont LUCK. Si luck_share = 60%, ton "skill apparent" est 40% de ce que tu crois.

Tentation 2 : "Trop compliqué de structurer epic_driver à l'entrée, c'est friction." → Sans driver structuré (KPI + magnitude + price_channel), B est impossible. La friction à l'entrée *est* la doctrine. Sans elle, tu calibres l'aléa.

### Application pratique

- À chaque création thèse conviction ≥ 4 : `driver_epic` requis (warning A0 si vide).
- À résolution +30j : tracer attribution 2x2 + UNATTRIBUTABLE rate.
- À audit `/audit` : `luck_share` est le verdict clé quand N ≥ 30 sur cohorte SKILL+LUCK. En dessous : gating L15 → None ("puissance insuffisante").
- Render.py panel decision_quality (TBD) : grille 2x2 + part LUCK + UNATTRIBUTABLE count.

### Test verrouillé

`tests/test_attribution_2x2.py` :
- `test_luck_quadrant_outcome_good_but_wrong_reason` — LUCK distinct de SKILL malgré outcome identique
- `test_unattributable_blocks_fabricated_skill` — résidu domine → refus de fabriquer cause

Si un de ces tests régresse, on a perdu L20.

### Référencer

CLAUDE.md "Catches récurrents" L20. Cf `docs/DECISION_QUALITY_ENGINE.md` spec complète. Pas de re-formulation ailleurs.

## L21 — QUALITY_BAR : les 3 mécanismes d'exécution (M1, M2, M3) + meta fail-closed

Pivot 07/06 nuit++ (red-team meta-doctrine). Source de vérité unique : `docs/QUALITY_BAR.md`. **Base non-négociable**.

### La base en une phrase

Un hedge fund ne pas raison plus souvent — il ne se ment jamais sur son edge, sa data, ou son risque. PRESAGE copie ça, pas la perfection.

### M1 — Triple (valeur, as_of, provenance), jamais scalaire

Un prix nu est interdit. `prices.get()` retourne `(price, asof, source)`. Toute query positions retourne son `price_asof`. Toute surface UI affiche la fraîcheur.

**Symptôme de violation** : un nombre présenté sans son `asof`. Ex : `position.eur_value=4336.32` dans `notes` = bug fondateur (valeur dérivée figée à l'instant T → morte à T+1).

**Application** :
- `shared/prices.py` get_current_price + get_fx_rate persistent `price_history` + `fx_history` append-only avec triple
- `shared/freshness.py` classifier SLA green/amber/rouge
- `shared/valuation.py` position_valuation() = fonction calcule live, jamais persistée

### M2 — Pre-registration tamper-evident des claims

Toute claim est `(direction, proba, horizon, baseline)` figé tamper-evident. Pas d'opinion sans ces 4 champs ancrés dans un ledger d'intégrité (hash chain + OTS anchor).

**Symptôme de violation** : conviction révisée post-hoc, kill-criteria flou, benchmark cherry-pické.

**Application** :
- `thesis_integrity_log` + `prediction_integrity_log` chain hash sha256
- `scripts/integrity_anchor.sh` OTS stamp Bitcoin trustless
- `commit-reveal hiding` sur predictions (payload+nonce privé, hash public)

### M3 — Sizing respecte l'edge prouvé, pas la conviction affirmée

À `N_resolu < 100`, l'edge est inconnu → **sous-Kelly** (compresser spread de conviction vers quasi-équipondéré), ballast obligatoire (cash / décorrélé / hedge de queue), stress-test = gate dure.

**Symptôme de violation** : sizing-cible 5.6% c5 vs 0.7% c1 alors qu'on n'a pas prouvé que c5 surperforme c1. Concentration single-factor sans ballast.

**Application** :
- `config/target_allocation.yaml` sizing-régime construction
- `intelligence/factor_exposures.py` exige ballast + flag < cible
- Stress-test monitor à transition (drawdown > seuil NAV → alerte)
- L19 invariant : aucune nouvelle calibration tant que `N < 100`

### Méta — Fail-closed (L15 généralisé)

Quand M1, M2 OU M3 ne peuvent être satisfaits :
- Data stale au-delà SLA → `position_valuation.value_eur = None` + `value_eur_fail_reason`
- Edge non-prouvé (N<100) → sizing sous-Kelly forcé, pas de boost conviction
- Chaîne intégrité cassée → scoring downstream refuse

Le système affiche **dégradé** ou **refuse**, jamais ne **fabrique**.

### Invariant transverse à graver

> Le système a le droit de dire « je ne sais pas / c'est stale / mon edge n'est pas prouvé ». Il n'a jamais le droit de présenter un nombre plus confiant que son évidence. La volonté de montrer sa propre ignorance est la qualité hedge-fund-worth — et c'est la seule qui convainc un adversaire.

### Test verrouillé

`tests/test_m1_inputs_dated.py::test_positions_schema_has_no_eur_value_column` — catch the founding bug si quelqu'un re-introduit `eur_value` en colonne. Plus largement : tout test qui présent un nombre sans asof est une violation M1.

### Référencer

Source canonique : `docs/QUALITY_BAR.md` (figé 07/06 nuit++). L21 ici = doctrine encodée pour grep transversal. CLAUDE.md "Catches récurrents" pointe L21. Pas de re-formulation ailleurs.

---

## L22 — Diversité des sources : N_effective ≠ N_brute (cohorte narrative)

**Catch** : compter 8 newsletters substack comme "8 signaux indépendants" est une violation de M2/M3 — une cohorte narrative macro corrélée n'est pas une lecture du marché, c'est UNE lecture (avec 8 voix). Le système doit afficher N_effective (familles distinctes), pas N_brute.

**Diagnostic au 07/06** : 74/76 sources = `narrative_newsletter` (97.4%), 1 = `primary_filing` (EDGAR), 1 = `manual`. Monoculture confirmée.

**Taxonomie canonique** (migration 0038 `sources.family`) :
- `primary_filing` : EDGAR 8-K/10-Q/10-K (orthogonal structurel)
- `insider` : Form 4, insider clusters (orthogonal comportemental)
- `narrative_newsletter` : substacks, beehiiv (cohorte narrative)
- `broker_research` : Goldman/Morgan/Jefferies
- `social` : reddit, twitter, WSB
- `chat` : user Telegram taps
- `manual` : ajouts manuels user
- `other` : fallback

**Famille orthogonale** = `{primary_filing, insider, broker_research}`. Les autres sont supposées corrélées entre elles (narrative drift commun, social drift commun).

**Symptôme de violation** : afficher "5 sources confirment X" sans expliciter qu'elles sont toutes du même substack circuit.

**Application** :
- `intelligence/source_diversity.effective_n_signals(signals)` = source canonique du calcul N_effective.
- Dashboard `_data_health_panel` chip "X% narrative / Y% orthogonal" — affiche honnêtement la monoculture.
- **Pas de wire scoring action** tant que calibration N<100 (gating L19/L21).

### Test verrouillé

`tests/test_source_diversity.py::test_monoculture_5_newsletters` — 5 signaux narrative → N_effective=1, is_monoculture=True. Le test prouve qu'on ne tombe pas dans le piège du comptage brut.

### Référencer

Source canonique : `docs/QUALITY_BAR.md` Axe 2 garde-fou (figé 07/06). L22 ici = encodage doctrine. CLAUDE.md "Catches récurrents" : ajouter L22 dans la liste compactée si la prochaine session en a besoin.

---

## L23 — Toute valeur dérivable est dérivée live, jamais figée en YAML/DB

**Catch** : un YAML déclaratif qui porte une *valeur* (pas une *cible* ou un *seuil*) crée le même piège que `eur_value` stocké dans `notes` (founding bug Axe 3). La valeur déclarée vieillit ; la réalité dérive ; le dashboard ment. Exemple 07/06 : `risk_watch.yaml` déclarait `current_ballast_strict_pct=14%` (mai), réalité live calculée = **10.1%**. Le YAML mentait de 4pp.

**Règle** : dans un YAML déclaratif (L17), n'écris JAMAIS une valeur dérivable depuis l'état du système. Écris seulement :
- des **cibles** (target_ballast_strict_pct=20%)
- des **seuils** (warn_pct=-25%, breach_pct=-30%)
- des **identifiants** (ballast_strict_tickers=[MP, SAF.PA, ...])
- des **flags doctrinaux** (archetype=concentrator_thematic, construction_phase=true)

La **valeur courante** est calculée par un helper dédié qui lit les positions / signaux / state DB live.

**Si une valeur "current_X" historique a une utilité de traçabilité** (ex : "ce que c'était au moment de la déclaration de la cible") → la garde comme `declared_pct` metadata explicite, et surface le live + la divergence si > tolérance.

**Symptôme de violation** : un dashboard qui affiche `target.current_ballast_strict_pct` directement, ou un Telegram qui réutilise la valeur YAML pour calculer un gap.

**Application** :
- `intelligence/ballast_compute.compute_ballast_strict(positions)` = source canonique du live.
- `dashboard.render._render_ballast_cell` consomme le live + surface `declared_pct` comme metadata si divergence > 1pp.
- Le YAML garde `target_ballast_strict_pct` + `ballast_strict_tickers` (déclaratif), pas `current_*`.

### Test verrouillé

`tests/test_ballast_compute.py::test_declared_vs_live_divergence_surfaced` — YAML déclare 14%, positions live → 10%, helper retourne `current_pct=10.0` + `declared_pct=14.0`. La divergence est SURFACÉE, jamais cachée. Le live PRIME.

### Référencer

Source canonique : `docs/QUALITY_BAR.md` M1 doctrine (figé 07/06). L23 ici généralise M1 du cas eur_value (Axe 3) à tout YAML déclaratif. CLAUDE.md "Catches récurrents" : avant tout ajout de `current_*` dans un YAML, demander "ai-je un helper qui dérive ça live ?". Si oui → garder seulement target/seuil/identifiants, pas la valeur courante.

---

## L24 — Walking skeleton bat squelette pur (chasse à la formule wrong)

**Catch** : quand une abstraction est neuve et que sa forme est incertaine, un squelette testé sur des mocks propres passe tous ses tests et reste **faux** — parce que la réalité n'est pas propre. Les bugs d'abstraction se découvrent **seulement** quand un vrai input la traverse. Reporter cette découverte à la phase d'intégration (calibration / backtest) = la payer au pire moment.

**Le cas fondateur (08/06/2026, cornerstone C6)** :
- `SPEC_CORNERSTONE.md §1` postulait `D = (croyance pricée) − (réalité livrable)` (soustraction de buckets).
- L'engine pur sur mocks aurait validé cette formule (les tests synthétiques tapent des valeurs déjà conformes).
- En implémentant le tracer-bullet HY_OAS via `macro_inputs.py`, l'examen du sign-theory canonique a révélé : tous les `z_signed` du YAML pointent **déjà** vers "divergence haute" (sign-théorie figé). Soustraire deux buckets dont les inputs sont déjà alignés vers la même direction = **compter le signal en double**.
- Formule correcte : `D = weighted_mean(z_signed)` agrégé globalement sur croyance_pricée + réalité_livrable. Le bucket sert à organiser/auditer, pas à inverser la sommation.
- **Si on avait shippé le squelette pur, on aurait wire 8 inputs en C7 sur une formule cassée**, et découvert le bug pendant le backtest historique (le moment le plus cher).

**Règle générale** : pour toute abstraction neuve (engine, primitive, contrat), faire un walking skeleton = primitive pure + UN vrai slice (interface → engine) **avant** d'investir dans le reste. La fixture (snapshot d'un vrai input messy) tue la flakiness sans tuer le réalisme.

**Pas un test bonus — c'est la phase de découverte de l'abstraction.** Le squelette pur seul est une dette de découverte.

**Symptômes de violation** :
- L'engine compile, tous les tests purs passent, mais la première intégration révèle un bug structurel.
- Une formule de la spec ne survit pas au premier vrai input.
- Le backtest historique trouve un bug qui n'est pas un bug de calibration mais de primitive.

**Application** :
- Sur toute nouvelle primitive : 1 fixture réelle (snapshot externe), 1 resolver, 1 tracer-bullet end-to-end. Avant les tests purs supplémentaires.
- Si le tracer-bullet révèle une formule wrong, **mettre à jour la spec doctrinale** avec la traçabilité (`Note tracer-bullet 08/06 : formule corrigée parce que ...`). La doctrine vit, elle ne se fige pas avant la première traversée réelle.
- En revue de spec : exiger explicitement "quel est le tracer-bullet ?" avant validation.

### Test verrouillé

`tests/test_macro_inputs_hy_oas.py::test_tracer_bullet_engine_consumes_hy_oas_real_input` — le tracer-bullet qui a découvert le formule-wrong. Verrouille pour l'avenir : un vrai input FRED (fixture deterministe) traverse `resolve_macro_inputs` → `compute_divergence`, et la sortie est honnête (degraded si fail-closed, ou D cohérent si forcé fresh).

### Référencer

Source de l'incident : commit `b8ef1b4` cornerstone C6 (08/06). La formule corrigée est documentée dans `intelligence/divergence_engine.py` docstring + `SPEC_CORNERSTONE.md` note d'erratum. CLAUDE.md "Catches récurrents" : avant toute abstraction nouvelle, demander **"quel est mon tracer-bullet ?"** — si la réponse est "des mocks", la doctrine n'est pas respectée.


## L25 — Suivi du canonique (gravé ≠ appliqué)

**Catch** : un SPEC gravé sans mécanisme de suivi devient un objet mort. Au mieux il dort, au pire il invite la dérive : un autre agent (ou moi-même) le ré-écrit en doublon parce que personne ne vérifie l'existant ; ses contrats ne sont jamais wired ; le canonique se fragmente silencieusement. La gouvernance d'une doctrine n'est pas son écriture — c'est son suivi.

**Le cas fondateur (08/06/2026, session doctrine post-cornerstone)** :
- Olivier signale "il y a beaucoup à enrichir, aussi si elle existe déjà pourquoi n'est-elle pas appliquée".
- Audit immédiat : 8 SPECs gravés dans le repo (`SPEC_*.md`), **un seul** (`SPEC_CORNERSTONE.md`) référencé par du code Python (4 fichiers). 7/8 = orphelins doctrinaux.
- Pire : dans la session courante, j'ai créé **2 doublons** en 30 minutes :
  - `SPEC_POSITIONS_CARD_LIAISON.md` alors que `SPEC_POSITIONS_CARD_LINK.md` existait déjà (mot synonyme — j'aurais dû `ls SPEC_*.md` avant de toucher).
  - `SPEC_TAXONOMY_PROFILES.md` alors que `SPEC_SECTOR_TAXONOMY.md` existait déjà.
- Pendant ce temps, la **fondation** (étape A du master §5) reste cassée : `eur_value` figé à J-15, incohérence 0,5×/1,80×, deux chemins de valorisation divergents. **Le goulot du projet n'est plus la doctrine, c'est l'absence de fondation honnête sur laquelle elle peut atterrir.** L'anti-pattern original (méta-étage qui court devant un socle cassé) que l'audit pivotal a diagnostiqué — je l'ai reproduit cette session.

**Règle générale** : graver un canonique implique trois engagements indissociables :
1. **Anti-doublon** : avant tout nouveau SPEC, `ls SPEC_*.md` + scan titres sur synonymes (link/liaison, taxonomy/profiles, etc.) puis grep du concept clé. Doublon créé = build rouge.
2. **Implementation Status footer** dans chaque SPEC : date gravage, date enrichissement, fichiers cibles (chemins concrets), état (`NOT_STARTED` / `IN_PROGRESS` / `IMPLEMENTED` / `DRIFTED`), prochain step (référence TODO).
3. **Audit drift automatisé** : script qui scanne tous les `SPEC_*.md`, vérifie le footer + l'existence des fichiers cibles, et compte les références code → reporte les orphelins. Intégré au `/close` rituel.

**Anti-pattern à bannir** :
- Graver un SPEC pour "se débarrasser de l'idée" et passer à autre chose. Un SPEC sans plan d'implémentation visible = dette doctrinale.
- Empiler de la doctrine quand la fondation est cassée. **Goulot d'abord, doctrine ensuite** — la doctrine sur fondation cassée est performative.
- Reformuler un canonique existant dans un nouveau SPEC. Si une SPEC mérite réécriture, elle se réécrit en place (avec note d'erratum traçable, cf L24).

**Application** :
- Pour chaque SPEC en cours/à venir : ajouter footer Implementation Status + créer la tâche TODO de référence + lier au CANONICAL_MAP.
- Pour chaque session : `scripts/audit_canonical_drift.py` en sortie du `/close`.
- Avant tout nouveau SPEC : `ls SPEC_*.md && rg -l "<concept>" SPEC_*.md` — **vérification obligatoire**, pas optionnelle.

### Test verrouillé

`scripts/audit_canonical_drift.py` (à wirer, cf TODO #104) : reporte par SPEC le ratio référence-code / orphelin. Build rouge si un SPEC sans footer Implementation Status, ou si un orphelin reste > N jours après gravage sans plan TODO de référence.

### Référencer

CLAUDE.md "Catches récurrents" : avant toute nouvelle SPEC, demander **"existe-t-il déjà un SPEC sur ce concept ? Quel est le plan d'implémentation ?"** — si la réponse est "non" ou "on verra plus tard", la doctrine n'est pas respectée. La règle voisine de [[L24]] (walking skeleton catches formule wrong) est : un SPEC gravé sans implémentation présuppose une formule qu'aucun tracer-bullet n'a vérifiée — double risque.
