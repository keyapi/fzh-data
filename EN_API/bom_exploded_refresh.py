# -*- coding: utf-8 -*-
"""刷新 BOM 的「展开物料」(BOM Explosion Item) —— 修复 2026-09-21 改面料用量留下的不一致。

背景：2026-09-21 用 `frappe.db.set_value` 直改了 848 份皮壳 BOM 的主面料用量，**绕过了
ERPNext 保存时的 `update_exploded_items()` 钩子**，导致这些 BOM 的 `exploded_items`
仍是旧值；而父级成品 BOM 的展开料是**读子 BOM 的 `BOM Explosion Item` 表**
（`bom.py:902 get_child_exploded_items`）再乘父级 stock_qty，所以父级也跟着错。

例：BOM-PK#KS0001-CMM-153-WHITE-001 面料 items=1.93 但 exploded_items=2.31；
    BOM-KS0001-CMM-153-WHITE-001 的展开料读它 → 也是 2.31。

修法：对受影响 BOM 调 `bom.update_exploded_items(save=True)`（`bom.py:863`）。
它走裸 SQL（DELETE + db_insert），**不受已提交状态限制**。

顺序：必须先修叶子（皮壳 BOM），再修父级——否则父级读到的还是旧的。
本脚本按 BFS 层级逐层修。

用法:
  python EN_API/bom_exploded_refresh.py scan     # 只读：找出所有不一致的叶子 BOM + 向上闭包
  python EN_API/bom_exploded_refresh.py dry      # 只读：逐份打印将要发生的变化
  python EN_API/bom_exploded_refresh.py backup   # 写前快照
  python EN_API/bom_exploded_refresh.py apply    # 逐层刷新
  python EN_API/bom_exploded_refresh.py verify   # 回读复核
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from bom_fabric_length_check import ENV_KEYS, ENV_URLS, ErpnextClient, load_env  # noqa: E402

SCRIPT_NAME = "zz_bom_exploded_refresh"
OUT_DIR = Path(__file__).resolve().parent / "out"
CHUNK = 60          # 每批处理的 BOM 数（避免单次 HTTP 请求超时）

SERVER_SCRIPT = '''mode = frappe.form_dict.get("mode")

if mode == "leafmismatch":
    # 叶子 BOM（没有子 BOM 行的）里 exploded_items 与 items 对不上
    fwd = frappe.db.sql("""
        SELECT DISTINCT b.name AS name, b.item AS item
        FROM `tabBOM` b
        JOIN `tabBOM Explosion Item` ei ON ei.parent = b.name
        LEFT JOIN `tabBOM Item` bi ON bi.parent = b.name AND bi.item_code = ei.item_code
        WHERE b.docstatus = 1
          AND NOT EXISTS (SELECT 1 FROM `tabBOM Item` x
                          WHERE x.parent = b.name AND IFNULL(x.bom_no, '') <> '')
          AND (bi.name IS NULL OR ABS(IFNULL(bi.stock_qty, 0) - IFNULL(ei.stock_qty, 0)) > 1e-9)
    """, as_dict=True)
    # 反向：items 里有、exploded 里没有
    rev = frappe.db.sql("""
        SELECT DISTINCT b.name AS name, b.item AS item
        FROM `tabBOM` b
        JOIN `tabBOM Item` bi ON bi.parent = b.name
        LEFT JOIN `tabBOM Explosion Item` ei ON ei.parent = b.name AND ei.item_code = bi.item_code
        WHERE b.docstatus = 1
          AND NOT EXISTS (SELECT 1 FROM `tabBOM Item` x
                          WHERE x.parent = b.name AND IFNULL(x.bom_no, '') <> '')
          AND ei.name IS NULL
    """, as_dict=True)
    items = {}
    for r in fwd:
        items[r.name] = r.item
    for r in rev:
        if r.name not in items:
            items[r.name] = r.item
    total_leaf = frappe.db.sql("""
        SELECT COUNT(*) FROM `tabBOM` b
        WHERE b.docstatus = 1
          AND NOT EXISTS (SELECT 1 FROM `tabBOM Item` x
                          WHERE x.parent = b.name AND IFNULL(x.bom_no, '') <> '')
    """)[0][0]
    frappe.response["data"] = {"count": len(items), "leaf_total": total_leaf, "items": items}

elif mode == "parentsof":
    names = json.loads(frappe.form_dict.get("names") or "[]")
    if not names:
        frappe.response["data"] = {"names": []}
    else:
        rows = frappe.db.sql("""
            SELECT DISTINCT bi.parent AS name
            FROM `tabBOM Item` bi
            JOIN `tabBOM` b ON b.name = bi.parent
            WHERE b.docstatus = 1 AND bi.bom_no IN %(names)s
        """, {"names": names}, as_dict=True)
        frappe.response["data"] = {"names": [r.name for r in rows]}

elif mode == "snapshot":
    names = json.loads(frappe.form_dict.get("names") or "[]")
    docs = []
    for nm in names:
        bom = frappe.get_doc("BOM", nm)
        docs.append({
            "name": nm, "item": bom.item, "quantity": bom.quantity,
            "exploded_items": [{"name": r.name, "item_code": r.item_code,
                                "stock_qty": frappe.utils.flt(r.stock_qty),
                                "rate": frappe.utils.flt(r.rate),
                                "amount": frappe.utils.flt(r.amount)} for r in (bom.get("exploded_items") or [])],
        })
    frappe.response["data"] = {"count": len(docs), "docs": docs}

elif mode == "preview":
    names = json.loads(frappe.form_dict.get("names") or "[]")
    limit = frappe.utils.cint(frappe.form_dict.get("limit") or 80)
    out = []
    for nm in names[:limit]:
        bom = frappe.get_doc("BOM", nm)
        before = {}
        for r in (bom.get("exploded_items") or []):
            before[r.item_code] = frappe.utils.flt(r.stock_qty)
        bom.update_exploded_items(save=False)          # 只算不写
        after = {}
        for r in (bom.get("exploded_items") or []):
            after[r.item_code] = frappe.utils.flt(r.stock_qty)
        changed = {}
        for k in set(list(before.keys()) + list(after.keys())):
            b = frappe.utils.flt(before.get(k))
            a = frappe.utils.flt(after.get(k))
            if abs(b - a) > 1e-9:
                changed[k] = [b, a]
        if changed:
            out.append({"bom": nm, "changed": changed})
    frappe.db.rollback()
    frappe.response["data"] = {"checked": min(len(names), limit), "changed_boms": len(out), "detail": out}

elif mode == "refresh":
    names = json.loads(frappe.form_dict.get("names") or "[]")
    done = []
    bad = []
    for nm in names:
        try:
            bom = frappe.get_doc("BOM", nm)
            before = {}
            for r in (bom.get("exploded_items") or []):
                before[r.item_code] = frappe.utils.flt(r.stock_qty)
            bom.update_exploded_items(save=True)
            after = {}
            for r in (bom.get("exploded_items") or []):
                after[r.item_code] = frappe.utils.flt(r.stock_qty)
            changed = {}
            for k in set(list(before.keys()) + list(after.keys())):
                b = frappe.utils.flt(before.get(k))
                a = frappe.utils.flt(after.get(k))
                if abs(b - a) > 1e-9:
                    changed[k] = [b, a]
            done.append({"bom": nm, "rows": len(bom.get("exploded_items") or []), "changed": changed})
        except Exception as exc:
            bad.append(nm + " :: " + repr(exc)[:200])
    frappe.db.commit()
    frappe.response["data"] = {"processed": len(done), "failed": len(bad),
                               "errors": bad[:20], "detail": done}

elif mode == "checkone":
    bom_name = frappe.form_dict.get("bom")
    item_code = frappe.form_dict.get("item_code")
    bom = frappe.get_doc("BOM", bom_name)
    hit = []
    for r in (bom.get("exploded_items") or []):
        if not item_code or r.item_code == item_code:
            hit.append({"item_code": r.item_code, "stock_qty": frappe.utils.flt(r.stock_qty),
                        "rate": frappe.utils.flt(r.rate), "amount": frappe.utils.flt(r.amount)})
    frappe.response["data"] = {"bom": bom_name, "rows": hit}
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


def build_levels(client: ErpnextClient) -> list[list[str]]:
    """BFS：level0 = 叶子不一致的 BOM；逐层往上找引用了它们的父 BOM。"""
    res = call(client, mode="leafmismatch")
    items = res["items"]
    roots = sorted(items)
    print(f"  level 0（叶子不一致）: {len(roots)} 份 / 叶子 BOM 共 {res['leaf_total']} 份")
    import collections
    pref = collections.Counter(
        ("PK# 皮壳" if v.startswith("PK#") else
         "ND# 内胆" if v.startswith("ND#") else
         "DKND# 底开内胆" if v.startswith("DKND#") else
         "SXBZ 包装" if v.startswith("SXBZ") else "其它")
        for v in items.values())
    for k, n in pref.most_common():
        print(f"     {k}: {n}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "bom_exploded_leaf_items.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    levels = [roots]
    seen = set(roots)
    while levels[-1]:
        parents = call(client, mode="parentsof", names=json.dumps(levels[-1]))["names"]
        nxt = [p for p in parents if p not in seen]
        if not nxt:
            break
        seen.update(nxt)
        levels.append(nxt)
        print(f"  level {len(levels) - 1}（上层父 BOM）: {len(nxt)} 份")
    return levels


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("scan", "dry", "backup", "apply", "verify"))
    ap.add_argument("--site", choices=("prod", "test"), default="prod")
    ap.add_argument("--only", default=None,
                    help="只处理这些 BOM（逗号分隔，按给定顺序：叶子在前、父级在后）")
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
            print("\n=== 找出不一致 ===")
            levels = build_levels(client)
            all_names = [n for lv in levels for n in lv]
            print(f"\n受影响合计 {len(all_names)} 份")
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            p = OUT_DIR / "bom_exploded_refresh_levels.json"
            p.write_text(json.dumps({"levels": levels}, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"落盘: {p}")
            return 0

        lv_file = OUT_DIR / "bom_exploded_refresh_levels.json"
        if args.only:
            names_only = [x.strip() for x in args.only.split(",") if x.strip()]
            levels = [names_only]
            print(f"\n（--only）只处理 {len(names_only)} 份，按给定顺序：")
            for n in names_only:
                print(f"    {n}")
            pars = call(client, mode="parentsof", names=json.dumps(names_only))["names"]
            print(f"  提示：这些 BOM 的父级还有 {pars}（本次 {'已包含' if all(p in names_only for p in pars) else '★未全部包含★'}）")
        elif not lv_file.exists():
            raise SystemExit("✗ 缺 levels 文件，先跑 scan")
        else:
            levels = json.loads(lv_file.read_text(encoding="utf-8"))["levels"]
        all_names = [n for lv in levels for n in lv]

        if args.action == "dry":
            print(f"\n=== dry-run（只读，update_exploded_items(save=False)）共 {len(all_names)} 份 ===")
            show = 40
            for i, lv in enumerate(levels):
                checked = changed_boms = 0
                printed = 0
                for j in range(0, len(lv), CHUNK):
                    chunk = lv[j:j + CHUNK]
                    res = call(client, mode="preview", names=json.dumps(chunk), limit=CHUNK)
                    checked += res["checked"]
                    changed_boms += res["changed_boms"]
                    for d in res["detail"]:
                        if printed < show:
                            print(f"    {d['bom']}")
                            for ic, ba in list(d["changed"].items())[:4]:
                                print(f"       {ic}: {ba[0]} -> {ba[1]}")
                            printed += 1
                    print(f"  level {i}: 已检查 {min(j + CHUNK, len(lv))}/{len(lv)}", flush=True)
                print(f"  level {i} 小计: 检查 {checked} 份，其中有变化 {changed_boms} 份")
            return 0

        if args.action == "backup":
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out = OUT_DIR / f"bom_exploded_refresh_backup_{args.site}_{ts}.json"
            print(f"\n=== 写前快照 {len(all_names)} 份 ===")
            snap = []
            for i in range(0, len(all_names), 100):
                chunk = all_names[i:i + 100]
                snap.extend(call(client, mode="snapshot", names=json.dumps(chunk))["docs"])
                print(f"  已快照 {min(i + 100, len(all_names))}/{len(all_names)}")
            out.write_text(json.dumps({"meta": {"env": args.site, "generated_at": datetime.now().isoformat(),
                                                "count": len(snap)}, "docs": snap},
                                      ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"✓ 快照: {out} ({out.stat().st_size / 1024 / 1024:.1f} MB)")
            return 0

        if args.action == "apply":
            print(f"\n=== ★ 刷新 {len(all_names)} 份（按层，先叶子后父级；每批 {CHUNK} 份）★ ===")
            total_done = total_failed = total_changed = 0
            for i, lv in enumerate(levels):
                lv_done = lv_changed = 0
                for j in range(0, len(lv), CHUNK):
                    chunk = lv[j:j + CHUNK]
                    res = call(client, mode="refresh", names=json.dumps(chunk))
                    ch = sum(len(d["changed"]) for d in res["detail"])
                    lv_done += res["processed"]
                    lv_changed += ch
                    total_done += res["processed"]
                    total_failed += res["failed"]
                    total_changed += ch
                    for e in res["errors"][:5]:
                        print("     [ERR]", e)
                    if j == 0:
                        for d in res["detail"]:
                            if d["changed"]:
                                print(f"     例 {d['bom']}: " + "、".join(
                                    f"{k} {v[0]}->{v[1]}" for k, v in list(d["changed"].items())[:3]))
                    print(f"  level {i}: {min(j + CHUNK, len(lv))}/{len(lv)}（成功 {lv_done}，失败 {res['failed']}，改动行 {lv_changed}）", flush=True)
                print(f"  level {i} 小计: 成功 {lv_done} 份，改动行 {lv_changed}")
            print(f"\n合计: 成功 {total_done} 份，失败 {total_failed} 份，改动行 {total_changed}")
            return 0

        if args.action == "verify":
            print("\n=== 回读复核 ===")
            roots = call(client, mode="leafmismatch")
            print(f"  叶子不一致剩余: {roots['count']}（应为 0）")
            for nm, ic in (("BOM-PK#KS0001-CMM-153-WHITE-001", "CMM2020-WHITE-142-260"),
                           ("BOM-KS0001-CMM-153-WHITE-001", "CMM2020-WHITE-142-260")):
                r = call(client, mode="checkone", bom=nm, item_code=ic)
                print(f"  {nm} / {ic}: {r['rows']}")
            return 0
    finally:
        drop_script(client)
    return 0


if __name__ == "__main__":
    sys.exit(main())
