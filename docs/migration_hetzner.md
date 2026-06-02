# Migration Mac -> Hetzner — runbook PRESAGE bot

> Status : plan execute pas a pas. Profil cible : CX22 Ubuntu 24.04 LTS,
> dashboard via SSH tunnel (pas TLS public), dry-run 24h avec 2e Telegram
> bot avant cutover. Decision actee 02/06/2026.
>
> Discipline : chaque phase a un gate "verification" ; on n'avance pas si
> rouge. Variables remplies au fil (`$VPS_IP`, etc).

---

## Phase 0 — Pre-flight (cote toi, web Hetzner)

1. Compte Hetzner Cloud cree (https://console.hetzner.cloud).
2. Project `presage` cree.
3. SSH key uploade depuis Mac :
   ```bash
   cat ~/.ssh/id_ed25519.pub   # si pas existe : ssh-keygen -t ed25519
   ```
   Colle le contenu dans Hetzner > Security > SSH Keys.
4. Creer Server :
   - Location : **Nuremberg (eu-central)** ou Falkenstein
   - Image : **Ubuntu 24.04**
   - Type : **CX22** (4.50€/mo)
   - Networking : IPv4 + IPv6
   - SSH Key : selectionne celle du step 3
   - Name : `presage-bot`
5. Note l'IPv4 publique. Exporte dans ton shell Mac :
   ```bash
   export VPS_IP=XX.XX.XX.XX
   ```

**Gate** : `ssh root@$VPS_IP "echo OK"` doit retourner `OK` sans mot de passe.

---

## Phase 1 — Harden VPS (15 min)

SSH en root, on cree un user unprivilegie + firewall stricte.

```bash
ssh root@$VPS_IP << 'EOF'
set -e

# Update + base tools
apt-get update && apt-get -y upgrade
apt-get -y install ufw fail2ban git curl ca-certificates software-properties-common build-essential

# Firewall : SSH seul, tout le reste ferme
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw --force enable

# fail2ban basique
systemctl enable --now fail2ban

# User non-root
useradd -m -s /bin/bash presage
mkdir -p /home/presage/.ssh
cp /root/.ssh/authorized_keys /home/presage/.ssh/
chown -R presage:presage /home/presage/.ssh
chmod 700 /home/presage/.ssh
chmod 600 /home/presage/.ssh/authorized_keys

# Disable root SSH (apres avoir verifie qu'on peut se log en presage)
EOF
```

Test login en `presage` :
```bash
ssh presage@$VPS_IP "whoami"   # doit retourner: presage
```

Si OK, retire root SSH :
```bash
ssh root@$VPS_IP "sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config && systemctl restart sshd"
```

**Gate** : `ssh root@$VPS_IP "echo x"` doit echouer maintenant.

---

## Phase 2 — Python 3.14 + deps systeme (10 min)

Python 3.14 n'est pas dans Ubuntu 24.04 par defaut. On utilise deadsnakes PPA.

```bash
ssh presage@$VPS_IP << 'EOF'
set -e
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt-get update
sudo apt-get -y install python3.14 python3.14-venv python3.14-dev
python3.14 --version  # doit afficher Python 3.14.x
EOF
```

**Gate** : `python3.14 --version` retourne `Python 3.14.x`.

---

## Phase 3 — Code + venv + secrets (15 min)

### 3.1 Clone repo (en presage)

```bash
ssh presage@$VPS_IP << 'EOF'
set -e
cd ~
git clone https://github.com/Conscious-Bot/mes-bots-finance.git
cd mes-bots-finance
python3.14 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt -r requirements-dev.txt
./venv/bin/python -m pytest tests/test_render_smoke.py -q  # sanity
EOF
```

**Gate** : smoke test passe.

### 3.2 Secrets (.env)

**Pour le dry-run**, on utilise un 2e Telegram bot pour eviter le conflit
mono-token avec le Mac. Steps :

1. Sur Telegram, talk to `@BotFather` -> `/newbot` -> name `presage-test`,
   username `presage_test_NNNN_bot`. Note le token.
2. `/start` au nouveau bot pour obtenir ton chat_id (ou utilise le meme).

Copie `.env` Mac -> VPS, en remplacant `TELEGRAM_BOT_TOKEN` par le test :

```bash
# Sur le Mac (extraire valeurs)
grep -v '^#' /Users/olivierlegendre/mes-bots-finance/.env | grep '=' > /tmp/env.template

# Edite /tmp/env.template a la main :
#   - garde TOUS les keys (ANTHROPIC_API_KEY, FRED_API_KEY, FMP_API_KEY, etc.)
#   - REMPLACE TELEGRAM_BOT_TOKEN par le nouveau bot test
#   - ENV=test (au lieu de prod)
#   - PAPER_ONLY=1 (zero ecriture broker)

# Upload via scp
scp /tmp/env.template presage@$VPS_IP:~/mes-bots-finance/.env

# Permissions stricts cote VPS
ssh presage@$VPS_IP "chmod 600 ~/mes-bots-finance/.env"

# Nettoie le template local
shred -u /tmp/env.template
```

**Gate** : `ssh presage@$VPS_IP "ls -la ~/mes-bots-finance/.env"` montre
`-rw------- 1 presage presage`.

---

## Phase 4 — Data : copy bot.db (snapshot dry-run) (10 min)

On copie une SNAPSHOT de bot.db sur le VPS. Le Mac continue d'ecrire dans
son bot.db pendant ces 24h. Au cutover on refera un snapshot final.

```bash
# Cote Mac : snapshot consistent (sqlite hot copy)
cd /Users/olivierlegendre/mes-bots-finance
./venv/bin/python -c "
import sqlite3, shutil
src = sqlite3.connect('data/bot.db')
src.execute('PRAGMA wal_checkpoint(TRUNCATE)')
src.close()
shutil.copy2('data/bot.db', '/tmp/bot.db.dryrun')
print('snapshot OK, size:', shutil.os.path.getsize('/tmp/bot.db.dryrun'))
"

# Push vers VPS
scp /tmp/bot.db.dryrun presage@$VPS_IP:~/mes-bots-finance/data/bot.db
ssh presage@$VPS_IP "ls -la ~/mes-bots-finance/data/bot.db"

# State files
scp data/bot_state.json presage@$VPS_IP:~/mes-bots-finance/data/

# Nettoie tmp
rm /tmp/bot.db.dryrun
```

**Gate** : `ssh presage@$VPS_IP "./venv/bin/python -c 'from shared.storage import db; print(db().__enter__().execute(\"SELECT COUNT(*) FROM predictions\").fetchone())'"` retourne le meme count que sur Mac.

---

## Phase 5 — Systemd services (15 min)

Deux services : `presage-bot` (bot.main, daemon principal) et
`presage-dashboard` (dashboard.serve, HTTP local 127.0.0.1:8000).

```bash
ssh presage@$VPS_IP << 'EOF'
set -e

# Service bot.main
sudo tee /etc/systemd/system/presage-bot.service > /dev/null << 'UNIT'
[Unit]
Description=PRESAGE bot main (Telegram + APScheduler)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=presage
Group=presage
WorkingDirectory=/home/presage/mes-bots-finance
EnvironmentFile=/home/presage/mes-bots-finance/.env
ExecStart=/home/presage/mes-bots-finance/venv/bin/python -m bot.main
Restart=on-failure
RestartSec=10
StandardOutput=append:/home/presage/mes-bots-finance/bot.log
StandardError=append:/home/presage/mes-bots-finance/bot.log

[Install]
WantedBy=multi-user.target
UNIT

# Service dashboard.serve
sudo tee /etc/systemd/system/presage-dashboard.service > /dev/null << 'UNIT'
[Unit]
Description=PRESAGE dashboard live server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=presage
Group=presage
WorkingDirectory=/home/presage/mes-bots-finance
EnvironmentFile=/home/presage/mes-bots-finance/.env
ExecStart=/home/presage/mes-bots-finance/venv/bin/python -m dashboard.serve
Restart=on-failure
RestartSec=5
StandardOutput=append:/home/presage/mes-bots-finance/dashboard/serve.log
StandardError=append:/home/presage/mes-bots-finance/dashboard/serve.log

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable presage-bot presage-dashboard
sudo systemctl start presage-bot presage-dashboard
sleep 5
sudo systemctl status presage-bot --no-pager | head -15
sudo systemctl status presage-dashboard --no-pager | head -15
EOF
```

**Gate** : les 2 services sont `active (running)`.

---

## Phase 6 — Smoke + dry-run 24h

### 6.1 Smoke immediat (5 min)

Dashboard via SSH tunnel :
```bash
# Depuis Mac, ouvre un terminal et garde-le ouvert
ssh -L 8000:127.0.0.1:8000 presage@$VPS_IP

# Dans un autre terminal Mac, ou navigateur :
open http://127.0.0.1:8000/dashboard.html
```

Test Telegram :
- DM au bot test : `/status` -> doit repondre
- Verifie qu'il n'y a PAS de message `Conflict 409` dans `~/mes-bots-finance/bot.log`
  (signe d'instance multiple) :
  ```bash
  ssh presage@$VPS_IP "grep -i conflict ~/mes-bots-finance/bot.log | tail -5"
  ```

### 6.2 24h observation

A surveiller via :
```bash
ssh presage@$VPS_IP "tail -f ~/mes-bots-finance/bot.log"
ssh presage@$VPS_IP "tail -f ~/mes-bots-finance/dashboard/serve.log"
```

Verifie :
- [ ] Cron tier1 (4h UTC) a tourne, debt_signals nouvelles rows
- [ ] yfinance prix fetches OK (pas de ban)
- [ ] Gmail ingest OK (si actif) -- attention OAuth peut demander refresh
- [ ] Anthropic API calls OK (verifie credit balance)
- [ ] Memory usage stable (< 1GB) : `ssh presage@$VPS_IP "free -h"`

**Gate avant cutover** : 24h sans crash, sans Conflict 409, dashboard rend OK.

---

## Phase 7 — Cutover (30 min, downtime ~10 min)

Quand dry-run validee :

```bash
# 1. STOP Mac bot
launchctl unload ~/Library/LaunchAgents/com.olivier.presagebot.plist 2>/dev/null || true
# OU si tournant en caffeinate manuel :
pkill -f "caffeinate.*bot.main" || true
pkill -f "python.*bot.main" || true
pkill -f "python.*dashboard.serve" || true

# Verifie qu'aucun process bot tourne sur Mac
ps aux | grep -E "bot\.main|dashboard\.serve" | grep -v grep
# (doit etre vide. ATTENTION : ne PAS toucher bot.py = tennis-bot !)

# 2. STOP VPS bot temporairement
ssh presage@$VPS_IP "sudo systemctl stop presage-bot presage-dashboard"

# 3. Snapshot DB final Mac
cd /Users/olivierlegendre/mes-bots-finance
./venv/bin/python -c "
import sqlite3, shutil
src = sqlite3.connect('data/bot.db')
src.execute('PRAGMA wal_checkpoint(TRUNCATE)')
src.close()
shutil.copy2('data/bot.db', '/tmp/bot.db.cutover')
"

# 4. Push DB finale + bot_state.json
scp /tmp/bot.db.cutover presage@$VPS_IP:~/mes-bots-finance/data/bot.db
scp data/bot_state.json presage@$VPS_IP:~/mes-bots-finance/data/

# 5. Swap Telegram token : test -> prod
ssh presage@$VPS_IP "sed -i 's/^TELEGRAM_BOT_TOKEN=.*/TELEGRAM_BOT_TOKEN=<TOKEN_PROD>/' ~/mes-bots-finance/.env"
ssh presage@$VPS_IP "sed -i 's/^ENV=.*/ENV=prod/' ~/mes-bots-finance/.env"

# 6. Restart VPS bot
ssh presage@$VPS_IP "sudo systemctl start presage-bot presage-dashboard"

# 7. Verifie
ssh presage@$VPS_IP "sleep 5 && sudo systemctl status presage-bot --no-pager | head -10"

# 8. Cleanup tmp
shred -u /tmp/bot.db.cutover
```

**Gate final** : Telegram `/status` au PROD bot repond depuis le VPS.

---

## Post-migration

- **Backup DB** : cron quotidien rsync vers Hetzner Storage Box (3€/mo,
  1TB) ou autre. Skeleton :
  ```bash
  ssh presage@$VPS_IP "echo '0 3 * * * /home/presage/mes-bots-finance/scripts/backup_db.sh' | crontab -"
  ```
- **Mac** : peut etre eteint. Tennis-bot continue separe (com.olivier.tennisbot
  launchd, autre repo). Touche a rien la-dessus.
- **Monitoring** : ajoute un healthcheck (cron simple qui pingue le VPS toutes
  les 5 min via `ssh presage@$VPS_IP "systemctl is-active presage-bot"`) ou
  Uptime Kuma cote Mac.
- **Updates** : `git pull` + `systemctl restart presage-bot` quand tu push.
  Eventuellement un webhook GitHub plus tard.

---

## Rollback (si catastrophe)

DB Mac n'a pas ete touchee, juste copiee. En cas de probleme post-cutover :

```bash
# Re-start Mac bot
cd /Users/olivierlegendre/mes-bots-finance
caffeinate -dimsu ./venv/bin/python -m bot.main &

# Stop VPS
ssh presage@$VPS_IP "sudo systemctl stop presage-bot presage-dashboard"

# Mac reprend avec son etat pre-cutover (predictions, bias_events, etc).
# Quelques signaux entre cutover et rollback peuvent etre perdus -- en general
# acceptable.
```

Backup Mac DB : `/tmp/bot.db.cutover` (snapshot final) + `data/bot.db.backup_*`
sont les filets de securite.
