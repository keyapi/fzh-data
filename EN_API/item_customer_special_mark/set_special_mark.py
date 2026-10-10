# -*- coding: utf-8 -*-
"""给 EN「客户物料」子表 (Item Customer Detail) 批量打 special_mark=碎海绵。

数据源: EN_API/数据源/2026年下单表.xlsx → 工作表「2026年度FBA订单（新）」(表头在第 2 行, 通途SKU 列)
映射:   通途SKU == Item.customer_items.ref_code  (通途SKU/客户物料号, 全局唯一)
目标:   命中的子表行 special_mark = 碎海绵

子命令:
  stats     只读盘点 → out/special_mark_stats_<stamp>.{csv,json}
  dry-run   只读打印「现值 → 目标值」
  apply     写生产 (先 snapshot → 建 zz_ Server Script → 调用 → 删脚本 → 回读)
  verify    只读回读校验
  rollback  按 snapshot 把 special_mark 还原 (同样走 zz_ 脚本, 用完即删)

默认 --env prod。写生产前请先确认字段 special_mark 已存在 (Phase 1/2)。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
EN_API = HERE.parent
OUT = EN_API / "out"
XLSX = EN_API / "数据源" / "2026年下单表.xlsx"
SHEET = "2026年度FBA订单（新）"
TT_COL = "通途SKU"
TARGET_MARK = "碎海绵"
CHILD_DT = "Item Customer Detail"
ZZ_SCRIPT_NAME = "zz_set_item_customer_special_mark"
ZZ_API_METHOD = "zz_set_item_customer_special_mark"

ZZ_BODY = """
pairs = json.loads(frappe.form_dict.get("pairs") or "[]")
n = 0
for p in pairs:
    frappe.db.set_value("Item Customer Detail", p[0], "special_mark", p[1])
    n = n + 1
