"""
grade_users.py  –  Compute a Smart-Score-Lite for every wallet in seen_users.txt

Usage:
    pip install requests tqdm pandas
    python grade_users.py

Outputs:
    grades.csv         # wallet, profit, roi, volume, score
    grades_sorted.csv  # same, sorted high→low score
"""

import requests, math, time, csv, sys
from pathlib import Path
from tqdm import tqdm           # progress bar
import random, time, requests

API_ACTIVITY = "https://data-api.polymarket.com/activity"
API_VALUE    = "https://data-api.polymarket.com/value"
PAGE_LIMIT   = 500
SLEEP        = 0.15              # polite pause between pages


def safe_get(url, *, params=None, timeout=30, retries=4):
    for attempt in range(retries):
        r = requests.get(url, params=params, timeout=timeout)
        if r.status_code != 429:        # success or other errors
            return r
        wait = (2 ** attempt) + random.random()      # 1 s, 2 s, 4 s, 8 s
        print(f"🔄 429 throttled – sleeping {wait:.1f}s")
        time.sleep(wait)
    r.raise_for_status()                # bubble up last error


def fetch_trades(addr):
    trades, offset = [], 0
    while True:
        params = {
            "user": addr,
            "type": "TRADE",
            "limit": PAGE_LIMIT,
            "offset": offset,
            "sortDirection": "ASC"     # cheapest to keep ordering stable
        }
        r = safe_get(API_ACTIVITY, params=params)
        if r.status_code != 200:
            print("   error", r.status_code, r.text[:120])
            break
        batch = r.json()
        trades.extend(batch)
        if len(batch) < PAGE_LIMIT:
            break
        offset += PAGE_LIMIT
        time.sleep(SLEEP)
    return trades

def fetch_value(addr):
    r = requests.get(API_VALUE, params={"user": addr}, timeout=15)
    if r.status_code != 200:
        return 0.0
    obj = r.json()
    return obj[0]["value"] if obj else 0.0

def grade_wallet(addr):
    trades = fetch_trades(addr.lower())
    spent = sum(t["usdcSize"] for t in trades if t["side"] == "BUY")
    recv  = sum(t["usdcSize"] for t in trades if t["side"] == "SELL")
    value = fetch_value(addr)
    profit = recv + value - spent
    roi = profit / spent if spent > 0 else 0.0
    volume = spent + recv

    # Smart-Score-Lite
    score_raw  = 0.60 * math.tanh(5*roi)
    score_raw += 0.25 * math.tanh(volume/1000)
    score_raw += 0.15 * math.tanh(profit/500)
    score = round(50 + 50*score_raw, 1)

    return {
        "wallet": addr,
        "profit": round(profit, 2),
        "roi": round(roi, 4),
        "volume": round(volume, 2),
        "score": score,
    }

def main():
    wallets = [w.strip() for w in Path("seen_users.txt").read_text().splitlines() if w.strip()]
    grades  = []

    print(f"Grading {len(wallets)} wallets …")
    for addr in tqdm(wallets):
        grades.append(grade_wallet(addr))

    # write files
    keys = ["wallet","profit","roi","volume","score"]
    with open("grades.csv","w",newline="") as f:
        csv.DictWriter(f,keys).writeheader(), csv.DictWriter(f,keys).writerows(grades)

    grades_sorted = sorted(grades, key=lambda g: g["score"], reverse=True)
    with open("grades_sorted.csv","w",newline="") as f:
        csv.DictWriter(f,keys).writeheader(), csv.DictWriter(f,keys).writerows(grades_sorted)

    print("Done!  • grades.csv  • grades_sorted.csv")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nInterrupted by user")
