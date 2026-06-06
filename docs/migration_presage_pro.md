# Migration `presage.pro` — préparation gel + checklist

> Préparé 01/06/2026 (matin J+1 post-marathon 31/05). Domaine `presage.pro` acheté. Ce doc verrouille l'état "ready-to-migrate" et liste les décisions + étapes le jour J.

## Fork architectural — 2 surfaces distinctes

| Surface | État actuel | Cible | Note |
|---|---|---|---|
| **Bot perso** Telegram + dashboard | Mac launchd PID 6437 + caffeinate sidecar + serve.py local | **RESTE local Mac** | Pas de besoin cloud. Latence Telegram + .env secrets locaux + DB privée. |
| **Site public `presage.pro`** | inexistant | Hébergement public | Brand + posts + futur SaaS multi-tenant. |

**Le bot ne migre PAS dans la phase 1.** Ce qui migre = la face publique séparément.

## État verrouillé (frozen snapshot pré-migration)

### Code & infrastructure
- HEAD : commit `a66603d` (Geist self-host) — pushé sur `origin/main`
- Migrations alembic : **0023 (head)** — bias_events v1 mécanique en place
- Bot launchd : `com.olivier.presage.plist` actif, auto-restart sur crash
- Dashboard local : `http://127.0.0.1:8000/dashboard.html` via stdlib serve.py + live-reload 1s
- Geist self-hosted : `dashboard/static/fonts/` (~128KB, 8 woff2, 0 CDN)

### Invariants verrouillés par tests (55/55 verts au gel)
- `tests/test_kpi2_invariants.py` (5) : KPI #2 exclut neutrals + v0
- `tests/test_build_profond_scaffolds.py` (9) : scaffolds no-op N<seuil
- `tests/test_prediction_audit_log.py` (4) : PIT append-only trigger
- `tests/test_bias_events_skeleton.py` (6) : CHECK constraints enums + skeleton no-op
- `tests/test_prices_fx.py` (24) : FX live + fallback hardcoded + freshness
- `tests/test_invariants_metier.py` (7) : positions + theses + brier coherence

### Backup DB
- `data/bot.db.backup_pre_migration_20260531_221614` (10.5 MB)
- Checksum SHA-256 : `efece8e325415b2df61f647153b479262a8ec65d2bcb496833dad1eedf8dcba6`

### Audit migration-safety
- Hardcoded `/Users/olivierlegendre/` dans code Python : **0 occurrence** ✅ portable
- Hardcoded `127.0.0.1` : seulement `dashboard/serve.py:164` (local dev OK, pas en prod publique)
- `.env` dans `.gitignore` : ✅ confirmé pas tracked, pas dans index, pas sur origin
- Secrets potentiels : `.env` local seulement, jamais commité

## Assets prêts pour le site public

| Asset | Path | Réutilisable directement |
|---|---|---|
| Brand identity | memory `presage_brand` (palette parchemin + Geist + manifeste "La vérité dans le bruit") | ✅ |
| Post #01 publié | `posts/post_01_calibration_unanchored.md` + tag `publish-post-01-20260531` | ✅ |
| Posts #02-04 draftés | `posts/post_02/03/04.md` | ✅ queue éditoriale |
| DESIGN_SYSTEM canonique | `docs/DESIGN_SYSTEM.md` (§1-15) | ✅ tokens hérités |
| tokens.css source unique | `dashboard/tokens.css` | ✅ |
| Geist woff2 self-host | `dashboard/static/fonts/` | ✅ |

## Décisions à acter avant migration (futur-toi-frais)

1. **Hébergement** :
   - VPS Hetzner (mentionné session 28/05) → contrôle complet, ~5€/mois CX22
   - Vercel/Netlify → static seulement, gratuit MVP
   - Cloudflare Pages → static + Workers si besoin edge
   - **Reco MVP** : Cloudflare Pages (DNS proxy gratuit + SSL auto + zero ops)
