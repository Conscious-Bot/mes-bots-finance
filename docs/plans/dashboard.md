# Dashboard — Spec (plan, pas encore buildé)

**Date**: 2026-05-26
**Status**: Spec figée. Build Tier A autorisé (time-boxé). Reste différé.
**Maquettes**: 4 vues validées (Comptes / Concentration / Asymétrie / nudge biais).
**Design tokens**: `docs/adrs/dashboard-design-system.md` fait autorité sur le visuel — cette spec ne le redéfinit pas, elle s'y soumet.

## Principe non-négociable : PAS de web app
Tout (donuts vivants, auto-refresh, colonnes triables, drill-down) s'obtient **sans serveur ni framework** :
- Cron `dashboard_render` lit SQLite via `shared/storage.py` (passerelle unique, CONVENTIONS §5) → calcule l'état → écrit **un seul HTML auto-contenu** (`data/dashboard.html`), data bakée inline.
- `<meta http-equiv="refresh">` recharge → tout redessiné sur data fraîche.
- JS vanilla embarqué : tri colonnes, drill-down, donuts SVG. Pas de fetch (data inline) → marche en `file://`.
- **Interdit** : FastAPI / Flask / Postgres / Redis / websocket. auto-refresh ≠ serveur.
- Variante (seulement si flicker du reload gêne) : `python -m http.server` (stdlib) + JS-poll d'un JSON. Process en plus → défaut = file://.

## Cadence
15min en séance / horaire hors séance (aligné cron prix). UN dump → toutes les vues depuis le **même** état → jamais de drift entre donuts.

## Architecture
- `intelligence/dashboard.py` : rendu pur (état → HTML).
- `crons/dashboard_render.sh` : wrapper cron.
- View-model calculé une fois, consommé par toutes les vues.

## Les 4 vues

### 1. Comptes (par courtier) — Image 2
MV, groupé par courtier, trié valeur desc. Donut secteur. Colonnes **Valeur / Poids / P&L cliquables** (tri client-side). Poids = % book total (MV).

### 2. Concentration (par secteur) — Image 3
**Cost-basis** (« Détenu »), hiérarchique cluster → sous-secteur → positions. Distinction **Détenu** vs **Prévu** (planifié non détenu, sans JOUR/P&L). Donut cluster + breach cap **35%** (ADR 010). Triable MAIS **hiérarchie préservée** : tri DANS les groupes + réordonne groupes ; **jamais aplatir**.

### 3. Asymétrie (Paliers + Risque) — Image 4 — LE cœur on-mission
- **Paliers vers la cible** : barre upside par position (ALAB 68% = 32% restant) = anti-biais #1 visible.
- **Risque · marge avant stop** : barre proximité-stop + jauge **Surchauffe**.
- Bidirectionnel : Paliers « laisse courir » / Risque « surveille le stop ».

### 4. Onglet thèse (par position)
Thèse + Paliers + **Sizing (déplacé ici)** + risque.

### Nudge biais (Image 1)
Copie : « Winner en profit, upside restant. Ton biais te pousse à sécuriser trop tôt — laisse courir vers ta cible. » SANS parenthèse PLTR/NVDA (oriente vers l'avant, pas la honte). Tier A = panneau read-only. Tier B (différé) = interruption active en flow de vente.

## IA dédupliquée — propriétaire canonique par donnée
Ailleurs = liens, pas copies.
| Donnée | Propriétaire unique |
|---|---|
| Sizing | Onglet thèse (sous Paliers) |
| Concentration / poids cluster | Page Concentration |
| Surchauffe | Panneau Risque |
| Holdings (valeur, courtier) | Page Comptes |
| Paliers + marge→stop | Panneau Asymétrie |

→ Bas page position : supprimer doublons → liens. Surchauffe : une seule occurrence (Risque).

## Tiers par disponibilité data
- **Tier A — build-now, read-only, SAFE observation** (data existe) : Comptes, Concentration, Asymétrie, nudge display-only, coût, signaux. **Time-boxé** — piège = trou-à-polish CSS, pas le code.
- **Tier B — behavior-affecting → différé post-J+28** : nudge actif en flow de vente.
- **Tier C — data-gated → post-27 mai / 10 juin** : calibration, bias-interruption à reçus, scorecard bot-vs-gut. Ajout = extension propre, pas churn.

## Verrous de correctness (non négociables)
1. **Cost-basis = axe unique de concentration**, labellé dans l'UI. NOTE : le code `/portfolio` calcule actuellement le cluster sur *market_value* → à réconcilier vers cost-basis au câblage `validate()` (à froid).
2. **Un seul dénominateur** du % concentration (held vs held+prévu), le **même** dashboard ET cap. Sinon divergence multi-chiffres (l'erreur de la session).
3. **Surchauffe = formule définie ou coupée.** Qu'est-ce qui bouge le « 3° » ? Sans formule = thermomètre-vibes = output non instrumenté = interdit par PHILOSOPHY. Jolie jauge vide = pire que pas de jauge (simule du signal).
4. **Tri hiérarchique** = dans-groupes + réordonne-groupes, jamais aplatir.

## Questions data ouvertes (au build)
- Où vivent les positions **Prévu** ? (theses status=watch ? table dédiée ?)
- Formule **Surchauffe** (verrou #3).
- Donut SVG hand-rolled vs micro-lib (rester self-contained, pas de CDN bloquant en file://).

## Ce que ça ne devient JAMAIS
Web app, real-time push, cloud. Le jour où « il faut un serveur » = signal de scope creep, pas un besoin.
