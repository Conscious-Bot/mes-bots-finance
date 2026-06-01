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

## Politique d'évolution

Toute nouvelle leçon (catch récurrent qu'on attrape pour la 2ème fois) **doit** être ajoutée ici avec :
- numéro `Lk` séquentiel
- règle en 1 phrase imperative
- pourquoi (le coût qu'on évite)
- cas concrets observés (références au code)
- éventuel red flag détectable à l'instant 0

Référencer depuis `CLAUDE.md` § "À retenir sans chercher" — pas de re-formulation ailleurs.
