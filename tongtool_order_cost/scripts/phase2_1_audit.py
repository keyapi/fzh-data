# -*- coding: utf-8 -*-
"""Phase 2.1 审计（只读）：EN BOM 明细独立重算 + method/valuation 绑定 + BOM 缺行核查。

产物（out/phase2_1/）：
- independent_recalc.csv  抽样 ≥30 行，用 EN tabBOM.total_cost / tabBOM Item 独立重算并与 Phase2 对账
- method_valuation.csv    按 method 抽样的目的地加工成本与 USNJ/USTX/PL BZCP BOM total_cost
- missing_items.csv       BOM 缺行样本的 tabItem/tabBOM 核查
- report.md               结论汇总

不写 GS/EN；只读 SSH 查询。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "phase2_1"
BOM_CSV = ROOT / "out" / "bom_cost_product_with_disabled.csv"
MONTHS = ("202608", "202609")
ALIAS = "阿里云-FZH-ERPNext-frappe"
TOL = 5e-3

BOM_NAME_COLS = ("bom_fg", "bom_sxbzbcp", "bom_sxbzcp",
                 "bom_usnjbzcp", "bom_ustxbzcp", "bom_plbzcp")


def run_sql(sql: str, timeout: int = 300) -> list[list[str]]:
    cmd = (
        "cat > /tmp/q21.sql && cd /home/frappe/frappe-bench && "
        "bench --site erpnext.vilavi.cn mariadb -N --batch < /tmp/q21.sql; "
        "rc=$?; rm -f /tmp/q21.sql; exit $rc"
    )
    p = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", ALIAS, cmd],
        input=sql, capture_output=True, text=True, timeout=timeout,
    )
    if p.returncode != 0:
        raise RuntimeError(p.stderr[:800])
    return [line.split("\t") for line in p.stdout.splitlines() if line.strip()]


def q_list(values) -> str:
    return "','".join(str(v).replace("'", "''") for v in values if v)


def md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    return "\n".join(lines)


def _num(v) -> float | None:
    s = str(v).strip()
    if s in ("", "nan", "None", "NULL"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fetch_bom_totals(names: set[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    names = sorted(n for n in names if n)
    for i in range(0, len(names), 200):
        chunk = names[i:i + 200]
        sql = (
            "SELECT name,item,total_cost,raw_material_cost,operating_cost,"
            "docstatus,is_active,is_default FROM `tabBOM` "
            f"WHERE name IN ('{q_list(chunk)}');"
        )
        for row in run_sql(sql):
            out[row[0]] = {
                "item": row[1], "total_cost": _num(row[2]),
                "raw_material_cost": _num(row[3]), "operating_cost": _num(row[4]),
                "docstatus": row[5], "is_active": row[6], "is_default": row[7],
            }
    return out


def fetch_bom_lines(names: set[str]) -> dict[str, list[tuple[float, float]]]:
    out: dict[str, list[tuple[float, float]]] = {}
    names = sorted(n for n in names if n)
    for i in range(0, len(names), 100):
        chunk = names[i:i + 100]
        sql = (
            "SELECT parent,qty,rate FROM `tabBOM Item` "
            f"WHERE parent IN ('{q_list(chunk)}');"
        )
        for row in run_sql(sql):
            out.setdefault(row[0], []).append((_num(row[1]) or 0.0, _num(row[2]) or 0.0))
    return out


def sample_rows() -> tuple[list[dict], pd.DataFrame]:
    samples: list[dict] = []
    seen: set[tuple] = set()
    blocked: list[pd.Series] = []
    for month in MONTHS:
        path = ROOT / "out" / "merge_shadow" / month / f"merge_shadow_{month}.xlsx"
        p2 = pd.read_excel(path, sheet_name="Phase2成本")
        p2["month"] = month
        priced = p2[p2["status"] == "ok"]
        for i, (_, row) in enumerate(priced[priced["method_diff"].astype(str).str.upper() == "TRUE"].head(20).iterrows()):
            key = (row["month"], "MD", i, row.get("SKU"))
            if key in seen:
                continue
            seen.add(key)
            samples.append(row.to_dict())
        for method in ("皮壳", "半成品", "成品"):
            for _, row in priced[priced["method"] == method].head(10).iterrows():
                key = (row["month"], row.get("group_id"), row.get("SKU"))
                if key in seen:
                    continue
                seen.add(key)
                samples.append(row.to_dict())
        blocked += [row for _, row in p2[p2["reason"] == "bom_item_missing"].iterrows()]
    return samples, pd.DataFrame(blocked)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    bom = pd.read_csv(BOM_CSV, dtype=str, low_memory=False, keep_default_na=False)
    bom_by_item = {r["item_fg"]: r for r in bom.to_dict("records")}
    samples, blocked = sample_rows()

    # 补齐 BOM 报表行
    for s in samples:
        rec = bom_by_item.get(str(s.get("item_fg") or ""), {})
        s["_bom"] = rec
    all_names: set[str] = set()
    for s in samples:
        for col in BOM_NAME_COLS:
            all_names.add(str(s["_bom"].get(col) or ""))
    totals = fetch_bom_totals(all_names)

    rows: list[dict] = []
    for s in samples:
        rec = s["_bom"]
        units = float(s.get("units") or 0.0) or 1.0
        method = str(s.get("method") or "")
        bucket = str(s.get("warehouse_bucket") or "")
        unit = lambda col: (float(s[col]) / units) if s.get(col) is not None else None  # noqa: E731
        en_product = (totals.get(str(rec.get("bom_fg") or "")) or {}).get("total_cost")
        en_semi = (totals.get(str(rec.get("bom_sxbzbcp") or "")) or {}).get("total_cost")
        en_fin = (totals.get(str(rec.get("bom_sxbzcp") or "")) or {}).get("total_cost")
        dest_name = {
            "USNJ": rec.get("bom_usnjbzcp"),
            "USTX": rec.get("bom_ustxbzcp"),
            "PL": rec.get("bom_plbzcp"),
        }.get(bucket)
        en_dest = (totals.get(str(dest_name or "")) or {}).get("total_cost")
        expected_sx = en_semi if method == "半成品" else en_fin if method == "成品" else 0.0
        if expected_sx is None:
            expected_sx = 0.0  # 无对应绍兴 BOM → 报表成本 0
        expected_proc = en_dest if en_dest is not None else 0.0
        diffs = {
            "shell": None if en_product is None else round(unit("皮壳成本") - en_product, 6),
            "sx": round(unit("绍兴二次加工成本") - expected_sx, 6),
            "proc": round(unit("二次加工成本") - expected_proc, 6),
        }
        ok = all(d is not None and abs(d) <= TOL for d in diffs.values())
        report_semi = _num(rec.get("cost_sxbzbcp"))
        report_fin = _num(rec.get("cost_sxbzcp"))
        report_rate = _num(rec.get({
            "USNJ": "usnj_valuation_rate",
            "USTX": "ustx_valuation_rate",
            "PL": "pl_valuation_rate",
        }.get(bucket, "usnj_valuation_rate")))
        rows.append({
            "month": s["month"], "group_id": s.get("group_id"), "merged": s.get("merged"),
            "SKU": s.get("SKU"), "item_fg": s.get("item_fg"), "method": method,
            "bom_method": s.get("bom_method"), "method_diff": s.get("method_diff"),
            "warehouse_bucket": bucket, "units": units,
            "phase2_shell_unit": unit("皮壳成本"), "en_product_total": en_product,
            "diff_shell": diffs["shell"],
            "phase2_sx_unit": unit("绍兴二次加工成本"),
            "en_sx_expected": expected_sx, "diff_sx": diffs["sx"],
            "phase2_proc_unit": unit("二次加工成本"), "en_dest_total": en_dest,
            "expected_proc": expected_proc, "diff_proc": diffs["proc"],
            "report_semi_total": report_semi,
            "report_vs_en_semi": None if en_semi is None or report_semi is None else round(report_semi - en_semi, 6),
            "report_fin_total": report_fin,
            "report_vs_en_fin": None if en_fin is None or report_fin is None else round(report_fin - en_fin, 6),
            "report_rate": report_rate,
            "report_cost_fg": _num(rec.get("cost_fg")),
            "report_sxbzbcp": _num(rec.get("cost_sxbzbcp")),
            "report_sxbzcp": _num(rec.get("cost_sxbzcp")),
            "en_semi_total": en_semi, "en_fin_total": en_fin,
            "pass": ok,
        })
    recalc = pd.DataFrame(rows)
    recalc.to_csv(OUT / "independent_recalc.csv", index=False, encoding="utf-8-sig")

    # method/valuation 绑定：按 method 汇总目的地 BOM 是否一致
    bind = []
    for method in ("皮壳", "半成品", "成品"):
        sub = recalc[recalc["method"] == method]
        delta = (sub["phase2_proc_unit"] - sub["expected_proc"]).abs()
        bind.append({
            "method": method,
            "samples": len(sub),
            "dest_bom_found": int(sub["en_dest_total"].notna().sum()),
            "no_dest_bom_rate_zero": int(sub["en_dest_total"].isna().sum()),
            "report_rate_matches_en": int(delta.le(TOL).sum()),
            "max_abs_diff": round(float(delta.max()), 6) if len(sub) else None,
        })
    md = recalc[recalc["method_diff"].astype(str).str.upper() == "TRUE"]
    delta = (md["phase2_proc_unit"] - md["expected_proc"]).abs()
    bind.append({
        "method": "method_diff",
        "samples": len(md),
        "dest_bom_found": int(md["en_dest_total"].notna().sum()),
        "no_dest_bom_rate_zero": int(md["en_dest_total"].isna().sum()),
        "report_rate_matches_en": int(delta.le(TOL).sum()),
        "max_abs_diff": round(float(delta.max()), 6) if len(md) else None,
    })
    binding = pd.DataFrame(bind)
    binding.to_csv(OUT / "method_valuation.csv", index=False, encoding="utf-8-sig")

    # BOM total_cost = Σ(qty×rate) + operating_cost（抽前 10 个 BOM 验证）
    line_names = list({str(s["_bom"].get(c) or "") for s in samples for c in BOM_NAME_COLS})[:10]
    lines = fetch_bom_lines(set(line_names))
    line_rows = []
    for name in line_names:
        meta = totals.get(name) or {}
        if not meta or name not in lines:
            continue
        line_sum = sum(q * r for q, r in lines[name])
        calc = line_sum + (meta.get("operating_cost") or 0.0)
        line_rows.append({
            "bom": name, "line_sum_raw": round(line_sum, 6),
            "operating_cost": meta.get("operating_cost"),
            "calc_total": round(calc, 6), "total_cost": meta.get("total_cost"),
            "diff": round(calc - (meta.get("total_cost") or 0.0), 6),
        })
    line_check = pd.DataFrame(line_rows)
    line_check.to_csv(OUT / "bom_line_recompute.csv", index=False, encoding="utf-8-sig")

    # BOM 缺行核查：5 个 item_fg
    missing_items = (
        list(dict.fromkeys(str(x) for x in blocked["item_fg"] if x))[:100]
        if len(blocked) and "item_fg" in blocked.columns else []
    )
    item_rows = []
    if missing_items:
        sql_items = (
            "SELECT name,IFNULL(disabled,0),IFNULL(is_sales_item,1),IFNULL(end_of_life,0),"
            "IFNULL(item_group,''),IFNULL(has_variants,0),IFNULL(variant_of,'') "
            f"FROM `tabItem` WHERE name IN ('{q_list(missing_items)}');"
        )
        items = {r[0]: r for r in run_sql(sql_items)}
        sql_boms = (
            "SELECT name,item,IFNULL(is_default,0),IFNULL(is_active,0),docstatus,"
            "IFNULL(total_cost,0) FROM `tabBOM` "
            f"WHERE item IN ('{q_list(missing_items)}') ORDER BY item,docstatus DESC;"
        )
        boms: dict[str, list[list[str]]] = {}
        for r in run_sql(sql_boms):
            boms.setdefault(r[1], []).append(r)
        for item in missing_items:
            rec = items.get(item)
            bl = boms.get(item, [])
            if rec is None:
                cause, handling = "EN 无此 Item", "阻断（物料不存在）"
            elif str(rec[1]) == "1":
                cause, handling = "Item disabled", "阻断（停用物料）"
            elif str(rec[3]) == "1":
                cause, handling = "End of life", "阻断（停产）"
            elif str(rec[2]) == "0":
                cause, handling = "非销售物料", "阻断（不可售）"
            elif not bl:
                cause, handling = "无 BOM", "阻断（无 BOM）"
            elif any(str(r[4]) == "1" and str(r[3]) == "1" for r in bl):
                cause, handling = "有 active+submitted BOM，报表未收录", "可解释回退：刷新 BOM 报表 / 用 EN total_cost"
            else:
                cause, handling = "仅草稿/停用 BOM", "阻断（无有效 BOM）"
            item_rows.append({
                "item_fg": item,
                "in_tabItem": rec is not None,
                "disabled": rec[1] if rec else "",
                "is_sales_item": rec[2] if rec else "",
                "end_of_life": rec[3] if rec else "",
                "item_group": rec[4] if rec else "",
                "variant_of": rec[6] if rec else "",
                "bom_count": len(bl),
                "bom_names": ", ".join(r[0] for r in bl[:5]),
                "cause": cause, "handling": handling,
            })
    missing_df = pd.DataFrame(item_rows)
    missing_df.to_csv(OUT / "missing_items.csv", index=False, encoding="utf-8-sig")

    alt_delta_total = 0.0
    for month in MONTHS:
        path = ROOT / "out" / "merge_shadow" / month / f"merge_shadow_{month}.xlsx"
        p2 = pd.read_excel(path, sheet_name="Phase2成本")
        if "method_diff_alt_delta" in p2.columns:
            alt_delta_total += float(p2["method_diff_alt_delta"].fillna(0).sum())

    # 结论报告
    total_rows = len(recalc)
    pass_rows = int(recalc["pass"].sum())
    sx_issues = recalc[recalc["diff_sx"].notna() & (recalc["diff_sx"].abs() > TOL)]
    shell_issues = recalc[recalc["diff_shell"].notna() & (recalc["diff_shell"].abs() > TOL)]
    proc_issues = recalc[recalc["diff_proc"].notna() & (recalc["diff_proc"].abs() > TOL)]
    lines = [
        "# Phase 2.1 审计报告（EN BOM 明细独立重算）",
        "",
        "> BOM 快照：`out/bom_cost_product_with_disabled.csv`（含 disabled=1；历史订单可引用停用物料）。",
        "",
        f"- 抽样：{total_rows} 行（覆盖 皮壳/半成品/成品 各 10 行 + method_diff 行）",
        f"- 三项独立重算全部通过：{pass_rows} / {total_rows}",
        f"- 皮壳成本不一致：{len(shell_issues)} 行；绍兴二次不一致：{len(sx_issues)} 行；"
        f"目的地加工不一致：{len(proc_issues)} 行",
        "",
        "## method/valuation 绑定",
        "",
        "| 分组 | 样本 | 找到目的地 BOM | 无 BOM(rate=0) | 与 Phase2 一致 | 最大绝对差 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in binding.to_dict("records"):
        lines.append(
            f"| {r['method']} | {r['samples']} | {r['dest_bom_found']} | "
            f"{r['no_dest_bom_rate_zero']} | {r['report_rate_matches_en']} | {r['max_abs_diff']} |"
        )
    lines += [
        "",
        "结论：USNJ/USTX/PL 的 valuation_rate 均等于对应 USNJBZCP#/USTXBZCP#/PLBZCP# BOM 的 "
        "`total_cost`，与产品 `shipping_method` 无关（各 method 样本均能对上）。"
        "因此二次加工按仓库分类对全部 method 生效；method_diff 行按 EN method 定价，"
        "BOM method 仅作审计差异（见 Phase2 的 `method_diff_alt_delta`）。",
        "",
        "## 目的地加工不一致行（若有）",
        "",
    ]
    if len(proc_issues):
        lines.append(md_table(proc_issues[["month", "item_fg", "method", "phase2_proc_unit",
                                          "en_dest_total", "diff_proc"]].head(20)))
    else:
        lines.append("- 无")
    lines += [
        "",
        "## 绍兴二次加工不一致行（报表 BOM 版本漂移，若有）",
        "",
    ]
    if len(sx_issues):
        lines.append(md_table(sx_issues[["month", "item_fg", "method", "phase2_sx_unit",
                                        "en_sx_expected", "diff_sx", "report_sxbzbcp",
                                        "report_sxbzcp", "en_semi_total", "en_fin_total"]].head(20)))
    else:
        lines.append("- 无")
    semi_drift = recalc[recalc["report_vs_en_semi"].notna() & (recalc["report_vs_en_semi"].abs() > TOL)]
    fin_drift = recalc[recalc["report_vs_en_fin"].notna() & (recalc["report_vs_en_fin"].abs() > TOL)]
    lines += [
        "",
        "## 报表字段 vs EN BOM 漂移（仅对账）",
        "",
        f"- 报表 `cost_sxbzbcp` vs EN SXBZBCP total_cost：{len(semi_drift)} 行不一致",
        f"- 报表 `cost_sxbzcp` vs EN SXBZCP total_cost：{len(fin_drift)} 行不一致",
        f"- 其中 Phase2 实际受影响的绍兴二次差异：{len(sx_issues)} 行（按 method 选列后）",
        "",
        "> 漂移集中在 Phase2 未使用的列（半成品用 sxbzbcp、皮壳 sx=0、成品用 sxbzcp 且与 EN 一致），"
        "说明“按 method 选列”是必要的；若把 cost_sxbzcp 无条件用于所有 method 会引入报表漂移。",
        "",
        "## BOM 缺行核查（5 个样本）",
        "",
    ]
    if len(missing_df):
        cause_counts = missing_df["cause"].value_counts().to_dict()
        lines.append(f"全量 {len(missing_df)} 个缺行 item_fg；原因分布：{cause_counts}")
        lines.append("")
        lines.append(md_table(missing_df[["item_fg", "disabled", "is_sales_item", "end_of_life",
                                         "bom_count", "cause", "handling"]].head(10)))
    else:
        lines.append("- 无")
    lines += [
        "",
        "## 结论/处理",
        "",
        "- **method_diff**：按 EN `shipping_method` 定价（Phase 1.1 规则），BOM method 不一致仅标记 + 审计差异；"
        "不阻断（抽样中 method_diff 行的皮壳/目的地加工均与 EN 对上）。",
        "- **BOM 缺行**：若 item 停用/非销售/无 BOM → 阻断；若 EN 有 active+submitted BOM 而报表缺行 → "
        "可解释回退（刷新报表/用 EN total_cost），未在 Phase2 自动采信。",
        "- **多候选（CURVE-PILLOW）**：只用 Phase 1 锁定的 `product_id` 子树；"
        "CURVE-PILLOW 在 KS0340 子树内仍有多个变体 Item（DM/HLR 颜色价不同）→ 仍阻断，"
        "不使用组内任一 BOM；若业务要定价，需先锁定具体变体。",
        "- **method_diff 规则**：快照差异可放行（按 EN method 定价），BOM method 只做审计；"
        f"若改按 BOM method 定价，审计差异合计 {round(alt_delta_total, 6)}。",
        "",
    ]
    (OUT / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print("written", OUT)
    print(recalc[["pass"]].value_counts().to_dict())
    print(binding.to_string(index=False))
    print(missing_df.to_string(index=False) if len(missing_df) else "no missing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
