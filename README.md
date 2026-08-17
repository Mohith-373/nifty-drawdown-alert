# NIFTY 50 Drawdown Alert System

Monitors the NIFTY 50 index during Indian market hours and sends alerts whenever
the index falls 10%, 15%, 20%, ... (configurable, 5-point increments) below its
rolling 52-week high. **Monitoring only — this system never places trades or
touches a demat/broker account.**

See [`docs/DESIGN.md`](docs/DESIGN.md) for the architecture rationale (data
source, 52-week-high logic, alert-state persistence, dedup/re-arm behavior).

## Architecture

```
Market Data Provider (yfinance, pluggable)
        │
        ▼
NIFTY 50 Price Service      (validates: not stale, not implausible)
        │
        ▼
52-Week High Calculator     (rolling 365-day high, persisted, never fabricated)
        │
        ▼
Drawdown Calculator         (pure function, floating-point-safe)
        │
        ▼
Threshold Engine            (crossing detection, dynamic 5% extension)
        │
        ▼
Alert State Manager         (persists armed/disarmed state, re-arm hysteresis)
        │
        ▼
Notification Service        (fan-out, per-channel delivery tracking)
        │
        ▼
Telegram / Email / SMS / Push
```

Every layer is independently unit-testable and swappable (see `src/`).

## Project layout

```
nifty-drawdown-alert/
├── src/
│   ├── config.py                     # all env-driven configuration
│   ├── main.py                       # entrypoint / scheduler loop
│   ├── alert_engine.py               # orchestrates one full evaluation cycle
│   ├── market_hours.py               # weekday/holiday/open-close logic
│   ├── data_provider/
│   │   ├── base.py                   # MarketDataProvider interface
│   │   └── yfinance_provider.py      # default implementation
│   ├── services/
│   │   ├── price_service.py          # validation + staleness checks
│   │   ├── high_calculator.py        # 52-week high, persisted
│   │   ├── drawdown_calculator.py    # pure math
│   │   ├── threshold_engine.py       # crossing + re-arm decision logic
│   │   ├── alert_state_manager.py    # bridges engine <-> persistence
│   │   └── message_formatter.py      # alert text formatting
│   ├── notifications/
│   │   ├── base.py                   # Notifier interface
│   │   ├── telegram_notifier.py
│   │   ├── email_notifier.py
│   │   ├── stub_notifiers.py         # SMS / Push - plug in a vendor
│   │   └── notification_service.py   # fan-out + delivery tracking
│   └── persistence/
│       └── database.py               # SQLite schema + access layer
├── config/
│   └── nse_holidays.json             # NSE trading holiday list
├── tests/
│   ├── unit/                         # one file per component, no I/O
│   └── integration/                  # full AlertEngine cycle w/ fakes
├── data/                             # SQLite DB lives here at runtime
├── logs/                             # log file output
├── requirements.txt
├── .env.example
├── pytest.ini
└── docs/DESIGN.md
```

## Setup

