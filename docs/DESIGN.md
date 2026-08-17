# Design Notes — NIFTY 50 Drawdown Alert System

## 1. Market data source

**Provider:** Yahoo Finance (`^NSEI` ticker) via the `yfinance` Python package, wrapped
behind an abstract `MarketDataProvider` interface (`src/data_provider/base.py`).

**Real-time or delayed?** Delayed — Yahoo Finance data for Indian indices typically
lags the live tape by roughly 15 minutes. This is fine for a drawdown alert system
(thresholds are 5-percentage-point bands, not tick-level triggers) but is **not**
suitable for order execution. If real-time data is required, implement a new
provider class (e.g. wrapping NSE's own API, Zerodha Kite Connect, Upstox, or a paid
vendor such as Twelve Data / Alpha Vantage) against the same interface — nothing
else in the system needs to change.

**Why the abstraction matters:** `PriceService`, `HighCalculator`, and everything
downstream depend only on `MarketDataProvider`, never on `yfinance` directly. Swapping
providers is a one-file change plus a config flag (`MARKET_DATA_PROVIDER`).

## 2. 52-week high calculation

`HighCalculator` asks the provider for the maximum daily **High** value of the NIFTY
50 index itself over the trailing 365 days (`get_52_week_high`). It is explicitly
computed from the index's own daily bars — never from any constituent stock's
52-week high.

The result is persisted (`fifty_two_week_high` table) and only ever updated
**upward**: a freshly computed high is stored only if it exceeds the currently
persisted value (or none exists yet). This means:
- A transient bad read from the provider can't erase a legitimate high.
- If the live provider is temporarily unavailable, `HighCalculator.get_current_high_value()`
  falls back to the last persisted high rather than failing the whole cycle
  (but never fabricates a number that was never actually observed).

## 3. Drawdown calculation

```
drawdown_percent = ((52_week_high - current_nifty50) / 52_week_high) * 100
```

Implemented as a pure function (`drawdown_calculator.py`) with no I/O, rounded to 6
decimal places to eliminate binary floating-point representation error (e.g.
`22500/25000` naively evaluates to `9.999999999999998` in IEEE 754 double
arithmetic — rounding ensures an exact 10% fall is recognized as exactly 10%, not
missed by 2e-15).

## 4. Threshold / alert-state design

- **Crossing detection:** a threshold `T` fires when
  `previous_drawdown < T <= current_drawdown` **and** `T` is currently "armed".
  Because this check is independent per threshold, a single large price move
  (e.g. 9% → 21% drawdown) correctly fires every threshold in between (10%, 15%,
  20%) in one cycle — see `ThresholdEngine.evaluate`.
- **Duplicate prevention:** once a threshold fires, it is immediately marked
  `is_armed = False` in SQLite. It cannot fire again no matter how many times the
  price re-checks near that level.
- **Re-arm (hysteresis):** a disarmed threshold `T` becomes armed again only once
  drawdown recovers to below `T - REARM_BUFFER_PCT` (default buffer: 2 percentage
  points). This is a config value (`REARM_BUFFER_PCT`), not hard-coded, so
  operators can tune how much recovery is required before re-arming.
- **Dynamic extension beyond configured max:** if drawdown exceeds the highest
  configured threshold (default 50%), the engine auto-generates further
  thresholds in the same 5-point increments (55%, 60%, ...) so alerting never
  silently stops in a severe crash.

## 5. State persistence & restart safety

All state lives in SQLite (`data/nifty_alerts.db` by default):
- `fifty_two_week_high` — current high + when it was set.
- `threshold_state` — per-threshold armed/disarmed flag + timestamps.
- `system_state` — misc key/value, notably `last_drawdown_pct` (used for crossing
  detection across cycles/restarts).
- `alerts` — full audit trail of every alert fired (price, high, drawdown,
  threshold, timestamp, message).
- `notification_deliveries` — per-channel delivery attempt + status for every alert.
- `error_log` — provider failures, validation failures, notification failures.
- `price_history` — every price observation used in a cycle.

Because `threshold_state.is_armed` is persisted and only flips on an explicit
trigger/re-arm event, restarting the application mid-drawdown does **not** cause
already-fired alerts to resend — even though `last_drawdown_pct` is also persisted
as a belt-and-braces measure to make crossing detection exact across restarts.

## 6. Notification layer

`Notifier` is an abstract interface (`send(message, subject) -> NotificationResult`)
implemented by `TelegramNotifier`, `EmailNotifier`, and stub `SmsNotifier` /
`PushNotifier` classes ready for a real vendor SDK. `NotificationService` fans a
message out to every **enabled** channel (`ENABLE_*` env flags) and persists a
delivery record (success/failure + detail) per channel per alert — a failure on
one channel never blocks the others or crashes the alert cycle.

## 7. Market hours handling

`MarketHours` treats the market as open only when: it's a weekday, it's not in the
configured NSE holiday list (`config/nse_holidays.json`), and local IST time falls
within `MARKET_OPEN_TIME`–`MARKET_CLOSE_TIME` inclusive. The main loop simply skips
evaluation cycles when the market is closed — no alerts are computed from
after-hours or holiday data.

## 8. Data quality safeguards

`PriceService` rejects (raises, never substitutes):
- non-positive or implausible prices (sanity range check)
- quotes older than `MAX_PRICE_STALENESS_SECONDS` (default 900s / 15 min)
- quotes timestamped in the future (clock-skew / bad-data guard)

A rejected quote skips the entire cycle — no drawdown is computed, no alert is
sent, and the failure is logged to `error_log`.
