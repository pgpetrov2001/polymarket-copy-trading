"""
grade_users.py – Compute performance scores for wallets in seen_users.txt using on-chain data from The Graph's Polymarket subgraph

Usage:
    pip install -r requirements.txt
    # Create .env with THEGRAPH_API_KEY=your_key_here (get from https://thegraph.com/studio)
    python grade_users.py

Outputs:
    grades.csv         # wallet, pnl, win_rate, volume, score
    grades_sorted.csv  # same, sorted high→low score
"""

import sys, csv, time, os
import argparse
import json
from dotenv import load_dotenv
from pathlib import Path
from tqdm import tqdm
from gql import gql, Client  # type: ignore
from gql.transport.requests import RequestsHTTPTransport

from process_grades import process_grades  # type: ignore

load_dotenv()

API_KEY = os.getenv("THEGRAPH_API_KEY")
if not API_KEY:
    print("Error: THEGRAPH_API_KEY environment variable not set. Get one from https://thegraph.com/studio")
    sys.exit(1)
SUBGRAPH_URL = f"https://gateway.thegraph.com/api/{API_KEY}/subgraphs/id/Bx1W4S7kDVxs9gC3s2G6DS8kdNBJNVhMviCtin2DiBp"
ACTIVITY_SUBGRAPH_ID = '81Dm16JjuFSrqz813HysXoUPvzTwE7fsfPk2RTf66nyC'


def create_client(subgraph_id=None):
    url = f"https://gateway.thegraph.com/api/{API_KEY}/subgraphs/id/{subgraph_id or 'Bx1W4S7kDVxs9gC3s2G6DS8kdNBJNVhMviCtin2DiBp'}"
    transport = RequestsHTTPTransport(url=url, use_json=True, headers={"Content-type": "application/json"})
    return Client(transport=transport, fetch_schema_from_transport=True)

def query_schema(client):
    query = gql('''
    {
      __schema {
        queryType {
          name
        }
        types {
          kind
          name
          fields(includeDeprecated: true) {
            name
            type {
              name
              kind
              ofType {
                name
                kind
              }
            }
          }
        }
      }
    }
    ''')
    result = client.execute(query)
    return result["__schema"]["types"]

def query_user_pnl(client, user):
    query = gql('''
    query GetUserData($user: String!) {
      splits(where: {stakeholder: $user}) {
        amount
      }
      merges(where: {stakeholder: $user}) {
        amount
      }
      redemptions(where: {redeemer: $user}) {
        payout
      }
    }
    ''')
    try:
        result = client.execute(query, variable_values={"user": user.lower()})
        splits = result.get("splits", [])
        merges = result.get("merges", [])
        redemptions = result.get("redemptions", [])
        pnl = sum(float(r["payout"]) for r in redemptions) + sum(float(m["amount"]) for m in merges) - sum(float(s["amount"]) for s in splits)
        pnl /= 1e6
        volume = sum(float(s["amount"]) for s in splits) + sum(float(m["amount"]) for m in merges)
        volume /= 1e6
        wins = sum(1 for r in redemptions if float(r["payout"]) > 0)
        win_rate = wins / len(redemptions) if redemptions else 0
        return {"pnl": pnl, "win_rate": win_rate, "volume": volume}
    except Exception as e:
        print(f"Error querying {user}: {e}")
        try:
            schema_fields = [f["name"] for f in query_schema(client)]
            print("Available query fields:", schema_fields)
        except Exception as schema_e:
            print("Error fetching schema:", schema_e)
        return {"pnl": 0.0, "win_rate": 0.0, "volume": 0.0}

def query_additional_volume(client, user, subgraph_id, entity, user_field, amount_fields):
    if isinstance(amount_fields, str):
        amount_fields = [amount_fields]
    total = 0.0
    skip = 0
    page = 0
    max_pages = 10
    while page < max_pages:
        where_clause = f'{{{user_field}: $user}}'
        if entity == 'transactions':
            where_clause = f'{{{user_field}: $user, type_in: [Buy, Sell]}}'
        query = gql(f'''
        query GetVolume($user: String!, $skip: Int) {{
          {entity}(where: {where_clause}, first: 100, skip: $skip) {{
            {'  '.join(amount_fields) if isinstance(amount_fields, list) else amount_fields}
          }}
        }}
        ''')
        result = client.execute(query, variable_values={"user": user.lower(), "skip": skip})
        items = result.get(entity, [])
        if not items:
            break
        if amount_fields == 'amountsAdded':
            total += sum(sum(float(a) for a in item['amountsAdded']) for item in items) / 1e6
        else:
            total += sum(sum(float(item[f]) for f in amount_fields) for item in items) / 1e6
        skip += 100
        page += 1
    return total

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--num', type=int, default=None, help='Number of wallets to process (default: all)')
    args = parser.parse_args()
    try:
        text = Path("seen_users.txt").read_text()
    except FileNotFoundError:
        print("Error: seen_users.txt not found")
        sys.exit(1)
    wallets = [w.strip() for w in text.splitlines() if w.strip()]
    if args.num is not None:
        wallets = wallets[:args.num]
    if len(wallets) == 0:
        client = create_client()
        types = query_schema(client)
        relevant_types = ['Query', 'Position', 'Condition', 'Redemption', 'FixedProductMarketMaker', 'NegRiskConversion', 'Trade', 'Account', 'User']
        for t in types:
            if t['name'] in relevant_types and t['kind'] == 'OBJECT':
                fields = [f['name'] for f in t.get('fields', [])]
                print(f"\nType: {t['name']}\nFields: {fields}")
        sys.exit(0)
    client = create_client()
    raw_metrics = []
    print(f"Grading {len(wallets)} wallets using on-chain data …")
    for addr in tqdm(wallets):
        metrics = query_user_pnl(client, addr)
        activity_vol = query_additional_volume(create_client(ACTIVITY_SUBGRAPH_ID), addr, ACTIVITY_SUBGRAPH_ID, 'transactions', 'user', ['tradeAmount', 'feeAmount'])
        fpmm_vol = query_additional_volume(create_client(ACTIVITY_SUBGRAPH_ID), addr, ACTIVITY_SUBGRAPH_ID, 'fpmmFundingAdditions', 'funder', 'amountsAdded')
        metrics['volume'] += activity_vol + fpmm_vol
        metrics['activity_vol'] = activity_vol
        metrics['fpmm_vol'] = fpmm_vol
        raw_metrics.append({'wallet': addr, 'metrics': metrics})
        time.sleep(0.5)  # Rate limit
    with open('raw_data.json', 'w') as f:
        json.dump(raw_metrics, f, indent=2)
    print('Raw data saved to raw_data.json.')
    process_grades(raw_metrics)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nInterrupted by user")
