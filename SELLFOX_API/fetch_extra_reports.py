"""Fetch 3 additional SP ad reports for BJRYECLTD-US — June 2026."""
import os, sys, json, time, hmac, hashlib, random, urllib.request, urllib.error, urllib.parse
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

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

env = load_env([SCRIPT_DIR / ".env", PROJECT_ROOT / "advertise" / ".env"])
APP_ID = env["SELLFOX_APP_ID"]
APP_SECRET = env["SELLFOX_APP_SECRET"]
DOMAIN = env.get("SELLFOX_API_DOMAIN", "https://openapi.sellfox.com")

ACCESS_TOKEN = None

def authenticate():
    global ACCESS_TOKEN
    url = f"{DOMAIN}/api/oauth/v2/token.json?client_id={APP_ID}&client_secret={APP_SECRET}&grant_type=client_credentials"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    ACCESS_TOKEN = data["data"]["access_token"]
    print(f"[OK] Token obtained, expires in {data['data']['expires_in'] // 3600000}h")

def signed_post(url_path, body=None):
    ts = str(int(time.time() * 1000))
    nonce = str(random.randint(1, 99999))
    sign_params = {
        "access_token": ACCESS_TOKEN, "client_id": APP_ID, "method": "post",
        "nonce": nonce, "timestamp": ts, "url": url_path,
    }
    sorted_str = "&".join(f"{k}={v}" for k, v in sorted(sign_params.items()))
    sig = hmac.new(APP_SECRET.encode(), sorted_str.encode(), hashlib.sha256).hexdigest()
    query = f"access_token={ACCESS_TOKEN}&client_id={APP_ID}&nonce={nonce}&timestamp={ts}&sign={sig}"
    data_bytes = json.dumps(body or {}).encode("utf-8")
    req = urllib.request.Request(f"{DOMAIN}{url_path}?{query}", data=data_bytes,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))["data"]
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        result = json.loads(raw)
        raise RuntimeError(f"API error: code={result.get('code')} msg={result.get('msg')}")

def download_file(url, filepath):
    parts = urllib.parse.urlparse(url)
    encoded_path = urllib.parse.quote(parts.path, safe='/:@!$&()*+,;=')
    safe_url = parts._replace(path=encoded_path).geturl()
    req = urllib.request.Request(safe_url)
    with urllib.request.urlopen(req, timeout=120) as resp:
        content = resp.read()
    with open(filepath, "wb") as f:
        f.write(content)
    return len(content)

# --- Main ---
SHOP_ID = "596841"
START = "2026-06-01"
END = "2026-06-30"
OUT_DIR = PROJECT_ROOT / "advertise" / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

EXTRA_REPORTS = [
    ("ad_group",       "adGroupReport",        "AdGroup"),
    ("ad_product",     "adProductReport",      "AdvertisedProduct"),
    ("purchased_item", "adPurchasedItemReport", "PurchasedItem"),
]

print(f"Fetching 3 extra reports for shop {SHOP_ID}: {START} ~ {END}")
authenticate()

tasks = {}
for key, code, label in EXTRA_REPORTS:
    body = {"shopIds": [SHOP_ID], "adTypeCode": "sp", "reportTypeCode": code,
            "timeUnit": "daily", "reportStartDate": START, "reportEndDate": END}
    tid = signed_post("/api/cpc/download/createTask.json", body)["id"]
    print(f"  [OK] {label} task: {tid}")
    tasks[key] = {"id": tid, "label": label}
    time.sleep(2)

print("\nPolling...")
all_tids = [t["id"] for t in tasks.values()]
pending = set(all_tids)
waited = 0
while pending and waited < 300:
    time.sleep(5)
    waited += 5
    data = signed_post("/api/cpc/download/pageList.json", {"taskIds": [str(t) for t in all_tids], "pageNo": 1, "pageSize": 50})
    for row in data.get("rows", []):
        tid = row["id"]
        if tid not in pending:
            continue
        state = row.get("reportState", "?")
        label = "?"
        for k, t in tasks.items():
            if t["id"] == tid:
                label = t["label"]
                break
        if state == "已生成":
            urls = row.get("downloadUrl", [])
            if urls:
                fpath = OUT_DIR / f"{label}_2026-06_JUN2026.xlsx"
                size = download_file(urls[0], fpath)
                print(f"  [{waited}s] {label}: DONE ({size} bytes -> {fpath})")
            pending.discard(tid)
        elif state == "失败":
            print(f"  [{waited}s] {label}: FAILED")
            pending.discard(tid)
    if pending:
        print(f"  [{waited}s] Waiting for {len(pending)} tasks...")

if pending:
    print(f"Timeout! Still pending: {pending}")
else:
    print(f"\nAll 3 extra reports downloaded to {OUT_DIR}")
