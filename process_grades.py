import json
import csv

def score_user(metrics):
    pnl_score = min(1, max(0, metrics["pnl"] / 10000))  # Normalize PnL up to 10k
    win_rate_score = metrics["win_rate"]
    volume_score = min(1, metrics["volume"] / 100000)   # Normalize volume up to 100k
    roi = metrics.get('roi', 0)
    return round(100 * (0.4 * pnl_score + 0.3 * win_rate_score + 0.2 * volume_score + 0.1 * roi), 1)

def process_grades(raw_metrics):
    grades = []
    for item in raw_metrics:
        addr = item['wallet']
        metrics = item['metrics']
        if metrics['volume'] > 0:
            roi = metrics['pnl'] / metrics['volume'] if metrics['volume'] > 0 else 0
            score = score_user({**metrics, 'roi': roi})
            if metrics["pnl"] > 0:
                grades.append({
                    "wallet": addr,
                    "pnl": round(metrics["pnl"], 2),
                    "win_rate": round(metrics["win_rate"], 4),
                    "volume": round(metrics["volume"], 2),
                    "roi": round(roi, 4),
                    "score": score
                })
    # write files
    keys = ["wallet", "pnl", "win_rate", "volume", "roi", "score"]
    with open("grades.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, keys)
        writer.writerow({"wallet": "# Note: All values normalized to USDC (raw BigInt / 1e6). Users with 0 volume filtered out."})
        writer.writeheader()
        writer.writerows(grades)
    grades_sorted = sorted(grades, key=lambda g: g["score"], reverse=True)
    with open("grades_sorted.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, keys)
        writer.writerow({"wallet": "# Note: All values normalized to USDC (raw BigInt / 1e6). Users with 0 volume filtered out."})
        writer.writeheader()
        writer.writerows(grades_sorted)
    print("Done!  • grades.csv  • grades_sorted.csv")

if __name__ == "__main__":
    with open('raw_data.json', 'r') as f:
        raw_metrics = json.load(f)
    process_grades(raw_metrics) 
