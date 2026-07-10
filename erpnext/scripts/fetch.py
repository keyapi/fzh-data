#!/usr/bin/env python3
"""ERPNext 生产工单数据拉取 — 按月份拉取工单/Job Card/Stock Entry 到本地 JSON"""
import argparse, json, os, ssl, sys, time, urllib.request
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = Path("/tmp")

# ── 凭证加载 (复用 EN_API 模式) ──────────────────────────
def load_credentials() -> tuple[str, str]:
    """Load API credentials. Priority: env vars > .env file."""
    key = os.environ.get("PROD_ERP_API_KEY") or os.environ.get("ERP_API_KEY", "")
    secret = os.environ.get("PROD_ERP_API_SECRET") or os.environ.get("ERP_API_SECRET", "")
    if key and secret:
        return key, secret

    env_file = PROJECT_ROOT / "EN_API" / ".env"
    if env_file.is_file():
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("PROD_ERP_API_KEY="):
                    key = line.split("=", 1)[1]
                elif line.startswith("PROD_ERP_API_SECRET="):
                    secret = line.split("=", 1)[1]
                elif line.startswith("ERP_API_KEY=") and not key:
                    key = line.split("=", 1)[1]
                elif line.startswith("ERP_API_SECRET=") and not secret:
                    secret = line.split("=", 1)[1]
    return key, secret


def api_get(path: str, key: str, secret: str) -> dict:
    """GET request to ERPNext REST API."""
    url = f"https://erpnext.vilavi.cn{path}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"token {key}:{secret}")
    ctx = ssl.create_default_context()
    try:
        resp = urllib.request.urlopen(req, context=ctx, timeout=60)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {url[:100]}", file=sys.stderr)
        return {"data": []}
    except Exception as e:
        print(f"  Error: {e}", file=sys.stderr)
        return {"data": []}


def fetch_work_orders(start: str, end: str, key: str, secret: str) -> list[dict]:
    """Pull all Work Orders with actual_end_date in [start, end]."""
    print(f"拉取工单 (actual_end_date {start}~{end})...")
    wo_data = []
    # First query with status filter to get total count
    filter_str = f'[["actual_end_date",">=","{start}"],["actual_end_date","<=","{end}"]]'
    fields = '["name","production_item","item_name","qty","produced_qty","open_material_qty","status","actual_start_date","actual_end_date","creation","company","modified_by","bom_no"]'
    path = f"/api/resource/Work%20Order?filters={filter_str}&fields={fields}&limit=500&order_by=actual_end_date%20desc"
    result = api_get(path, key, secret)
    data = result.get("data", [])
    wo_data.extend(data)
    print(f"  共 {len(data)} 条工单")

    # Now fetch individual WOs with operations child table
    print("拉取工单工序明细...")
    wo_full = {}
    for i, wo in enumerate(data):
        wo_name = wo["name"]
        detail = api_get(f"/api/resource/Work%20Order/{wo_name}", key, secret).get("data", {})
        ops = detail.get("operations", [])
        wo_full[wo_name] = {
            "production_item": wo.get("production_item", ""),
            "item_name": wo.get("item_name", ""),
            "qty": wo.get("qty", 0),
            "produced_qty": wo.get("produced_qty", 0),
            "open_material_qty": wo.get("open_material_qty", 0) or 0,
            "status": wo.get("status", ""),
            "creation": wo.get("creation", ""),
            "actual_start_date": wo.get("actual_start_date", ""),
            "actual_end_date": wo.get("actual_end_date", ""),
            "company": wo.get("company", ""),
            "modified_by": wo.get("modified_by", ""),
            "bom_no": wo.get("bom_no", ""),
            "ops_count": len(ops),
            "operations": [{
                "seq": o.get("sequence_id", 0),
                "name": o.get("operation", ""),
                "status": o.get("status", ""),
                "completed_qty": o.get("completed_qty", 0) or 0,
            } for o in ops],
        }
        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{len(data)}")
    print(f"  {len(data)}/{len(data)} 完成")

    # Save
    output = OUTPUT_DIR / "erpnext_wo_data.json"
    with open(output, "w", encoding="utf-8") as f:
        json.dump(wo_full, f, ensure_ascii=False, indent=2)
    print(f"  → {output}")
    return list(wo_full.keys())


def fetch_job_cards(wo_list: list[str], key: str, secret: str) -> dict:
    """Pull all Job Cards (non-cancelled) for given Work Orders."""
    print(f"拉取 Job Card (共 {len(wo_list)} 个工单)...")
    all_jc = {}
    batch_size = 20
    for batch_start in range(0, len(wo_list), batch_size):
        batch = wo_list[batch_start:batch_start + batch_size]
        # Query all JCs from the month via date range
        if batch_start == 0:
            # Bulk pull all recent JCs first
            jc_data = api_get(
                "/api/resource/Job%20Card?fields=[\"name\",\"work_order\",\"owner\",\"operation\",\"for_quantity\",\"total_completed_qty\",\"status\"]&filters=[[\"docstatus\",\"<\",\"2\"]]&limit=10000&order_by=creation%20desc",
                key, secret
            ).get("data", [])
            for jc in jc_data:
                wo = jc.get("work_order", "")
                if wo and wo in wo_list:
                    all_jc.setdefault(wo, []).append(jc)
            print(f"  批量拉取完成, {len(all_jc)} 个工单有 JC 数据")

        # Per-WO fallback for missing
        for wo in batch:
            if wo in all_jc and len(all_jc[wo]) > 0:
                continue
            time.sleep(0.2)
            jcs = api_get(
                f"/api/resource/Job%20Card?filters=[[\"work_order\",\"=\",\"{wo}\"],[\"docstatus\",\"<\",\"2\"]]&fields=[\"name\",\"work_order\",\"owner\",\"operation\",\"for_quantity\",\"total_completed_qty\",\"status\"]&limit=500",
                key, secret
            ).get("data", [])
            if jcs:
                all_jc.setdefault(wo, []).extend(jcs)
        print(f"  {min(batch_start + batch_size, len(wo_list))}/{len(wo_list)}", end="\r")
    print(f"  {len(wo_list)}/{len(wo_list)} 完成")

    output = OUTPUT_DIR / "erpnext_jc_data.json"
    with open(output, "w", encoding="utf-8") as f:
        json.dump(all_jc, f, ensure_ascii=False, indent=2)
    print(f"  → {output}")
    return all_jc


