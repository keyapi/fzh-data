"""
Fetch 4 SP ad reports from Sellfox OpenAPI.
Usage: python fetch_ad_reports.py [--days 7] [--shop SHOP_ID]
"""
import os
import sys
import json
import time
import hmac
import hashlib
import random
import argparse
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

# --- Load .env ---
def load_env(paths):
    env = {}
    for path in paths:
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env[k.strip()] = v.strip()
        except FileNotFoundError:
            pass
    env.update({k: v for k, v in os.environ.items() if v})
    return env

env = load_env([
    SCRIPT_DIR / ".env",
    PROJECT_ROOT / "advertise" / ".env",
])

APP_ID = env.get("SELLFOX_APP_ID", "")
APP_SECRET = env.get("SELLFOX_APP_SECRET", "")
DOMAIN = env.get("SELLFOX_API_DOMAIN", "https://openapi.sellfox.com")

if not APP_ID or not APP_SECRET:
    print("ERROR: SELLFOX_APP_ID and SELLFOX_APP_SECRET required in SELLFOX_API/.env")
    sys.exit(1)

# --- Globals set after auth ---
ACCESS_TOKEN = None

# --- Core API ---
def signed_post(url_path, body=None):
    """POST to the API with HMAC-SHA256 signing. Returns parsed data dict."""
    ts = str(int(time.time() * 1000))
    nonce = str(random.randint(1, 99999))
    sign_params = {
        "access_token": ACCESS_TOKEN,
        "client_id": APP_ID,
        "method": "post",
        "nonce": nonce,
        "timestamp": ts,
        "url": url_path,
    }
    sorted_str = "&".join(f"{k}={v}" for k, v in sorted(sign_params.items()))
    sig = hmac.new(APP_SECRET.encode(), sorted_str.encode(), hashlib.sha256).hexdigest()
    query = f"access_token={ACCESS_TOKEN}&client_id={APP_ID}&nonce={nonce}&timestamp={ts}&sign={sig}"
    full_url = f"{DOMAIN}{url_path}?{query}"
    data_bytes = json.dumps(body or {}).encode("utf-8")
    req = urllib.request.Request(full_url, data=data_bytes,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
    result = json.loads(raw)
    if result.get("code") != 0:
        raise RuntimeError(f"API error on {url_path}: code={result.get('code')} msg={result.get('msg', result)}")
    return result["data"]

def download_file(url, filepath):
    # Percent-encode non-ASCII characters in URL (e.g. Chinese filenames)
    parts = urllib.parse.urlparse(url)
    encoded_path = urllib.parse.quote(parts.path, safe='/:@!$&()*+,;=')
    safe_url = parts._replace(path=encoded_path).geturl()
    req = urllib.request.Request(safe_url)
    with urllib.request.urlopen(req, timeout=120) as resp:
        content = resp.read()
    with open(filepath, "wb") as f:
        f.write(content)
    return len(content)

# --- Auth ---
def authenticate():
    global ACCESS_TOKEN
    url = f"{DOMAIN}/api/oauth/v2/token.json?client_id={APP_ID}&client_secret={APP_SECRET}&grant_type=client_credentials"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("code") != 0:
        raise RuntimeError(f"Token failed: {data}")
    ACCESS_TOKEN = data["data"]["access_token"]
    expires_ms = data["data"]["expires_in"]
    print(f"[OK] Token obtained, expires in {expires_ms // 3600000}h")
    return ACCESS_TOKEN

# --- Shop ---
def list_shops():
    data = signed_post("/api/shop/pageList.json", {"pageSize": 200})
    rows = data.get("rows", [])
    total = data.get("totalSize", len(rows))
    print(f"\n=== Shops: {total} total, showing {len(rows)} ===")
    for i, shop in enumerate(rows):
        print(f"  [{i}] {shop['name']} | {shop['marketplaceId']} | {shop['region']} | ad={shop.get('adStatus','?')} | id={shop['id']}")
    return rows

# --- Reports ---
REPORT_TYPES = {
    "campaign":    ("adCampaignReport",    "Campaign"),
    "targeting":   ("adTargeringReport",   "Targeting"),
    "search_term": ("adSearchTermReport",   "SearchTerm"),
    "placement":   ("adSpaceReport",        "Placement"),
}

def create_task(shop_id, code, label, start, end):
    body = {
        "shopIds": [str(shop_id)],
        "adTypeCode": "sp",
        "reportTypeCode": code,
        "timeUnit": "daily",
        "reportStartDate": start,
        "reportEndDate": end,
    }
    data = signed_post("/api/cpc/download/createTask.json", body)
    tid = data.get("id")
    print(f"  [OK] {label} task created: {tid}")
    return tid

def check_tasks(task_ids):
    """Query status of multiple tasks. Returns dict {tid: (state_str, row)}."""
    data = signed_post("/api/cpc/download/pageList.json", {
        "taskIds": [str(t) for t in task_ids],
        "pageNo": 1,
        "pageSize": 50,
    })
    rows = data.get("rows", [])
    result = {}
    for row in rows:
        tid = row.get("id")
        state = row.get("reportState", "unknown")
        # "已生成" = done, "失败" = failed, "生成中" = processing
        result[tid] = (state, row)
    return result

# --- Main ---
def main():
    parser = argparse.ArgumentParser(description="Fetch SP ad reports from Sellfox API")
    parser.add_argument("--days", type=int, default=7, help="Days to look back (default: 7)")
    parser.add_argument("--shop", type=str, help="Shop ID (skip listing)")
    parser.add_argument("--shop-name", type=str, help="Filter shop by name substring")
    args = parser.parse_args()

    end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    print(f"Date range: {start_date} ~ {end_date}")

    # 1. Auth
    print("\n--- Step 1: Authenticate ---")
    authenticate()

    # 2. Shop
    if args.shop:
        shop_id = args.shop
        print(f"\n--- Step 2: Using provided shop ID: {shop_id} ---")
    else:
        print("\n--- Step 2: List shops ---")
        shops = list_shops()
        if not shops:
            print("No shops found!")
            return
        if args.shop_name:
            shops = [s for s in shops if args.shop_name.lower() in s["name"].lower()]
            if not shops:
                print(f"No shops matching '{args.shop_name}'")
                return
        shop = shops[0]
        shop_id = shop["id"]
        print(f"\nUsing: {shop['name']} (id={shop_id})")

    # 3. Create download tasks (with delay to avoid rate limiting)
    print("\n--- Step 3: Create download tasks ---")
    tasks = {}
    for key, (code, label) in REPORT_TYPES.items():
        tasks[key] = {"id": create_task(shop_id, code, label, start_date, end_date), "label": label}
        time.sleep(2)  # rate limit avoidance

    # 4. Poll
    print("\n--- Step 4: Poll for completion ---")
    out_dir = PROJECT_ROOT / "advertise" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_tids = [t["id"] for t in tasks.values()]
    pending = set(all_tids)
    max_wait = 300
    waited = 0
    while pending and waited < max_wait:
        time.sleep(5)
        waited += 5
        results = check_tasks(all_tids)
        for tid, (state, row) in results.items():
            if tid not in pending:
                continue
            # Find label for this task
            label = "?"
            for key, t in tasks.items():
                if t["id"] == tid:
                    label = t["label"]
                    break
            if state == "已生成":
                urls = row.get("downloadUrl", [])
                if urls and len(urls) > 0:
                    url = urls[0]
                    fpath = out_dir / f"{label}_{start_date}_{end_date}.xlsx"
                    size = download_file(url, fpath)
                    print(f"  [{waited}s] {label}: DONE ({size} bytes -> {fpath})")
                else:
                    print(f"  [{waited}s] {label}: DONE but no URL. Keys: {list(row.keys())[:10]}")
                pending.discard(tid)
            elif state == "失败":
                print(f"  [{waited}s] {label}: FAILED row={row}")
                pending.discard(tid)
        if pending:
            print(f"  [{waited}s] Waiting for {len(pending)} tasks...")

    if pending:
        print(f"\nTimeout! Still pending after {waited}s: {pending}")
    else:
        print(f"\nAll 4 reports downloaded to {out_dir}")

if __name__ == "__main__":
    main()
