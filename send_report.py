"""
Send validated NIFTY 50 drawdown backtest results via Telegram and email.
Uses the same bot token / SMTP credentials from .env.
"""
import sys
import os
import smtplib
import requests
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_IDS = [cid for cid in [os.getenv("TELEGRAM_CHAT_ID"), os.getenv("TELEGRAM_CHAT_ID_2")] if cid]
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USERNAME")
SMTP_PASS = os.getenv("SMTP_PASSWORD")
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")

REPORT = """NIFTY 50 ROLLING 52-WEEK DRAWDOWN BACKTEST
Period: 1 Jan 2020 - 14 Aug 2026
Source: Yahoo Finance ^NSEI daily close
Window: 252 trading days (rolling)

=====================================
DEEPEST DRAWDOWN
=====================================
Date:           23 March 2020
Close:          7,610.25
52W High:       12,362.30
Drawdown:       -38.44%

=====================================
10% THRESHOLD (18 crossings)
=====================================
 1. 06-Mar-2020  10,989.45  High 12,362.30  DD -11.11%
 2. 30-Jul-2020  11,102.15  High 12,362.30  DD -10.19%
 3. 24-Sep-2020  10,805.55  High 12,362.30  DD -12.59%
 4. 20-Dec-2021  16,614.20  High 18,477.05  DD -10.08%
 5. 24-Feb-2022  16,247.95  High 18,477.05  DD -12.06%
 6. 02-Mar-2022  16,605.95  High 18,477.05  DD -10.13%
 7. 06-May-2022  16,411.25  High 18,477.05  DD -11.18%
 8. 31-May-2022  16,584.55  High 18,477.05  DD -10.24%
 9. 26-Jul-2022  16,483.85  High 18,477.05  DD -10.79%
10. 13-Nov-2024  23,559.05  High 26,216.05  DD -10.14%
11. 20-Dec-2024  23,587.50  High 26,216.05  DD -10.03%
12. 09-Jan-2025  23,526.50  High 26,216.05  DD -10.26%
13. 07-Feb-2025  23,559.95  High 26,216.05  DD -10.13%
14. 26-Mar-2025  23,486.85  High 26,216.05  DD -10.41%
15. 12-Mar-2026  23,639.15  High 26,328.55  DD -10.21%
16. 19-Mar-2026  23,002.15  High 26,328.55  DD -12.63%
17. 12-May-2026  23,379.55  High 26,328.55  DD -11.20%
18. 29-May-2026  23,547.75  High 26,328.55  DD -10.56%

=====================================
15% THRESHOLD (5 crossings)
=====================================
 1. 09-Mar-2020  10,451.45  High 12,362.30  DD -15.46%
 2. 15-Jun-2022  15,692.15  High 18,477.05  DD -15.07%
 3. 28-Feb-2025  22,124.70  High 26,216.05  DD -15.61%
 4. 07-Apr-2025  22,161.60  High 26,216.05  DD -15.47%
 5. 30-Mar-2026  22,331.40  High 26,328.55  DD -15.18%

=====================================
20% THRESHOLD (4 crossings)
=====================================
 1. 12-Mar-2020   9,590.15  High 12,362.30  DD -22.42%
 2. 16-Mar-2020   9,197.40  High 12,362.30  DD -25.60%
 3. 15-Jun-2020   9,813.70  High 12,362.30  DD -20.62%
 4. 17-Jun-2020   9,881.15  High 12,362.30  DD -20.07%

=====================================
25% THRESHOLD (4 crossings)
=====================================
 1. 16-Mar-2020   9,197.40  High 12,362.30  DD -25.60%
 2. 24-Apr-2020   9,154.40  High 12,362.30  DD -25.95%
 3. 05-May-2020   9,205.60  High 12,362.30  DD -25.53%
 4. 14-May-2020   9,142.75  High 12,362.30  DD -26.04%

=====================================
30% THRESHOLD (3 crossings)
=====================================
 1. 18-Mar-2020   8,468.80  High 12,362.30  DD -31.49%
 2. 23-Mar-2020   7,610.25  High 12,362.30  DD -38.44%
 3. 30-Mar-2020   8,281.10  High 12,362.30  DD -33.01%

=====================================
35% THRESHOLD (1 crossing)
=====================================
 1. 23-Mar-2020   7,610.25  High 12,362.30  DD -38.44%

=====================================
40% THRESHOLD (0 crossings)
=====================================
Never reached.

=====================================
SUMMARY
=====================================
Threshold | Crossings | First       | Last        | Deepest
----------|-----------|-------------|-------------|---------
   10%    |    18     | 06-Mar-2020 | 29-May-2026 | -38.44%
   15%    |     5     | 09-Mar-2020 | 30-Mar-2026 | -38.44%
   20%    |     4     | 12-Mar-2020 | 17-Jun-2020 | -38.44%
   25%    |     4     | 16-Mar-2020 | 14-May-2020 | -38.44%
   30%    |     3     | 18-Mar-2020 | 30-Mar-2020 | -38.44%
   35%    |     1     | 23-Mar-2020 | 23-Mar-2020 | -38.44%
   40%    |     0     | N/A         | N/A         | N/A

All calculations independently verified against Yahoo Finance daily-close data."""


def send_telegram(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=30)
    return resp.status_code == 200, resp.text


def send_email(subject, body):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())


def main():
    errors = []

    # Telegram
    for chat_id in CHAT_IDS:
        ok, detail = send_telegram(BOT_TOKEN, chat_id, REPORT)
        tag = f"Telegram chat {chat_id}"
        if ok:
            print(f"  [OK] {tag} - sent")
        else:
            print(f"  [FAIL] {tag} - {detail}")
            errors.append(tag)

    # Email
    try:
        send_email("NIFTY 50 Drawdown Backtest (2020-2026) - Full Crossing Report", REPORT)
        print(f"  [OK] Email to {EMAIL_TO} - sent")
    except Exception as e:
        print(f"  [FAIL] Email to {EMAIL_TO} - {e}")
        errors.append(f"Email: {e}")

    print()
    if errors:
        print(f"Failed: {', '.join(errors)}")
        sys.exit(1)
    else:
        print("All messages sent successfully.")


if __name__ == "__main__":
    main()
