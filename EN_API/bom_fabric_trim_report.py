# -*- coding: utf-8 -*-
"""三角靠枕 皮壳/内胆 BOM 面料用量下调 —— 只读统计报告（交付物 1，不写任何数据）

需求：
  生产 ERPNext 上，三角靠枕的「皮壳 BOM」面料用量整体下调 30cm、「内胆 BOM」下调 40cm。
  例：1.00 米 -> 0.70 米（皮壳）；1.00 米 -> 0.60 米（内胆）。
  执行前先出这份统计报告给用户确认。

口径（均在生产实测确认）：
  - 三角靠枕   : BOM.item_name 含「三角」且含「靠枕」（同 bom_cost_list_excel.classify）
  - 皮壳 BOM   : BOM.item 以 PK#   开头
  - 内胆 BOM   : BOM.item 以 ND#   开头（普通内胆）/ DKND# 开头（底开内胆）
  - 状态为默认 : BOM.is_default = 1（BOM 单据没有 status 字段，只有 is_active / is_default）
  - 面料       : **组件物料的 Item Group 祖先链里含「面料」**（树：所有物料组 > 原材料 > 主材 > 面料）
                 例 春亚纺 < 内胆布 < 面料 = 面料；绗缝布 < 面料 = 面料；
                    流苏 < 绳线 < 辅材、尼龙拉链 < 拉链 < 辅材、扣胚 < 扣类 < 辅材 = 非面料。
                 这是系统既有的权威口径，不靠 uom/名称猜。

报告内容：把这 902 份 BOM 的**全部子表明细**都列出来（不只面料），逐行标注是否面料与处理结果。

已知边界：
  - 26 行面料 qty 不足下调值（如 0.09~0.2 米），扣减会变负 -> 不动，单独一张 sheet 列出
  - 子表不能用 /api/resource/BOM Item list（生产 403），必须逐份取父单据

用法:
  python EN_API/bom_fabric_trim_report.py                    # prod，默认
  python EN_API/bom_fabric_trim_report.py --env test
  python EN_API/bom_fabric_trim_report.py --workers 16

输出（EN_API/out/）:
  bom_fabric_trim_report_<ts>.xlsx   统计报告
  bom_fabric_trim_backup_<ts>.json   完整 BOM 单据快照（回滚用）
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from decimal import Decimal
from itertools import groupby
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

sys.stdout.reconfigure(encoding="utf-8")

_DIR = Path(__file__).resolve().parent
OUT_DIR = _DIR / "out"

ENV_URLS = {"prod": "https://erpnext.vilavi.cn", "test": "https://ensh.vilavi.cn"}
ENV_KEYS = {
    "prod": ("PROD_ERP_API_KEY", "PROD_ERP_API_SECRET"),
    "test": ("TEST_ERP_API_KEY", "TEST_ERP_API_SECRET"),
}

# ── 业务口径 ─────────────────────────────────────────
FABRIC_ROOT = "面料"           # Item Group 树里「面料」这一层的组名，祖先链含它即为面料
DELTA = {"皮壳": Decimal("0.30"), "内胆": Decimal("0.40"), "底开内胆": Decimal("0.40")}

KIND_ORDER = ["皮壳", "内胆", "底开内胆"]

# 明细表列（一行一个物料；IDENT_COLS 会在同一 BOM 内纵向合并）
DETAIL_HEADERS = [
    "BOM", "类型", "物料", "物料名称", "行号", "组件ITEM", "组件名称", "组件物料组",
    "是否面料", "单位", "原数量", "下调", "新数量", "处理结果",
]
IDENT_COLS = (1, 2, 3, 4)          # BOM / 类型 / 物料 / 物料名称 —— 同一 BOM 内合并单元格
DETAIL_WIDTHS = [40, 9, 26, 34, 5, 34, 34, 14, 9, 7, 10, 8, 10, 16]


def load_env(env: str) -> tuple[str, str]:
    """读 EN_API/.env（必要时回退上层 .env）。"""
    vals: dict[str, str] = {}
    for p in (_DIR / ".env", _DIR.parent / ".env", _DIR.parent.parent / ".env"):
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                v = v[1:-1]
            vals.setdefault(k.strip(), v)
    key_name, sec_name = ENV_KEYS[env]
    return vals.get(key_name, ""), vals.get(sec_name, "")


class _NoExpectAdapter(HTTPAdapter):
    def send(self, request, **kwargs):  # noqa: ANN001
        request.headers.pop("Expect", None)
        return super().send(request, **kwargs)


class ErpnextClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"token {api_key}:{api_secret}"
        self.session.mount("https://", _NoExpectAdapter())
        self.session.mount("http://", _NoExpectAdapter())

    def _request(self, method: str, path: str, *, retries: int = 3,
                 retry_delay: float = 3.0, **kwargs: Any) -> requests.Response:
        timeout = kwargs.pop("timeout", (30, 300))
        url = f"{self.base_url}{path}"
        last: Exception | None = None
        for attempt in range(retries + 1):
            try:
                r = self.session.request(method, url, timeout=timeout, **kwargs)
                r.raise_for_status()
                return r
            except Exception as exc:  # noqa: BLE001
                last = exc
                if attempt < retries:
                    time.sleep(retry_delay * (attempt + 1))
        assert last is not None
        raise last

    def get_list(self, doctype: str, filters: list | None = None,
                 fields: list[str] | None = None, limit_page_length: int = 0) -> list[dict]:
        params: dict[str, str] = {"limit_page_length": str(limit_page_length)}
        if filters is not None:
            params["filters"] = json.dumps(filters)
        if fields is not None:
            params["fields"] = json.dumps(fields)
        return self._request("GET", f"/api/resource/{quote(doctype, safe='')}",
                             params=params).json()["data"]

    def get_doc(self, doctype: str, name: str) -> dict:
        return self._request(
            "GET", f"/api/resource/{quote(doctype, safe='')}/{quote(name, safe='')}"
        ).json()["data"]

    def get_items_meta(self, codes: list[str], batch: int = 60) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for s in range(0, len(codes), batch):
            rows = self.get_list(
                "Item", filters=[["name", "in", codes[s:s + batch]]],
                fields=["name", "item_code", "item_name", "item_group", "stock_uom"],
            )
            for r in rows:
                out[r["name"]] = r
        return out


class ItemGroupTree:
    """Item Group 树：判断某物料组是否属于「面料」（祖先链含 FABRIC_ROOT）。"""

    def __init__(self, groups: list[dict]) -> None:
        self.parent = {g["name"]: (g["parent_item_group"] or "") for g in groups}
        self._cache: dict[str, bool] = {}

    def chain(self, name: str) -> list[str]:
        out: list[str] = []
        cur = name
        while cur and cur not in out:
            out.append(cur)
            cur = self.parent.get(cur, "")
        return out

    def is_fabric(self, name: str) -> bool:
        if not name:
            return False
        if name not in self._cache:
            self._cache[name] = FABRIC_ROOT in self.chain(name)
        return self._cache[name]


def kind_of(item_code: str) -> str | None:
    if item_code.startswith("PK#"):
        return "皮壳"
    if item_code.startswith("DKND#"):
        return "底开内胆"
    if item_code.startswith("ND#"):
        return "内胆"
    return None


def is_triangle_backrest(name: str) -> bool:
    return bool(name) and "三角" in name and "靠枕" in name


def new_qty(qty: float, delta: Decimal) -> Decimal:
    return (Decimal(str(qty)) - delta).quantize(Decimal("0.01"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env", choices=("prod", "test"), default="prod")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args()

    key, sec = load_env(args.env)
    if not key or not sec:
        print(f"✗ 缺少 {ENV_KEYS[args.env]} 凭证")
        return 1
    base = ENV_URLS[args.env]
    client = ErpnextClient(base, key, sec)
    print(f"环境: {args.env} ({base})\n")

    # 1) Item Group 树（面料判定口径）
    print("[1/6] 取 Item Group 树（面料判定口径）…")
    tree = ItemGroupTree(client.get_list(
        "Item Group",
        fields=["name", "item_group_name", "parent_item_group", "is_group"],
    ))
    print(f"      物料组 {len(tree.parent)} 个；「{FABRIC_ROOT}」祖先链: "
          f"{' < '.join(tree.chain(FABRIC_ROOT))}")

    # 2) BOM 清单
    print("\n[2/6] 拉取三角靠枕 BOM 清单 …")
    boms = client.get_list(
        "BOM",
        filters=[["item_name", "like", "%三角靠枕%"],
                 ["is_default", "=", 1],
                 ["docstatus", "=", 1],
                 ["is_active", "=", 1]],
        fields=["name", "item", "item_name", "is_default", "is_active", "docstatus"],
    )
    scoped = []
    for b in boms:
        k = kind_of(b["item"])
        if k and is_triangle_backrest(b["item_name"]):
            b["_kind"] = k
            scoped.append(b)
    kind_by_name = {b["name"]: b["_kind"] for b in scoped}
    print(f"      命中 {len(boms)} 份，其中 皮壳/内胆/底开内胆 {len(scoped)} 份")
    print("      类型分布:", dict(Counter(b["_kind"] for b in scoped)))

    # 3) 逐份取完整 BOM 单据（子表无法 list，生产 403）
    print(f"\n[3/6] 逐份取 BOM 单据（{args.workers} 线程）…")
    docs: list[dict] = []
    names = [b["name"] for b in scoped]
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(client.get_doc, "BOM", n): n for n in names}
        for i, fut in enumerate(as_completed(futures), start=1):
            nm = futures[fut]
            try:
                docs.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                print(f"      [WARN] 取 {nm} 失败: {exc}")
            if i % 200 == 0 or i == len(names):
                print(f"      已取 {i}/{len(names)}")

    # 4) 全部组件物料的 meta（含非面料行）
    print("\n[4/6] 查询全部组件物料的 item_group …")
    all_codes = sorted({i["item_code"] for d in docs for i in (d.get("items") or [])})
    meta = client.get_items_meta(all_codes)
    missing = [c for c in all_codes if c not in meta]
    if missing:
        print(f"      [WARN] {len(missing)} 个组件查不到 meta，样例: {missing[:5]}")
    print(f"      组件物料 {len(all_codes)} 个，已取 meta {len(meta)} 个")

    # 5) 逐行分类（全部行都进报告）
    print("\n[5/6] 逐行分类 …")
    detail: dict[str, list[dict]] = {k: [] for k in KIND_ORDER}
    to_adjust: list[dict] = []
    negatives: list[dict] = []
    non_fabric: list[dict] = []
    bom_rows = Counter()
    fabric_rows = Counter()

    for d in docs:
        k = kind_by_name[d["name"]]
        bom_rows[k] += 1
        delta = DELTA[k]
        for idx, row in enumerate(d.get("items") or [], start=1):
            cm = meta.get(row["item_code"], {})
            grp = cm.get("item_group", "")
            fab = tree.is_fabric(grp)
            rec = {
                "bom": d["name"], "kind": k, "item": d["item"], "item_name": d["item_name"],
                "idx": idx,
                "code": row["item_code"],
                "name": cm.get("item_name") or row.get("item_name") or "",
                "group": grp, "chain": " < ".join(tree.chain(grp)) if grp else "",
                "is_fabric": fab, "uom": row.get("uom"), "qty": float(row.get("qty") or 0),
                "delta": delta, "row_name": row.get("name"),
            }
            if not fab:
                rec["status"] = "不调-非面料"; rec["new"] = None
                non_fabric.append(rec)
            else:
                fabric_rows[k] += 1
                nq = new_qty(rec["qty"], delta)
                rec["new"] = nq
                if nq < 0:
                    rec["status"] = "跳过-会变负"
                    negatives.append(rec)
                else:
                    rec["status"] = "待调整"
                    to_adjust.append(rec)
            detail[k].append(rec)

    planned: dict[str, dict[str, str]] = {}
    for k in KIND_ORDER:
        detail[k].sort(key=lambda r: (r["bom"], r["idx"]))   # 稳定排序（docs 是并发完成顺序）
    to_adjust.sort(key=lambda r: (r["bom"], r["idx"]))
    negatives.sort(key=lambda r: (r["bom"], r["idx"]))
    non_fabric.sort(key=lambda r: (r["bom"], r["idx"]))
    for r in to_adjust:
        planned.setdefault(r["bom"], {})[r["row_name"]] = str(r["new"])

    # 6) 输出
    print("\n[6/6] 写报告与备份 …")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    xlsx = args.out_dir / f"bom_fabric_trim_report_{ts}.xlsx"
    backup = args.out_dir / f"bom_fabric_trim_backup_{ts}.json"

    summary = {
        "env": args.env, "base_url": base, "generated_at": datetime.now().isoformat(),
        "fabric_rule": f"Item Group 祖先链含「{FABRIC_ROOT}」",
        "bom_rows": dict(bom_rows),
        "fabric_rows": dict(fabric_rows),
        "total_item_rows": sum(len(v) for v in detail.values()),
        "adjust_rows": {k: sum(1 for r in detail[k] if r["status"] == "待调整") for k in KIND_ORDER},
        "negative_rows": len(negatives), "non_fabric_rows": len(non_fabric),
        "planned_boms": len(planned), "planned_total": len(to_adjust),
        "uom_mismatch": [f'{r["code"]} uom={r["uom"]}' for r in to_adjust if r["uom"] != "米"][:20],
    }
    write_report(xlsx, summary, detail, to_adjust, negatives, non_fabric)

    payload = {
        "meta": {
            "generated_at": datetime.now().isoformat(), "environment": args.env,
            "base_url": base,
            "scope": "三角靠枕 皮壳BOM(-30cm)/内胆BOM(-40cm), is_default=1",
            "fabric_rule": summary["fabric_rule"],
            "note": "boms 是完整 BOM 单据快照（含 items 原数组），可直接 PUT 回滚",
            "summary": summary,
        },
        "planned": planned,
        "boms": docs,
    }
    backup.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    # 控制台汇总
    print("\n" + "=" * 64)
    print("汇总")
    print("=" * 64)
    print(f"  范围: 三角靠枕 BOM (is_default=1) 共 {sum(bom_rows.values())} 份，"
          f"子表明细共 {summary['total_item_rows']} 行")
    for k in KIND_ORDER:
        print(f"  {k:<6} BOM {bom_rows[k]:>4} 份 | 明细 {len(detail[k]):>4} 行 | "
              f"面料 {fabric_rows[k]:>4} | 待调整 {summary['adjust_rows'][k]:>4} | 下调 -{DELTA[k]}")
    print(f"\n  面料待调整 : {len(to_adjust)} 行，涉及 {len(planned)} 份 BOM")
    print(f"  跳过-会变负: {len(negatives)} 行")
    print(f"  不调-非面料: {len(non_fabric)} 行")
    if summary["uom_mismatch"]:
        print(f"\n  ⚠ 面料行里 uom 不是「米」的 {len(summary['uom_mismatch'])} 个样例: {summary['uom_mismatch']}")
    print(f"\n✓ 报告: {xlsx}")
    print(f"✓ 备份: {backup}  ({backup.stat().st_size / 1024 / 1024:.1f} MB)")
    return 0


def write_report(out: Path, summary: dict, detail: dict[str, list[dict]],
                 to_adjust: list[dict], negatives: list[dict], non_fabric: list[dict]) -> None:
    wb = Workbook()
    head_fill = PatternFill("solid", fgColor="DDEBF7")
    red_fill = PatternFill("solid", fgColor="FFC7CE")
    green_fill = PatternFill("solid", fgColor="E2EFDA")
    gray_fill = PatternFill("solid", fgColor="EDEDED")

    # ── 汇总 ──
    ws = wb.active
    ws.title = "汇总"
    ws.append(["三角靠枕 皮壳/内胆 BOM 面料用量下调 — 统计（只读，未写库）"])
    ws["A1"].font = Font(bold=True, size=12)
    ws.append([])
    ws.append(["环境", summary["env"], "生成时间", summary["generated_at"]])
    ws.append(["面料判定口径", summary["fabric_rule"],
               "", "（Item Group 树：所有物料组 > 原材料 > 主材 > 面料）"])
    ws.append([])
    ws.append(["类型", "BOM份数", "子表明细行数", "其中面料行", "待调整行数", "下调幅度"])
    for k in KIND_ORDER:
        ws.append([k, summary["bom_rows"].get(k, 0), len(detail[k]),
                   summary["fabric_rows"].get(k, 0), summary["adjust_rows"].get(k, 0),
                   f"-{DELTA[k]}米"])
    ws.append(["合计", sum(summary["bom_rows"].values()), summary["total_item_rows"],
               sum(summary["fabric_rows"].values()), summary["planned_total"], ""])
    ws.append([])
    ws.append(["面料待调整", summary["planned_total"], f"涉及 {summary['planned_boms']} 份 BOM"])
    ws.append(["跳过-调后会变负", summary["negative_rows"], "面料但数量不足下调值，不动"])
    ws.append(["不调-非面料", summary["non_fabric_rows"], "拉链/扣胚/流苏/滚边绳等辅料，不动"])
    for c in ws[6]:
        c.font = Font(bold=True)
        c.fill = head_fill
    for col, w in {"A": 34, "B": 14, "C": 16, "D": 14, "E": 14, "F": 34}.items():
        ws.column_dimensions[col].width = w

    # ── 明细表：一行一个物料；同一 BOM 的 BOM/类型/物料/物料名称 四列纵向合并 ──
    def write_detail(title: str, recs: list[dict]) -> None:
        sheet = wb.create_sheet(title)
        sheet.append(DETAIL_HEADERS)
        for c in sheet[1]:
            c.font = Font(bold=True)
            c.fill = head_fill
            c.alignment = Alignment(horizontal="center", vertical="center")

        row = 2
        for _bom, grp in groupby(recs, key=lambda r: r["bom"]):
            grp = list(grp)
            start = row
            for j, r in enumerate(grp):
                first = j == 0
                sheet.append([
                    r["bom"] if first else None,
                    r["kind"] if first else None,
                    r["item"] if first else None,
                    r["item_name"] if first else None,
                    r["idx"], r["code"], r["name"], r["group"],
                    "是" if r["is_fabric"] else "否", r["uom"], r["qty"],
                    float(r["delta"]) if r["is_fabric"] else "",
                    "" if r["new"] is None else float(r["new"]), r["status"],
                ])
                if not r["is_fabric"]:
                    for ci in range(1, len(DETAIL_HEADERS) + 1):
                        sheet.cell(row=row, column=ci).fill = gray_fill
                elif r["status"] == "跳过-会变负":
                    for ci in range(1, len(DETAIL_HEADERS) + 1):
                        sheet.cell(row=row, column=ci).fill = red_fill
                elif r["status"] == "待调整":
                    for ci in range(9, len(DETAIL_HEADERS) + 1):
                        sheet.cell(row=row, column=ci).fill = green_fill
                row += 1
            end = row - 1
            for col in IDENT_COLS:                      # 纵向合并 BOM/类型/物料/物料名称
                if end > start:
                    sheet.merge_cells(start_row=start, start_column=col,
                                      end_row=end, end_column=col)
                cell = sheet.cell(row=start, column=col)
                cell.alignment = Alignment(vertical="center", wrap_text=(col == 4))

        for i, w in enumerate(DETAIL_WIDTHS, start=1):
            sheet.column_dimensions[get_column_letter(i)].width = w
        sheet.freeze_panes = "E2"

    INNER = ("内胆", "底开内胆")
    write_detail("皮壳BOM", detail["皮壳"])
    write_detail("内胆BOM", detail["内胆"] + detail["底开内胆"])
    wb.save(str(out))
if __name__ == "__main__":
    raise SystemExit(main())
