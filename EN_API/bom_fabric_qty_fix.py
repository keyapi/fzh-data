# -*- coding: utf-8 -*-
"""三角靠枕 皮壳 BOM 面料用量修正 —— 统计 / dry-run / 写回 / 校验

口径（2026-09-21 与用户确认）：
  把每份「三角靠枕 皮壳 BOM」的**主面料行**用量改成需求值：
      新用量(米) = (尺寸 + 40) / 100
  例：160 -> 2.00 米（现 2.38，下调）；45 -> 0.85 米（现 0.82，上调，需工厂确认）

  范围：皮壳BOM核对表 874 份，排除
        - 复古拼色 KS0383（24 份）
        - 欧式拼色 KS0520（1 份）—— 两者均属「拼色异形款」
        - PK#KS0206-HLR-75-GREY 自立式（1 份）
      => 实际处理 848 份（上调 51 / 下调 796 / 不变 1）

  只改主面料行；成本按增量同步（不调 calculate_cost，避免重取估值价波及其它行）。

写回方式：已提交 BOM 走不了 REST 保存，用临时 API Server Script + frappe.db.set_value
（与 set_bom_operation_cost.py 同一套路，用完即删）。

用法:
  python EN_API/bom_fabric_qty_fix.py scan      # 出统计清单，只读（先给用户确认）
  python EN_API/bom_fabric_qty_fix.py dry       # 复核：对线上现状验算，不写
  python EN_API/bom_fabric_qty_fix.py apply     # 写生产
  python EN_API/bom_fabric_qty_fix.py verify    # 回读校验

输出（EN_API/out/）:
  bom_fabric_qty_fix_manifest_<ts>.xlsx / .json   变更清单（scan 产出，后续 dry/apply 复用）
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

sys.stdout.reconfigure(encoding="utf-8")

from bom_fabric_length_check import (  # noqa: E402
    ENV_KEYS, ENV_URLS, SIZE_BONUS_CM, ErpnextClient, collect, evaluate, load_env,
    need_meter,
)

_DIR = Path(__file__).resolve().parent
OUT_DIR = _DIR / "out"

EXCLUDE_MODELS = {"KS0383", "KS0520"}          # 复古拼色 / 欧式拼色 —— 拼色异形款，无需处理
EXCLUDE_ITEMS = {"PK#KS0206-HLR-75-GREY"}      # 自立式三角靠枕，无需处理

SCRIPT_NAME = "zz_set_bom_fabric_qty"
ROLLBACK_SCRIPT_NAME = "zz_restore_bom_fabric_qty"
RATE_PRECISION = 3                             # BOM Item.rate 的 precision（实测）

MANIFEST_HEADERS = [
    "BOM", "父物料", "父物料名称", "型号", "材质码", "尺寸", "颜色",
    "主面料物料", "主面料名称", "子行ID", "现用量(米)", "新用量(米)", "方向",
    "单价", "现金额", "新金额", "现原材料成本", "新原材料成本", "现总成本", "新总成本",
]
MANIFEST_WIDTHS = [40, 30, 34, 10, 10, 7, 14, 34, 32, 14, 11, 11, 7,
                   12, 12, 12, 14, 14, 12, 12]

SERVER_SCRIPT = '''plan = json.loads(frappe.form_dict.get("plan"))
done = []
bad = []
for bom_name in sorted(plan.keys()):
    item = plan[bom_name]
    try:
        bom = frappe.get_doc("BOM", bom_name)
        conv = frappe.utils.flt(bom.conversion_rate) or 1
        row = None
        for r in bom.items:
            if r.name == item["row"]:
                row = r
                break
        if row is None:
            bad.append(bom_name + " :: child row not found " + item["row"])
            continue
        old_amt = frappe.utils.flt(row.amount)
        old_bamt = frappe.utils.flt(row.base_amount)
        row.qty = frappe.utils.flt(item["new_qty"])
        row.stock_qty = row.qty * (frappe.utils.flt(row.conversion_factor) or 1)
        row.amount = frappe.utils.flt(row.rate, row.precision("rate")) * frappe.utils.flt(row.qty, row.precision("qty"))
        row.base_amount = row.amount * conv
        row.db_update()
        d_amt = frappe.utils.flt(row.amount) - old_amt
        d_bamt = frappe.utils.flt(row.base_amount) - old_bamt
        frappe.db.set_value("BOM", bom_name, {
            "raw_material_cost": frappe.utils.flt(bom.raw_material_cost) + d_amt,
            "base_raw_material_cost": frappe.utils.flt(bom.base_raw_material_cost) + d_bamt,
            "total_cost": frappe.utils.flt(bom.total_cost) + d_amt,
            "base_total_cost": frappe.utils.flt(bom.base_total_cost) + d_bamt,
        }, update_modified=False)
        done.append(bom_name + " | " + row.item_code + " | " + str(old_amt) + " -> " + str(row.amount))
    except Exception as exc:
        bad.append(bom_name + " :: " + repr(exc)[:160])

frappe.db.commit()
frappe.response["data"] = {"processed": len(done), "failed": len(bad),
                           "errors": bad[:40], "detail_sample": done[:20]}
'''

ROLLBACK_SERVER_SCRIPT = '''snap = json.loads(frappe.form_dict.get("snap"))
done = []
bad = []
for bom_name in sorted(snap.keys()):
    one = snap[bom_name]
    try:
        frappe.db.set_value("BOM Item", one["row_name"], one["row"], update_modified=False)
        frappe.db.set_value("BOM", bom_name, one["head"], update_modified=False)
        done.append(bom_name)
    except Exception as exc:
        bad.append(bom_name + " :: " + repr(exc)[:160])

frappe.db.commit()
frappe.response["data"] = {"processed": len(done), "failed": len(bad), "errors": bad[:40]}
'''


def call(client: ErpnextClient, method: str, **data: Any) -> Any:
    """API 型 Server Script 的返回值：脚本里写 frappe.response["data"] 时，
    Frappe 把它放在响应的 data 键下（写 frappe.flags 时才在 message 下）。两个都认。"""
    r = client._request("POST", f"/api/method/{method}", data=data, timeout=(30, 600))
    body = r.json()
    for k in ("message", "data"):
        if k in body:
            return body[k]
    return body


def delete_script(client: ErpnextClient, name: str = SCRIPT_NAME) -> None:
    try:
        client._request("DELETE", f"/api/resource/Server Script/{name}",
                        timeout=60, retries=0)
    except requests.HTTPError:
        pass


def deploy_script(client: ErpnextClient, name: str, body: str) -> None:
    delete_script(client, name)
    r = client._request("POST", "/api/resource/Server Script",
                        json={"name": name, "script_type": "API", "api_method": name,
                              "script": body, "allow_guest": 0, "disabled": 0},
                        timeout=60).json()["data"]
    print(f"已部署临时 Server Script: {r['name']}")


def drop_script(client: ErpnextClient, name: str) -> None:
    delete_script(client, name)
    try:
        client._request("GET", f"/api/resource/Server Script/{quote(name, safe='')}",
                        timeout=60, retries=0)
        print(f"  ⚠ Server Script {name} 删除后仍能读到，请复查")
    except requests.HTTPError:
        print(f"已删除 Server Script {name}（复查残留 0）")


def decimal_qty(size: int) -> Decimal:
    return need_meter(size).quantize(Decimal("0.01"))


def build_plan(env: str, from_json: Path | None, workers: int) -> tuple[list[dict], dict]:
    key, sec = load_env(env)
    if not key or not sec:
        raise SystemExit(f"✗ 缺少 {ENV_KEYS[env]} 凭证")
    client = ErpnextClient(ENV_URLS[env], key, sec)
    docs, meta, tree = collect(env, client, workers, from_json)
    records, undecided = evaluate(docs, meta, tree)

    docs_by_name = {d["name"]: d for d in docs}
    plan: list[dict] = []
    skipped: list[dict] = []

    for r in records:
        if r["model"] in EXCLUDE_MODELS or r["item"] in EXCLUDE_ITEMS:
            skipped.append({**r, "skip_reason": "拼色异形款/自立式，无需处理"})
            continue
        doc = docs_by_name[r["bom"]]
        new_qty = decimal_qty(r["size"])
        if new_qty == r["qty"]:
            direction = "不变"
        elif new_qty > r["qty"]:
            direction = "上调"
        else:
            direction = "下调"
        plan.append({**r, "new_qty": new_qty, "direction": direction, "doc": doc})

    plan.sort(key=lambda r: (r["direction"] != "上调", r["size"], r["model"], r["color"]))
    return plan, {"env": env, "skipped": skipped, "undecided": undecided}


def write_manifest(path: Path, plan: list[dict], info: dict) -> None:
    wb = Workbook()
    head_fill = PatternFill("solid", fgColor="DDEBF7")
    red_fill = PatternFill("solid", fgColor="FFC7CE")
    green_fill = PatternFill("solid", fgColor="E2EFDA")

    ws = wb.active
    ws.title = "变更清单"
    ws.append(MANIFEST_HEADERS)
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = head_fill
        c.alignment = Alignment(horizontal="center", vertical="center")
    for r in plan:
        rate = r["fabric_rows"][0]["rate"] if r["fabric_rows"] else 0
        main_row = next((x for x in r["fabric_rows"] if x["code"] == r["code"]), r["fabric_rows"][0])
        rate = main_row["rate"]
        old_amt = main_row["amount"]
        new_amt = float(round(Decimal(str(rate)).quantize(Decimal("0.001")) * r["new_qty"], 6))
        d_amt = new_amt - old_amt
        doc = r["doc"]
        ws.append([
            r["bom"], r["item"], r["item_name"], r["model"], r["material"],
            r["size"], r["color"], r["code"], r["name"], main_row["row_name"],
            float(r["qty"]), float(r["new_qty"]), r["direction"],
            rate, old_amt, new_amt,
            doc.get("raw_material_cost"), float(Decimal(str(doc.get("raw_material_cost") or 0)) + Decimal(str(d_amt))),
            doc.get("total_cost"), float(Decimal(str(doc.get("total_cost") or 0)) + Decimal(str(d_amt))),
        ])
        fill = red_fill if r["direction"] == "上调" else (green_fill if r["direction"] == "下调" else None)
        if fill:
            for ci in range(1, len(MANIFEST_HEADERS) + 1):
                ws.cell(row=ws.max_row, column=ci).fill = fill
        for ci in (11, 12, 14, 15, 16, 17, 18, 19, 20):
            ws.cell(row=ws.max_row, column=ci).number_format = "0.00"
    for i, w in enumerate(MANIFEST_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(MANIFEST_HEADERS))}{ws.max_row}"

    ws2 = wb.create_sheet("无需处理")
    ws2.append(["BOM", "父物料", "父物料名称", "尺寸", "现用量(米)", "新用量(米)", "原因"])
    for c in ws2[1]:
        c.font = Font(bold=True)
        c.fill = head_fill
    for r in info["skipped"]:
        ws2.append([r["bom"], r["item"], r["item_name"], r["size"],
                    float(r["qty"]), float(r["need"]), r["skip_reason"]])
    for col, w in {"A": 40, "B": 30, "C": 34, "D": 8, "E": 12, "F": 12, "G": 30}.items():
        ws2.column_dimensions[col].width = w

    wb.save(str(path))


def cmd_scan(args: argparse.Namespace) -> int:
    print(f"环境: {args.env} ({ENV_URLS[args.env]})   统计模式（只读）\n", flush=True)
    t0 = time.time()
    plan, info = build_plan(args.env, args.from_json, args.workers)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    xlsx = args.out_dir / f"bom_fabric_qty_fix_manifest_{ts}.xlsx"
    js = args.out_dir / f"bom_fabric_qty_fix_manifest_{ts}.json"

    write_manifest(xlsx, plan, info)
    js.write_text(json.dumps({
        "meta": {
            "env": args.env, "generated_at": datetime.now().isoformat(),
            "formula": f"新用量(米) = (尺寸 + {SIZE_BONUS_CM}) / 100",
            "exclude_models": sorted(EXCLUDE_MODELS), "exclude_items": sorted(EXCLUDE_ITEMS),
        },
        "plan": {r["bom"]: {"row": next(x["row_name"] for x in r["fabric_rows"] if x["code"] == r["code"]),
                            "item_code": r["code"], "old_qty": str(r["qty"]),
                            "new_qty": str(r["new_qty"]), "direction": r["direction"]}
                 for r in plan},
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    ups = [r for r in plan if r["direction"] == "上调"]
    downs = [r for r in plan if r["direction"] == "下调"]
    same = [r for r in plan if r["direction"] == "不变"]
    print("=" * 64)
    print("统计（待用户确认后才 dry-run / apply）")
    print("=" * 64)
    print(f"  处理范围 : {len(plan)} 份   （排除 {len(info['skipped'])} 份拼色异形/自立式）")
    print(f"    上调   : {len(ups)}  尺寸 {sorted({r['size'] for r in ups})}")
    print(f"    下调   : {len(downs)}")
    print(f"    不变   : {len(same)}")
    print(f"  无法判定 : {len(info['undecided'])}")
    print(f"\n  被排除的 {len(info['skipped'])} 份:")
    for m in sorted({r["model"] for r in info["skipped"]}):
        print(f"    {m:<8} {sum(1 for r in info['skipped'] if r['model'] == m)} 份")
    print(f"\n  上调明细:")
    for r in ups:
        print(f"    {r['bom']:<52} {float(r['qty'])} -> {r['new_qty']}")
    print(f"\n  耗时 {time.time() - t0:.0f}s")
    print(f"✓ 清单: {xlsx}")
    print(f"✓ 清单: {js}   （dry / apply 直接用 --manifest 指向它）")
    return 0


def cmd_dry(args: argparse.Namespace) -> int:
    plan_data = json.loads(args.manifest.read_text(encoding="utf-8"))["plan"]
    key, sec = load_env(args.env)
    client = ErpnextClient(ENV_URLS[args.env], key, sec)
    print(f"环境: {args.env} ({client.base_url})   dry-run（只读，不写）")
    print(f"清单: {args.manifest}   共 {len(plan_data)} 份\n")

    bad_formula, drift, ok = [], [], 0
    for i, (bom_name, item) in enumerate(sorted(plan_data.items()), start=1):
        d = client.get_doc("BOM", bom_name)
        row = next((r for r in (d.get("items") or []) if r.get("name") == item["row"]), None)
        if row is None:
            bad_formula.append(f"{bom_name}: 子行 {item['row']} 不存在")
            continue
        # 验算：用 ERPNext 的公式复现「现金额」，验证 precision 假设
        calc_old = round(Decimal(str(row["rate"])).quantize(Decimal("0.001")) * Decimal(str(row["qty"])), 6)
        if abs(float(calc_old) - float(row["amount"])) > 1e-6:
            bad_formula.append(
                f"{bom_name}: rate={row['rate']} qty={row['qty']} "
                f"金额复现={calc_old} 实存={row['amount']}")
        # 漂移检查：现用量是否还是清单里的值
        if abs(float(row["qty"]) - float(item["old_qty"])) > 1e-9:
            drift.append(f"{bom_name}: 现用量 {row['qty']} != 清单 {item['old_qty']}")
        ok += 1
        if i % 200 == 0:
            print(f"  已验 {i}/{len(plan_data)}", flush=True)

    print(f"\n  验算 {ok} 份")
    print(f"  金额公式不符 : {len(bad_formula)}")
    for x in bad_formula[:10]:
        print("     ", x)
    print(f"  现用量漂移   : {len(drift)}")
    for x in drift[:10]:
        print("     ", x)

    ups = sum(1 for v in plan_data.values() if v["direction"] == "上调")
    print(f"\n  [dry-run] 将执行：临时 Server Script 逐份把主面料行 qty 改为新用量，"
          f"并按增量同步 raw_material_cost / total_cost。")
    print(f"             {len(plan_data)} 份（上调 {ups} / 下调 {len(plan_data) - ups - sum(1 for v in plan_data.values() if v['direction'] == '不变')}）")
    print(f"  加 --apply 才写入。公式不符或有漂移时请先排查。")
    return 1 if (bad_formula or drift) else 0


def cmd_apply(args: argparse.Namespace) -> int:
    payload = json.loads(args.manifest.read_text(encoding="utf-8"))["plan"]
    if args.only:
        keep = {x.strip() for x in args.only.split(",") if x.strip()}
        payload = {k: v for k, v in payload.items() if k in keep}
    if not payload:
        print("✗ 没有要处理的对象")
        return 1
    key, sec = load_env(args.env)
    client = ErpnextClient(ENV_URLS[args.env], key, sec)
    print(f"环境: {args.env} ({client.base_url})   ★ 写入模式 ★")
    print(f"对象: {len(payload)} 份 BOM")

    deploy_script(client, SCRIPT_NAME, SERVER_SCRIPT)
    try:
        res = call(client, SCRIPT_NAME, plan=json.dumps(payload, ensure_ascii=False))
        print("执行结果:", json.dumps(res, ensure_ascii=False, indent=1)[:4000])
    finally:
        drop_script(client, SCRIPT_NAME)
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    """写前快照：把待改的每份 BOM 的子行/主表原值完整存下来，供 rollback 用。"""
    plan_data = json.loads(args.manifest.read_text(encoding="utf-8"))["plan"]
    key, sec = load_env(args.env)
    client = ErpnextClient(ENV_URLS[args.env], key, sec)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = args.out_dir / f"bom_fabric_qty_fix_backup_{ts}.json"
    print(f"环境: {args.env} ({client.base_url})   写前快照 {len(plan_data)} 份\n")

    snap: dict[str, dict] = {}
    docs: list[dict] = []
    for i, (bom_name, item) in enumerate(sorted(plan_data.items()), start=1):
        d = client.get_doc("BOM", bom_name)
        row = next((r for r in (d.get("items") or []) if r.get("name") == item["row"]), None)
        if row is None:
            print(f"  [WARN] {bom_name}: 子行 {item['row']} 不存在，跳过")
            continue
        snap[bom_name] = {
            "item_code": row["item_code"],
            "row_name": row["name"],
            "row": {k: row.get(k) for k in ("qty", "stock_qty", "amount", "base_amount", "rate")},
            "head": {k: d.get(k) for k in ("raw_material_cost", "base_raw_material_cost",
                                           "total_cost", "base_total_cost")},
        }
        docs.append(d)
        if i % 200 == 0 or i == len(plan_data):
            print(f"  已快照 {i}/{len(plan_data)}", flush=True)

    out.write_text(json.dumps({
        "meta": {"env": args.env, "generated_at": datetime.now().isoformat(),
                 "source_manifest": args.manifest.name, "count": len(snap),
                 "note": "rollback 用 snap；docs 是完整 BOM 原文，供人工核对"},
        "snap": snap, "docs": docs,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    args.snap_file = out
    print(f"\n✓ 快照: {out}  ({out.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"  回滚命令: python EN_API/bom_fabric_qty_fix.py rollback --snap {out.name}")
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    snap_path = args.snap
    if snap_path is None:
        cands = sorted(args.out_dir.glob("bom_fabric_qty_fix_backup_*.json"))
        if not cands:
            print("✗ 找不到快照")
            return 1
        snap_path = cands[-1]
        print(f"（未指定 --snap，用最新的 {snap_path.name}）")
    snap = json.loads(snap_path.read_text(encoding="utf-8"))["snap"]
    key, sec = load_env(args.env)
    client = ErpnextClient(ENV_URLS[args.env], key, sec)
    print(f"环境: {args.env} ({client.base_url})   ★ 回滚模式 ★")
    print(f"快照: {snap_path.name}   对象 {len(snap)} 份")

    deploy_script(client, ROLLBACK_SCRIPT_NAME, ROLLBACK_SERVER_SCRIPT)
    try:
        res = call(client, ROLLBACK_SCRIPT_NAME, snap=json.dumps(snap, ensure_ascii=False))
        print("回滚结果:", json.dumps(res, ensure_ascii=False, indent=1)[:2000])
    finally:
        drop_script(client, ROLLBACK_SCRIPT_NAME)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    plan_data = json.loads(args.manifest.read_text(encoding="utf-8"))["plan"]
    key, sec = load_env(args.env)
    client = ErpnextClient(ENV_URLS[args.env], key, sec)
    print(f"环境: {args.env} ({client.base_url})   校验 {len(plan_data)} 份\n")
    bad = []
    for bom_name, item in sorted(plan_data.items()):
        d = client.get_doc("BOM", bom_name)
        row = next((r for r in (d.get("items") or []) if r.get("name") == item["row"]), None)
        want = Decimal(str(item["new_qty"]))
        if row is None:
            bad.append(f"{bom_name}: 子行消失")
            continue
        got = Decimal(str(row["qty"]))
        calc_amt = (Decimal(str(row["rate"])).quantize(Decimal("0.001")) * got).quantize(Decimal("0.000001"))
        amt_ok = abs(float(calc_amt) - float(row["amount"])) <= 1e-6
        if got != want or not amt_ok:
            bad.append(f"{bom_name}: qty {got} (期望 {want}) 金额 {row['amount']} (期望 {calc_amt})")
    print(f"  一致 {len(plan_data) - len(bad)} / {len(plan_data)}")
    for x in bad[:20]:
        print("     ", x)
    print("校验:", "全部一致" if not bad else f"{len(bad)} 份不一致")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=("scan", "dry", "backup", "apply", "rollback", "verify"),
                    default="scan", nargs="?")
    ap.add_argument("--env", choices=("prod", "test"), default="prod")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--from-json", type=Path, default=None, help="scan 时改用本地 BOM 快照")
    ap.add_argument("--manifest", type=Path, default=None, help="dry/apply/verify 用的清单 JSON")
    ap.add_argument("--snap", type=Path, default=None, help="rollback 用的写前快照 JSON")
    ap.add_argument("--only", default=None, help="apply 时只处理这些 BOM（逗号分隔）")
    args = ap.parse_args()

    if args.action == "scan":
        return cmd_scan(args)
    if args.action == "rollback":
        return cmd_rollback(args)
    if args.manifest is None:
        cands = sorted(args.out_dir.glob("bom_fabric_qty_fix_manifest_*.json"))
        if not cands:
            print("✗ 找不到清单，先跑 scan")
            return 1
        args.manifest = cands[-1]
        print(f"（未指定 --manifest，用最新的 {args.manifest.name}）")
    return {"dry": cmd_dry, "backup": cmd_backup,
            "apply": cmd_apply, "verify": cmd_verify}[args.action](args)


if __name__ == "__main__":
    raise SystemExit(main())
