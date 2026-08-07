# Audit cartes × recherche web — 2026-08-07

> Deep audit (matrice DB) × deep research (4 agents, ~60 recherches sourcées).
> Statuts invalidateurs : RAS / SIGNAL (fait s'en approche) / TOUCHÉ (condition remplie).
> Les diffs d'invalidateurs sont des PROPOSITIONS — le gérant valide, rien n'est écrit.

## Synthèse exécutive

| carte | état | le fait |
|---|---|---|
| **7011.T** | ⛔ **invalidateur TOUCHÉ** | TerraPower Natrium en construction (Bechtel, avr.) + X-energy a choisi IHI (MoU mars) = « ≥2 flagships advanced-reactor US sans MHI » rempli littéralement. MAIS GTCC +65 % YoY, guidance relevée : la jambe nucléaire meurt, la jambe turbines prospère. **Décision gérant requise : réviser la thèse (retirer l'optionalité nucléaire du sizing) ou sortir.** |
| **AVGO** | ⚠ date fausse + SIGNAL fort | Print **02/09** (confirmé IR), pas 03/09 (baseline S13 à corriger). Dual-sourcing TPU : MediaTek établi sur l'inference v8 (Tom's HW mai) + discussions Google-Marvell ≤30 j → S10 quasi-touché en lecture large, à re-préciser. |
| **2802.T** | ✅ print 06/08 = **issue A** | Matériaux **+54 % YoY** (attendu +30-40), OP segment ¥19,1 Md = 1er contributeur du groupe, guidance FY relevée ¥202 Md, capacité ABF +50 % d'ici 2030, absorption Fine-Techno annoncée. Aucun invalidateur ne coche. **P1 résoluble** (stops/cibles posés le 05/08 tiennent). |
| **GEV** | 🟠 SIGNAL wind | Pertes wind Q2 275 M$ (vs 165 a/a), run-rate vers le guide ~400 M$ ; commandes −40 %. Contre-point : tarifs re-guidés EN BAISSE (100-200 M$), revenue FY relevée. P/E fwd 47 vs seuil 35. |
| **SAF.PA** | 🟠 SIGNAL P&W | AOG ~720 (loin de <100) mais GTF Advantage certifié EASA + « comeback bid » Farnborough + objectif AOG single-digits fin 2026 → le compteur « P&W regagne 2 trim. » peut commencer à tourner. |
| **SPCX** | requalif post-IPO | Cotée depuis 12/06 (fusion xAI 02/02). Q2 04/08 : CA 7,8 Md$ +92 %, perte nette réduite (−541 M vs −4,3 Md Q1), MAIS capex AI 15,8 Md$/trim (~86 % du capex) non plafonné, titre −13,6 % le 05/08. Invalidateur « levée dilutive » obsolète (IPO = levée par définition) → à réécrire. |
| 15 autres | ✅ RAS | Baselines fraîches disponibles partout (voir fiches). |

## Dates d'earnings (bloc SQL fourni séparément)

Confirmées IR : AVGO 02/09 · BESI 22/10 · SAF.PA 23/10 (CA Q3) · SU.PA 29/10 (CA Q3) · CCJ 30/10 (page events IR).
En DB déjà : AMZN 29/10 (non conf.) · GOOGL 28/10 (non conf., TipRanks dit 27) · GEV 21/10 (non conf.) · MU 23/09 · TSM 15/10.
Estimées (historique, à confirmer quand annoncées) : ASML ~14/10 · KLAC ~28/10 · SNPS ~26/08 · 000660 ~28/10 · 2802.T ~05/11 · 4063.T ~23/10 · 6857.T ~28/10 · 7011.T ~05/11 · LNG ~05/11 · MP ~05/11 · HO.PA ~22/10 · SPCX ~03/11.

## Diffs d'invalidateurs proposés (à valider ligne par ligne)

### Corrections factuelles (écriture immédiate si accord)
- **AVGO S13** : « print 03/09 » → « print **02/09** » (source : PR Broadcom IR).
- **AMZN** : baseline marge AWS « Q1 2026 : 37,7 % » → « **Q2 2026 : 39,4 %** » (8-K 30/07). AWS +36,7 % YoY (plus forte croissance en 18 trim.), backlog 496 Md$.
- **000660** : baseline marges « 76 % » désormais = OPM record T2 (le seuil se mesure depuis un sommet — noter « baseline T2-2026 : OPM 76 %, GM 83 % »).
- **ASML** : T1 déjà daté (15/07, guidance relevée ×2). Rien à corriger, baseline vivante.

### Affûtages proposés (« intelligents » : mesurables, datés, non déjà-vrais)
- **AVGO S10** (dual-sourcing) : l'inference v8 est DÉJÀ splittée MediaTek (état de fait) → le trigger tel qu'écrit est mort-vivant. Proposé : « un second partner obtient du **training** TPU OU >30 % du volume TPU total (design win documenté) ». Sinon S10 se déclenche sur une lecture large alors que le moat (training) tient.
- **GOOGL KC5 (NOUVEAU — attrition)** : « départ effectif de Hassabis d'Alphabet OU ≥2 départs suppl. de leaders IA nommés (VP DeepMind / Fellow) sous 6 mois glissants → révision forcée ». Contexte : Discovery Loop (Dean, Ghemawat, Vinyals, Le) + recensés 06/08 : Shazeer (OpenAI), Jumper (Anthropic), Adler, Pritzel. Le compteur court depuis le 05/08.
- **ASML** : « export restrictions étendues aux matériaux » (flou) → « **MATCH Act promulgué** OU restriction DUV immersion effective (fenêtre 150 j d'alignement NL/JP : échéance sept.-oct. 2026) ». Devient un event daté surveillable.
- **SPCX** : « levée dilutive majeure » (obsolète post-IPO) → « émission secondaire >5 % du flottant OU capex AI non couvert par (cash + EBITDA connectivité) 2 trim. consécutifs ». L'invalidateur « pertes AI ni plafonnées ni séparées d'ici 12 mois » : le reporting Q2 sépare l'EBITDA connectivité mais AUCUN plafond capex → compteur à dater (départ 04/08/2026, échéance 04/08/2027).
- **MU** : ajouter la sentinelle S12 partagée déjà en veille ailleurs : « SK hynix démontre parité yield hybrid bonding vs MR-MUF en mass production » — TrendForce 29/04 : validation 12-high faite, yields en montée. SIGNAL précoce, pas touché.
- **BESI** : préciser l'invalidateur 3 : la 1re commande HB mass-production SK hynix est allée à AMAT+**Besi** (fait favorable) ; le trigger reste « TEL/ASMPT qualifié en mass production HB » — inchangé mais noter la baseline (Besi incumbent depuis 07/2026, clients HB 15→21).
- **7011.T** : si la thèse est révisée plutôt que sortie : remplacer l'invalidateur nucléaire mort par « GTCC : commandes grandes turbines <20 unités/an OU baisse séquentielle 2 trim. » (la jambe qui reste).

### Baselines fraîches à dater dans les thèses (sans changer les seuils)
- TSM : GM 67,7 % Q2 (guidance Q3 65-67, dilution N2 −1,7 pt intégrée) ; FY relevé « >+40 % ».
- KLAC : GM 62,4 % Q4 FY26 ; WFE 2026 ~150 Md$ ; Chine 24,3 % du CA (mars) — au-dessus du seuil 20 % de l'invalidateur 4 : à surveiller au prochain print.
- SNPS : Design IP −5,8 % YoY au 27/05 ; DEUX publications restantes avant l'échéance Q4 FY26 de l'invalidateur 2.
- 4063.T : cycle de HAUSSES prix wafers (+18-22 % AI/HPC, +5-8 % H2) — l'invalidateur LTA-en-baisse a sa contre-évidence datée (juin 2026).
- 6857.T : OPM 51,7 % T1 (baseline janv. remplacée) ; TAM memory testers relevé 2,5-3,0 Md$ ; Teradyne Magnum 7H = SIGNAL sur inv. 1.
- CCJ : coûts unitaires guide RELEVÉ au T2 (SIGNAL inv. 1, pas encore 2 trim. >10 %) ; spot 86,83 $ +25 % a/a.
- LNG : CCL Stage 3 >98 % complet (inv. 2 contre-évidence) ; storage UE 57,2 % au 02/08 = plus bas ≥2009 (inv. 4 à l'opposé).
- MP : NdPr 112-115 $/kg (>2× le seuil 50) ; floor DoD 110 $ actif ; Magnetics en revenue.
- HO.PA : commandes +21 % H1, guidance relevée ; budgets UE ~634 Md$ 2,53 % PIB.
- SU.PA : marge 19,3 % H1 vs seuil 19,1 % — l'invalidateur 2 se joue à 20 bps, print 29/10.
- SAF.PA : LEAP 1 030 H1 (+41 %) ; spares guide relevé ~+25 %.
- GOOGL : Cloud marge ~35-36 % Q2 (seuil 25) ; StatCounter 91,31 % juillet (relevé direct) ; appel antitrust plaidé fin 2026-début 2027.

## Écarts de récit corrigés (honnêteté du journal)
- La séquence Asie : le 5/08 Tokyo a RALLIÉ (Advantest +8,77 %) ; le sell-off était les **6-7/08** (Kospi −4,58 % puis hynix −4,82 % à 1 423 000 ₩). Le journal de bord du 5 au soir lisait la chute dans les prix intraday — la chronologie fine est celle-ci.
- SPCX « privée non cotée » : faux depuis le 12/06 — le système la priçait déjà, le narratif de session était en retard sur sa propre base.

## Doctrine — mutations de thèse (formalisée 07/08, dictée gérant ; à monter en LESSON à la prochaine clôture)

**Une thèse s'entretient, ne se réécrit pas : identité + historique conservés.** Taxonomie FERMÉE — six classes, cinq autorisées en UPDATE, la sixième nommée pour être interdite :

| classe | opération cognitive | exemple du jour | portée (affichée au PLAN) | processus |
|---|---|---|---|---|
| correction | rétablir un fait | AVGO print 03/09 → 02/09 | minimale | UPDATE |
| clarification | réduire l'ambiguïté (même falsifieur) | « export restrictions » → « MATCH Act promulgué » | sémantique | UPDATE |
| datation | ajouter une horloge | compteur pertes-AI, échéance 04/08/2027 | horloge | UPDATE |
| photographie remplacée | nouvelle photo datée (une photographie n'est jamais modifiée — le texte garde « remplace X ») | AWS Q2 39,4 % remplace Q1 37,7 % | photo | UPDATE |
| remplacement de trigger consommé | un invalidateur consommé ne doit plus exister | SPCX « levée dilutive » consommé par l'IPO | **maximale autorisée** | UPDATE |
| **REQUALIFICATION** | changer la raison de posséder | 7011.T : l'optionalité nucléaire meurt | — | **TRIBUNAL uniquement — interdite en UPDATE, le code la refuse** |

**PLAN-ID (traçabilité analyse → revue → écriture)** : le PLAN est le document auditable, l'APPLY une opération mécanique qui ne contient AUCUNE décision. L'identifiant (`PLAN-<date>-<hash8>`) est dérivé du hash de la **représentation auditée** — le texte que l'humain lit, pas la structure source : l'identité porte sur ce qui a effectivement été revu. Si le contenu change entre lecture et APPLY, le hash ne matche plus, rien ne s'écrit. La décision est prise au moment où le PLAN est validé ; le COMMIT n'est que sa matérialisation.

**Invariant d'orthogonalité** : chaque mutation porte exactement UNE classe — une opération cognitive a une seule nature. Un changement qui semble appartenir à deux classes doit être découpé en deux mutations successives (démonstration du jour : SPCX = un *remplacement* + une *datation*, deux mutations, pas une). C'est ce qui garde la taxonomie orthogonale et empêche les catégories de dériver.

**Pattern canonique** : `docs/templates/mutation_plan_pattern.md` — tout futur bloc d'écriture DB (thèses ou autre store) instancie ce protocole ; un outil qui ne PEUT PAS accomplir une action interdite est supérieur à un outil qui rappelle qu'elle l'est (la REQUALIFICATION n'existe pas dans l'outil).

**Règle des perceptions** : une perception manquante est une donnée manquante, pas un texte à compléter — les drafts sortent `[PERCEPTION GÉRANT REQUISE]`, jamais de la prose fabriquée.

Règles de sélection d'un invalidateur : **observable, daté, causal, robuste** — le raffinement excessif est l'overfitting du falsifieur (symétrique du L16 : à force de décrire le passé, le trigger ne se déclenchera jamais). Le tribunal ne répond pas « faut-il vendre ? » mais « la raison de posséder existe-t-elle encore ? » — invalidateur touché ≠ société mauvaise, et les confondre coûte dans les deux sens.

**Trois niveaux de changement, trois processus, trois niveaux de preuve** : TRIBUNAL change la thèse · UPDATE entretient la thèse · LESSON change la méthode. Tout traiter comme des « modifications » est la dérive lente qu'un registre décisionnel ne détecte jamais de l'intérieur.

**Pattern de bloc « mode audit »** (barrière humaine finale, atomicité intacte) : tout bloc d'écriture DB sort d'abord son PLAN (old → new → classe → raison) avec `APPLY=False` ; le gérant lit, passe `APPLY=True`, recolle. Une moitié de mise à jour est pire qu'aucune — même famille que fail-closed, gate digest, [CLOSE].

**Objectif des cartes, requalifié** : non pas « 22 cartes pleines » mais « 22 cartes dont chaque ligne est défendable devant le tribunal ». Une carte incomplète et honnête bat une carte complète et mauvaise — les drafts de variants hériteront de cette règle (trou déclaré plutôt que prose fabriquée).

*Sources : rapports agents 07/08 (~60 recherches, URLs dans les transcripts de session) — prints IR officiels cités en priorité.*
