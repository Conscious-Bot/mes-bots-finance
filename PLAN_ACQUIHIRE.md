# PLAN ACQUIHIRE — 6 MOIS

**Date** : 30 mai 2026
**Horizon** : fin novembre 2026 (6 mois)
**Owner** : Olivier Legendre
**Projet** : mes-bots-finance / PRESAGE

---

## L'objectif, énoncé honnêtement

Être **acquihire-READY et VISIBLE** d'ici fin novembre 2026 — **pas « acquis »**.

L'acquisition est la décision d'un tiers. Le succès à 6 mois = des conversations qui démarrent (inbound, intros, entretiens), parce que le bon profil a vu le système et reconnu le jugement.

**Ce qui est vendu** : le jugement. Pas le bot. Le bot est la preuve.

**Le goulot réel** : pas la qualité du système — le fait que personne ne le voit. Levier n°1 des 6 mois = rendre le raisonnement public et vérifiable.

---

## La règle — où parfait, où shippé

**Parfait = non-négociable** (load-bearing pour la crédibilité)

- **Intégrité du track record** : prediction → résolution → score sans bug. Une erreur ici = fatal.
- **Justesse des chiffres** : EUR-canonical, FX, bug devise. Faux chiffres publics = fatal.
- **Sécurité des secrets** : clés, tokens, données courtier. Jamais dans git, jamais exposés.

**Shippé > parfait** (assez bon + visible gagne)

- **UI / esthétique** : signal de goût, puis ship. Pas SaaS-grade.
- **Features** : gel + élagage. Less surface > more.
- **Write-ups** : B+ publié bat A+ jamais publié.
- **Code** : lisible + testé, pas immaculé.
- **Seamless** : pas la cible. Bords rugueux pardonnés ; pensée boueuse non.

> Si on polit un truc de la colonne « shippé », on se sabote.

---

## Les 4 red-team adressés (avant de figer le plan)

1. **Contingence Brier-mauvais** : le batch 10/06 produira **~13 outcomes brier-scored sur 40** (67% neutral observé sur 6 résolus) dans **1 seul bucket de probabilité [0.608-0.658]**. Reliability diagram non-publiable scientifiquement. **Pivot** : Phase B publie le RAISONNEMENT (decision logs, post-mortems, biais détectés), pas un graphe Brier. Track record = liste d'outcomes vérifiables, pas calibration plot.

2. **Mono-cible Anthropic = pari étroit**. Anthropic acquihire peu. PRESAGE matche aussi quant funds (Two Sigma, Renaissance, Quantum Black), fintech AI (Stripe-like), agents companies (Sierra, Adept). Pitch lisible par 3-4 archétypes, coût marginal ≈ 0.

3. **Stock de drafts sans deadline = procrastination structurelle**. Engagement : **1er post publié fin juillet, date dure** dans le calendrier comme 10/06.

4. **« Repo lisible en 20 min » est non-mesuré**. 50+ fichiers Python, 407 tests, ADRs dispersés = plus 1h aujourd'hui. **Réaliste** : 1h. Cible juillet : README architecture + ADR index + parcours guidé (3 fichiers à lire dans cet ordre).

---

## PHASE A — Fondations + amorçage (juin–juillet)

**Thème** : fondation digne de confiance. Commencer à écrire. Pas de polish public encore.

