"""Fetch all available SB and SD ad reports for BJRYECLTD-US — June 2026."""
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
TOKEN = None

def authenticate():
    global TOKEN
    url = f"{DOMAIN}/api/oauth/v2/token.json?client_id={APP_ID}&client_secret={APP_SECRET}&grant_type=client_credentials"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        TOKEN = json.loads(resp.read().decode("utf-8"))["data"]["access_token"]

def signed_post(url_path, body=None):
    ts = str(int(time.time() * 1000))
    nonce = str(random.randint(1, 99999))
    sp = {"access_token": TOKEN, "client_id": APP_ID, "method": "post", "nonce": nonce, "timestamp": ts, "url": url_path}
    ss = "&".join(f"{k}={v}" for k, v in sorted(sp.items()))
    sig = hmac.new(APP_SECRET.encode(), ss.encode(), hashlib.sha256).hexdigest()
    q = f"access_token={TOKEN}&client_id={APP_ID}&nonce={nonce}&timestamp={ts}&sign={sig}"
    req = urllib.request.Request(f"{DOMAIN}{url_path}?{q}", data=json.dumps(body or {}).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))["data"]
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        return json.loads(raw)  # may have code != 0

def download_file(url, filepath):
    parts = urllib.parse.urlparse(url)
    encoded_path = urllib.parse.quote(parts.path, safe='/:@!$&()*+,;=')
    req = urllib.request.Request(parts._replace(path=encoded_path).geturl())
    with urllib.request.urlopen(req, timeout=120) as resp:
        content = resp.read()
    with open(filepath, "wb") as f:
        f.write(content)
    return len(content)

SHOP = "596841"
START, END = "2026-06-01", "2026-06-30"
OUT = PROJECT_ROOT / "advertise" / "data"
OUT.mkdir(parents=True, exist_ok=True)

# SB reports: adCampaignReport, adGroupReport, adProductReport, adSpaceReport, adTargeringReport, adSearchTermReport, adPurchasedItemReport
SB_REPORTS = [
    ("sb_campaign",    "adCampaignReport",       "SB-Campaign"),
    ("sb_group",       "adGroupReport",          "SB-AdGroup"),
    ("sb_product",     "adProductReport",        "SB-AdProduct"),
    ("sb_placement",   "adSpaceReport",          "SB-Placement"),
    ("sb_targeting",   "adTargeringReport",      "SB-Targeting"),
    ("sb_searchterm",  "adSearchTermReport",     "SB-SearchTerm"),
    ("sb_purchased",   "adPurchasedItemReport",  "SB-PurchasedItem"),
]

# SD reports: adCampaignReport, adGroupReport, adProductReport, adPurchasedItemReport, sdTargetListReport
SD_REPORTS = [
    ("sd_campaign",    "adCampaignReport",       "SD-Campaign"),
    ("sd_group",       "adGroupReport",          "SD-AdGroup"),
    ("sd_product",     "adProductReport",        "SD-AdProduct"),
    ("sd_purchased",   "adPurchasedItemReport",  "SD-PurchasedItem"),
    ("sd_targeting",   "sdTargetListReport",     "SD-Targeting"),
]

authenticate()

all_tasks = {}
for ad_type, reports in [("sb", SB_REPORTS), ("sd", SD_REPORTS)]:
    print(f"\n=== {ad_type.upper()} Reports ===")
    for key, code, label in reports:
        try:
            body = {"shopIds": [SHOP], "adTypeCode": ad_type, "reportTypeCode": code,
                    "timeUnit": "daily", "reportStartDate": START, "reportEndDate": END}
            result = signed_post("/api/cpc/download/createTask.json", body)
            if isinstance(result, dict) and result.get("id"):
                tid = result["id"]
                print(f"  [OK] {label}: {tid}")
                all_tasks[key] = {"id": tid, "label": label}
            else:
                print(f"  [SKIP] {label}: API returned {result} (likely no data)")
        except Exception as e:
            print(f"  [ERR] {label}: {e}")
        time.sleep(2)

if not all_tasks:
    print("\nNo tasks created!")
    sys.exit(0)

print(f"\n=== Polling {len(all_tasks)} tasks ===")
all_tids = [t["id"] for t in all_tasks.values()]
pending = set(all_tids)
waited = 0
while pending and waited < 300:
    time.sleep(5)
    waited += 5
    data = signed_post("/api/cpc/download/pageList.json", {"taskIds": [str(t) for t in all_tids], "pageNo": 1, "pageSize": 100})
    if not isinstance(data, dict):
        continue
    for row in data.get("rows", []):
        tid = row.get("id") or row.get("taskId")
        if not tid or tid not in pending:
            continue
        state = row.get("reportState", "?")
        label = "?"
        for k, t in all_tasks.items():
            if t["id"] == tid:
                label = t["label"]
                break
        if state == "已生成":
            urls = row.get("downloadUrl", [])
            if urls:
                fpath = OUT / f"{label}_2026-06_JUN2026.xlsx"
                size = download_file(urls[0], fpath)
                print(f"  [{waited}s] {label}: DONE ({size:,} bytes)")
            else:
                print(f"  [{waited}s] {label}: DONE but no URL")
            pending.discard(tid)
        elif state == "失败":
            print(f"  [{waited}s] {label}: FAILED (no data for this ad type?)")
            pending.discard(tid)
    if pending:
        print(f"  [{waited}s] {len(pending)} tasks still pending...")

if pending:
    print(f"\nTimeout! Still pending ({len(pending)}): {pending}")
else:
    print(f"\nDone — {len(all_tasks)} reports in {OUT}")