1. **Python 3.10+** recommended.

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Copy the example environment file and fill in your values:
   ```bash
   cp .env.example .env
   ```
   At minimum, set up **one** notification channel (Telegram is the simplest to
   start with — create a bot via [@BotFather](https://t.me/BotFather), then set
   `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`).

4. Start the interactive Telegram assistant for the same bot:
   ```bash
   python nifty_ai_telegram_assistant.py
   ```
   This starts a Telegram polling bot that answers status/drawdown/threshold questions and uses the same configured bot token.

4. Update `config/nse_holidays.json` with the current year's official NSE holiday
   list (published annually by NSE/BSE).

5. Run the tests:
   ```bash
   pytest
   ```

6. Start the monitor:
   ```bash
   python -m src.main
   ```
   It polls every `POLL_INTERVAL_SECONDS` (default 60s) while the market is open,
   and sleeps through market-closed periods (nights, weekends, holidays).

## Configuration reference

All settings are environment variables — see `.env.example` for the full list with
defaults and comments. Key ones:

| Variable | Purpose | Default |
|---|---|---|
| `MARKET_DATA_PROVIDER` | which provider implementation to use | `yfinance` |
| `DRAWDOWN_THRESHOLDS` | comma-separated alert levels | `10,15,20,25,30,35,40,45,50` |
| `REARM_BUFFER_PCT` | recovery margin required before a threshold re-arms | `2.0` |
| `POLL_INTERVAL_SECONDS` | how often to check price during market hours | `60` |
| `MAX_PRICE_STALENESS_SECONDS` | reject quotes older than this | `900` |
| `ENABLE_TELEGRAM_NOTIFIER` / `ENABLE_EMAIL_NOTIFIER` / `ENABLE_SMS_NOTIFIER` / `ENABLE_PUSH_NOTIFIER` | per-channel toggles | Telegram on, rest off |

## How duplicate alerts and re-arming work

- Each threshold (10%, 15%, ...) is either **armed** (eligible to fire) or
  **disarmed** (already fired, waiting to reset), tracked in SQLite.
- A threshold fires once when drawdown crosses it while armed, then disarms
  itself — it will not fire again on every subsequent check at the same level.
- It only re-arms once drawdown recovers to below `threshold - REARM_BUFFER_PCT`.
  E.g. with the default 2% buffer, the 10% alert re-arms once drawdown falls back
  below 8%, and could then fire again if the market falls through 10% a second
  time.
- This state is persisted to disk, so restarting the application never causes
  already-fired alerts to resend.

## Deployment

### Option A — systemd (Linux VM)

Create `/etc/systemd/system/nifty-alert.service`:

```ini
[Unit]
Description=NIFTY 50 Drawdown Alert System
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/nifty-drawdown-alert
EnvironmentFile=/opt/nifty-drawdown-alert/.env
ExecStart=/opt/nifty-drawdown-alert/venv/bin/python -m src.main
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now nifty-alert
```

Because all alert state lives in SQLite, restarts (crash, redeploy, reboot) are
safe — no duplicate alerts, no lost history.

### Option B — Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "-m", "src.main"]
```

```bash
docker build -t nifty-alert .
docker run -d --env-file .env -v $(pwd)/data:/app/data -v $(pwd)/logs:/app/logs nifty-alert
```

Mount `./data` and `./logs` as volumes so state and logs survive container
restarts/redeploys.

### Option C — cron-driven (instead of a long-running loop)

If you'd rather not run a persistent process, you can invoke a single cycle from
cron and let `MarketHours` decide whether to actually do anything:

```python
# run_once.py
from src.main import build_engine
from src.market_hours import MarketHours
from src.config import CONFIG

engine = build_engine()
mh = MarketHours(CONFIG.market_open_time, CONFIG.market_close_time,
                  CONFIG.market_timezone, CONFIG.load_holidays())
if mh.is_market_open():
    engine.run_once()
```
```
* 9-15 * * 1-5  cd /opt/nifty-drawdown-alert && venv/bin/python run_once.py
```

## Testing

```bash
pytest                          # everything
pytest tests/unit                # fast, no external deps beyond stdlib+pytz
pytest tests/integration         # full AlertEngine cycles with fake providers
pytest -v --tb=short             # verbose output
```

Coverage includes: 0%/5%/exact-10%/10.01%/15%/20% drawdown math, multi-threshold
jumps in one price move, new 52-week-high handling, API failure handling, stale
price rejection, restart/duplicate-alert prevention, re-arm/recovery behavior,
and market-hours/holiday/weekend gating.

## Scope & safety

This is a **read-only monitoring and alerting system**. It does not place orders,
does not connect to a demat account, and does not require broker API credentials.
If you later want automated order execution, that is a materially different,
higher-risk feature requiring its own explicit authentication, confirmation
workflow, risk controls, and broker API integration — not something to bolt onto
this alerting service silently.
