# RISK_FRAMEWORK — L'ARCHITECTURE DE RISQUE À VIE (v1, 31/07/2026)

> Demande gérant : « le book est ultra-concentré AI/semi aujourd'hui, mais il est
> fait pour me suivre toute ma vie en évoluant — risk-proof au max. »
> Principe : le risque se gère par COUCHES. Chaque couche a ses LIMITES (chiffrées,
> validées gérant), ses CAPTEURS (monitors, pattern canonique) et ses ACTIONS
> PRÉ-ÉCRITES (zéro délibération au moment T). Le prix n'est jamais un input de
> décision ; l'exposition, si. Sœur de QUALITY_BAR (qualité) et NORTH_STAR
> (sélection) — ce doc gouverne la TAILLE et la SURVIE.

## 1. COUCHE LIGNE (existe — à sceller)

- **Caps par conviction (compressés, N<100)** : c5 ≤ 7 % · c4 ≤ 5.5 % · c3 ≤ 4 % ·
  c2 = 0 (pas de position). ⚠ STATUT : proposés 30/07, **à sceller formellement**.
- **VENTURE : matrice de sizing, PLUS un cap fixe** (v1.1, 01/08 — argument gérant
  accepté : *le sizing dérive de la distribution des résultats, pas de la catégorie*).

### 1bis. FONCTION DE SIZING VENTURE (remplace « venture = 1 % » — v1.2, 01/08)

**On grave la FONCTION, pas des catégories** (argument gérant : une grille V1/V2/V3
engendre un V4 puis une jurisprudence ; une fonction s'applique dans cinq ans à une
entreprise qui n'existe pas encore). Les tailles sont des SORTIES, jamais des règles.

```
TAILLE = min(
    quart_Kelly(asymétrie) × d_observabilité × d_corrélation,
    plafond_dur 3 %,
    budget_poche_restant                        # venture + illiquide ≤ 5 % du book
)

quart_Kelly : f* = p/l − q/b   (b = gain fractionnaire, l = perte fractionnaire)
              puis × 0,25      (erreur d'estimation : p est estimé, jamais connu ;
                                surparier ruine, sous-parier coûte peu)
d_observabilité : 1,0 comptes publics + milestones vérifiables trimestriellement
                  0,6 partiel (segments agrégés, gouvernance verrouillée)
                  0,3 opaque
d_corrélation   : (1 − ρ) vs le facteur dominant du book — Kelly suppose
                  l'indépendance ; les paris corrélés se dimensionnent en CLUSTER
RÈGLE D'ARRÊT   : f* ≤ 0 → PAS DE POSITION (une « venture » peut être un mauvais
                  pari, pas seulement un pari mal dimensionné)
```

**Exemple d'application — SPCX (01/08/2026)** : gain +200 % / perte −50 % (Starlink
fait plancher) · p = 0,25→0,35 · d_obs = 0,6 · ρ ≈ 0,5 (mixte compute ET défense —
Starshield/DoD/NRO ne corrèlent pas au capex IA) → **sortie 0,9 % à 2,8 % selon p ;
retenu ≈ 2 % (milieu de fourchette)**. La sensibilité à `p` EST la raison d'être du
quart-Kelly : on ne prétend pas connaître p, on borne l'erreur.

**Garde-fous non négociables** (sans eux la fonction fabrique la concentration qu'elle
prétend gérer) :
1. **Kelly fractionnaire** : le plafond 3 % ≈ quart-de-Kelly sur une venture
   d'asymétrie extrême. Kelly plein suppose des probabilités CONNUES ; elles sont
   estimées, et le surdimensionnement ruine quand le sous-dimensionnement coûte peu.
   Une venture ne dépasse jamais 3 %, quelle que soit la conviction.
2. **PLAFOND DE POCHE : venture + illiquide ≤ 5 % du book** — la contrainte mordante.
   Trois V3 = 9 % : interdit. La poche se partage.
3. **Zéro stop prix** (une venture ne se juge pas au cours), **milestones écrits**,
   **revue à date fixe**, **gel d'add hors plan de tranches écrit**.
