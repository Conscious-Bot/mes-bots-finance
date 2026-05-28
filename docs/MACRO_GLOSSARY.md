# Macro Monitor — Glossary

Référence des indicateurs du moniteur macro/stress (page Urgence du dashboard PRESAGE).
Chaque entrée : ce que c'est, ce qu'elle dit, seuils, pertinence pour le book AI_compute.

---

## MARCHÉ & LIQUIDITÉ

### Bitcoin ($)
Le BTC est devenu un baromètre du risk-on et un proxy de liquidité globale. Quand les banques centrales pompent du cash, BTC monte ; quand elles serrent, il corrige. Pas directement lié au book (crypto pause), mais utile comme jauge d'humeur du capital spéculatif — quand BTC se shoot, l'AI rally est probablement porté par le même appétit.

### Dollar (DXY)
Indice du dollar contre 6 monnaies majeures (EUR, JPY, GBP, CAD, SEK, CHF). Un DXY fort serre la liquidité globale et pèse sur les multinationales US (revenus étrangers convertis en moins de dollars). **99 = modéré. > 105 = vent contraire sérieux pour le book tech ; > 110 = stress global.**

### Spread HY (bp)
Le supplément de rendement que les obligations *high yield* (junk corporates) paient au-dessus du Treasury. Baromètre du risk-on/off du **marché crédit**. **< 300 bp = complacent, 400-500 = vigilance, > 600 = panique.** Un spread qui se dilate avant les actions est un signal avancé précieux.

### VIX
Volatilité implicite du S&P 500 à 30 jours, "l'indice de peur". **< 15 = euphorique, 15-20 = normal, > 25 = stressé, > 40 = panique.** Indicateur **coïncident** (bouge en même temps que les actions), pas avancé.

### USD/JPY
Yens par dollar. Baromètre du *carry trade* global : les hedge funds empruntent en yen à ~0%, achètent du tech US, le yen faible amplifie. Quand ça dépasse 160, la Banque du Japon menace d'intervenir → crash brutal possible → unwind forcé du carry → vente massive de tech US. **Zone d'alerte ≥ 159.** Pour le book c'est important : un crash USD/JPY te liquide indirectement.

### Or ($/oz)
Couverture multi-rôle : taux réels, débasement monétaire, géopolitique. Peut signaler du *de-dollarisation* (BRICS) ou couverture massive contre taux réels qui craqueraient. Pas de seuil "stress" net — surveiller la tendance et la course en parallèle des actions.

### Taux US 30 ans (%)
Rendement du Treasury 30 ans, le **taux d'actualisation long pour toutes les actions growth/tech** (cash flows lointains). **5% est le seuil clé : au-dessus, les multiples tech craquent historiquement** (cf. octobre 2023). Le book est très sensible au discount rate.

---

## STRESS BANCAIRE

### Ratio cuivre/or
Cuivre = industriel (consommé par la croissance), Or = refuge. Le ratio monte = optimisme cyclique ; baisse = peur de récession. Plus interprétatif que de seuil — surveiller la tendance.

### Réserves bancaires Fed ($M)
Cash que les banques détiennent *à la Fed*. **LA jauge de plomberie bancaire US.** Quand ça descend trop bas, stress repo arrive (crise septembre 2019 déclenchée à ~1.4T). **> 3T = confortable.**

### Pente 10a-2a (%)
Le yield curve. Inversé (négatif) = signal de récession à 12-18 mois ; **dé-inversion** (revient positif) = récession imminente (3-6 mois). La dé-inversion en cours est historiquement la phase dangereuse — ATTENTION, pas APAISEMENT.

### Banques régionales ($)
Indice des banques régionales US (KRE ETF). Elles explosent en premier en cas de stress de plomberie (SVB mars 2023). Forme du chart compte plus que le niveau : décrochage brutal = alarme.

### Vol. obligataire (MOVE)
Le VIX des obligations Treasury. **< 100 = calme, > 130 = stressé.** Quand MOVE spike avant VIX, le marché obligataire flaire le trouble avant les actions — signal avancé précieux.

---

## MACRO LENTE

### Inflation core (%)
Core CPI YoY hors énergie/alimentaire. Cible Fed = 2%. **> 2.5% → la Fed ne peut pas couper agressivement → politique restrictive prolongée → vent contraire pour growth/tech.**

---

## AUTRES

### MfgIP_yoy
Manufacturing Industrial Production en glissement annuel. **> 0 = expansion** (molle ou forte), < 0 = contraction.

### FedBalance
Taille du bilan de la Fed. En contraction depuis le pic de 9T (QT en cours). Tendance baissière = liquidité retirée → vent contraire risk assets. **La vélocité de contraction compte plus que le niveau absolu.**

### RepoSRF
Usage de la *Standing Repo Facility* (outil d'urgence Fed pour prêter du cash overnight contre du Treasury). **Normal = bas. > 30B spike = manque de cash aigu dans le système → alarme plomberie ultra-court terme.**

---

## MOMENTUM MARCHÉ — RSI(14) daily

**RSI (Relative Strength Index)** : oscillateur 0-100 mesurant si un actif a "trop monté trop vite" ou "trop baissé trop vite" sur 14 jours. **> 70 = overbought** (rally s'essouffle, pullback risque). **< 30 = oversold** (chute s'épuise, bounce probable).

- **SPY** = S&P 500, baromètre marché global.
- **QQQ** = Nasdaq 100, biais tech, proche du book.
- **SMH** = ETF semi-conducteurs, *littéralement* l'exposition AI_compute. SMH RSI > 75 + tentation d'add NVDA = **biais #1 doit freiner**.
- **IWM** = Russell 2000, small-caps. Confirme la breadth via momentum : si SMH RSI = 80 et IWM RSI = 65+, rally large (sain) ; si SMH = 80 et IWM = 45, AI rip solo → exposition fragile.

---

## BREADTH — RSP/SPY ratio

**RSP** = S&P 500 *equal-weight* (chaque action ~0.2%). **SPY** = S&P 500 *cap-weighted* (10 plus grosses ~35%).

Le **ratio RSP/SPY** mesure la **largeur** du rally :
- Ratio monte = les 490 autres actions participent → marché large, sain.
- Ratio baisse = seulement les mega-caps portent l'index → rally étroit, fragile, classique de fin de cycle.

**Critique pour ce book** : composé majoritairement de noms qui DOMINENT SPY (NVDA, GOOGL, MSFT, META, AVGO, AMZN). Quand RSP/SPY baisse, le SPY a l'air calme — *parce que ces positions portent le marché à elles seules*. Le VIX et le HY spread ne flaggent jamais ça. Signal silencieux qui n'apparaît nulle part ailleurs dans le moniteur.

---

## Lecture rapide état actuel (28/05/2026)

Régime macro : crédit calme (HY 274), peur basse (VIX 17, MOVE 78), liquidité encore OK (Fed reserves 3.13T), inflation au-dessus cible mais sage. **Drapeau rouge** : 30y à 5.026% — la cherté du capital long écrase silencieusement les multiples growth. **Drapeau ambre** : USD/JPY à 159, zone intervention BoJ, tail risk unwind carry violent.

Net : pas de stress aigu visible, deux risques *tail* asymétriques. Le marché peut continuer à monter ou casser net sur un de ces deux fronts. **La breadth (RSP/SPY) sera le signal silencieux de cassure approchant** — quand elle commence à baisser pendant que SPY monte encore, c'est le moment d'écouter le biais #1 et de trim les leaders.
