# PROVISION — Heimdall sur VPS (Hetzner)

Boucle autonome decouplee du laptop. `serve` reste sur 127.0.0.1 — jamais expose.

## 0. Box
- Hetzner CAX11 (ARM, 3,79EUR/mo) ou CX22 (x86, 4,59EUR) si friction ARM sur torch.
- Ubuntu 24.04. Cle SSH a la creation. Firewall: port 22 (SSH) uniquement.
- ARM: torch/sentence-transformers ont des wheels aarch64 — verifier a l'install ; sinon -> CX22.

## 1. Base
    sudo apt update && sudo apt install -y git build-essential libssl-dev zlib1g-dev \
      libbz2-dev libreadline-dev libsqlite3-dev libffi-dev liblzma-dev curl

## 2. Python 3.14.4 (pyenv — absent des depots Ubuntu)
    curl https://pyenv.run | bash
    # ajouter les 3 lignes pyenv au ~/.bashrc puis: exec $SHELL
    pyenv install 3.14.4

## 3. Clone (repo prive -> PAT GitHub)
    git clone https://github.com/Conscious-Bot/mes-bots-finance.git
    cd mes-bots-finance && pyenv local 3.14.4
    python -m venv venv && source venv/bin/activate
    pip install -U pip && pip install -r requirements.txt

## 4. *** TEST YFINANCE EN PREMIER — go/no-go de la migration ***
    python - <<'PY'
    from shared.prices import get_current_price_in_eur
    for t in ["NVDA", "4063.T", "000660.KS"]:
        print(t, get_current_price_in_eur(t))
    PY
    # Valeurs reelles -> continuer.
    # None/429/timeout -> Yahoo bloque l'IP datacenter. STOP.
    #   -> proxy residentiel, ou source de prix alternative, AVANT d'aller plus loin.

## 5. Secrets (depuis le Mac)
Rotation OAuth d'abord (seul secret expose dans le Projet):
- Google Cloud Console -> Credentials -> reset client secret -> nouveau credentials.json
- Mac: supprimer token.json, relancer l'auth (flow navigateur localhost) -> token.json neuf
- Telegram/Anthropic/FMP/FRED: non exposes, copier tels quels.
Puis, depuis le Mac:
    scp .env credentials.json token.json heimdall@<IP>:~/mes-bots-finance/

## 6. DB (snapshot coherent depuis le Mac, bot vivant OK grace a WAL)
    sqlite3 data/bot.db ".backup /tmp/bot.db.snap"
    scp /tmp/bot.db.snap heimdall@<IP>:~/mes-bots-finance/data/bot.db

## 7. systemd user (rootless, demarre au boot sans login)
    mkdir -p ~/.config/systemd/user
    cp deploy/heimdall-bot.service deploy/heimdall-serve.service ~/.config/systemd/user/
    loginctl enable-linger heimdall
    systemctl --user daemon-reload
    systemctl --user enable --now heimdall-serve

## 8. CUTOVER — instance unique (sinon Conflict getUpdates)
    # Mac: tuer le bot local AVANT (NB: binaire "Python" majuscule -> -i obligatoire)
    pkill -fi "Python -m bot.main"
    # Box:
    systemctl --user enable --now heimdall-bot
    journalctl --user -u heimdall-bot -n 30 --no-pager

## 9. Dashboard via tunnel SSH (jamais expose)
    # depuis le Mac:
    ssh -L 8000:localhost:8000 heimdall@<IP>
    # navigateur Mac -> http://localhost:8000/dashboard.html
    # serve reste bind 127.0.0.1 sur la box ; rien n'ecoute en public.

## Verifs
- journalctl --user -u heimdall-bot -f   (heartbeat, crons)
- Telegram /brief repond
- Mac bot bien mort (zero double instance)