def fetch_version_records(wo_list: list[str], key: str, secret: str) -> dict:
    """Check Version records for 杨义森 involvement."""
    print("拉取 Version 活动记录 (yangyisen92)...")
    # Query all yangyisen Version records
    vdata = api_get(
        '/api/resource/Version?filters=[["ref_doctype","=","Work Order"],["owner","=","yangyisen92@dingtalk.com"]]&fields=["name","docname","owner","modified"]&limit=5000',
        key, secret
    ).get("data", [])

    yang_wos = {}
    for v in vdata:
        wo = v.get("docname", "")
        if wo and wo in wo_list:
            yang_wos.setdefault(wo, []).append({"name": v["name"], "modified": v["modified"]})

    print(f"  杨义森触碰过 {len(yang_wos)} 个工单")

    output = OUTPUT_DIR / "erpnext_version_data.json"
    with open(output, "w", encoding="utf-8") as f:
        json.dump(yang_wos, f, ensure_ascii=False, indent=2)
    print(f"  → {output}")
    return yang_wos


def fetch_stock_entries(wo_list: list[str], key: str, secret: str) -> dict:
    """Pull Manufacture Stock Entries linked to target WOs."""
    print("拉取 Stock Entry (Manufacture)...")
    month_start = min(
        (wo_list[0][:2] if wo_list else "WO-26"),
        key=lambda x: x
    )
    # Bulk pull all Manufacture SEs
    se_data = api_get(
        '/api/resource/Stock%20Entry?filters=[["stock_entry_type","=","Manufacture"]]&fields=["name","work_order","posting_date","owner"]&limit=5000',
        key, secret
    ).get("data", [])

    wo_se = {}
    for se in se_data:
        wo = se.get("work_order", "")
        if wo and wo in wo_list:
            wo_se.setdefault(wo, []).append({
                "name": se["name"],
                "posting_date": se["posting_date"],
                "owner": se["owner"],
            })

    # For key WOs, pull SE items to get actual quantities
    print(f"  拉取 SE 入库明细 (含数量)...")
    for wo in list(wo_se.keys()):
        for se_entry in wo_se[wo]:
            time.sleep(0.15)
            se_detail = api_get(f"/api/resource/Stock%20Entry/{se_entry['name']}", key, secret).get("data", {})
            items = se_detail.get("items", [])
            total_in = sum(
                item.get("qty", 0)
                for item in items
                if item.get("t_warehouse") and not item.get("s_warehouse")
            )
            se_entry["receipt_qty"] = total_in

    output = OUTPUT_DIR / "erpnext_se_data.json"
    with open(output, "w", encoding="utf-8") as f:
        json.dump(wo_se, f, ensure_ascii=False, indent=2)
    print(f"  → {output}")
    return wo_se


def main():
    parser = argparse.ArgumentParser(description="ERPNext 工单数据拉取")
    parser.add_argument("--month", required=True, help="目标月份, 格式 YYYY-MM (如 2026-06)")
    parser.add_argument("--step", choices=["wo", "jc", "se", "version", "all"], default="all",
                        help="只拉取指定步骤 (默认 all)")
    args = parser.parse_args()

    key, secret = load_credentials()
    if not key or not secret or "your_" in key:
        print("✗ API 凭证未配置。请先运行:")
        print("  uv run python erpnext/scripts/setup.py")
        sys.exit(1)

    # Parse month range
    month = args.month
    start = f"{month}-01"
    # Calculate end of month
    year, mon = month.split("-")
    if mon == "12":
        end = f"{int(year)+1}-01-01"
    else:
        end = f"{year}-{int(mon)+1:02d}-01"
    # Use last day of month
    from calendar import monthrange
    last_day = monthrange(int(year), int(mon))[1]
    end = f"{month}-{last_day} 23:59:59"

    print(f"目标月份: {start} ~ {end}")
    print(f"系统: 生产 (erpnext.vilavi.cn)")
    print()

    # Step 1: Work Orders
    if args.step in ("wo", "all"):
        wo_list = fetch_work_orders(start, end, key, secret)
    else:
        wo_list = []

    # Step 2: Version records
    if args.step in ("version", "all") and wo_list:
        fetch_version_records(wo_list, key, secret)

    # Step 3: Job Cards
    if args.step in ("jc", "all") and wo_list:
        fetch_job_cards(wo_list, key, secret)

    # Step 4: Stock Entries
    if args.step in ("se", "all") and wo_list:
        fetch_stock_entries(wo_list, key, secret)

    print()
    print("拉取完成。下一步:")
    print("  uv run python erpnext/scripts/gen_report.py")


if __name__ == "__main__":
    main()
