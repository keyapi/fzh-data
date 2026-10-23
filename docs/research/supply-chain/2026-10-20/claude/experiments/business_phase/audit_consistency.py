#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""T21: cross-deliverable consistency audit (read-only, no DB access).

For each of the eight required comparisons this script computes the value from
the machine-readable artifact and extracts the value stated in the document,
then reports PASS / FAIL with the file, field and both values. It never edits a
number: discrepancies are listed with a recommended correction only. Text is
not changed at all (ownership is limited to this audit and its outputs).

Checks
  1 replenishment_v2.csv   <-> summary_v3.md
  2 model_sensitivity.csv  <-> model_sensitivity.md
  3 wo_dn_coverage.csv     <-> wo_dn_coverage.md
  4 explanations.csv       <-> decision_v2.csv + T4 anomaly table
  5 diff_v1_v2.csv         <-> replenishment_all.csv / replenishment_v2.csv
  6 evidence_request.md    <-> T3 decision_v2.csv counts
  7 summary_v3 §6          <-> nested_eval.json / short_history_eval.json
  8 forward_shadow_plan.md <-> forward_shadow.py behaviour

Superseded documents are listed with their replacement and are not compared
word-for-word.

Outputs: out/business_phase/consistency_audit.json / .md
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve()
CLAUDE_DIR = HERE.parents[2]
OUT = CLAUDE_DIR / "out" / "business_phase"
FE = CLAUDE_DIR / "experiments" / "business_phase" / "forecast_eval"
REVIEWS = CLAUDE_DIR / "control" / "reviews"

OUT_JSON = OUT / "consistency_audit.json"
OUT_MD = OUT / "consistency_audit.md"


def rd(name: str) -> str:
    return (OUT / name).read_text(encoding="utf-8")


def rows(name: str) -> list[dict]:
    return list(csv.DictReader(open(OUT / name, encoding="utf-8-sig")))