2. **Stack site public** :
   - **Option A — Static Astro/Hugo** : posts en MD → build → upload. 1-2j MVP.
   - **Option B — Custom HTML** : reuse `dashboard/render.py` patterns + tokens. Plus long mais brand cohérent.
   - **Reco MVP** : A (Astro = MD-first + tokens.css import natif)
3. **DNS + SSL** : Cloudflare proxy (orange cloud) — gratuit + DDoS protection
4. **DB cible future SaaS** : SQLite reste local. Si SaaS multi-tenant arrive → PostgreSQL séparé (pas pollue le bot perso).
5. **Auth pour futur `app.presage.pro`** : différé. Phase 1 = static landing + posts seulement.

## Checklist jour J (quand hosting prêt)

### Phase 0 — préparation (TODO maintenant)
- [x] Backup DB timestamped
- [x] Lock invariants (55 tests verts)
- [x] Push origin (commits + tag)
- [x] Doc migration (ce fichier)

### Phase 1 — site statique MVP
- [ ] Acheter DNS `presage.pro` chez registrar (FAIT par user)
- [ ] Setup hébergement (Cloudflare Pages ou choix final)
- [ ] Créer repo `presage-pro-site` séparé OU folder `site/` dans monorepo
- [ ] Setup Astro skeleton + import tokens.css + Geist fonts
- [ ] Migrer posts/*.md → site/content/posts/
- [ ] Landing page : manifeste "La vérité dans le bruit" + 4 piliers + diagramme L'ESSENCE
- [ ] DNS Cloudflare proxy actif + SSL Let's Encrypt
- [ ] Test public access : curl https://presage.pro

### Phase 2 — pas avant Pile 2.1 v2 + 10/06
- [ ] Sous-domaine `app.presage.pro` (futur dashboard SaaS multi-tenant)
- [ ] Auth (Clerk / Supabase / custom)
- [ ] DB Postgres multi-tenant
- [ ] Subscription Stripe

## Rollback en cas de problème

Si la migration phase 1 échoue ou casse quelque chose :
1. DNS revert (Cloudflare admin) — propagation ~5 min
2. Bot perso continue à tourner local (jamais touché)
3. Local dashboard continue à servir (jamais touché)
4. Backup DB intact (3 backups timestamped dans `data/`)
5. `git reset --hard a66603d` si commits foireux

## Ce qui ne migre PAS jamais

- `.env` (secrets, recreate sur target si besoin)
- `data/bot.db` (DB perso, jamais publique)
- `data/bot.db.backup_*` (backups perso)
- `bot.log` (logs locaux)
- `dashboard/dashboard.html` (généré local par serve.py)
- `dashboard/serve.log` (logs serve local)
- `friction.md` (privé, journal interne)
- `SESSION_STATE.md` (privé, contexte LLM)
- `TODO.md` (privé, backlog)
- `posts/post_02/03/04.md` AVANT publication (drafts)

---

# Annexe — Phase 2 détaillée : SaaS multi-tenant subscription (01/06 soir)

Le doc ci-dessus couvre phase 1 (landing publique). Cette annexe détaille la phase 2 : `app.presage.pro` = SaaS multi-tenant avec subscription paid.

## Décisions architecture phase 2 (à valider)

### Stack frontend
**Recommandé : Next.js 15 App Router + React Server Components**
- SEO landing public (Vercel edge)
- RSC pour dashboard auth
- Components Stars actuels (Python) → portés React preserve `.page-star` CSS
- `tokens.css` → `app/globals.css` import (source unique palette)
- Alternative : SvelteKit (plus léger mais écosystème SaaS plus pauvre)

### Backend / API
**Recommandé : Next.js API routes + Supabase (Postgres managé + Auth + Realtime)**
- API routes pour CRUD positions, queries
- Postgres exige (vs SQLite actuelle) : concurrence + Row Level Security per tenant
- Supabase = Postgres + auth (magic link + Google OAuth) + RLS tout-en-un
- Alternative : Neon Postgres + Clerk auth (séparation, plus de polish UX mais 2 services)

### Multi-tenancy
**Recommandé : Shared DB + RLS strict**
- 1 schéma Postgres, toutes tables ont `user_id uuid`
- Supabase RLS policies = isolation per-row + audit trail natif
- Migrations alembic actuelles → Supabase migrations (script de portage)
- Alternative DB per tenant = overkill complexité

### Payment
**Recommandé : Stripe Subscription mode**
- Free trial 14 jours sans CC
- Stripe Customer Portal pour upgrade/cancel
- Webhook Stripe → DB `user.subscription_tier`

### Hosting
- Vercel (frontend + API routes, edge network, free tier large)
- Supabase (DB + auth, free tier 500MB DB / 2GB bandwidth)
- Coût démarrage 0€/mois, scale linéaire utilisateurs payants

### Workers / Cron (intelligence non-JS)
- Bot Python local NE migre PAS (cf phase 1)
- Pour SaaS users : cron daily portfolio_snapshot + macro composite refresh via :
  - **Option A** : Supabase Edge Functions (Deno, simple)
  - **Option B** : Vercel Cron + API routes (limites timeout)
  - **Option C** : Hetzner/Railway worker Python séparé (si garde intelligence Python)

## Pricing tiers (proposition)

| Tier | Prix | Limites | Cible |
|------|------|---------|-------|
| **Free** (trial 14j) | 0€ | 1 portfolio · 5 thèses · 3 LLM/mois · pas macro | Essai |
| **Standard** | **29€/mois** | Portfolios illimités · thèses illimitées · 50 LLM/mois · macro + bias + track record · export PDF | Retail investor sérieux |
| **Pro** | **79€/mois** | Multi-portfolios équipe · 200 LLM · API access · priority support · webhooks | Family office / advisors |
| **Enterprise** | sur devis | White-label · DB dédiée RLS isolated · SLA 99.9% · integrations custom | RIAs / hedge funds boutique |

**Coût marginal** infrastructure ~5-10€/user/mois (DB + LLM API). Marge brute Standard ~65%.

## Modules à porter (mapping Python → SaaS)

### Frontend Next.js
| Local | Cible | Effort |
|-------|-------|--------|
| `dashboard/render.py` 8 Stars | Composants React `<StarUrgence/>` etc. | 2 semaines |
| `tokens.css` palette | `app/globals.css` import | 1h |
| `_APP_JS` modals + keyboard | Hooks React + Radix UI (Dialog/DropdownMenu) | 3 jours |
| `_CTA_JS` search Cmd+K | `cmdk` lib (Linear/Vercel standard) | 1 jour |
| Sparkline SVG inline | recharts / uPlot React / keep inline | 2 jours |
| Right-click ctx menu | Radix UI ContextMenu | 1 jour |
| Sticky header + animations | Tailwind utilities + framer-motion (subtle) | 2 jours |

### Backend (Next.js API + Supabase)
| Module Python | Équivalent SaaS | Effort |
|---------------|-----------------|--------|
| `shared/storage.py` (3462l) | Tables Postgres + Supabase client | 2 semaines |
| `intelligence/portfolio_grade.py` | API route TypeScript | 1 semaine |
| `intelligence/debt_monitor.py` macro | Cron Edge Function quotidien | 1 semaine |
| `intelligence/bias_events.py` | API route + RLS policies | 1 semaine |
| Signal ingestion EDGAR/Gmail | Cron Edge Function ou worker Python séparé | 1 semaine |

## Roadmap 3 mois (juin 2026 → août 2026)

### Mois 1 — Foundation
**S1-2 setup** :
- [ ] Vercel project `presage-app` + GitHub repo séparé
- [ ] Supabase project + auth (email magic + Google OAuth)
- [ ] DNS `app.presage.pro` → Vercel
- [ ] Tokens.css portage + Geist fonts hosted
- [ ] Stripe account + products configurés (Standard 29€, Pro 79€)

**S3-4 Landing + Auth** :
- [ ] Landing presage.pro (déjà fait phase 1 — landing statique)
- [ ] app.presage.pro signup → portfolio setup
- [ ] Magic link + Google OAuth flow
- [ ] Dashboard route protégé avec RLS basic
- [ ] Stripe Checkout integration

### Mois 2 — Dashboard MVP
**S5-6 Stars portés** :
- [ ] `<StarUrgence/>` `<StarConcentration/>` `<StarSignaux/>` etc.
- [ ] Tables Postgres : `portfolios`, `positions`, `theses`, `portfolio_snapshots`
- [ ] API routes CRUD positions
- [ ] Sparkline component (inline SVG portage)

**S7-8 Import + Pricing** :
- [ ] Import CSV broker (Trade Republic, Degiro, IBKR formats Europe)
- [ ] Plaid integration optionnel (US brokers)
- [ ] Stripe webhook → tier update DB
- [ ] Free trial 14j flow
- [ ] Customer Portal gérer subscription

### Mois 3 — Intelligence + Launch
**S9-10 Intelligence** :
- [ ] Track record cluster KPI #2 portage (table predictions)
- [ ] Bias detection lock_in + fomo_greed
- [ ] Macro composite V3 (après OOS validation TODO #67)
- [ ] LLM analyses (Anthropic API server-side)

**S11-12 Launch** :
- [ ] Print stylesheet portage
- [ ] Emails transactionnels (welcome, subscription)
- [ ] Analytics (Plausible ou Posthog)
- [ ] Soft launch via Twitter/X + ProductHunt
- [ ] Docs publics `/docs`

## Risques migration (phase 2)

1. **Refactor coût** : 2 mois full-time minimum. Si side-project 4-6 mois.
2. **Stack divergent** : Python local intelligence vs Next.js web → maintenir 2 codebases en parallèle. Risque : drift entre logique Python (bot perso) et logique JS (SaaS).
3. **Track record import** : data PRESAGE actuelle (43k€) doit migrer pour preserve "Day 0" honnête.
4. **Plaid coût** : 0.30$/connected/mois → érode marge Standard.
5. **LLM API costs** : 50 analyses × Claude Opus 4.7 ~0.10€ = 5€/user/mois fixe.
6. **Compliance** : pas custody (juste analyse), donc pas KYC/AML. GDPR oui (DSR/portability/erase).

## Décisions AVANT démarrage phase 2

1. **Stack frontend final** : Next.js confirmé OU SvelteKit ?
2. **DB managée** : Supabase OU Neon+Clerk ?
3. **Python intelligence** : tout porté JS OU conservé via worker séparé (2 codebases) ?
4. **Pricing final** : tiers + prix confirmés ?
5. **Launch strategy** : soft réseau perso OU aggressive PH + cold outreach ?
6. **Co-fondateur tech** : solo OU dev partenaire pour accélérer ?

**Revenue model 6 mois conservateur** :
- 50 trial → 20 Standard (40% conversion) = 580€/mois
- + 5 Pro = 395€/mois
- Total = **975€/mois recurring**
- Infra ~150€/mois
- **Marge nette : ~825€/mois à mois 6**

## TODO maintenant pour mettre en route phase 2

- [ ] Décider stack frontend (Next.js recommandé)
- [ ] Décider DB managée (Supabase recommandé)
- [ ] Setup Vercel + Supabase + Stripe accounts (1h)
- [ ] Créer repo `presage-app` (séparé du bot perso `mes-bots-finance`)
- [ ] Portage tokens.css + Geist en premier (1h)
- [ ] Stars Component (1 d'abord, Urgence le plus impactant) en proof-of-concept

