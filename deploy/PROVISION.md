# PROVISION — Presage sur VPS (Hetzner)

Runbook complet **mis a jour 05/06/2026 post-migration reelle**. Tous les gotchas
rencontres pendant la migration Mac->Hetzner sont catalogues ici pour qu'une
prochaine migration (autre VPS, refaire propre) ne retombe pas dans les memes
pieges. `serve` reste sur 127.0.0.1 -- jamais expose.

## 0. Box
- **Verifie le 05/06/2026** : Hetzner CX22 x86_64 + Ubuntu 26.04 LTS. yfinance
  passe depuis IP datacenter Helsinki (NVDA / 4063.T / 000660.KS reels).
- CAX11 (ARM, 3,79EUR/mo) untested ce jour : torch + sentence-transformers
  wheels aarch64 a verifier. CX22 (x86, 4,59EUR) est le default sain.
- Cle SSH a la creation. Firewall: port 22 (SSH) uniquement. Pas d'IPv6-only
  (verifie qu'IPv4 est present sinon friction Mac FAI possiblement IPv4-only).

## 0bis. User non-root (DOCTRINE : pas tourner en root)
    ssh root@<IP>
    useradd -m -s /bin/bash presage
    usermod -aG sudo presage
    echo 'presage ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/90-presage
    chmod 440 /etc/sudoers.d/90-presage
    # Copy ta pubkey Mac dans authorized_keys du user presage
    mkdir -p /home/presage/.ssh && chmod 700 /home/presage/.ssh
    cp ~/.ssh/authorized_keys /home/presage/.ssh/authorized_keys
    chown -R presage:presage /home/presage/.ssh && chmod 600 /home/presage/.ssh/authorized_keys
    # Test : ssh presage@<IP> doit passer + sudo -n whoami = root

## 1. Base (DEPS ELARGIES post-migration : tk-dev / xz-utils / wget manquaient)
    sudo apt update && sudo apt install -y \
      git build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev \
      libsqlite3-dev libffi-dev liblzma-dev curl tk-dev wget xz-utils sqlite3

## 2. Python 3.14.4 via pyenv (absent des depots Ubuntu)
    curl -fsSL https://pyenv.run | bash
    cat >> ~/.bashrc <<'EOF'
    export PYENV_ROOT="$HOME/.pyenv"
    [[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init - bash)"
    EOF
    exec $SHELL  # ou source ~/.bashrc
    pyenv install 3.14.4   # ~10-15min, compile from source

## 2.5. Swap + TMPDIR (sans ces 2, pip install torch echoue OOM ou disk quota)
    # 2G swap (sinon OOM possible pendant pip install torch ~700MB residente)
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    # TMPDIR persistent sur disque (Ubuntu Cloud /tmp = tmpfs 1.9G,
    # trop petit pour wheels lourdes torch / nvidia-cu*)
    mkdir -p ~/.cache/pip-tmp
    echo 'export TMPDIR=$HOME/.cache/pip-tmp' >> ~/.bashrc
    export TMPDIR=$HOME/.cache/pip-tmp

## 3. Clone (Deploy Key SSH read-only > PAT GitHub)
**Recommandation 05/06** : deploy key SSH dediee au repo, read-only. PAT donne
acces a TOUS tes repos -- principe least-privilege casse.

    # Sur la VM :
    ssh-keygen -t ed25519 -C "presage-deploy@hetzner" -f ~/.ssh/github_deploy -N ""
    cat ~/.ssh/github_deploy.pub
    # Paste pubkey dans github.com -> repo Settings -> Deploy keys -> Add
    # (laisser "Allow write access" DECOCHE)

    # Config SSH client pour utiliser cette cle sur github.com :
    cat >> ~/.ssh/config <<'EOF'
    Host github.com
        HostName github.com
        User git
        IdentityFile ~/.ssh/github_deploy
        IdentitiesOnly yes
    EOF
    chmod 600 ~/.ssh/config

    # Trust github host key :
    ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts

    # Clone via SSH URL (pas https sinon la deploy key n'est pas sollicitee)
    git clone git@github.com:Conscious-Bot/mes-bots-finance.git
    cd mes-bots-finance && pyenv local 3.14.4
    ~/.pyenv/versions/3.14.4/bin/python3 -m venv venv && source venv/bin/activate
    pip install -U pip
    pip install -r requirements.txt    # ~3-5min avec wheels prebuilt

## 4. *** TEST YFINANCE EN PREMIER — go/no-go de la migration ***
    python - <<'PY'
    from shared.prices import get_current_price_in_eur
    for t in ["NVDA", "4063.T", "000660.KS"]:
        print(t, get_current_price_in_eur(t))
    PY
    # Valeurs reelles -> continuer.
    # None / 429 / timeout -> Yahoo bloque l'IP datacenter. STOP.
    #   -> proxy residentiel, ou source de prix alternative, AVANT le reste.

## 5. Secrets (depuis le Mac)
Rotation OAuth Google : sur la console moderne Hetzner-style (>2024) le
bouton est **"+ Add secret"** (pas "Reset secret"). Ca cree un 2e secret
actif en parallele, zero downtime entre ancien et nouveau.
- Google Cloud Console -> Credentials -> click ton OAuth client -> "+ Add secret"
- Download JSON (nouveau secret embarque) -> overwrite credentials.json local
- Supprimer token.json local, relancer flow (clic Allow browser) -> token.json neuf
- Apres validation prod (cf section 8 verifs) : delete ancien secret pour
  serrer la surface
- Telegram / Anthropic / FMP / FRED / Healthchecks : non exposes, copier tels quels

Puis, depuis le Mac :
    scp .env credentials.json token.json presage@<IP>:~/mes-bots-finance/
    # Sur la VM :
    chmod 600 ~/mes-bots-finance/{.env,credentials.json,token.json}

## 6. DB (snapshot atomique depuis le Mac, bot vivant OK grace a WAL)
    # Snapshot initial (peut etre vieux de quelques heures, c'est OK pour bootstrap) :
    sqlite3 data/bot.db ".backup /tmp/bot.db.snap"
    scp /tmp/bot.db.snap presage@<IP>:~/mes-bots-finance/data/bot.db

    # Verifie cote VM :
    sqlite3 ~/mes-bots-finance/data/bot.db "PRAGMA integrity_check;"
    sqlite3 ~/mes-bots-finance/data/bot.db \
        "SELECT 'signals', COUNT(*) FROM signals
         UNION ALL SELECT 'positions', COUNT(*) FROM positions
         UNION ALL SELECT 'theses', COUNT(*) FROM theses
         UNION ALL SELECT 'predictions', COUNT(*) FROM predictions;"
    # Doit matcher la sortie Mac equivalente.

## 7. systemd user (rootless, demarre au boot via linger)
    mkdir -p ~/.config/systemd/user
    cp deploy/presage-bot.service deploy/presage-serve.service \
       deploy/presage-backup.service deploy/presage-backup.timer \
       ~/.config/systemd/user/
    sudo loginctl enable-linger presage   # CRUCIAL : sinon services killed au logout
    systemctl --user daemon-reload
    systemctl --user enable --now presage-serve
    # PAS encore presage-bot -- celui-la c'est au cutover (section 8)
    systemctl --user enable --now presage-backup.timer
    systemctl --user list-timers presage-backup --no-pager

## 8. CUTOVER — instance unique (sinon Conflict getUpdates Telegram)
**Le piege rencontre 05/06** : tu peux `pkill -fi "Python -m bot.main"` autant
de fois que tu veux sur le Mac, ca respawn instantanement parce que **launchd
le maintient en vie**. Verifie + unload le launchd AVANT :

    # Sur le Mac, DETECT puis UNLOAD le launchd qui respawn :
    launchctl list | grep presage
    # Si com.olivier.presage liste -> unload le plist :
    launchctl unload ~/Library/LaunchAgents/com.olivier.presage.plist
    # PUIS kill (cette fois ca tient) :
    pkill -fi "bot.main"
    sleep 3 && pgrep -fi "bot.main" || echo "Mac bot mort"
    # !!! Tennis-bot lance "python -m bot" SANS ".main" -- pattern distinct,
    # pas affecte par "bot.main". Verifie quand meme : pgrep -fl python | grep tennis

    # RE-SNAPSHOT DB juste avant pour catch les ~30min de writes :
    sqlite3 data/bot.db ".backup /tmp/bot.db.cutover.snap"
    scp /tmp/bot.db.cutover.snap presage@<IP>:~/mes-bots-finance/data/bot.db.new

    # Sur la VM : atomic swap + restart serve + start bot
    systemctl --user stop presage-serve
    cd ~/mes-bots-finance/data
    mv bot.db.new bot.db
    rm -f bot.db-wal bot.db-shm   # clean WAL sidecars orphans
    systemctl --user start presage-serve
    systemctl --user enable --now presage-bot
    journalctl --user -u presage-bot -n 30 --no-pager
    # Doit voir : "Scheduler started with N jobs" (verifier N attendu)
    # Possible 1x Conflict 409 dans la fenetre overlap (~30s), auto-resolu

## 9. Dashboard via tunnel SSH (jamais expose)
    # Depuis le Mac (port local 8000 occupe par serve.py local ? -> tunnel sur 8001) :
    lsof -nP -iTCP:8000 -sTCP:LISTEN  # si occupe par python -> renomme local :
    ssh -fN -L 8001:localhost:8000 presage@<IP>
    # Browser Mac -> http://localhost:8001/dashboard.html
    # (serve reste bind 127.0.0.1 sur la box ; rien n'ecoute en public)

    # Verifier que c'est BIEN la VM qui sert : kill le tunnel, refresh -> doit retourner
    # connection refused. Re-open tunnel -> 200 OK.

## 10. Backup offsite Storage Box (post-migration, hygiene)
**Doctrine 05/06** : ne JAMAIS rester local-only silencieusement sur serveur
distant. Le Mac dev a le droit (warn). VPS, non.

    # Sur la VM : cle ed25519 dediee au backup (jamais sur Mac)
    ssh-keygen -t ed25519 -C "presage-backup@hetzner" -f ~/.ssh/backup_storagebox -N ""
    cat ~/.ssh/backup_storagebox.pub
    # Provisionne Storage Box BX11 (1TB / 3,84EUR/mo) cote Hetzner console.
    # Activer SSH support + External reachability dans Settings de la box.
    # Note : les cles SSH des subaccounts Storage Box NE SE configurent PAS
    # via la UI, il faut SFTP avec password puis ecrire .ssh/authorized_keys.
    #
    # Cree un subaccount Storage Box dedie (least-privilege) :
    #   - base directory = `presage` (pas `.ssh` -- vrai isolement)
    #   - SSH support + External reachability cochés
    #   - Password genere random (utilise une seule fois pour bootstrap)
    # Puis depuis la VM :
    sshpass -p '<bootstrap-password>' sftp -P 23 u<id>-sub1@u<id>-sub1.your-storagebox.de <<EOF
    mkdir .ssh
    chmod 700 .ssh
    put /home/presage/.ssh/backup_storagebox.pub .ssh/authorized_keys
    chmod 600 .ssh/authorized_keys
    mkdir presage-backups
    EOF
    # Reset password apres bootstrap : la cle SSH suffit pour la suite.

    # Config env file :
    mkdir -p ~/.config/presage
    cat > ~/.config/presage/backup.env <<EOF
    BACKUP_REMOTE_HOST=u<id>-sub1@u<id>-sub1.your-storagebox.de
    BACKUP_REMOTE_PATH=presage-backups
    BACKUP_REMOTE_PORT=23
    BACKUP_SSH_KEY=/home/presage/.ssh/backup_storagebox
    EOF
    chmod 600 ~/.config/presage/backup.env

    # Test force-run :
    systemctl --user start presage-backup.service
    journalctl --user -u presage-backup -n 30 --no-pager
    # Doit voir : Push offsite: OK

## 11. Healthchecks.io (J-day dead-man's-switch, optionnel mais recommande)
    # Creer compte healthchecks.io (free tier OK)
    # Creer check : Schedule Mode = Cron, Cron Expression = `30 9 10 6 *`
    # (= 09:30 le 10 juin uniquement), Grace 4h, Timezone Europe/Paris
    # Copier la Ping URL puis :
    echo 'HEALTHCHECKS_J_DAY_URL=https://hc-ping.com/<uuid>' >> ~/mes-bots-finance/.env
    systemctl --user restart presage-bot

## Verifs finales
- `systemctl --user is-active presage-bot presage-serve presage-backup.timer` : 3x active
- `journalctl --user -u presage-bot -f` : heartbeat + crons tirent
- Telegram /brief repond (depuis ton phone)
- Mac bot bien mort (`pgrep -fi bot.main` vide cote Mac)
- Backup chain valide : `presage-backup.timer` show next_run + force-run OK
- `cat ~/.ssh/known_hosts` ne contient PAS d'IP/host bizarre