4. Kelly négatif = **pas de position** (ex. 20 % de chance de ×3 : f* < 0 — une
   « venture » peut être un mauvais pari, pas seulement un pari mal dimensionné).

**Application SPCX (01/08)** : asymétrie haute mais bornée par une valorisation
d'entrée déjà énorme (1,4 T$) · observabilité MOYENNE (S-1 public, segments agrégés,
82,4 % des votes chez le fondateur) · corrélation **MOYENNE À ÉLEVÉE** — mixte :
compute (segment AI, régime de valorisation partagé) ET défense (Starshield, DoD,
NRO, orthogonale au capex IA) → **sortie de fonction ≈ 2 %**. Note : la nature mixte
de la corrélation plaide marginalement pour PLUS que 2 % ; la fourchette 0,9-2,8 % et
le principe de prudence sur `p` fixent le retenu au milieu.
- **Stop par ligne** : niveau structurel (low traversé − buffer vol), décision
  FORCÉE sous 24 h (exécuter OU révision écrite datée). Jamais d'auto-exec broker
  (gaps/illiquides), jamais de limbo (leçon constitutive de juillet).
- **Risque €/ligne** : poids × distance stop ≤ **~1 % du book** par ligne.
- **À la création d'une ligne** : thèse signée (variant + falsifieurs + cible +
  stop) AVANT l'ordre · gate §XI (financement × preuve) · tag plateau
  (niveau|accélération) · typage (compounder | trade-de-cycle | venture | ballast).

## 2. COUCHE FACTEUR (NOUVEAU — le trou qui a produit juillet)

**Définition** : un facteur = un DRIVER de demande, pas un secteur GICS.
Facteurs actuels : AI-compute (équipement + mémoire + foundry + EDA + plateformes-capex
+ power-DC) · Défense/sécurité · Énergie non-DC · Démographie/annuités (cible NORTH_STAR)
· Special situations (put gouvernemental).

**Limites structurelles (valeurs À VALIDER gérant — L16, rien de figé sans lui)** :

| Limite | Proposition | Note |
|---|---|---|
| Facteur max (AI-compute) | **65 % cliquet descendant — ✅ VALIDÉ GÉRANT 31/07** | courant ~64-66 % |
| Sleeve accélération max | **45 %** du book (tags plateau) | courant ~40-45 % |
| Cluster devise max (JPY, KRW…) | **20 %** par devise hors EUR/USD | JPY courant ~17 % |
| Illiquide + venture total | **5 %** | SPCX seule ≈ 5.6 % → §XIII résout |
| Ballast contracté + cash min | **20 %** (cible 25-30 à terme NORTH_STAR) | |

**Règle du cliquet** : les caps facteur DESCENDENT vers la cible NORTH_STAR
(AI-compute 65 → ~55 % sur 12-24 mois) par APPORTS et MIGRATION (le nouveau
capital dilue), **jamais par vente forcée** — sauf breach par APPRÉCIATION :
facteur > cap pendant 4 semaines consécutives → trim-to-cap forcé, rightsize
jamais exit, et on ne trim JAMAIS sous le cap (anti-lock_in : la règle ne peut
pas devenir une machine à vendre les winners).

## 3. COUCHE BOOK — L'ÉCHELLE DE DRAWDOWN (mécanique, plus jamais ad-hoc)

Juillet a improvisé (digue posée à la main, tribunal déclenché par la douleur,
backstop écrit à J+30). La prochaine fois, tout est pré-écrit — depuis le HWM :

