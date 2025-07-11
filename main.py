# main.py  –  Polymarket trade-scanner (Data-API edition)
#
# ▶  What it does
#     • Every 20 min: pulls trades from https://data-api.polymarket.com/trades
#     • Filters for trades newer than the last run
#     • Extracts unique proxyWallet addresses
#     • Persists them in seen_users.txt (so you never print duplicates)
#     • Persists the last-checked timestamp in last_check.txt
#
# ▶  Requirements
#     pip install requests schedule python-dotenv  # dotenv is optional here
# ---------------------------------------------------------------------------

import requests, schedule, time, os, json
from datetime import datetime, timedelta, timezone

API_URL            = "https://data-api.polymarket.com/trades"
SEEN_USERS_FILE    = "seen_users.txt"
LAST_CHECK_FILE    = "last_check.txt"
FETCH_LIMIT        = 500            # Data-API maximum
SCAN_INTERVAL_MIN  = 4

# ─────────────────────────── helpers ────────────────────────────────────────
def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def load_seen_users() -> set[str]:
    try:
        with open(SEEN_USERS_FILE, "r") as f:
            return {line.strip() for line in f if line.strip()}
    except FileNotFoundError:
        return set()

def save_seen_users(users: set[str]) -> None:
    with open(SEEN_USERS_FILE, "w") as f:
        for u in sorted(users):
            f.write(f"{u}\n")

def load_last_timestamp() -> int:
    try:
        with open(LAST_CHECK_FILE, "r") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        # default: 20 min ago
        return int((utc_now() - timedelta(minutes=SCAN_INTERVAL_MIN)).timestamp())

def save_last_timestamp(ts: int) -> None:
    with open(LAST_CHECK_FILE, "w") as f:
        f.write(str(ts))

def fetch_trades_since(since_ts: int) -> list[dict]:
    """Paginate through Data-API until we hit trades older than `since_ts`."""
    trades, offset = [], 0
    while True:
        params = {"limit": FETCH_LIMIT, "offset": offset}
        resp   = requests.get(API_URL, params=params, timeout=30)
        if resp.status_code != 200:
            print(f"⚠️  HTTP {resp.status_code}: {resp.text}")
            break
        batch = resp.json()
        if not batch:
            break

        # Keep only trades newer than our last checkpoint
        fresh = [t for t in batch if t.get("timestamp", 0) > since_ts]
        trades.extend(fresh)

        oldest_in_batch = batch[-1]["timestamp"]
        # Stop paging once we cross the old timestamp or batch is partial
        if oldest_in_batch <= since_ts or len(batch) < FETCH_LIMIT:
            break
        offset += FETCH_LIMIT
    return trades

def extract_addresses(trades: list[dict]) -> set[str]:
    return {t["proxyWallet"] for t in trades if "proxyWallet" in t}

# ─────────────────────────── scheduled job ─────────────────────────────────
def job():
    print(f"\n[{utc_now().isoformat()}] 🔄 running trade scan …")

    seen_users   = load_seen_users()
    last_ts      = load_last_timestamp()
    new_trades   = fetch_trades_since(last_ts)
    new_addrs    = extract_addresses(new_trades) - seen_users

    if new_addrs:
        print(f"🧠 found {len(new_addrs)} new users:")
        for a in sorted(new_addrs):
            print(f" • {a}")
        seen_users.update(new_addrs)
        save_seen_users(seen_users)
    else:
        print("No new users this round.")

    save_last_timestamp(int(utc_now().timestamp()))

# ─────────────────────────── main ──────────────────────────────────────────
print("🚀 Polymarket User Monitor (Data-API) started.")
job()                                    # immediate run on launch
schedule.every(SCAN_INTERVAL_MIN).minutes.do(job)

while True:
    schedule.run_pending()
    time.sleep(5)
