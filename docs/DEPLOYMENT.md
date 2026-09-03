# Cloud Deployment Guide — run the alerts 24/7

The system is fully containerized and self-healing, which makes it straightforward
to run on any always-on machine (a cheap cloud VPS, a home server, or a
Raspberry Pi) independent of your laptop. This guide covers deploying the Docker
Compose stack to a Linux cloud server.

> **Why bother?** On a laptop, alerts only fire while the machine is on and awake.
> If you shut down or sleep the laptop during NSE market hours (09:15–15:30 IST),
> you miss alerts. A small always-on server removes that risk.

---

## Table of contents

1. [What this stack is](#1-what-this-stack-is)
2. [Prerequisites](#2-prerequisites)
3. [Get the code on the server](#3-get-the-code-on-the-server)
4. [Create the production env file](#4-create-the-production-env-file)
5. [Build & start](#5-build--start)
6. [Verify it's running](#6-verify-its-running)
7. [Check health & logs](#7-check-health--logs)
8. [How to update](#8-how-to-update)
9. [Backup the database](#9-backup-the-database)
10. [Example: DigitalOcean droplet (fastest path)](#10-example-digitalocean-droplet-fastest-path)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. What this stack is

The repo ships a `docker-compose.yml` that runs **two** containers:

| Service | Container | Purpose |
|---|---|---|
| `nifty-alert` | `nifty-drawdown-alert` | Drawdown monitor (`src.main`) |
| `nifty-assistant` | `nifty-telegram-assistant` | Interactive Telegram bot |

Both are configured with `restart: unless-stopped`, named **volumes** for the DB
and logs, and Docker **healthchecks**. This means:

- If either process crashes, Docker restarts it automatically.
- On host reboot, Docker brings both back up automatically.
- State (SQLite DB, alert arm/disarm history) survives restarts and redeploys.

---

## 2. Prerequisites

On the server (Ubuntu/Debian example), install **Docker + Docker Compose plugin**:

```bash
# Install Docker Engine + Compose plugin
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"

# Log out and back in (so the docker group takes effect), then verify:
docker --version
docker compose version
```

You also need:

- The **`.env.prod`** values (same ones you use locally): Telegram bot token,
  chat IDs, thresholds, etc. — see [step 4](#4-create-the-production-env-file).

---

## 3. Get the code on the server

```bash
# Clone the public repo (no auth needed — it's public)
git clone https://github.com/Mohith-373/nifty-drawdown-alert.git
cd nifty-drawdown-alert
```

> Optional but recommended: check out a pinned release/tag instead of `main`
> so deploys are reproducible.

---

## 4. Create the production env file

`docker-compose.yml` reads a file named `.env.prod` for secrets. **This file is
gitignored — never commit it.** Create it on the server:

```bash
cp .env.example .env.prod
nano .env.prod        # fill in your real values
```

At minimum, set:

- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` (+ `TELEGRAM_CHAT_ID_2` if you use
  a second chat)
- `DRAWDOWN_THRESHOLDS`, `REARM_BUFFER_PCT`, `POLL_INTERVAL_SECONDS`, and the
  market-hours settings (same as local)

The compose file overrides `DATABASE_PATH`, `LOG_FILE`, and the assistant
heartbeat path with in-container `/app/...` locations, so you do **not** need to
change those in `.env.prod`.

> ⚠️ **Security:** `.env.prod` contains the real bot token. Keep it private on
> the server (this is why it's gitignored and never part of the image or repo).

---

## 5. Build & start

```bash
docker compose up -d --build
```

That's it. Docker builds the image and starts **both** containers detached.

---

## 6. Verify it's running

```bash
docker compose ps
```

You should see both services **`Up`** and **`(healthy)`**:

```
NAME                        COMMAND                  STATUS
nifty-drawdown-alert        "python -u -m src.ma…"   Up X minutes (healthy)
nifty-telegram-assistant    "python -u nifty_ai_te…" Up X minutes (healthy)
```

---

## 7. Check health & logs

```bash
# Drawdown monitor logs
docker logs -f nifty-drawdown-alert

# Assistant logs (note: logging goes here via -u unbuffered)
docker logs -f nifty-telegram-assistant

# Confirm live data is being recorded (SQLite inside the data volume)
docker exec nifty-drawdown-alert python -c \
  "import sqlite3;c=sqlite3.connect('/app/data/nifty_alerts.db');\
   print(c.execute('select price,drawdown_pct,price_timestamp from price_history \
   order by id desc limit 3').fetchall())"
```

If it's within market hours you should see recent price rows with a non-empty
drawdown.

---

## 8. How to update

```bash
git pull                      # fetch the latest code
docker compose up -d --build  # rebuild image + recreate changed containers
```

The named volumes persist the DB and logs across updates, so **no alerts are
lost and nothing is re-fired** after a deploy.

---

## 9. Backup the database

State lives in the `nifty_data` volume. To back it up:

```bash
# Copy the DB out of the running monitor container
docker cp nifty-drawdown-alert:/app/data/nifty_alerts.db \
  ./backup-$(date +%F).db
```

To restore, copy it back the same way. (Stop the monitor briefly if you want a
consistent snapshot.)

---

## 10. Example: DigitalOcean droplet (fastest path)

1. Create a **DigitalOcean droplet** (or any VPS): **Ubuntu 22.04/24.04 LTS**,
   **$6/mo (1 GB) or larger**, any region (Mumbai/`blr1` is close to IST).
2. Add your SSH key and create it.
3. SSH in and install Docker (steps in [§2](#2-prerequisites)).
4. Follow steps [3](#3-get-the-code-on-the-server) → [5](#5-build--start).

That's a ~10-minute setup and the alerts then run 24/7.

> Pick a provider/host you control so `restart: unless-stopped` + Docker
> auto-start give you full self-recovery after reboots.

---

## 11. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `CREDENTIAL error: exec: "docker-credential-desktop"` | Only affects Docker Desktop; not an issue on Linux. If it appears, unset `credsStore`: `unset DOCKER...` or edit `~/.docker/config.json`. |
| Containers `Exited` but not restarting | Check `docker inspect -f '{{.State.Error}}' <name>`. Ensure `restart: unless-stopped` is present and the failure is a crash, not a `docker kill`/`docker stop` (those are intentional and won't auto-restart). |
| No prices recorded during market hours | `.env.prod` network/API blocked, or yfinance momentarily down — check `docker logs nifty-drawdown-alert` for errors; the monitor skips and recovers automatically. |
| Assistant not answering | Verify `nifty-telegram-assistant` is `(healthy)` and polling in its logs; confirm `TELEGRAM_BOT_TOKEN` matches the token @BotFather gave you. |
| Firewall / outbound blocked | The monitor and assistant need outbound HTTPS to `api.telegram.org` and yfinance. Open no inbound ports unless you add a web UI. |

---

**Scope reminder:** this is a read-only monitoring and alerting system — it
never places trades or touches a broker/demat account.