| Palier | Déclencheur (close, hystérésis 5 pts pour dégel) | Action MÉCANIQUE |
|---|---|---|
| **R1 — GEL** | DD −15 % | gel des achats AUTO (digue v2, monitor journalisé) + revue triggers sous 7 j |
| **R2 — TRIBUNAL** | DD −25 % | tribunal complet FORCÉ sous 7 j (l'équivalent du 30/07, mais à date contrainte) |
| **R3 — BACKSTOP** | valeur compte < 30 000 € (2 closes) | dé-risque à ~50 % investi, ordre de coupe pré-défini (1. sans thèse revue, 2. convictions basses, 3. gros poids), zéro re-délibération |

Journal append-only (pattern monitor canonique + test L4). Un palier franchi
NOTIFIE et impose sa date — il ne demande pas d'avis.

**✅ VALIDÉ GÉRANT 31/07 : R1 −15 % gel auto · R2 −25 % tribunal forcé · R3 = §IX.**

## 4. COUCHE VIE (les paramètres MANQUANTS — le book ne connaît pas son porteur)

Inputs jamais enregistrés, dus par le gérant (cf « 5 questions » du 31/07) :
**horizon** (quand l'argent sera-t-il NÉCESSAIRE ?) · **apports mensuels** ·
**besoins de liquidité datés** · **part du patrimoine total que représente le book**.

Règles d'échelle une fois les inputs connus :
- Le backstop devient une RÈGLE (% du HWM annuel, proposition : −35 %), plus une
  instance (30 000 € = la valeur 2026).
- La sleeve accélération max DÉCROÎT quand l'horizon-au-besoin < 7 ans.
- Les apports donnent un droit de moyenner ENCADRÉ (plan écrit, jamais improvisé).
- Révision des limites : 1×/an (revue NORTH_STAR) OU événement de vie — jamais
  en drawdown (les règles ne se réécrivent pas sous le feu, cf anti-plancher-roulant §IX).

## 4bis. LE TAIL ASSUMÉ — TAÏWAN (nommé 31/07, après Griffin/Goldman APEX)

**Le seul scénario que l'architecture ne borne PAS.** TSM ~7,9 % en direct, mais
l'exposition réelle est au second degré : ASML/KLAC/Advantest/BESI vendent aux fabs,
SNPS conçoit pour elles, la mémoire coréenne partage la géographie du risque. Un choc
Taïwan **gappe** — il ne descend pas l'échelle R1→R2→R3 palier par palier, il saute
directement sous le backstop avant tout close exploitable. Le backstop borne
l'AMPLITUDE d'un drawdown ordonné, pas la VITESSE d'un choc géopolitique.

**Décision : tail ASSUMÉ, pas hedgé.** Pas d'options (§5), pas de sous-pondération
permanente de la meilleure entreprise du monde sur un scénario non-datable. Les
seules mitigations honnêtes, toutes déjà au framework : ballast contracté non-corrélé
+ cash (= « rester en position de contre-attaquer »), cap facteur 65 %, manche
démographie/annuités à construire, zéro levier (le levier transforme un choc
survivable en ruine — leçon SALP).

**Lecture Griffin adoptée (inversion du sens de calcul)** : partir de la PERTE
TOLÉRABLE et en déduire l'exposition, plutôt que l'inverse. « Definable, tolerable,
still in business, still in a position to fight back. » Cette inversion exige
l'input §4 (couche vie) — une perte tolérable se déduit d'une VIE, pas d'un book.
Corollaire §XI côté demande : auditer aussi le LABEL chez l'acheteur (« la plupart
des gains attribués à l'IA sont du ML/optimisation/digitalisation » — marqueur Q2 :
quelle part des gains AI survivrait à un ré-étiquetage honnête ?).

## 4ter. L'ARBITRE SOUVERAIN — ORDRE TOTAL DES CONTRAINTES (gravé 01/08/2026)

**Trou identifié à l'audit** : si Q1 dit « thèse intacte », Q2 « sous le cap », le cap
facteur « dépassé », l'échelle « R1 gel », et que le gérant veut acheter — rien
n'écrivait qui l'emporte. Chaque conflit se résolvait par l'humeur du jour, et deux
implémentations du même système pouvaient produire deux décisions différentes.

**Décomposition qui rend le problème tractable** — les contraintes sont de deux
natures, et une seule exige un ordre :

- **INTERDICTIONS** (gel R1 · caps de ligne, facteur, devise, poche · §XI · gates de
  prix NORTH_STAR) : elles **composent trivialement**. Leur intersection est toujours
  cohérente ; une seule qui mord suffit à bloquer. **Aucun ordre nécessaire.**
- **INJONCTIONS** (elles peuvent se contredire — d'où l'ordre) :

| Rang | Injonction | L'emporte sur tout ce qui suit |
|---|---|---|
| 1 | **R3 backstop** (2 closes < seuil) → dé-risque ~50 %, ordre de coupe pré-défini | absolu |
| 2 | **R2 tribunal forcé** (DD −25 %) → instruction complète sous 7 j | — |
| 3 | **Decision-trigger touché** → décision forcée sous 24 h (exécuter OU réviser par écrit) | — |
| 4 | **Breach de cap facteur** persistant 4 semaines → trim-to-cap (jamais sous le cap) | — |
| 5 | **Rightsize Q2** (poids > cap de conviction) | — |

**Règles de l'arbitre** : (a) un rang supérieur ne peut jamais être assoupli par un
rang inférieur ni par un solveur ; (b) une injonction de rang N suspend les injonctions
de rang > N tant qu'elle n'est pas exécutée ou révisée par écrit ; (c) **Q1 n'est pas
dans l'ordre** — il ne mandate rien, il qualifie l'état d'une thèse ; (d) un override
du gérant peut contredire une injonction, mais alors il en prend le rang et doit être
écrit avec contrefactuels armés (§XIII).

**Théorème à vérifier par machine (remplace l'assertion)** : l'ordre ci-dessus est
**total** sur les cinq injonctions ; aucune paire n'est incomparable ; donc toute
séquence d'évaluation produit la même décision. Vérification exhaustive : 5 injonctions
→ 2⁵ = 32 états d'activation, chacun doit produire une action unique. À implémenter en
test de propriété (cf. axe « théorèmes plutôt qu'assertions »).

## 5. CE QU'ON N'UTILISE PAS (décisions explicites, pas des oublis)

- **Levier : JAMAIS** (la leçon SALP : 4x + −60 % facteur = mort même en ayant raison).
- **Options/hedges : NON** — coût + complexité + skill de timing ; la défense
  anti-tail de ce book = ballast contracté + cash + échelle de drawdown + backstop.
  Révisable uniquement par amendement écrit de ce doc.
- **Stops auto-exec broker : NON** — décision forcée > automatisme aveugle.
- **Régime-guessing : NON** — les limites réagissent à des OBSERVABLES (DD, poids,
  closes), jamais à des prédictions de phase.

## 6. ENFORCEMENT (le système, pas la vigilance — L27)

- **Panneau Risque (dashboard)** : expositions par facteur vs caps · clusters
  devise · part accélération · distance au R1/R2/R3 · somme des risques-stops
  (invariant : Σ risques ≤ distance au backstop) · liste des breaches.
- **Monitors** (pattern canonique, 7 tests dont L4) : `factor_cap` (nouveau) ·
  `over_cap` (armé avec caps scellés) · `drawdown_ladder` (nouveau, remplace la
  digue manuelle) · `stop_touch` (décision forcée 24 h, notify).
- **Cadence** : revue risque TRIMESTRIELLE (rituel : expositions, breaches,
  résolutions du resolver — les overrides battent-ils les règles ?) · revue
  ANNUELLE des limites (avec NORTH_STAR). Le resolver ferme la boucle : si les
  overrides gagnent systématiquement, les règles s'amendent PAR ÉCRIT — pas par érosion.

## 7. DÛ PAR LE GÉRANT POUR SCELLER v1 — ORDRE CORRIGÉ (amendement 31/07, critique session terminale acceptée : la couche VIE n'est pas une couche, c'est la FONDATION)

1. **COUCHE VIE D'ABORD — horizon · apports/mois · besoins datés · part du patrimoine.**
   C'est elle qui transforme les items 2-6 de « chiffres plausibles » en « limites
   calibrées ». Scellée en un seul message ; tout le reste se scelle presque seul derrière.
2. Cap facteur AI-compute : ✅ 65 % cliquet — VALIDÉ 31/07
3. Échelle R1 −15 % / R2 −25 % : ✅ VALIDÉE 31/07 (R3 = §IX)
4. Caps conviction compressés : validation formelle (c5 7 / c4 5.5 / c3 4 / c2 0 / venture 1)
5. Ballast min 20 % ? · Accélération max 45 % ? · Devise max 20 % ? · Illiquide max 5 % ?
6. Backstop en règle : −35 % du HWM annuel à partir de 2027 ?
