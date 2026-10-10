# -*- coding: utf-8 -*-
"""重量模板(ZLMB#)问题盘点 + KS0322 迁移 dry-run。

背景：BOM Cost List V2 用 `item.name.split('-')[:3]` 拼 `ZLMB#{型号}-{面料}-{尺寸}`（固定 3 段）。
若重量模板被建成带颜色的 4 段，报表取不到 → 成品计费重量 0 → 「发成品尾程前成本」记 0。

子命令：
  issues          拉/读报表 → 列出所有「重量模板解析不到」的产品并分类 → out/*.xlsx
  ks0322-dryrun   只读：打印 ZLMB#KS0322 的迁移计划（旧变体重尺 → 新 3 段模板）

只读为主；不写生产。
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
EN_API = HERE.parent
OUT = EN_API / "out"
RAW = OUT / "bclv2_raw.json"          # 报表原始响应缓存（可由 issues --refresh 重拉）
REPORT_FIELDS = [
    "custom_cover_weight_per_unit", "custom_fg_weight_per_unit",
    "custom_package_volume", "custom_sfg_package_volume", "custom_sfg_weight_per_unit",
]
# 一并搬运的其它重尺字段（报表暂不用，但保持一致）
EXTRA_FIELDS = [
    "weight_uom", "custom_cover_weight_uom", "custom_fg_weight_uom", "custom_sfg_weight_uom",
    "custom_item_volume", "custom_outer_package_volume",
    "custom_item_length", "custom_item_width", "custom_item_height",
    "custom_outer_package_length", "custom_outer_package_width", "custom_outer_package_height",
    "custom_sfg_weight_per_unit", "custom_sfg_item_volume", "custom_sfg_outer_package_volume",
    "custom_package_length", "custom_package_width", "custom_package_height",
    "custom_finish_good_weight_per_unit", "custom_fg_item_volume",
    "custom_fg_outer_package_volume", "custom_fg_package_volume",
]


def load_env() -> dict[str, str]:
    env = {}
    for p in (EN_API.parent / ".env", EN_API / ".env"):
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("'\"")
    return env


ENV = load_env()
BASE = "https://erpnext.vilavi.cn"
HEAD = {"Authorization": f"token {ENV['PROD_ERP_API_KEY']}:{ENV['PROD_ERP_API_SECRET']}"}


def _get(path: str):
    return json.loads(urllib.request.urlopen(urllib.request.Request(BASE + path, headers=HEAD), timeout=120).read().decode())


def get_item(name: str):
    try:
        return _get("/api/resource/Item/" + urllib.parse.quote(name, safe=""))["data"]
    except Exception:
        return None


def item_attr_names(doc) -> list[str]:
    return [a.get("attribute") for a in (doc or {}).get("attributes") or []]


def load_report(refresh: bool) -> dict:
    if refresh or not RAW.exists():
        filters = {"item_group": "产品", "show_disabled": 1, "show_ref_code": 1,
                   "sum_columns_at_end": 1, "pllc_sfg_missing_use_cover": 0, "simplified_column_view": 0}
        q = urllib.parse.urlencode({"report_name": "BOM Cost List V2", "ignore_prepared_report": 1,
                                    "filters": json.dumps(filters)})
        d = _get("/api/method/frappe.desk.query_report.run?" + q)["message"]
        OUT.mkdir(parents=True, exist_ok=True)
        RAW.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return json.loads(RAW.read_text(encoding="utf-8"))


def classify(code: str) -> dict:
    parts = str(code).split("-")
    report_code = "ZLMB#" + "-".join(parts[:3])          # 报表口径
    full_code = "ZLMB#" + str(code)                       # 全码（含颜色）
    rep_doc, full_doc = get_item(report_code), get_item(full_code)
    full_attrs = item_attr_names(full_doc)
    has_color = any("颜色" in (a or "") for a in full_attrs)
    if full_doc and has_color:
        cat, act = "带颜色模板", "去掉模板颜色属性 + 变体改/补名为 3 段（保留重尺）"
    elif full_doc:
        cat, act = "段位不符(报表3段假设)", "模板名其实正确 → 改报表取值逻辑"
    else:
        cat, act = "缺重量模板", "按惯例补建 ZLMB#{型号}-{面料}-{尺寸}"
    return {
        "产品编号": code, "报表口径模板码": report_code, "报表口径模板存在": bool(rep_doc),
        "实际模板码(全码)": full_code, "实际模板存在": bool(full_doc),
        "实际模板属性": " / ".join(a or "" for a in full_attrs), "是否带颜色": "是" if has_color else "",
        "类别": cat, "建议动作": act,
    }


def cmd_issues(refresh: bool) -> None:
    d = load_report(refresh)
    prods = sorted({r["item_fg"] for r in d["result"]
                    if isinstance(r, dict) and r.get("item_zlmb") and (r.get("item_zlmb_name") in (None, ""))})
    rows = [classify(c) for c in prods]
    df = pd.DataFrame(rows)
    name_by_code = {}
    for r in d["result"]:
        if isinstance(r, dict) and r.get("item_fg") not in name_by_code:
            name_by_code[r["item_fg"]] = r.get("item_fg_name")
    df.insert(1, "产品名称", df["产品编号"].map(name_by_code))
    df = df.sort_values(["类别", "产品编号"])
    OUT.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    p = OUT / f"weight_template_issues_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    with pd.ExcelWriter(p, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="重量模板问题清单", index=False)
        df["类别"].value_counts().rename_axis("类别").reset_index(name="数量").to_excel(w, sheet_name="分类汇总", index=False)
    print(f"共 {len(df)} 个产品 → {p}")
    print(df["类别"].value_counts().to_string())


def cmd_ks0322_dryrun() -> None:
    tpl, src, tgt = get_item("ZLMB#KS0322"), get_item("ZLMB#KS0322-HLR-65-GREY"), get_item("ZLMB#KS0322-HLR-65")
    print("模板 重量模板#手臂支撑枕 = ZLMB#KS0322")
    print("   属性:", item_attr_names(tpl), "| 含颜色:", any("颜色" in (a or "") for a in item_attr_names(tpl)))
    print("旧变体 ZLMB#KS0322-HLR-65-GREY 存在:", bool(src), "| 属性:", item_attr_names(src))
    print("目标  ZLMB#KS0322-HLR-65 存在:", bool(tgt))
    if not src:
        print("!! 找不到旧变体，无法迁移"); return
    print("\n计划：")
    print(" 1) 从模板 ZLMB#KS0322 移除「颜色」属性（否则新变体不带颜色会被 ERPNext 拒）")
    print("    注意：模板已存在变体时移除属性需在测试机先验证（可能需先处理旧变体）")
    print(" 2) 建/改出 3 段变体 ZLMB#KS0322-HLR-65，attributes = 面料=荷兰绒, 尺寸=65X60X15")
    print("    custom_model_id 前缀沿用 ZLMB#")
    print("\n 3) 从旧变体抄这些字段（报表实际读前 5 个）：")
    for f in REPORT_FIELDS:
        print(f"      {f:<40} = {src.get(f)!r}   ← 报表必读")
    extra_nonzero = [(f, src.get(f)) for f in EXTRA_FIELDS if f not in REPORT_FIELDS and src.get(f) not in (None, "", 0)]
    print(f"    （另有 {len(extra_nonzero)} 个非空重尺字段一并抄）")
    print("\n 4) 旧变体 ZLMB#KS0322-HLR-65-GREY 先保留（不删），确认报表取到新模板后再决定停用")
    print("\n(只读 dry-run，未做任何写入)")


def _put_item(name: str, payload: dict):
    url = BASE + "/api/resource/Item/" + urllib.parse.quote(name, safe="")
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="PUT", headers={**HEAD, "Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=120).read().decode())["data"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"PUT {name} -> {e.code}: {e.read().decode()[:300]}") from None


def _zz_run(script_name: str, api_method: str, body: str):
    post = urllib.request.Request(BASE + "/api/resource/Server%20Script",
                                  data=json.dumps({"doctype": "Server Script", "name": script_name, "script_type": "API",
                                                   "api_method": api_method, "script": body, "allow_guest": 0}).encode(),
                                  method="POST", headers={**HEAD, "Content-Type": "application/json"})
    urllib.request.urlopen(post, timeout=120).read()
    try:
        call = urllib.request.Request(BASE + "/api/method/" + api_method, data=b"{}", method="POST",
                                      headers={**HEAD, "Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(call, timeout=180).read().decode())
    finally:
        try:
            urllib.request.urlopen(urllib.request.Request(
                BASE + "/api/resource/Server%20Script/" + urllib.parse.quote(script_name, safe=""), method="DELETE", headers=HEAD), timeout=60).read()
        except Exception as e:
            print("删脚本告警:", e)


def cmd_ks0322_apply(yes: bool) -> None:
    from datetime import datetime
    TPLM, VAR, NEW = "ZLMB#KS0322", "ZLMB#KS0322-HLR-65-GREY", "ZLMB#KS0322-HLR-65"
    tpl, var = get_item(TPLM), get_item(VAR)
    OUT.mkdir(parents=True, exist_ok=True)
    snap = OUT / f"ks0322_snapshot_{datetime.now():%Y%m%d_%H%M%S}.json"
    snap.write_text(json.dumps({"template": tpl, "variant": var}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"① 快照 -> {snap}")
    print(f"   模板属性: {item_attr_names(tpl)}")
    print(f"   变体属性: {[(a.get('attribute'), a.get('attribute_value')) for a in var['attributes']]}")
    print(f"   变体重尺: cover={var.get('custom_cover_weight_per_unit')} fg={var.get('custom_fg_weight_per_unit')} pkgvol={var.get('custom_package_volume')}")
    if get_item(NEW):
        raise SystemExit(f"!! 目标 {NEW} 已存在，中止")
    if not yes:
        print("(未传 --yes，未做任何写入)"); return

    var_attrs = [{"attribute": a["attribute"], "attribute_value": a.get("attribute_value")}
                 for a in var["attributes"] if "颜色" not in (a["attribute"] or "")]
    print("② 删变体颜色行 ->", [(x["attribute"], x["attribute_value"]) for x in var_attrs])
    _put_item(VAR, {"attributes": var_attrs})

    tpl_attrs = [{"attribute": a["attribute"]} for a in tpl["attributes"] if "颜色" not in (a["attribute"] or "")]
    print("③ 删模板颜色属性 ->", [x["attribute"] for x in tpl_attrs])
    _put_item(TPLM, {"attributes": tpl_attrs})

    print(f"④ rename {VAR} -> {NEW}")
    body = (f'frappe.rename_doc("Item", "{VAR}", "{NEW}", force=True)\nfrappe.db.commit()\n'
            f'frappe.response["message"] = {{"new": bool(frappe.db.exists("Item","{NEW}")), "old": bool(frappe.db.exists("Item","{VAR}"))}}')
    print("   ->", json.dumps(_zz_run("zz_rename_ks0322_weight", "zz_rename_ks0322_weight", body), ensure_ascii=False)[:200])

    nv = get_item(NEW)
    print("⑤ 回读:", NEW, "| attrs:", [(a.get("attribute"), a.get("attribute_value")) for a in (nv or {}).get("attributes", [])],
          "| cover:", (nv or {}).get("custom_cover_weight_per_unit"), "fg:", (nv or {}).get("custom_fg_weight_per_unit"),
          "pkgvol:", (nv or {}).get("custom_package_volume"))
    print("   旧码仍在?", bool(get_item(VAR)), "| 模板属性:", item_attr_names(get_item(TPLM)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", choices=["issues", "ks0322-dryrun", "ks0322-apply"])
    ap.add_argument("--refresh", action="store_true", help="issues 时强制重拉报表")
    ap.add_argument("--yes", action="store_true", help="ks0322-apply 真正写生产")
    args = ap.parse_args()
    if args.cmd == "issues":
        cmd_issues(args.refresh)
    elif args.cmd == "ks0322-dryrun":
        cmd_ks0322_dryrun()
    else:
        cmd_ks0322_apply(args.yes)


if __name__ == "__main__":
    main()
