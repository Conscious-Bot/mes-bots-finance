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

### Règle structurelle (le vrai fix, à shipper)

Les fixtures DB tests **sont dérivées de la migration head courante**, pas commitées comme snapshots statiques. Régénération automatique au CI via `alembic upgrade head` sur un volume éphémère + minimal seed. Tue le mode de défaillance à sa racine — 1h d'écriture, économie illimitée.

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

## Politique d'évolution

Toute nouvelle leçon (catch récurrent qu'on attrape pour la 2ème fois) **doit** être ajoutée ici avec :
- numéro `Lk` séquentiel
- règle en 1 phrase imperative
- pourquoi (le coût qu'on évite)
- cas concrets observés (références au code)
- éventuel red flag détectable à l'instant 0

Référencer depuis `CLAUDE.md` § "À retenir sans chercher" — pas de re-formulation ailleurs.
