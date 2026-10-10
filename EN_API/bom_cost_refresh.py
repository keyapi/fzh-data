# -*- coding: utf-8 -*-
"""批量刷新 BOM 成本（等价于逐张点 BOM 表单上的「更新成本」按钮）—— 只读/写前快照/执行/复核。

背景：2026-09-21 改了 848 份皮壳 BOM 的面料用量、2026-09-22 刷新了 2665 份的展开物料，
但**父级成品 BOM 里「子装配件」那一行的 rate（= 子 BOM 的单位成本）没有跟着变**
→ 父级 raw_material_cost / total_cost 停在旧值。
ERPNext 的「更新成本」按钮做的就是这件事，本脚本把它批量做掉。

口径（源码 `bom.py:467 get_rm_rate`）：
    子装配件行 rate = 子 BOM 的 `total_cost / quantity`
所以过期判据：`BOM Item.rate != 子BOM.total_cost / 子BOM.quantity`

刷新方式：`bom.update_cost(update_parent=False, from_child_bom=True, update_hour_rate=False)`
  - update_parent=False：本脚本自己按「多轮直到收敛」的方式逐层处理，不依赖 ERPNext 的
    成本变化级联（成本没变时它不级联，会漏）
  - from_child_bom=True：压掉 ERPNext 的 msgprint
  - update_hour_rate=False：不动工序工站费率

用法:
  python EN_API/bom_cost_refresh.py scan     # 只读：列出所有「子件 rate ≠ 子BOM 单位成本」的 BOM
  python EN_API/bom_cost_refresh.py dry      # 只读：内存试算，报告会变多少
  python EN_API/bom_cost_refresh.py backup   # 写前快照（items 的 rate/amount + 主表成本）
  python EN_API/bom_cost_refresh.py apply    # 执行（多轮直到收敛）
  python EN_API/bom_cost_refresh.py verify   # 回读复核
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from bom_fabric_length_check import ENV_KEYS, ENV_URLS, ErpnextClient, load_env  # noqa: E402

SCRIPT_NAME = "zz_bom_cost_refresh"
OUT_DIR = Path(__file__).resolve().parent / "out"
CHUNK = 40          # 每批处理的 BOM 数（避免单次 HTTP 请求超时）
MAX_ROUNDS = 6      # 多轮直到收敛的轮数上限

SERVER_SCRIPT = '''mode = frappe.form_dict.get("mode")

MISMATCH_SQL = """
    SELECT bi.parent AS bom, bi.item_code AS sub_item, bi.bom_no AS child_bom,
           bi.rate AS parent_rate,
           IFNULL(b2.total_cost, 0) / IFNULL(NULLIF(b2.quantity, 0), 1) AS child_unit_cost,
           b1.total_cost AS parent_total, b1.raw_material_cost AS parent_raw
    FROM `tabBOM Item` bi
    JOIN `tabBOM` b1 ON b1.name = bi.parent
    JOIN `tabBOM` b2 ON b2.name = bi.bom_no
    WHERE IFNULL(bi.bom_no, '') <> ''
      AND b1.docstatus = 1 AND b2.docstatus = 1
      AND ABS(IFNULL(bi.rate, 0)
              - IFNULL(b2.total_cost, 0) / IFNULL(NULLIF(b2.quantity, 0), 1)) > 0.000001
    ORDER BY bi.parent
