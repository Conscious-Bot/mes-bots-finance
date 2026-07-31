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
  c2 = 0 (pas de position) · VENTURE ≤ 1 %, zéro stop prix, milestone écrit.
  ⚠ STATUT : proposés depuis le 30/07, **jamais validés gérant** — à sceller.
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

## 7. DÛ PAR LE GÉRANT POUR SCELLER v1 (les nombres, rien d'autre)

1. Cap facteur AI-compute : 65 % cliquet ? (ou 60/70)
2. Caps conviction compressés : validation formelle (c5 7 / c4 5.5 / c3 4 / c2 0 / venture 1)
3. Ballast min : 20 % ? · Sleeve accélération max : 45 % ? · Devise max : 20 % ? · Illiquide max : 5 % ?
4. Échelle : R1 −15 % / R2 −25 % — validation (R3 = 30 k déjà gravé §IX)
5. Couche vie : horizon · apports/mois · besoins datés · part du patrimoine
6. Backstop en règle : −35 % du HWM annuel à partir de 2027 ?
