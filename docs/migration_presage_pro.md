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
