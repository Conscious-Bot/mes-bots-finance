# PRESAGE — Décortiquage projet & dashboard (01/06/2026)

Analyse multi-angle post-livraison Stars + Polish, en utilisant les frameworks Emil Kowalski + taste-skill + Karpathy LLM Council.

## Partie 1 — Projet PRESAGE

### Mission & vision
**Quoi** : Outil rigoureux de gestion d'un book actions individuel + futur SaaS multi-tenant (vision actée 31/05). Track record performance = proof-of-value, pas newsletter narrative.

**Positionnement** : zone investisseur sérieux + auto-correction systématique (User Bias Detector mécanisé) + calibration probabiliste (Brier KPI #2). Anti-Robinhood-gamification : discipline > dopamine.

**Tension assumée** : aesthetic Robinhood/TR au service d'une mécanique anti-séduction. Interface séduisante pour rendre la discipline lisible.

### Stack
- Python 3.14, SQLite WAL, APScheduler
- Pas FastAPI/Postgres/Redis (local-only Mac)
- `dashboard/render.py` monolithique (~6300 lignes, HTML statique + live-reload)
- Bot Telegram pour alertes + chat copilot (Opus 4.7)
- 49 tickers actifs + universe étendu

### Forces architecturales
- Source unique de vérité (`shared.storage.DB_PATH`)
- Forward-only signal wiring SEC EDGAR + Gmail
- Track record cluster KPI #2 (Brier + Wilson IC95%)
- Bias detection mécanisé (lock_in + fomo_greed via kill_criteria/over_cap)
- Leçons L1-L11 codifiées (`docs/LESSONS.md`)

### Faiblesses identifiées
1. `render.py` monolithique → ingérable à 8000+ lignes
2. Macro composite V3 in-sample tuned, sans holdout dur
3. `over_cap` dark by decision tant que phase construction (oubli possible à 70k)
4. Tests fixtures ≠ schéma prod (L8 à fix racine)
5. Coverage critique mince (`materiality_boost` 17%, `asymmetry` 41%)
6. 4/7 logos asian placeholders (vs brand SVGs)

### Risques second-ordre
- Refactor différé → coût composé chaque feature future
- Star pattern non documenté → changement palette = 8 endroits à toucher
- Search modal recent localStorage sans versioning → ancien cache plante si shape change
- MCP ruflo lourd cold-start 5-10s

## Partie 2 — Dashboard

### Réussites (DNA acquis)
1. Stars pattern 8 pages (verdict 3 secondes)
2. Palette Trade Republic + Robinhood dose tempérée
3. Logos cascade 4 niveaux
4. Cmd+K + Cmd+1..9 (power-user Linear-grade)
5. Sparkline hero Catmull-Rom + area fill (Robinhood signature)
6. Right-click menu ticker (Bloomberg pattern)
7. Sticky page header + entry animations .26s ease-out

### Mérite encore travail (par priorité)
- P0 : macro composite V3 holdout OOS, logo PRESAGE sidebar
- P1 : refactor render.py modules, tests dashboard Playwright
- P2 : sparkline hover state crosshair, keyboard nav dans modal chips, mobile, a11y

### Verdict
Qualité fintech moderne dépassant 80% des outils investisseurs payants du marché en aesthetic, équivalent en data density. La discipline mécanisée distingue substantiellement.

### Direction recommandée
1. **Court terme cette semaine** : refactor render.py modules + backtest macro Voie B OOS
2. **Moyen terme 10/06 J-day** : observer activation scaffolds, 1er track record point, Publi #01
3. **Long terme 6 mois** : SaaS multi-tenant + presage.pro public landing — direction "cahier de bord instrument"

### Méta-edge
Le projet est lui-même un anti-biais : mécaniser la discipline (au lieu de juste y croire), codifier les leçons L1-L11 (au lieu de les oublier), valider OOS avant de wirer (au lieu de croire l'in-sample). C'est l'edge structurel — la plupart des projets fintech individuels meurent par excès de confiance en l'intuition.
