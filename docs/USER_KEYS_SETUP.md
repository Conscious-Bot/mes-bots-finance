# User keys setup — 23/06/2026

5 keys à signer pour activer composants livrés 14/06 dormants. ETA total ~15 min.

## Order (par valeur immédiate × effort)

### 1. EDGAR_IDENTITY (free, 30 sec) — REQUIS basics SEC

```bash
# Mac + VM
echo 'EDGAR_IDENTITY=Olivier Legendre ofmlegendre@gmail.com' >> .env
```

Pas de signup. SEC exige juste un User-Agent identifiable (nom + email) pour rate-limiting. Active : `shared/edgar_client.py` 10-Q value-add (déjà wired dans crons EDGAR).

---

### 2. FRED_API_KEY (déjà SET — vérifier validité)

```bash
grep FRED_API_KEY .env  # Mac : present depuis 12/06
```

Si rate-limited ou expired : nouvelle key gratuite sur https://fred.stlouisfed.org/docs/api/api_key.html (instant, no email verif).

---

### 3. VOYAGE_API_KEY (free 200M tokens, 2 min signup)

URL : https://www.voyageai.com/ → Sign up → Dashboard → API Keys → Create.

```bash
# Mac + VM
echo 'VOYAGE_API_KEY=pa-...' >> .env
```

Active : `shared/thesis_library.py` semantic search via voyage-finance-2 embeddings + Chroma local DB. Skill `/thesis-similar` opérationnel. Coût : 200M tokens free, suffisant 6+ mois usage perso.

---

### 4. HEALTHCHECKS keys (free 20 checks, 5 min)

URL : https://healthchecks.io → Sign up → Create Project "PRESAGE" → Note ping URLs.

Création de 9 checks dans le project :
- `j_day_batch_close` (date trigger)
- `daily_signals_check`, `daily_brier_compute`, `daily_over_cap_check`, `daily_stale_target_check`, `daily_invalidation_trigger_check`, `daily_kill_criteria_evaluation`, `daily_drift_detector`, `weekly_calibration_audit`

```bash
# Mac + VM
echo 'HEALTHCHECKS_PROJECT_URL=https://hc-ping.com/<PROJECT_UUID>' >> .env
echo 'HEALTHCHECKS_J_DAY_URL=https://hc-ping.com/<J_DAY_CHECK_UUID>' >> .env
```

Active : 9 crons preparés silent-noop fail-soft livrés 14/06. Telegram alerts quand un cron ne ping pas dans son schedule. Soft cure pour la classe de bug "cron fenêtre fixe + APScheduler default = pas robuste aux downtimes bot" (3 cures historiques mémorisées).

---

### 5. BIGDATA_API_KEY (paid PRO, optionnel si tu veux /research live)

URL : https://bigdata.com/ → Si pas déjà abonné, plan PRO requis pour API.

```bash
# Mac + VM
echo 'BIGDATA_API_KEY=...' >> .env
```

Active : `intelligence/research_brief.py` `/research <ticker>` handler avec backend réel. Sans : fallback stub (fail-closed L15, retourne template "data missing"). Coût : connecteur PRO déjà payé via claude.ai donc check si API key derive automatiquement.

---

## Restart Claude (OpenInsider MCP)

Après ajout des keys, **restart Claude Code session** :
- L'MCP server `openinsider` charge ses 16 outils SEC EDGAR / FINRA / OpenInsider / Yahoo au démarrage de session
- Sans restart, les `mcp__openinsider__*` tools restent inaccessibles dans la session courante

---

## Verification post-setup

```bash
cd ~/mes-bots-finance && source venv/bin/activate
python3 -c "
import os
for k in ['VOYAGE_API_KEY', 'HEALTHCHECKS_PROJECT_URL', 'BIGDATA_API_KEY', 'EDGAR_IDENTITY', 'FRED_API_KEY']:
    v = os.environ.get(k)
    print(f'{k}: {\"SET\" if v else \"MISSING\"} ({len(v) if v else 0} chars)')
"
```

VM sync : ajouter mêmes keys côté Hetzner via `ssh presage@37.27.247.126`.

---

## Status après setup

- thesis_library opérationnel (Chroma local DB indexée)
- 9 healthchecks alertes activées
- research_brief mode "real" (Bigdata backend)
- MCP openinsider tools accessibles
- EDGAR 10-Q value-add wire complet
