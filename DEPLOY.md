# Deploying the paper bot on a VM

Runs IB Gateway (via the gnzsnz/ib-gateway Docker image) plus live_ibkr.py on a small
Ubuntu VM, unattended, logging every signal/fill to trade_log.csv.

## 1. Gateway (Docker)
    sudo apt update && sudo apt install -y docker.io docker-compose-v2
    sudo usermod -aG docker $USER   # then log out/in
    mkdir -p ~/ibgw && cd ~/ibgw
    # put docker-compose.yml here, fill in the paper login
    docker compose up -d
    docker compose logs -f          # wait for the "Simulated Trading" login line

Port note: this image serves the paper API on container port 4004, mapped to host 4002,
which is what live_ibkr.py expects (127.0.0.1:4002). Restart daily is handled in-image.

## 2. Bot
    mkdir -p ~/bot && cd ~/bot
    python3 -m venv venv && source venv/bin/activate
    pip install ib_async pandas numpy
    # copy backtest_hull.py and live_ibkr.py here
    # quick connect test:
    python3 -c "from ib_async import IB; ib=IB(); ib.connect('127.0.0.1',4002,clientId=99,timeout=30); print('connected', ib.isConnected()); ib.disconnect()"
    # run in tmux so it survives SSH dropping:
    tmux new -s bot
    python3 live_ibkr.py            # MODE='shadow' first; flip to 'paper' after a few clean days
    # detach: Ctrl-b then d   |   reattach: tmux attach -t bot

## 3. Watch
    tail -f ~/bot/trade_log.csv     # one row per signal/entry/stop_move/exit

## Notes
- One bot only: clientId 1. Starting a second one gives Error 326 (id in use).
- Deep history seed (seed/<symbol>.csv) is OPTIONAL at MAXSPAN 1200 (~3 months suffices).
- trade_log.csv columns: ts_utc,event,symbol,mode,dir,qty,entry,stop,R_planned,fill,exit_px,R_realized,note
  -> this is the file to compare against the backtest at the go/no-go review.
