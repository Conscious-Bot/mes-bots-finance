# SPEC — `/research <ticker_ou_theme>` Handler (research_brief)

**Statut** : Spec proposée, exécution en session dédiée future
**Date spec** : 13 juin 2026
**Mode** : feature build, hors barrière #150
**Estimation effort** : 1h-1h30 session fraîche

---

## 1. Mission

Fournir à Olivier la **matière factuelle structurée** pour calibrer ses intuitions de paris, sans franchir la barrière #150 (jugement / décision auto interdit tant que la couche de redevabilité n'a pas tranché si la calibration humaine ajoute de la valeur).

> *"Le bot me donne data/chiffres/articles qui valident OU infirment mes intuitions."*

C'est la **posture analyste** explicitement autorisée par la mémoire `feedback_no_probability_anchoring` :

> *"Les DRIVERS et le claim_text peuvent être formulés avec Claude (matière factuelle = analyste), mais la PROB/décision est exclusivement Olivier."*

Pattern validé en pratique : ce que Claude a fait pendant la calibration des 10 sentinelles session 13/06 (Bigdata search → matière structurée → Olivier pose). On packageise comme handler bot pour le rendre disponible hors session conversationnelle.

---

## 2. Frontière (CRITIQUE — ne pas franchir)

| ✅ AUTORISÉ | ❌ INTERDIT (viole barrière #150) |
|---|---|
| Fournir faits chiffrés (revenue, marges, multiples, guidance) | Calculer un "score" ou "probability" interne |
| Citer consensus analyste (target_mean, recommendation) tel quel | Suggérer "achète" / "vends" |
| Surface news récents (3-5 articles datés, sources attribuées) | Comparer "X mieux que Y" ou ranking |
| Cadre causal (forces pro / forces contre conceptuelles) | Découverte autonome ("voici 5 stocks intéressants cette semaine") |
| Pointer divergence prix vs consensus (chiffres bruts) | Conclure "undervalued" / "overvalued" comme verdict |

**Test de frontière** : si une réponse du bot contient les mots "achète", "vends", "recommandation", "il faut", "tu devrais", "probable que" suivis d'une direction, **c'est un fail** — le brief a franchi en zone décision.

Implémentation de la frontière : test unitaire `test_research_brief_no_verdict.py` qui parse les réponses générées et asserte l'absence de ces patterns (regex).

---

## 3. Architecture

```
Telegram
  /research <ticker_ou_theme>
       │
       ▼
bot/handlers/research.py::cmd_research
  - parse args
  - rate-limit check (1/heure/user)
  - call intelligence.research_brief.fetch(target)
       │
       ▼
intelligence/research_brief.py::fetch(target: str) -> str
  - resolve target (ticker via find_securities OR theme as-is)
  - 3 queries Bigdata.com en parallèle (smart mode) :
    Q1 : "{target} financials récents revenue marges guidance" 
    Q2 : "{target} analyst consensus price target recommendation last 30 days"
    Q3 : "{target} news significant developments last 14 days"
  - format markdown structuré (cf §4)
  - return string ready for Telegram
       │
       ▼
notify.send_text (parse_mode=Markdown, split if >4096 chars)
```

**Dépendances existantes réutilisées** :
- `shared/notify.py` send_text (split chunks, parse_mode)
- `mcp__claude_ai_Bigdata_com__bigdata_search` ou wrapper si disponible côté bot
- `shared/storage.py` pour rate-limit tracking (table `research_brief_log` minimal)

---

## 4. Format de réponse (markdown Telegram)

```
🔍 RESEARCH BRIEF — {target}
asof : {timestamp UTC}

═══ FAITS CHIFFRÉS ═══
{2-4 chiffres clés sourcés : revenue last quarter, gross margin, 
 guidance forward, multiples si applicable. Chaque chiffre avec source + date.}

═══ CONSENSUS ANALYSTE ═══
{si applicable : target_mean / target_median / N analysts /
 recommendation_key / divergence vs spot price actuel. Pas de jugement.}

═══ NEWS RÉCENTS (14 derniers jours) ═══
{3-5 bullet items, chacun :
 • [Date] Titre court — Source (lien)
 Pas de commentaire éditorial.}

═══ CADRE CAUSAL ═══
{Liste 2-3 forces pro + 2-3 forces contre, en termes mécaniques :
 • Pro : "X% des revenue dépendent de Y, Y a doublé YoY"
 • Contre : "Lead times Z stretching à 5 ans → cycle peak proche ?"
 ZÉRO conclusion. Question posée, pas répondue.}

─────
Sources : Bigdata.com — https://bigdata.com
Pas de jugement. Toi de calibrer.
```

**Variant brief** (si target = thème non-ticker comme *"data center power grid"*) :
- Section "FAITS CHIFFRÉS" devient "MARKET CONTEXT" (TAM, growth rate, key players)
- Section "CONSENSUS" omise (n/a)
- Le reste identique

---

## 5. Garde-fous (non-négociables)

### 5.1 Rate-limit
- Max **1 brief / heure / user**.
- Tracker via table `research_brief_log` (timestamp, target, user_id, cost_estimate).
- Si exceeded : retour Telegram *"Rate-limit : 1 brief/h. Prochain dispo dans X min."*
- ABORT propre, pas de message vide.

### 5.2 Budget LLM cap
- Budget hard par brief : **N tokens max** (à calibrer post smoke, target ~$0.10/brief).
- Si query Bigdata retourne >max chunks, tronquer.
- Logger le cost réel dans `research_brief_log.cost_actual_usd`.
- Si cumulé > $X/jour : hard stop avec notif Telegram à Olivier.

### 5.3 Fail-closed (doctrine L15)
- Si Bigdata API down : retour *"Sources indisponibles maintenant, retry dans X min."* — pas de brief fabriqué sans sources.
- Si LLM down : idem.
- Si target non-résolvable (find_securities échec) : retour *"Cible non reconnue. Format : ticker (AAPL) ou thème (data center power grid)."*

### 5.4 Anti-anchoring (doctrine `feedback_no_probability_anchoring`)
- Le format response NE CONTIENT JAMAIS de chiffre de "probability" produit par le bot.
- Le format response NE CONTIENT JAMAIS de directive ("achète", "vends", "tu devrais").
- Test mécanisé : `test_research_brief_no_verdict.py` regex check sur output (interdit `acheter|vendre|recommandé|tu devrais|il faut acheter|probable que [le titre]`).

---

## 6. Tests requis

1. **`test_research_brief_smoke`** : mock Bigdata, vérifier format markdown structuré, sections présentes.
2. **`test_research_brief_rate_limit`** : 2 appels rapprochés → 2e retourne rate-limit message.
3. **`test_research_brief_no_verdict`** : regex check anti-anchoring (cf §5.4).
4. **`test_research_brief_fail_closed_no_sources`** : mock Bigdata empty → retour propre, pas de brief fabriqué.
5. **`test_research_brief_budget_cap`** : mock cost-tracker > budget → ABORT clair.

---

## 7. Cas d'usage validés (à smoke après build)

| Cas | Input | Sortie attendue |
|---|---|---|
| Ticker équity US | `/research MGM` | Faits MGM + consensus + news + cadre Osaka/Dubai mentionnés |
| Ticker équity foreign | `/research 000660.KS` | Faits Hynix + consensus + news + HBM/AI mentionnés |
| Thème macro | `/research data center power grid` | Market context + key players + news + drivers |
| Cible inconnue | `/research XYZQAAA` | Fail-closed message clair |
| Spam | `/research` puis `/research` 30s plus tard | Rate-limit message |

---

## 8. Effort estimation détaillée

| Tâche | Temps |
|---|---|
| Module `intelligence/research_brief.py` (~150 lignes) | 30 min |
| Handler `bot/handlers/research.py` (~50 lignes) | 15 min |
| Table `research_brief_log` migration + helpers storage | 15 min |
| 5 tests dédiés | 20 min |
| Smoke 5 cas d'usage + validation budget | 15 min |
| **Total** | **1h35 session fraîche** |

---

## 9. Effets de bord positifs (bonus)

- **Pre-pose fact-check sentinelles** (doctrine amendée `feedback_no_probability_anchoring` §amendement 13/06) : `/research <ticker>` peut servir de fact-check pré-pose obligatoire. Si l'événement de la sentinelle apparaît dans le brief comme "déjà arrivé publiquement" → opérateur ne pose pas (cf S6 Doosan, S10 Google TPU).
- **Mémoire `research_brief_log`** = corpus utile pour Unit C narrative_drift quand barrière #150 lèvera (training data sur ta prose calibrée).
- **Pas de feature parallèle** : ce handler ne crée pas de table predictions ni de bias_events. Aucun side-effect sur le ledger Brier.

---

## 10. Non-goals (anti-scope-creep)

- Pas de découverte autonome ("voici les 5 stocks de la semaine") → barrière #150
- Pas de "watch alerts" ("ping moi quand MGM publie ses earnings") → c'est un autre handler
- Pas de "compare A vs B" → ranking implicite = jugement
- Pas de génération d'image / chart → markdown texte seulement
- Pas de cache du brief (chaque /research = appel frais Bigdata, sinon stale)

---

## 11. Ouverture future (post-barrière #150)

Si dans 18 mois la nulle paresseuse a parlé et a montré un edge mesurable, ce handler peut évoluer :
- Ajouter un section "📊 BRIER CALIBRATION REMINDER" qui montre ton track record sur des claims similaires (depuis le ledger predictions).
- Permettre `/research_compare <ticker_A> <ticker_B>` qui montre les deux sans ranking.

Mais ces évolutions sont **explicitement gated** par la levée de la barrière #150. Aucune anticipation dans l'implémentation initiale.
