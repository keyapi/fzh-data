# -*- coding: utf-8 -*-
"""EN `Delivery Note` 单据级补证（**有界只读**）：只查证据用到的 DN，不全量扫。

用法
    uv run python scripts/en_dn_items_evidence_fetch.py \
        --from-xlsx "D:/Work/fzh-order-store/analysis/仓库归属_A337_v6r8b_2026-10-30.xlsx" \
        --out "D:/Work/fzh-order-store/analysis/en_dn_items_evidence_2026-10-30.json"

规则
- 只发 GET：`/api/resource/Delivery Note/<name>`（主键直查，不用无索引条件扫描）。
- DN 清单来自工作簿 `旧151逐行对账` / `未证13逐行对账` 的 `DN源行`、`DN源行_同产品键`
  里的证据 ID → `DN证据明细.源行号` → `DN单号`；去重后逐单查询。
- 子表 `Delivery Note Item` 不能直接 list（403 PermissionError），故按单取文档。
- 只保留需要的字段；原始响应按单裁剪后落盘（不存整文档，避免体积与敏感字段扩散）。
- 逐单记录状态码/耗时；任何非 200 也记录，不静默跳过。
- 输出 JSON 缓存 + manifest（DN 清单来源、请求数、状态码分布、耗时、输出 SHA）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests

BASE = "https://erpnext.vilavi.cn"
ENV_PATH = Path("D:/Work/赛狐/Cursor/EN_API/.env")
DOC_FIELDS = ("name", "docstatus", "is_return", "posting_date", "customer", "status",
              "set_target_warehouse", "po_no")
ITEM_FIELDS = ("name", "item_code", "item_name", "qty", "uom", "so_detail", "warehouse",
               "against_sales_order")


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def dns_from_workbook(path: Path) -> tuple[list[str], dict]:
    xl = pd.ExcelFile(path)
    dn_tbl = pd.read_excel(xl, sheet_name="DN证据明细")
    by_row = dn_tbl.set_index("源行号")["DN单号"].to_dict()
    rows, names = [], set()
    for sheet in ("旧151逐行对账", "未证13逐行对账"):
        df = pd.read_excel(xl, sheet_name=sheet)
        for col in ("DN源行", "DN源行_同产品键"):
            for cell in df[col].fillna("").astype(str):
                for tok in cell.split(";"):
                    tok = tok.strip()
                    if not tok.startswith("DN:"):
                        continue
                    rid = int(tok.split(":")[1])
                    names.add(by_row[rid])
                    rows.append(dict(来源表=sheet, 列=col, 证据ID=tok, 源行号=rid,
                                     DN单号=by_row[rid]))
    return sorted(names), dict(引用记录数=len(rows), 唯一DN数=len(names))


def fetch_one(session: requests.Session, name: str) -> dict:
    t0 = time.time()
    url = f"{BASE}/api/resource/Delivery Note/{quote(name, safe='')}"
    rec = dict(dn=name)
    try:
        r = session.get(url, timeout=90)
    except requests.RequestException as exc:
        rec.update(status="EXC", error=repr(exc)[:300], elapsed_s=round(time.time() - t0, 3))
        return rec
    rec["http_status"] = r.status_code
    rec["elapsed_s"] = round(time.time() - t0, 3)
    rec["bytes"] = len(r.content)
    if r.status_code != 200:
        rec["error"] = r.text[:300]
        return rec
    d = r.json().get("data", {})
    rec["doc"] = {k: d.get(k) for k in DOC_FIELDS}
    rec["items"] = [{k: it.get(k) for k in ITEM_FIELDS} for it in (d.get("items") or [])]
    rec["item_count"] = len(rec["items"])
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description="EN DN 单据级补证（有界只读）")
    ap.add_argument("--from-xlsx", default="D:/Work/fzh-order-store/analysis/"
                                          "仓库归属_A337_v6r8b_2026-10-30.xlsx")
    ap.add_argument("--out", default="D:/Work/fzh-order-store/analysis/"
                                     "en_dn_items_evidence_2026-10-30.json")
    ap.add_argument("--sleep", type=float, default=0.2, help="请求间隔秒，避免压站")
    ap.add_argument("--max-dn", type=int, default=200, help="硬上限，防止误触全量")
    args = ap.parse_args()

    names, src_stat = dns_from_workbook(Path(args.from_xlsx))
    if len(names) > args.max_dn:
        raise SystemExit(f"DN 数量 {len(names)} 超过上限 {args.max_dn}，拒绝执行（有界原则）")

    env = load_env(ENV_PATH)
    key, secret = env.get("ERP_API_KEY"), env.get("ERP_API_SECRET")
    if not key or not secret:
        raise SystemExit("EN_API/.env 缺少 ERP_API_KEY / ERP_API_SECRET")
    token = f"token {key}:{secret}"
    if token in json.dumps(src_stat):
        raise SystemExit("凭证不得进入产物")
    session = requests.Session()
    session.headers["Authorization"] = token
    session.headers.pop("Expect", None)

    started = datetime.now(timezone.utc)
    results = []
    for i, name in enumerate(names, 1):
        results.append(fetch_one(session, name))
        if args.sleep:
            time.sleep(args.sleep)
        if i % 20 == 0:
            print(f"  …{i}/{len(names)}")

    ok = [r for r in results if r.get("http_status") == 200]
    out = dict(
        endpoint=f"{BASE}/api/resource/Delivery Note/<name>",
        fetched_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        started_at_utc=started.isoformat(timespec="seconds"),
        source_workbook=str(args.from_xlsx),
        source_workbook_sha256=hashlib.sha256(Path(args.from_xlsx).read_bytes()).hexdigest(),
        dn_list_source=src_stat,
        request_count=len(results),
        ok_count=len(ok),
        status_counts={str(s): sum(1 for r in results if str(r.get("http_status", r.get("status"))) == str(s))
                       for s in sorted({str(r.get("http_status", r.get("status"))) for r in results})},
        total_items=sum(len(r.get("items") or []) for r in ok),
        results=results,
    )
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    manifest = dict(
        endpoint=out["endpoint"], fetched_at_utc=out["fetched_at_utc"],
        request_count=out["request_count"], ok_count=out["ok_count"],
        status_counts=out["status_counts"], total_items=out["total_items"],
        dn_list_source=src_stat, source_workbook=out["source_workbook"],
        source_workbook_sha256=out["source_workbook_sha256"],
        output=dict(path=str(args.out), sha256=hashlib.sha256(Path(args.out).read_bytes()).hexdigest(),
                    bytes=Path(args.out).stat().st_size),
        read_only=True,
        note="仅 GET；按 DN 主键逐单取文档（子表 Delivery Note Item 直接 list 会 403）；"
             "只保留 DOC_FIELDS/ITEM_FIELDS，不落整文档。",
    )
    Path(str(args.out) + ".manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in
                      ("request_count", "ok_count", "status_counts", "total_items")},
                     ensure_ascii=False))
    print("缓存：", args.out, "\nmanifest：", str(args.out) + ".manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
