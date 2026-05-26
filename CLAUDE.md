# CLAUDE.md — Contexte de collaboration (mes-bots-finance / HEIMDALL)

> À ajouter aux fichiers du projet pour injection dans chaque conv. Bootstrap d'une conv fraîche au niveau opérationnel courant. Évergreen — l'état roulant est dans `SESSION_STATE.md` (tail).

## 1. Comment on travaille (le plus important — n'existe nulle part ailleurs)

- **Canal** : Claude n'exécute PAS la machine. Claude écrit des blocs terminal/heredoc → Olivier les colle dans zsh macOS → recolle output/screenshots. Le container de Claude ≠ le repo. `dashboard/render.py` (~1860 l) vit sur le Mac ; Claude le lit via `grep/sed/awk` collés, jamais de mémoire.
- **Discipline non négociable** : (1) verify-before-patch — `grep/awk/sqlite` la vraie source/données AVANT tout patch, jamais deviner ; (2) safe-fail — tout patch Python fait `assert s.count(old)==1` avant `replace` (pas d'écriture si mismatch) ; (3) gates chaînées `&&` (`ruff` + `import` + serve reload) après chaque patch ; (4) commits en unités cohérentes + tag de clôture.
- **Leçons canal-paste (heredoc/zsh)** : blocs multi-lignes en chaîne raw `r"""…"""` (raw → gère le `\` de `/!\`), le paste arrive en bytes bruts (wrap cosmétique) ; édits courts = une ligne physique avec `\n` échappés OU regex tolérant-whitespace `re.escape(start)+r'.*?'+re.escape(end)` ; matcher seulement le texte HTML interne (entre `>` et `<`, sans quotes) ; zsh `--include="*.py"` TOUJOURS quoté ; pas de tags parasites dans les blocs bash.
- **Feedback** : `serve.py` sert en live + auto-reload ≤60s → patch visible vite, pas de regen manuel.
- **Préfs Olivier (partout)** : vérité > déférence, ZÉRO flagornerie (red-team Claude inclus), premier-principes + structure causale, second-ordre + tail risks, taste/minimal-moving-parts, appeler la médiocrité (même celle de Claude). Français, droit au but, jargon pro. Défaut aux points d'arrêt = clôture complète la plus propre, PAS de matrices γ/δ/ε.

## 2. Le dashboard (carte mentale)

- `render.py` génère `dashboard/dashboard.html` (`OUTPUT`) et retourne le Path. `serve.py` (stdlib, PAS FastAPI) sert sur `http://127.0.0.1:8000/dashboard.html`, hot-reload sur mtime, regen `HEIMDALL_REFRESH` (60s). **http, jamais `file://`** (l'auto-reload n'existe qu'en http). Lancer : `python3 -m dashboard.serve`. Santé : `tail dashboard/serve.log` (`regen Xs`, pas `FAILED`).
- **Prix** : source unique `_cached_price_eur`, throttle anti-ban yfinance via `_PX_TTL=1800` (30 min), cache `_PX_CACHE` chaud entre regens. Le knob = `_PX_TTL`, pas l'intervalle de regen.
- **Panneaux** : Vue d'ensemble (distline OKLCH) · Positions (donut secteurs SVG interactif) · Risque (jauge surchauffe fine) · Thèses (sizing cible-taille col3 + message dessous, barre prix hero pleine largeur).
- **Conventions visuelles** : OKLCH, thin, no glow ; symboles € $ ¥ ₩ ; `get_short_name` ; JS injecté par constantes (`_SORT_JS` / `_CSORT_JS` / `_DONUT_JS` / `_THEME_INIT`).
- **Sizing** : modèle conviction-normalisée `cible_i = cap(conv_i)/Σ(caps tenus)×100` ; lit `line_cap_by_conviction` → à réconcilier vs ADR 009. Règle : `alléger`/`renforcer` = rightsize, jamais exit.

## 3. Le modèle (pointeurs, pas de duplication)

Mission/stack → `FICHE_TECHNIQUE`. Code/data → `CONVENTIONS`. Boucle + High Standard → `PHILOSOPHY`. État roulant → `SESSION_STATE` (tail). Backlog/KPIs/ADRs → `TODO`. Urgences → `PROCEDURE_URGENCE`.

À retenir sans chercher : 2 biais mécanisés (#1 vend winners trop tôt ; #2 ne vend pas crypto aux tops) · conviction c1–c5 + caps · horloge track-record (la vraie substance, pas la polish) : 27 mai 1res résolutions, 10 juin/J+28 batch KPI #2 + ADR-008, mi-juin pruning + orphelins c1 · stack contraint (Py3.14 / SQLite WAL / APScheduler ; pas FastAPI/Postgres/Redis ; local Mac ; cascade Haiku/Sonnet/Opus).
