import sqlite3
import yfinance as yf

# Check alerts in database
conn = sqlite3.connect('data/nifty_alerts.db')
cursor = conn.cursor()

print("=== DATABASE SCHEMA ===")
cursor.execute("SELECT sql FROM sqlite_master WHERE type='table'")
for table_def in cursor.fetchall():
    print(table_def[0])

print("\n=== DATABASE ALERTS ===")
try:
    cursor.execute('SELECT * FROM alerts LIMIT 20')
    alerts = cursor.fetchall()
    print(f"Total alerts in DB: {len(alerts)}")
    for row in alerts:
        print(row)
except Exception as e:
    print(f"Error: {e}")

print("\n=== THRESHOLD STATE ===")
cursor.execute('SELECT * FROM threshold_state')
thresholds = cursor.fetchall()
for row in thresholds:
    print(row)

conn.close()

# Check current NIFTY price
print("\n=== CURRENT NIFTY STATUS ===")
data = yf.download('^NSEI', period='1y', progress=False)
current_price = data['Close'].iloc[-1].item() if hasattr(data['Close'].iloc[-1], 'item') else data['Close'].iloc[-1]
high_52w = data['Close'].max().item() if hasattr(data['Close'].max(), 'item') else data['Close'].max()
drawdown_pct = ((current_price - high_52w) / high_52w) * 100

print(f"Current Price: {current_price:.2f}")
print(f"52-Week High: {high_52w:.2f}")
print(f"Drawdown: {drawdown_pct:.2f}%")

if drawdown_pct >= -10:
    print("NOT in drawdown (< 10%)")
else:
    print(f"IN DRAWDOWN ({abs(drawdown_pct):.2f}%)")
    if drawdown_pct < -15:
        print("  Should have 15% alert")
    if drawdown_pct < -20:
        print("  Should have 20% alert")
    if drawdown_pct < -25:
        print("  Should have 25% alert")