### Juin (4 semaines)
- **Semaine 1** : Uptime durci. caffeinate confirmé, daily check log, bot tourne 7j/7.
- **Semaine 1-2** : Audit pré-10/06 résolution loop **fait** (30/05). Verdict ci-dessus.
- **10 juin** : **Batch résolution KPI #2** (~40 predictions). Premier vrai point de données. **Événement load-bearing**.
- **Semaines 2-3** : Si Brier insuffisant (cf red-team #1), pivot raisonnement-first sans drame. Si OK, capture des findings.
- **Semaines 3-4** : Book canonique M1 finalisé (Brief 10 points déjà 90% fait). Time-box dur.
- **Tout juin** : Gel features. Élagage. Hygiène secrets re-confirmée.

### Juillet (4 semaines)
- **Semaine 1-2** : Commencer 3 brouillons (decision logs : LNG vs Cameco, MU bug owné, pourquoi pas de price stops).
- **Semaine 3** : README architecture + ADR index. Cible parcours 1h.
- **Semaine 4** : **1er post publié fin juillet, date dure**. Brouillon-OK. Force la friction.

**Vérité fin juillet** : repo lisible 1h + book canonique fini + premier post live + 2-3 drafts en pipeline + uptime prouvé sur 60j.

---

## PHASE B — Surface publique (août–septembre)

**Thème** : devenir visible. Shipper la surface.

### Août
- **Cadence publication** : 1 post toutes les 2 semaines minimum. 2 en août.
- **Track record public** : page dédiée, prédictions + outcomes listables. Pas de graphe Brier mono-bucket. Format : "N prédictions résolues, M correct, P incorrect, S neutral, voici les décisions ownées".
- **Repo public** ou partageable : README + ADR index + 3 modules clés (book canonique, position invariants, self_loop V0).

### Septembre
- **2 posts** (rythme bimensuel maintenu).
- **2e batch résolution** (mi-septembre, ~3 mois post-mai). Plus de matière, peut-être 2 buckets de proba si la generation a diversifié entre-temps.
- **Esthétique site public** : tokens parchemin (cf mémoire `presage_brand`), Geist, signal-subtil DNA. Pas de polish au-delà du goût.

**Vérité fin septembre** : quelqu'un qui raisonne publiquement avec rigueur + track record vérifiable (jeune) + ingénierie inspectable.

---

## PHASE C — Distribution + conversations (octobre–novembre)

**Thème** : devant les bonnes personnes, déclencher des conversations.

### Octobre
- **3 posts** (cadence soutenue).
- **Distribution active** : partage dans HN, Twitter/X tech, communautés finance + AI, Lobsters.
- **Track record ≈ 4 mois** post-10/06 : présenté honnêtement, "jeune mais rigoureux".

### Novembre
- **3 posts**.
- **Outreach ciblé** : 4 archétypes (cf red-team #2). Cold + warm. Pitch cristallisé.
- **Pitch type** : *« Système de décision auto-correcteur qui mécanise la calibration et attrape mes propres biais. Track record vérifiable, raisonnement public. »*

**Vérité fin novembre** : visible, crédible, on-thesis, **conversations qui démarrent**.

---

## Les 4 indicateurs de succès (acquihire-READY)

À cocher fin novembre :

- [ ] Track record public et vérifiable, LIVE (pas calibration plot — liste d'outcomes ownés)
- [ ] 8-12 write-ups publiés (cadence régulière)
- [ ] Repo lisible par un tiers en ~1h (README + ADR index + parcours guidé)
- [ ] N conversations / inbound / intros démarrées (N à définir, suggestion : 5+)

Si ces quatre cases sont cochées : **acquihire-READY**. Le « oui » suit son propre calendrier.

---

## Garde-fous (relire chaque mois)

- **Ne rushe pas, ne maquille pas le track record**. Court + honnête bat trafiqué.
- **L'honnêteté, y compris sur les ratés, EST l'actif**. Pas un risque à gérer.
- **Less surface > more**. Chaque feature ajoutée avec du désordre dessert.
- **Règle parfait/shippé** : si on polit un « shippé », on se sabote.
- **Calendrier dur** : 10/06, 1er post fin juillet, batchs résolution mensuels.

---

## Check-in mensuel (template court)

Date : ___ / mois : ___

- État des 4 indicateurs (cocher progression)
- Qu'est-ce qui dérive vs plan ?
- Décisions prises (pivots, abandons, ajouts)
- Posts publiés ce mois : N
- Outcomes résolus ce mois : N (correct/incorrect/neutral)
- Une chose à corriger le mois suivant

---

## Liens internes

- Tactique court-terme : `TODO.md`
- État système courant : `SESSION_STATE.md`
- Convention code/data : `CONVENTIONS.md`
- Mission/stack : `FICHE_TECHNIQUE.md`
- Boucle + standard : `PHILOSOPHY.md`
- Marque publique : mémoire `presage_brand`