frappe.db.commit()
frappe.response["message"] = {"updated": n}
"""


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for path in (EN_API.parent / ".env", EN_API / ".env"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("'\"")
    return env


class Client:
    def __init__(self, which: str) -> None:
        env = load_env()
        if which == "prod":
            self.base = "https://erpnext.vilavi.cn"
            self.key = env["PROD_ERP_API_KEY"]
            self.sec = env["PROD_ERP_API_SECRET"]
        else:
            self.base = env.get("TEST_ERP_URL", "https://ensh.vilavi.cn")
            self.key = env["TEST_ERP_API_KEY"]
            self.sec = env["TEST_ERP_API_SECRET"]

    def _req(self, method: str, path: str, body=None):
        url = self.base + path
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"token {self.key}:{self.sec}")
        req.add_header("Content-Type", "application/json")
        try:
            raw = urllib.request.urlopen(req, timeout=180).read().decode("utf-8")
            return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            raise RuntimeError(f"{method} {path} -> HTTP {e.code}: {detail[:400]}") from None

    def get_list(self, dt, filters, fields, limit=0):
        q = urllib.parse.urlencode({
            "filters": json.dumps(filters),
            "fields": json.dumps(fields),
            "limit_page_length": str(limit),
        })
        return self._req("GET", f"/api/resource/{urllib.parse.quote(dt)}?{q}").get("data") or []

    def get_doc(self, dt, name):
        return self._req("GET", f"/api/resource/{urllib.parse.quote(dt)}/{urllib.parse.quote(name, safe='')}")["data"]

    def method(self, path, body):
        return self._req("POST", f"/api/method/{path}", body)


def load_skus() -> list[str]:
    df = pd.read_excel(XLSX, sheet_name=SHEET, header=1)
    df.columns = [str(c).replace("\n", "").strip() for c in df.columns]
    if TT_COL not in df.columns:
        raise SystemExit(f"工作表缺少列 {TT_COL!r}，现有: {list(df.columns)}")
    return sorted({str(x).strip() for x in df[TT_COL].dropna() if str(x).strip()})


def resolve_targets(client: Client, skus: list[str]) -> list[dict]:
    sku_set = set(skus)
    items = client.get_list(
        "Item",
        [["Item Customer Detail", "ref_code", "in", skus]],
        ["name", "item_group"],
    )
    rows: list[dict] = []
    for nm in sorted({it["name"] for it in items}):
        doc = client.get_doc("Item", nm)
        for ci in doc.get("customer_items") or []:
            rc = (ci.get("ref_code") or "").strip()
            if rc in sku_set:
                rows.append({
                    "item_code": doc["name"],
                    "item_group": doc.get("item_group"),
                    "row_name": ci.get("name"),
                    "idx": ci.get("idx"),
                    "ref_code": rc,
                    "customer_group": ci.get("customer_group"),
                    "special_mark": ci.get("special_mark") or "",
                })
    rows.sort(key=lambda r: (r["item_code"], r["idx"] or 0))
    return rows


def coverage_report(rows: list[dict], skus: list[str]) -> tuple[list[str], list[str]]:
    covered = {r["ref_code"] for r in rows}
    return sorted(set(skus) & covered), sorted(set(skus) - covered)


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def cmd_stats(client: Client) -> None:
    skus = load_skus()
    rows = resolve_targets(client, skus)
    hit, miss = coverage_report(rows, skus)
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = _stamp()
    csv_path = OUT / f"special_mark_stats_{stamp}.csv"
    json_path = OUT / f"special_mark_stats_{stamp}.json"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["item_code", "item_group", "row_name", "idx", "ref_code", "customer_group", "special_mark"])
        w.writeheader()
        w.writerows(rows)
    json_path.write_text(json.dumps({
        "generated": stamp, "n_skus": len(skus), "n_items": len({r["item_code"] for r in rows}),
        "n_rows": len(rows), "skus_matched": len(hit), "skus_unmatched": miss, "rows": rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"SKU 总数={len(skus)}  命中SKU={len(hit)}  未命中={len(miss)}")
    print(f"物料数={len({r['item_code'] for r in rows})}  子表行数={len(rows)}")
    print(f"CSV:  {csv_path}")
    print(f"JSON: {json_path}")
    if miss:
        print("未命中 SKU:", json.dumps(miss, ensure_ascii=False))


def cmd_dry_run(client: Client) -> None:
    skus = load_skus()
    rows = resolve_targets(client, skus)
    print(f"{'item_code':<38}{'row':<12}{'ref_code':<30}{'now':<8}-> target")
    for r in rows:
        flag = "" if r["special_mark"] == TARGET_MARK else "  *"
        print(f"{r['item_code']:<38}{r['row_name']:<12}{r['ref_code']:<30}{r['special_mark']!r:<8}-> {TARGET_MARK}{flag}")
    print(f"合计 {len(rows)} 行 (物料 {len({r['item_code'] for r in rows})} 个)")


def _deploy_zz(client: Client) -> None:
    payload = {
        "doctype": "Server Script",
        "name": ZZ_SCRIPT_NAME,
        "script_type": "API",
        "api_method": ZZ_API_METHOD,
        "script": ZZ_BODY,
        "allow_guest": 0,
    }
    client._req("POST", f"/api/resource/{urllib.parse.quote('Server Script')}", payload)


def _remove_zz(client: Client) -> None:
    try:
        client._req("DELETE", f"/api/resource/{urllib.parse.quote('Server Script')}/{urllib.parse.quote(ZZ_SCRIPT_NAME, safe='')}")
    except RuntimeError as e:
        print("删脚本告警:", e)


def _run_pairs(client: Client, pairs: list[list[str]]) -> int:
    _deploy_zz(client)
    try:
        res = client.method(ZZ_API_METHOD, {"pairs": json.dumps(pairs)})
        return (res.get("message") or {}).get("updated", 0)
    finally:
        _remove_zz(client)


def cmd_apply(client: Client, yes: bool) -> None:
    skus = load_skus()
    rows = resolve_targets(client, skus)
    todo = [r for r in rows if r["special_mark"] != TARGET_MARK]
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = _stamp()
    snap = OUT / f"special_mark_snapshot_{stamp}.json"
    snap.write_text(json.dumps({"generated": stamp, "target": TARGET_MARK, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"快照: {snap}  (共 {len(rows)} 行, 待改 {len(todo)} 行)")
    if not yes:
        print("(未传 --yes, 仅快照, 未写库)")
        return
    if not todo:
        print("无待改行")
        return
    pairs = [[r["row_name"], TARGET_MARK] for r in todo]
    n = _run_pairs(client, pairs)
    print(f"已写 {n} 行")
    cmd_verify(client)


def cmd_verify(client: Client) -> None:
    skus = load_skus()
    rows = resolve_targets(client, skus)
    ok = [r for r in rows if r["special_mark"] == TARGET_MARK]
    bad = [r for r in rows if r["special_mark"] != TARGET_MARK]
    print(f"目标行中已标记={len(ok)}/{len(rows)}")
    if bad:
        print("未生效:", json.dumps([r["row_name"] for r in bad], ensure_ascii=False))
    try:
        all_marked = client.get_list(CHILD_DT, [["special_mark", "=", TARGET_MARK]], ["name"])
        print(f"全库 special_mark={TARGET_MARK} 的行数: {len(all_marked)}")
    except RuntimeError as e:
        print(f"(全库计数不可用——子表 REST list 常 403: {str(e)[:80]})")


def _is_keep_group(item_group: str) -> bool:
    g = item_group or ""
    return ("三角" in g) or ("平条" in g)


def cmd_fix_scope(client: Client, yes: bool) -> None:
    """修正范围：只保留 item_group 含「三角」或「平条」的行，其余清空。"""
    skus = load_skus()
    rows = resolve_targets(client, skus)
    keep = [r for r in rows if _is_keep_group(r["item_group"])]
    drop = [r for r in rows if not _is_keep_group(r["item_group"])]
    todo = [r for r in drop if (r["special_mark"] or "") != ""]
    print(f"总行 {len(rows)} | 保留 {len(keep)} | 清除(范围外) {len(drop)} | 其中待清 {len(todo)}")
    for r in drop:
        print(f"  DROP {r['item_code']:<38}{r['item_group']:<14}{r['row_name']:<12}{r['special_mark']!r}")
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = _stamp()
    snap = OUT / f"special_mark_scopefix_snapshot_{stamp}.json"
    snap.write_text(json.dumps({"generated": stamp, "rows": rows, "dropped_rows": todo}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"快照: {snap}")
    if not yes:
        print("(未传 --yes, 仅快照, 未写库)")
        return
    if not todo:
        print("无待清行")
        return
    pairs = [[r["row_name"], ""] for r in todo]
    print(f"已清 {_run_pairs(client, pairs)} 行")
    cmd_verify(client)


def cmd_rollback(client: Client, snap_path: str, yes: bool) -> None:
    data = json.loads(Path(snap_path).read_text(encoding="utf-8"))
    pairs = [[r["row_name"], r.get("special_mark") or ""] for r in data["rows"]]
    print(f"按快照还原 {len(pairs)} 行 (快照 {snap_path})")
    if not yes:
        print("(未传 --yes, 未写库)")
        return
    print(f"已还原 {_run_pairs(client, pairs)} 行")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", choices=["stats", "dry-run", "apply", "verify", "rollback", "fix-scope"])
    ap.add_argument("--env", choices=["prod", "test"], default="prod")
    ap.add_argument("--yes", action="store_true", help="apply/rollback 真正写库")
    ap.add_argument("--snapshot", default=None, help="rollback 用快照路径")
    args = ap.parse_args()
    client = Client(args.env)
    print(f"env={args.env} base={client.base}")
    if args.cmd == "stats":
        cmd_stats(client)
    elif args.cmd == "dry-run":
        cmd_dry_run(client)
    elif args.cmd == "apply":
        cmd_apply(client, args.yes)
    elif args.cmd == "verify":
        cmd_verify(client)
    elif args.cmd == "rollback":
        if not args.snapshot:
            raise SystemExit("rollback 需要 --snapshot <path>")
        cmd_rollback(client, args.snapshot, args.yes)
    elif args.cmd == "fix-scope":
        cmd_fix_scope(client, args.yes)


if __name__ == "__main__":
    main()
