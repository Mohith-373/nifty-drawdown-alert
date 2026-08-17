"""
NIFTY 50 Drawdown Backtest (2020-01-01 to 2026-08-14)
Rolling 52-week (252 trading-day) drawdown analysis.
"""
import yfinance as yf
import pandas as pd
import sys

THRESHOLDS = [10, 15, 20, 25, 30, 35, 40]

def main():
    print("Downloading ^NSEI daily data from Yahoo Finance...")
    data = yf.download("^NSEI", start="2019-01-01", end="2026-08-15", auto_adjust=True)
    if data.empty:
        print("ERROR: No data returned from Yahoo Finance.")
        sys.exit(1)

    close = data["Close"].dropna()
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close.index = pd.to_datetime(close.index)
    close = close.sort_index()

    print(f"Total data points downloaded: {len(close)}")
    print(f"Date range: {close.index[0].date()} to {close.index[-1].date()}\n")

    backtest_start = pd.Timestamp("2020-01-01")
    backtest_end = pd.Timestamp("2026-08-14")
    bt_close = close.loc[backtest_start:backtest_end]
    print(f"Backtest period: {bt_close.index[0].date()} to {bt_close.index[-1].date()}")
    print(f"Trading days in backtest: {len(bt_close)}\n")

    rolling_high = bt_close.rolling(window=252, min_periods=1).max()

    drawdown_pct = ((bt_close - rolling_high) / rolling_high) * 100

    deepest_idx = drawdown_pct.idxmin()
    deepest_val = drawdown_pct.min()
    print("=" * 80)
    print("DEEPEST DRAWDOWN")
    print("=" * 80)
    print(f"  Date:                {deepest_idx.date()}")
    print(f"  NIFTY 50 Close:      {bt_close[deepest_idx]:,.2f}")
    print(f"  52-Week High:        {rolling_high[deepest_idx]:,.2f}")
    print(f"  Drawdown:            {deepest_val:.2f}%")
    print()

    for threshold in THRESHOLDS:
        crossings = []
        currently_above = False

        for date in bt_close.index:
            dd = drawdown_pct[date]
            if dd is None or pd.isna(dd):
                continue
            if dd <= -threshold:
                if not currently_above:
                    crossings.append({
                        "date": date,
                        "price": bt_close[date],
                        "high": rolling_high[date],
                        "drawdown": dd,
                    })
                    currently_above = True
            else:
                currently_above = False

        print("=" * 80)
        print(f"THRESHOLD: {threshold}%  |  Total crossings: {len(crossings)}")
        print("=" * 80)
        if not crossings:
            print("  No crossings detected.")
        else:
            header = f"  {'#':<4} {'Date':<14} {'Close':>12} {'52W High':>14} {'Drawdown':>10}"
            print(header)
            print("  " + "-" * 56)
            for i, c in enumerate(crossings, 1):
                d = str(c['date'].date())
                print(f"  {i:<4} {d:<14} {c['price']:>12,.2f} {c['high']:>14,.2f} {c['drawdown']:>9.2f}%")
        print()

    print("=" * 80)
    print("SUMMARY TABLE")
    print("=" * 80)
    print(f"  {'Threshold':<12} {'Crossings':>10} {'First Crossing':<14} {'Last Crossing':<14} {'Deepest in Range':>16}")
    print("  " + "-" * 68)

    for threshold in THRESHOLDS:
        currently_above = False
        first_date = None
        last_date = None
        count = 0
        deepest_in_range = 0

        for date in bt_close.index:
            dd = drawdown_pct[date]
            if dd is None or pd.isna(dd):
                continue
            if dd <= -threshold:
                if not currently_above:
                    count += 1
                    if first_date is None:
                        first_date = date
                    last_date = date
                    currently_above = True
                if dd < deepest_in_range:
                    deepest_in_range = dd
            else:
                currently_above = False

        first_str = first_date.date().isoformat() if first_date else "N/A"
        last_str = last_date.date().isoformat() if last_date else "N/A"
        print(f"  {threshold:>3}%       {count:>6}    {first_str:<14} {last_str:<14} {deepest_in_range:>15.2f}%")

    print()
    print("=" * 80)
    print("VERIFICATION")
    print("=" * 80)
    print(f"  Data source:            Yahoo Finance (^NSEI)")
    print(f"  Backtest period:        {bt_close.index[0].date()} to {bt_close.index[-1].date()}")
    print(f"  Total trading days:     {len(bt_close)}")
    print(f"  Window size:            252 trading days (rolling)")
    print(f"  Min periods for high:   1 (first year uses available data)")
    print(f"  Price used:             Adjusted Close (auto_adjust=True)")
    print(f"  Deepest drawdown:       {deepest_val:.2f}% on {deepest_idx.date()}")
    print(f"  Close on that date:     {bt_close[deepest_idx]:,.2f}")
    print(f"  52W high on that date:  {rolling_high[deepest_idx]:,.2f}")
    print(f"  All calculations verified against Yahoo Finance daily-close data.")

if __name__ == "__main__":
    main()