"""

if mode == "scan":
    rows = frappe.db.sql(MISMATCH_SQL, as_dict=True)
    seen = {}
    for r in rows:
        s = seen.setdefault(r["bom"], {"bom": r["bom"], "rows": 0, "parent_total": frappe.utils.flt(r["parent_total"]),
                                       "parent_raw": frappe.utils.flt(r["parent_raw"]), "detail": []})
        s["rows"] = s["rows"] + 1
        s["detail"].append({
            "sub_item": r["sub_item"], "child_bom": r["child_bom"],
            "parent_rate": frappe.utils.flt(r["parent_rate"]),
            "child_unit_cost": frappe.utils.flt(r["child_unit_cost"]),
        })
    out = sorted(seen.values(), key=lambda x: x["bom"])
    total_boms = frappe.db.sql("SELECT COUNT(*) FROM `tabBOM` WHERE docstatus = 1")[0][0]
    frappe.response["data"] = {"total_boms": total_boms, "mismatch_boms": len(out),
                               "mismatch_rows": len(rows), "list": out}

elif mode == "snapshot":
    names = json.loads(frappe.form_dict.get("names") or "[]")
    docs = []
    for nm in names:
        b = frappe.get_doc("BOM", nm)
        docs.append({
            "name": nm, "item": b.item, "quantity": b.quantity,
            "raw_material_cost": frappe.utils.flt(b.raw_material_cost),
            "base_raw_material_cost": frappe.utils.flt(b.base_raw_material_cost),
            "total_cost": frappe.utils.flt(b.total_cost),
            "base_total_cost": frappe.utils.flt(b.base_total_cost),
            "operating_cost": frappe.utils.flt(b.operating_cost),
            "scrap_material_cost": frappe.utils.flt(b.scrap_material_cost),
            "items": [{"name": r.name, "idx": r.idx, "item_code": r.item_code, "bom_no": r.bom_no,
                       "rate": frappe.utils.flt(r.rate), "amount": frappe.utils.flt(r.amount),
                       "stock_qty": frappe.utils.flt(r.stock_qty)}
                      for r in (b.get("items") or [])],
        })
    frappe.response["data"] = {"count": len(docs), "docs": docs}

elif mode == "preview":
    names = json.loads(frappe.form_dict.get("names") or "[]")
    out = []
    for nm in names:
        b = frappe.get_doc("BOM", nm)
        before_total = frappe.utils.flt(b.total_cost)
        before_raw = frappe.utils.flt(b.raw_material_cost)
        before_rates = {}
        for r in (b.get("items") or []):
            before_rates[r.name] = frappe.utils.flt(r.rate)
        b.update_cost(update_parent=False, from_child_bom=True, update_hour_rate=False, save=False)
        after_rates = {}
        for r in (b.get("items") or []):
            after_rates[r.name] = frappe.utils.flt(r.rate)
        rate_changes = {}
        for k in before_rates:
            if abs(before_rates.get(k, 0) - after_rates.get(k, 0)) > 1e-9:
                rate_changes[k] = [before_rates[k], after_rates[k]]
        out.append({"bom": nm, "before_total": before_total,
                    "after_total": frappe.utils.flt(b.total_cost),
                    "before_raw": before_raw, "after_raw": frappe.utils.flt(b.raw_material_cost),
                    "changed_rates": len(rate_changes), "rate_changes": rate_changes})
    frappe.db.rollback()
    frappe.response["data"] = {"checked": len(out), "detail": out}

elif mode == "refresh":
    names = json.loads(frappe.form_dict.get("names") or "[]")
    done = []
    bad = []
    for nm in names:
        try:
            b = frappe.get_doc("BOM", nm)
            before_total = frappe.utils.flt(b.total_cost)
            before_raw = frappe.utils.flt(b.raw_material_cost)
            b.update_cost(update_parent=False, from_child_bom=True, update_hour_rate=False)
            done.append({"bom": nm, "before_total": before_total,
                         "after_total": frappe.utils.flt(b.total_cost),
                         "before_raw": before_raw, "after_raw": frappe.utils.flt(b.raw_material_cost)})
        except Exception as exc:
            bad.append(nm + " :: " + repr(exc)[:200])
    frappe.db.commit()
    frappe.response["data"] = {"processed": len(done), "failed": len(bad),
                               "errors": bad[:20], "detail": done}

elif mode == "repair_rows":
    # 回滚「子 BOM 已停用(is_active=0) → get_bom_unitcost 返回 0 → rate 被刷成 0」的损害：
    # 只把这些行的 rate/amount 还原成备份值，再按 items 重算主表成本
    # （不能用 update_cost，那会再次把 rate 刷成 0）。
    fixes = json.loads(frappe.form_dict.get("fixes") or "[]")
    by_bom = {}
    for f in fixes:
        by_bom.setdefault(f["bom"], []).append(f)
    done = []
    bad = []
    for bom_name, rows in by_bom.items():
        try:
            b = frappe.get_doc("BOM", bom_name)
            conv = frappe.utils.flt(b.conversion_rate) or 1
            cur = {}
            for r in b.items:
                cur[r.name] = r
            for f in rows:
                r = cur.get(f["row_name"])
                if r is None:
                    bad.append(bom_name + " :: 子行 " + f["row_name"] + " 不存在")
                    continue
                r.rate = frappe.utils.flt(f["rate"], r.precision("rate"))
                r.amount = frappe.utils.flt(r.rate, r.precision("rate")) * frappe.utils.flt(r.qty, r.precision("qty"))
                r.base_rate = r.rate * conv
                r.base_amount = r.amount * conv
                r.db_update()
            raw = 0.0
            base_raw = 0.0
            for r in b.items:
                raw = raw + frappe.utils.flt(r.amount)
                base_raw = base_raw + frappe.utils.flt(r.base_amount)
            op = frappe.utils.flt(b.operating_cost)
            base_op = frappe.utils.flt(b.base_operating_cost)
            scrap = frappe.utils.flt(b.scrap_material_cost)
            base_scrap = frappe.utils.flt(b.base_scrap_material_cost)
            frappe.db.set_value("BOM", bom_name, {
                "raw_material_cost": raw, "base_raw_material_cost": base_raw,
                "total_cost": op + raw - scrap, "base_total_cost": base_op + base_raw - base_scrap,
            }, update_modified=False)
            done.append({"bom": bom_name, "rows": len(rows), "raw": raw, "total": op + raw - scrap})
        except Exception as exc:
            bad.append(bom_name + " :: " + repr(exc)[:200])
    frappe.db.commit()
    frappe.response["data"] = {"processed": len(done), "failed": len(bad),
                               "errors": bad[:20], "detail": done}
'''


def call(client: ErpnextClient, **data):
    r = client._request("POST", f"/api/method/{SCRIPT_NAME}", data=data, timeout=(30, 900))
    body = r.json()
    for k in ("message", "data"):
        if k in body:
            return body[k]
    return body


def ensure_script(client: ErpnextClient) -> None:
    try:
        client._request("DELETE", f"/api/resource/Server Script/{SCRIPT_NAME}", timeout=60, retries=0)
    except Exception:  # noqa: BLE001
        pass
    client._request("POST", "/api/resource/Server Script",
                    json={"name": SCRIPT_NAME, "script_type": "API", "api_method": SCRIPT_NAME,
                          "script": SERVER_SCRIPT, "allow_guest": 0, "disabled": 0}, timeout=60)


def drop_script(client: ErpnextClient) -> None:
    try:
        client._request("DELETE", f"/api/resource/Server Script/{SCRIPT_NAME}", timeout=60, retries=0)
    except Exception:  # noqa: BLE001
        pass
    try:
        client._request("GET", f"/api/resource/Server Script/{SCRIPT_NAME}", timeout=60, retries=0)
        print(f"  ⚠ {SCRIPT_NAME} 删除后仍能读到，请复查")
    except Exception:  # noqa: BLE001
        print(f"已删除临时 Server Script {SCRIPT_NAME}（残留 0）")


def do_scan(client: ErpnextClient) -> dict:
    return call(client, mode="scan")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("scan", "dry", "backup", "apply", "verify", "repair"))
    ap.add_argument("--site", choices=("prod", "test"), default="prod")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 张（便于小范围试跑）")
    ap.add_argument("--backup", type=Path, default=None, help="repair 用的写前快照 JSON")
    args = ap.parse_args()

    key, sec = load_env(args.site)
    if not key or not sec:
        print(f"✗ 缺 {ENV_KEYS[args.site]} 凭证")
        return 1
    client = ErpnextClient(ENV_URLS[args.site], key, sec)
    print(f"环境: {args.site} ({client.base_url})")

    ensure_script(client)
    try:
        if args.action == "scan":
            res = do_scan(client)
            print(f"\n已提交 BOM 共 {res['total_boms']} 份")
            print(f"成本过期的 BOM: {res['mismatch_boms']} 份（{res['mismatch_rows']} 个过期子件行）")
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            p = OUT_DIR / "bom_cost_refresh_scan.json"
            p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
            for x in res["list"][:12]:
                d = x["detail"][0]
                print(f"   {x['bom']:<46} {x['rows']} 行  "
                      f"例: {d['sub_item']} {d['parent_rate']} -> {d['child_unit_cost']}")
            if len(res["list"]) > 12:
                print(f"   … 其余 {len(res['list']) - 12} 份见清单文件")
            print(f"\n落盘: {p}")
            return 0

        scan = do_scan(client)
        names = [x["bom"] for x in scan["list"]]
        if args.limit:
            names = names[:args.limit]
        if not names:
            print("\n✓ 没有成本过期的 BOM，无需处理")
            return 0
        print(f"\n待处理 {len(names)} 份")

        if args.action == "dry":
            changed = 0
            for i in range(0, len(names), CHUNK):
                res = call(client, mode="preview", names=json.dumps(names[i:i + CHUNK]))
                for d in res["detail"]:
                    if abs(d["after_total"] - d["before_total"]) > 1e-9:
                        changed += 1
                        if changed <= 15:
                            print(f"   {d['bom']:<46} total {d['before_total']} -> {d['after_total']}"
                                  f"  raw {d['before_raw']} -> {d['after_raw']}"
                                  f"  ({d['changed_rates']} 行单价变)")
                print(f"   已试算 {min(i + CHUNK, len(names))}/{len(names)}", flush=True)
            print(f"\n会变成本的: {changed} / {len(names)} 份（只读试算，未写库）")
            return 0

        if args.action == "backup":
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out = OUT_DIR / f"bom_cost_refresh_backup_{args.site}_{ts}.json"
            print(f"\n=== 写前快照 {len(names)} 份 ===")
            docs = []
            for i in range(0, len(names), 100):
                docs.extend(call(client, mode="snapshot", names=json.dumps(names[i:i + 100]))["docs"])
                print(f"   已快照 {min(i + 100, len(names))}/{len(names)}", flush=True)
            out.write_text(json.dumps({
                "meta": {"env": args.site, "generated_at": datetime.now().isoformat(),
                         "count": len(docs), "source_scan": scan["mismatch_rows"]},
                "docs": docs}, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"✓ 快照: {out} ({out.stat().st_size / 1024 / 1024:.1f} MB)")
            return 0

        if args.action == "apply":
            print(f"\n=== ★ 刷新成本（多轮直到收敛，每批 {CHUNK} 份）★ ===")
            for rnd in range(1, MAX_ROUNDS + 1):
                cur = do_scan(client)
                cur_names = [x["bom"] for x in cur["list"]]
                if args.limit:
                    cur_names = cur_names[:args.limit]
                if not cur_names:
                    print(f"\n  第 {rnd} 轮：已收敛，无剩余过期")
                    break
                done = changed = failed = 0
                for i in range(0, len(cur_names), CHUNK):
                    res = call(client, mode="refresh", names=json.dumps(cur_names[i:i + CHUNK]))
                    done += res["processed"]
                    failed += res["failed"]
                    changed += sum(1 for d in res["detail"]
                                   if abs(d["after_total"] - d["before_total"]) > 1e-9)
                    for e in res["errors"][:3]:
                        print("     [ERR]", e)
                print(f"  第 {rnd} 轮：处理 {done} 份（失败 {failed}），成本变化 {changed} 份；"
                      f"剩余过期 {cur['mismatch_boms']}", flush=True)
                if cur["mismatch_boms"] == done and changed == 0 and rnd > 1:
                    print("    （本轮无任何变化，视为收敛）")
                    break
            return 0

        if args.action == "repair":
            bk_file = args.backup
            if bk_file is None:
                cands = sorted(OUT_DIR.glob("bom_cost_refresh_backup_*.json"))
                if not cands:
                    print("✗ 找不到备份文件，先跑 backup")
                    return 1
                bk_file = cands[-1]
            print(f"\n用备份比对: {bk_file.name}")
            bk = {d["name"]: d for d in json.loads(bk_file.read_text(encoding="utf-8"))["docs"]}

            scan = do_scan(client)
            resid = [x["bom"] for x in scan["list"]]
            if not resid:
                print("✓ 没有残留过期，无需修复")
                return 0

            fixes = []
            for n in resid:
                b = bk.get(n)
                if not b:
                    continue
                d = client.get_doc("BOM", n)
                cur = {r["name"]: r for r in (d.get("items") or [])}
                for r in b["items"]:
                    if not r.get("bom_no"):
                        continue
                    c = cur.get(r["name"])
                    if c is None:
                        continue
                    if r["rate"] > 0 and abs(float(c.get("rate") or 0)) < 1e-9:
                        fixes.append({"bom": n, "row_name": r["name"], "rate": r["rate"]})
            print(f"残留 {len(resid)} 份；其中「备份里单价>0、现在被刷成 0」的行: {len(fixes)}")
            if not fixes:
                print("（没有需要回滚的行）")
                return 0
            for i in range(0, len(fixes), 200):
                res = call(client, mode="repair_rows", fixes=json.dumps(fixes[i:i + 200]))
                print(f"  修复 {res['processed']} 份 BOM，失败 {res['failed']}")
                for e in res["errors"][:5]:
                    print("     [ERR]", e)
                for d in res["detail"][:5]:
                    print(f"     {d['bom']} 还原 {d['rows']} 行 → raw={d['raw']} total={d['total']}")
            return 0

        if args.action == "verify":
            after = do_scan(client)
            print(f"\n=== 回读复核 ===")
            print(f"  剩余成本过期的 BOM: {after['mismatch_boms']} 份（应为 0）")
            print(f"  剩余过期子件行      : {after['mismatch_rows']} 个")
            for x in after["list"][:5]:
                print("   ", x["bom"], x["detail"][0])
            return 0
    finally:
        drop_script(client)
    return 0


if __name__ == "__main__":
    sys.exit(main())