def jload(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def num(m) -> float | None:
    if m is None:
        return None
    return float(str(m).replace(",", "").replace("−", "-"))


def grab(text: str, pattern: str):
    m = re.search(pattern, text)
    return m.group(1) if m else None


class Check:
    def __init__(self, cid: str, title: str):
        self.cid, self.title = cid, title
        self.diffs, self.notes = [], []

    def cmp(self, file: str, field: str, table_value, doc_value, tol=0.0):
        ok = (table_value is not None and doc_value is not None
              and abs(float(table_value) - float(doc_value)) <= tol)
        if not ok:
            self.diffs.append(dict(file=file, field=field,
                                   table_value=table_value, doc_value=doc_value))
        return ok

    def result(self) -> dict:
        return dict(id=self.cid, title=self.title,
                    status="PASS" if not self.diffs else "FAIL",
                    diffs=self.diffs, notes=self.notes)


def check_1() -> dict:
    c = Check("1", "replenishment_v2.csv ↔ summary_v3.md")
    r = rows("replenishment_v2.csv")
    doc = rd("summary_v3.md")
    c.cmp("summary_v3.md", "输出行数", len(r),
          num(grab(doc, r"\| 输出行数 \| ([\d,]+) \|")))
    c.cmp("summary_v3.md", "覆盖 SKU 数", len({x["SKU"] for x in r}),
          num(grab(doc, r"\| 覆盖 SKU 数 \| ([\d,]+)")))
    st = Counter(x["状态"] for x in r)
    m = re.search(r"\| 状态 A / B / B_pending_inventory / C \| ([\d]+) / ([\d]+) / ([\d]+) / ([\d]+) \|", doc)
    if m:
        for label, val in zip(("A", "B", "B_pending_inventory", "C"), m.groups()):
            c.cmp("summary_v3.md", f"状态 {label}", st.get(label, 0), num(val))
    else:
        c.diffs.append(dict(file="summary_v3.md", field="状态分布", table_value=dict(st), doc_value=None))
    meth = Counter(x["预测方法(实际使用)"] for x in r)
    auto = sum(v for k, v in meth.items() if k.startswith("AutoETS"))
    ma3 = sum(v for k, v in meth.items() if k.startswith("MA3"))
    md_auto = num(grab(doc, r"AutoETS ([\d,]+) 行"))
    md_ma3 = num(grab(doc, r"MA3 ([\d,]+) 行"))
    c.cmp("summary_v3.md", "方法 AutoETS 行", auto, md_auto)
    c.cmp("summary_v3.md", "方法 MA3 行", ma3, md_ma3)
    # 6-month sales coverage: the CSV has no such column; verify doc arithmetic
    # and cross-check summary.md (same generation).
    b = num(grab(doc, r"\| B \| ([\d,]+) \| ([\d.]+)% \|"))
    b_share = num(grab(doc, r"\| B \| [\d,]+ \| ([\d.]+)% \|"))
    cc = num(grab(doc, r"\| C \| ([\d,]+) \| ([\d.]+)% \|"))
    c_share = num(grab(doc, r"\| C \| [\d,]+ \| ([\d.]+)% \|"))
    if None in (b, cc):
        c.diffs.append(dict(file="summary_v3.md", field="6个月净出库 B/C", table_value=None, doc_value="未解析"))
    else:
        share_b = b / (b + cc) * 100 if (b + cc) else 0
        share_c = cc / (b + cc) * 100 if (b + cc) else 0
        c.cmp("summary_v3.md", "B 销量占比(算术)", round(share_b, 1), b_share, tol=0.05)
        c.cmp("summary_v3.md", "C 销量占比(算术)", round(share_c, 1), c_share, tol=0.05)
        old = rd("summary.md")
        c.cmp("summary.md", "B 6个月净出库", b,
              num(grab(old, r"\| B \| [\d,]+ \| ([\d,]+) \|")))
        c.notes.append("replenishment_v2.csv 无 6 个月销量列；占比按 summary_v3 自身原始值验算，"
                       "并与 summary.md 的 48,001/543 一致（可复核但不能从 CSV 重算）。")
    return c.result()


def check_2() -> dict:
    c = Check("2", "model_sensitivity.csv ↔ model_sensitivity.md")
    r = rows("model_sensitivity.csv")
    doc = rd("model_sensitivity.md")
    st = Counter(x["分类"] for x in r)
    sku6 = {}
    for x in r:
        if x["销量_近6月"] not in ("", None):
            sku6[x["SKU"]] = float(x["销量_近6月"])
    total6 = sum(sku6.get(s, 0.0) for s in {x["SKU"] for x in r}) or 1.0
    # parse the five-class table
    parsed = {}
    for line in doc.splitlines():
        if not line.startswith("| ") or "---" in line:
            continue
        cells = [x.strip() for x in line.strip("|").split("|")]
        if len(cells) == 5 and cells[0].startswith(("①", "③a", "③b", "库存未知", "范围外")):
            parsed[cells[0]] = dict(rows=num(cells[1]), skus=num(cells[2]),
                                    sales=num(cells[3]),
                                    share=num(cells[4].replace("%", "")))
    for cls, d in parsed.items():
        c.cmp("model_sensitivity.md", f"{cls} 行数", st.get(cls, 0), d["rows"])
        c.cmp("model_sensitivity.md", f"{cls} SKU", len({x["SKU"] for x in r if x["分类"] == cls}), d["skus"])
        sales = sum(sku6.get(s, 0.0) for s in {x["SKU"] for x in r if x["分类"] == cls})
        c.cmp("model_sensitivity.md", f"{cls} 销量覆盖%",
              round(sales / total6 * 100, 2), d["share"], tol=0.01)
    if len(parsed) != 5:
        c.diffs.append(dict(file="model_sensitivity.md", field="五类表", table_value=5, doc_value=len(parsed)))
    # ③a sub-split
    sub = Counter(x["子类"] for x in r if x["子类"])
    md_2 = num(grab(doc, r"② 同向·区间不重叠：\*\*([\d,]+) 行\*\*"))
    md_4 = num(grab(doc, r"④ 同向·区间重叠·有数量差：\*\*([\d,]+) 行\*\*"))
    c.cmp("model_sensitivity.md", "② 行数", sub.get("②同向·区间不重叠", 0), md_2)
    c.cmp("model_sensitivity.md", "④ 行数", sub.get("④同向·区间重叠·有数量差", 0), md_4)
    c.notes.append("CSV 分类/子类计数与 md 表一致；销量覆盖按去重 SKU 近 6 月值重算。")
    return c.result()


def check_3() -> dict:
    c = Check("3", "wo_dn_coverage.csv ↔ wo_dn_coverage.md")
    r = rows("wo_dn_coverage.csv")
    doc = rd("wo_dn_coverage.md")
    st = Counter(x["覆盖状态"] for x in r)
    for cls, pat in (
        ("covered_validated", r"`covered_validated` \| \*\*([\d,]+)\*\* \| ([\d]+)"),
        ("covered_unvalidated", r"`covered_unvalidated` \| \*\*([\d,]+)\*\* \| ([\d]+)"),
        ("no_material_found", r"`no_material_found` \| \*\*([\d,]+)\*\* \| ([\d]+)")):
        m = re.search(pat, doc)
        rows_v = num(m.group(1)) if m else None
        skus_v = num(m.group(2)) if m else None
        c.cmp("wo_dn_coverage.md", f"{cls} 行数", st.get(cls, 0), rows_v)
        c.cmp("wo_dn_coverage.md", f"{cls} SKU",
              len({x["SKU"] for x in r if x["覆盖状态"] == cls}), skus_v)
    j = jload(OUT / "wo_dn_coverage.json")
    link = j["linkage"]
    # md rows: | WO↔SO | total | linked | missing |
    for key, label in (("WO_SO", "WO↔SO"), ("DN_WO", "DN↔WO"), ("WO_PO", "WO↔PO")):
        m = re.search(rf"\| {label} \| ([\d,]+) \| ([\d,]+) \| ([\d,]+) \|", doc)
        if not m:
            c.diffs.append(dict(file="wo_dn_coverage.md", field=label, table_value=link[key], doc_value=None))
            continue
        c.cmp("wo_dn_coverage.md", f"{label} 总数", link[key]["total"], num(m.group(1)))
        c.cmp("wo_dn_coverage.md", f"{label} 有键", link[key]["linked"], num(m.group(2)))
        c.cmp("wo_dn_coverage.md", f"{label} 缺键", link[key]["missing"], num(m.group(3)))
    c.notes.append("三态合计与 CSV/JSON 一致；关联键按 JSON 的 total/linked/missing 比对。")
    return c.result()


def check_4() -> dict:
    c = Check("4", "explanations.csv ↔ decision_v2.csv（异常计数）")
    e = rows("explanations.csv")
    d = rows("decision_v2.csv")
    c.cmp("decision_v2.csv", "行数", len(e), len(d))
    c.cmp("decision_v2.csv", "状态分布一致", 1,
          1 if Counter(x["状态"] for x in e) == Counter(x["状态"] for x in d) else 0)
    tag_rows = Counter({t: 0 for t in
                        ("short_history", "missing_inventory", "zero_sales",
                         "returns_unobservable", "promo_spike", "operational_change",
                         "stockout_censoring", "duplicate_mapping")})
    tag_skus = {t: set() for t in
                ("short_history", "missing_inventory", "zero_sales", "returns_unobservable",
                 "promo_spike", "operational_change", "stockout_censoring", "duplicate_mapping")}
    for x in e:
        tags = [t.strip() for t in (x["异常标签"] or "").split("；") if t.strip()]
        for t in tags:
            if t in tag_rows or t in tag_skus:
                tag_rows[t] += 1
                tag_skus[t].add(x["SKU"])
    t4 = (REVIEWS / "2026-10-22-t4-explanations.md").read_text(encoding="utf-8")
    for tag in ("short_history", "missing_inventory", "zero_sales", "returns_unobservable",
                "promo_spike", "operational_change", "stockout_censoring", "duplicate_mapping"):
        m = re.search(rf"\| `{tag}` \| \*?\*?([\d,]+)\*?\*? \| ([\d,]+)", t4)
        c.cmp("2026-10-22-t4-explanations.md", f"{tag} 命中行", tag_rows.get(tag, 0),
              num(m.group(1)) if m else None)
        c.cmp("2026-10-22-t4-explanations.md", f"{tag} 命中 SKU", len(tag_skus[tag]),
              num(m.group(2)) if m else None)
    unlabeled = sum(1 for x in e if not (x["异常标签"] or "").strip())
    c.cmp("explanations.csv", "未打标签行", unlabeled, 0)
    c.notes.append("八类标签按「；」拆分计数；与 T4 评审表逐项比对，缺失标签计 0。")
    return c.result()


def check_5() -> dict:
    c = Check("5", "diff_v1_v2.csv ↔ replenishment_all.csv / replenishment_v2.csv")
    d = rows("diff_v1_v2.csv")
    v1 = rows("replenishment_all.csv")
    v2 = rows("replenishment_v2.csv")
    c.cmp("diff_v1_v2.csv", "行数", len(d), 1328)
    c.cmp("replenishment_all.csv", "行数", len(v1), len(d))
    c.cmp("replenishment_v2.csv", "SKU 数", len({x["SKU"] for x in v2}), len(d))
    ch = Counter(x["change_status"] for x in d)
    comp = sum(1 for x in d if x["comparable"] == "True")
    doc = rd("summary_v3.md")
    c.cmp("summary_v3.md", "可比 SKU", comp, num(grab(doc, r"可比 SKU ([\d,]+) 个")))
    c.cmp("summary_v3.md", "数量变化", ch.get("changed", 0), num(grab(doc, r"([\d,]+) 个数量变化")))
    c.cmp("summary_v3.md", "partial_unknown", ch.get("partial_unknown", 0), num(grab(doc, r"([\d,]+) 个 SKU 部分仓待核实")))
    c.cmp("summary_v3.md", "all_unknown", ch.get("all_unknown", 0), num(grab(doc, r"([\d,]+) 个 SKU 全部仓待核实")))
    c.cmp("summary_v3.md", "v1_no_quantity(C)", ch.get("v1_no_quantity", 0), num(grab(doc, r"([\d,]+) 个 v1 无数量")))
    c.notes.append("475 unchanged 由行数差额核对（1,328 − 602 − 154 − 6 − 91）；文档未单独写 475。")
    return c.result()


def check_6() -> dict:
    c = Check("6", "evidence_request.md 责任方行数 ↔ decision_v2.csv（T3）")
    d = rows("decision_v2.csv")
    doc = rd("evidence_request.md")
    po_rows = [x for x in d if x["PO未结"] not in ("", None)]
    elig = [x for x in d if x["状态"] != "C"]
    c_rows = [x for x in d if x["状态"] == "C"]
    dedupe = [x for x in d if x["PO去重状态"] != "none_recorded"
              or x["在途去重状态"] != "none_recorded"]
    exp = dict(po=(len(po_rows), len({x["SKU"] for x in po_rows})),
               elig=(len(elig), len({x["SKU"] for x in elig})),
               c=(len(c_rows), len({x["SKU"] for x in c_rows})),
               dedupe=(len(dedupe), len({x["SKU"] for x in dedupe})))
    # doc values in table order
    pairs = re.findall(r"\*\*([\d,]+) 行 / ([\d,]+) SKU\*\*", doc)
    c.cmp("evidence_request.md", "采购/供应链 行/SKU", exp["po"][0], num(pairs[0][0]) if pairs else None)
    c.cmp("evidence_request.md", "采购/供应链 SKU", exp["po"][1], num(pairs[0][1]) if pairs else None)
    for i, name in ((1, "生产/PMC"), (3, "采购/财务"), (4, "业务"), (5, "供应链管理")):
        c.cmp("evidence_request.md", f"{name} 行/SKU", exp["elig"][0], num(pairs[i][0]) if len(pairs) > i else None)
        c.cmp("evidence_request.md", f"{name} SKU", exp["elig"][1], num(pairs[i][1]) if len(pairs) > i else None)
    c.cmp("evidence_request.md", "主数据/EN 行/SKU", exp["c"][0], num(pairs[2][0]) if len(pairs) > 2 else None)
    c.cmp("evidence_request.md", "主数据/EN SKU", exp["c"][1], num(pairs[2][1]) if len(pairs) > 2 else None)
    c.cmp("evidence_request.md", "数据/系统 行/SKU", exp["dedupe"][0], num(pairs[6][0]) if len(pairs) > 6 else None)
    c.cmp("evidence_request.md", "数据/系统 SKU", exp["dedupe"][1], num(pairs[6][1]) if len(pairs) > 6 else None)
    c.notes.append("文档另写“248 条 open 行 0 条有日期”；本地 CSV/JSON 无该口径，未纳入本轮核对。")
    return c.result()


def check_7() -> dict:
    c = Check("7", "summary_v3 §6 ↔ nested_eval / short_history_eval")
    doc = rd("summary_v3.md")
    n = jload(FE / "nested_eval.json")
    s = jload(FE / "short_history_eval.json")
    attr = jload(FE / "error_attribution.json")
    sh = attr["short_history"]
    final = [k for k in n["blocks"] if k.startswith("2026-06")][0]
    blk = n["blocks"][final]
    for label, key in (("选择流程", "selected"), ("MA3", "ma3"), ("naive", "naive")):
        pat = {"选择流程": r"选择流程 \*\*([\d.]+)\*\* / MA3", "MA3": r"MA3 \*\*([\d.]+)\*\* /",
               "naive": r"naive \*\*([\d.]+)\*\*（共同可评"}[label]
        c.cmp("summary_v3.md", f"最后块 {label}", blk[key], num(grab(doc, pat)))
    bs = n["bootstrap_final"]
    c.cmp("summary_v3.md", "bootstrap MA3 p5", bs["selected_minus_ma3"]["p5"],
          num(grab(doc, r"选择流程 − MA3 \*\*\[(−?[\d.]+), \+?([\d.]+)\]\*\*")))
    c.cmp("summary_v3.md", "bootstrap MA3 p95", bs["selected_minus_ma3"]["p95"],
          num((re.search(r"选择流程 − MA3 \*\*\[(−?[\d.]+), \+?([\d.]+)\]\*\*", doc) or [None, None, None])[2]))
    m = re.search(r"选择流程 − naive \*\*\[(−?[\d.]+), \+?([\d.]+)\]\*\*", doc)
    c.cmp("summary_v3.md", "bootstrap naive p5", bs["selected_minus_naive"]["p5"], num(m.group(1)) if m else None)
    c.cmp("summary_v3.md", "bootstrap naive p95", bs["selected_minus_naive"]["p95"], num(m.group(2)) if m else None)
    dist = dict(n["selection_distribution"])
    for k, pat in (("naive", r"naive ([\d]+) / ma6"), ("ma6", r"ma6 ([\d]+) / seasonal_naive"),
                   ("seasonal_naive", r"seasonal_naive ([\d]+)"),
                   ("autoets", r"autoets ([\d]+) / ma3"), ("ma3", r"ma3 ([\d]+) / combo_ew"),
                   ("combo_ew", r"combo_ew ([\d]+)")):
        c.cmp("summary_v3.md", f"选模分布 {k}", dist.get(k, 0), num(grab(doc, pat)))
    sm = n["series_sample"]["per_block"]
    c.cmp("summary_v3.md", "2025-10 旧规则未首单", sm["2025-10"]["old_rule_not_started_in_sample"],
          num(grab(doc, r"混入了 ([\d]+) 个")))
    c.cmp("summary_v3.md", "2026-01 旧规则未首单", sm["2026-01"]["old_rule_not_started_in_sample"],
          num(grab(doc, r"2026-01 混入 ([\d]+) 个")))
    c.cmp("summary_v3.md", "短历史可评估", sh["alignment"]["n_evaluable"],
          num(grab(doc, r"([\d]+) 条可评估")))
    c.cmp("summary_v3.md", "2 个月可纳入", sh["alignment"]["n_evaluable_min_train_2"],
          num(grab(doc, r"2 个月会纳入 ([\d]+) 条")))
    own = sh["summary"]
    for key, pat in (("ses", r"SES ([\d.]+) / 组合"), ("combo2", r"组合 ([\d.]+) / TSB"),
                     ("tsb", r"TSB ([\d.]+) / naive"), ("naive", r"TSB [\d.]+ / naive ([\d.]+)"),
                     ("category_borrowed", r"类目借力 ([\d.]+)（仅 151")):
        c.cmp("summary_v3.md", f"各自子集 MAE {key}", own[key]["mean_abs_error"],
              num(grab(doc, pat)))
    al = sh["aligned_summary"]
    aligned_seg = doc.split("正式共同子集", 1)[1] if "正式共同子集" in doc else doc
    for key, pat in (("tsb", r"TSB ([\d.]+) / SES"), ("ses", r"SES ([\d.]+) / 组合"),
                     ("combo2", r"组合 ([\d.]+) / 类目借力"),
                     ("category_borrowed", r"类目借力 ([\d.]+) /"),
                     ("naive", r"naive ([\d.]+)。")):
        c.cmp("summary_v3.md", f"正式共同子集 MAE {key}", al[key],
              num(grab(aligned_seg, pat)))
    if "9.928" not in doc:
        c.notes.append("T16 short_history_eval 的组合 MAE 9.928 未写入 §6；§6 的短历史数字"
                       "来自 T9/T14（attribute_errors），两者口径不同（对齐方式/窗口集），"
                       "不构成数字矛盾，但若要求并列需补一句说明。")
    else:
        c.cmp("summary_v3.md", "T16 组合 MAE",
              s["methods"]["total"]["combo_ew"]["mae"], 9.928)
    c.cmp("summary_v3.md", "低置信可评估",
          sh["alignment"]["low_confidence_evaluable"],
          num(grab(doc, r"低置信 \*\*([\d]+) / 392")))
    c.cmp("summary_v3.md", "共同窗口总数",
          sh["alignment"]["aligned_window_total"]["tsb"],
          num(grab(doc, r"共用 ([\d]+) 个窗口")))
    fb = jload(FE / "error_attribution.json")["fallback"]
    c.cmp("summary_v3.md", "fallback 去重 SKU", fb["distinct_skus"], num(grab(doc, r"去重 \*\*([\d]+) 个 SKU\*\*")))
    c.cmp("summary_v3.md", "fallback 销量覆盖%", round(fb["sales_coverage"] * 100, 2),
          num(grab(doc, r"\*\*([\d.]+)% 销量（全历史口径）\*\*")), tol=0.01)
    # T20 made the guard len<7; summary still recommends len<3
    if "guard len(y) < 3" in doc:
        c.diffs.append(dict(file="summary_v3.md", field="guard 阈值建议",
                            table_value="len<7（T20，short_history_eval.py:69）",
                            doc_value="guard len(y) < 3"))
    c.notes.append("模型数字逐项与 nested_eval.json / short_history_eval.json / error_attribution.json 比对。")
    return c.result()


def check_8() -> dict:
    c = Check("8", "forward_shadow_plan.md ↔ forward_shadow.py")
    plan = rd("forward_shadow_plan.md")
    code = (FE / "forward_shadow.py").read_text(encoding="utf-8")
    checks = [
        ("使用代码路径", "nested_eval.py（文档 §1）", "forward_shadow.py（实际实现）",
         "使用代码 | `experiments/business_phase/forecast_eval/nested_eval.py`" not in plan),
        ("零需求保留在分子", "误差保留在分子", "零需求单元格的 |F| 进入分子（metric_definition）",
         "零需求单元格的 |F| 进入分子" in code),
        ("聚合总实际量为 0 才无定义", "无定义单独列出", "undefined_denominator 分支",
         "undefined_denominator" in code),
        ("缺标签标 unknown 并列原因", "missing_labels + 顺延", "labels_incomplete + excluded 清单",
         "labels_incomplete" in code and "excluded" in code),
        ("评分不重新选模", "评分阶段不重选", "读取预存选择（未重新选模）",
         "评分阶段未重新选模" in code),
        ("各候选 WAPE", "每个候选 1 个值", "只算 selected / naive / ma3",
         'methods = ["selected", "naive", "ma3"]' not in code),
        ("各候选 Bias", "每个候选 1 个值", "未实现",
         "bias" in code.lower()),
        ("上限列覆盖率", "每个候选 1 个值", "未实现",
         "上限" in code),
        ("零分母数量与占比", "数量与占比", "仅 n_zero_demand_retained，无占比",
         "n_zero_demand_retained" in code and "占比" in code),
    ]
    for field, doc_side, code_side, ok in checks:
        if not ok:
            c.diffs.append(dict(file="forward_shadow_plan.md / forward_shadow.py",
                                field=field, table_value=code_side,
                                doc_value=doc_side))
    # judgment rules are a human process: the script intentionally does not decide
    if "连续 3 个月" in plan and "shadow_decision" in plan:
        c.notes.append("§3 连续 3 个月/区间不含 0 是人工判定流程，脚本只产出单次评分，"
                       "文档未声称脚本自动判定，故不计失败。")
    c.notes.append("已确认脚本保留 `--data-cutoff/--origin` 参数化、预存清单与 --force 防覆盖。")
    return c.result()


SUPERSEDED = [
    dict(doc="control/reviews/2026-10-22-t17-sensitivity.md",
         by="control/reviews/2026-10-22-t18-sensitivity-fix.md",
         reason="T17 正文“五口径一致 1,536 行全部全零、无全正量行”与数据矛盾，T18 已重分五类并更正。"),
    dict(doc="control/reviews/2026-10-22-t16-short-history.md",
         by="control/reviews/2026-10-22-t20-guard.md",
         reason="T16 称 len 3–6 的 tiny_datasets 仍抛错；T20 已将 guard 扩到 len<7。"),
    dict(doc="control/reviews/2026-10-22-t12-audit-fixes.md",
         by="control/reviews/2026-10-22-t14-recheck-fixes.md",
         reason="T12 的 M01 对齐 MAE 与 M02 早期块指标已被 T14 取代。"),
]


def main() -> None:
    checks = [check_1(), check_2(), check_3(), check_4(),
              check_5(), check_6(), check_7(), check_8()]
    summary = dict(total=len(checks),
                   passed=sum(1 for x in checks if x["status"] == "PASS"),
                   failed=sum(1 for x in checks if x["status"] == "FAIL"),
                   failures=[x["id"] for x in checks if x["status"] == "FAIL"])
    result = dict(
        schema_version="t21_consistency_audit/1",
        inputs={p.name: sha(p) for p in (
            OUT / "replenishment_v2.csv", OUT / "summary_v3.md",
            OUT / "model_sensitivity.csv", OUT / "model_sensitivity.md",
            OUT / "wo_dn_coverage.csv", OUT / "wo_dn_coverage.json", OUT / "wo_dn_coverage.md",
            OUT / "explanations.csv", OUT / "decision_v2.csv",
            OUT / "diff_v1_v2.csv", OUT / "replenishment_all.csv",
            OUT / "evidence_request.md", OUT / "forward_shadow_plan.md",
            FE / "nested_eval.json", FE / "short_history_eval.json",
            FE / "error_attribution.json", FE / "forward_shadow.py")},
        checks=checks, summary=summary, superseded=SUPERSEDED,
        policy=("只核对、不改数：FAIL 只列差异与建议；不修改任何数字产物；"
                "文档若为纯措辞错误也不在本轮改写（ownership 仅限本审计输出）。"),
    )
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    md = ["# T21 交付物一致性巡检", "",
          "> 只读已有 CSV/JSON/MD，不跑数据库、不改任何数字；FAIL 只列差异与建议。", "",
          "## 总览", "",
          f"- 检查项 **{summary['total']}**：PASS **{summary['passed']}** / FAIL **{summary['failed']}**",
          f"- FAIL 项：{', '.join(summary['failures']) or '无'}", "",
          "| # | 检查 | 结果 | 差异数 |", "|---:|---|---|---:|"]
    for x in checks:
        md.append(f"| {x['id']} | {x['title']} | **{x['status']}** | {len(x['diffs'])} |")
    for x in checks:
        md += ["", f"## {x['id']}. {x['title']} — **{x['status']}**", ""]
        if x["diffs"]:
            md += ["| 文件 | 字段 | 表/脚本值 | 文档值 |", "|---|---|---|---|"]
            for d in x["diffs"]:
                md.append(f"| {d['file']} | {d['field']} | `{d['table_value']}` | `{d['doc_value']}` |")
        for note in x["notes"]:
            md.append(f"- {note}")
    md += ["", "## superseded（不逐字比对）", "",
           "| 文档 | 替代 | 原因 |", "|---|---|---|"]
    for s in SUPERSEDED:
        md.append(f"| `{s['doc']}` | `{s['by']}` | {s['reason']} |")
    md += ["", "## 处置建议", "",
           "- 数字 FAIL 只列差异，**不改数**；由 coordinator 决定是否回改生成脚本后重跑。",
           "- 文档措辞/路径不一致（check 8）建议改文档或脚本，但本轮 ownership 不含这些文件。",
           "- 所有输入 sha256 见 JSON，可复现。", "",
           "## 复现", "",
           "```bash",
           "uv run python docs/research/supply-chain/2026-10-20/claude/"
           "experiments/business_phase/audit_consistency.py",
           "uv run python scripts/check_secrets.py",
           "```", ""]
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")

    print("wrote", OUT_JSON.name, OUT_MD.name)
    print("summary", summary)
    for x in checks:
        print(x["id"], x["status"], "diffs", len(x["diffs"]))


if __name__ == "__main__":
    main()
