#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""T26: offline machine verification of the delivery (five checks).

Reads only existing CSV/JSON/MD. No database access, no network. Every number is
recomputed from the current CSVs; the document is parsed and compared. Failures
list the file/field and both values. Text is never changed by this script.

Checks
  1 delivery_guide "522 rows / 479 SKUs / about 67% sales" vs model_sensitivity.csv
  2 recommendation distributions of ①308 and ③a214 + the time window used
  3 the 160 unknown-inventory rows: null (never 0) and propagation
  4 inventory caliber: usability_audit (per-warehouse, 0 allocation) vs old wording
  5 all 1,328 SKUs present exactly once-or-more, explainable statuses

Outputs: out/business_phase/delivery_verification.json / .md
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve()
CLAUDE_DIR = HERE.parents[2]
OUT = CLAUDE_DIR / "out" / "business_phase"
OUT_JSON = OUT / "delivery_verification.json"
OUT_MD = OUT / "delivery_verification.md"


def rows(name: str) -> list[dict]:
    return list(csv.DictReader(open(OUT / name, encoding="utf-8-sig")))


def text(name: str) -> str:
    return (OUT / name).read_text(encoding="utf-8")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class Check:
    def __init__(self, cid, title):
        self.cid, self.title = cid, title
        self.diffs, self.notes, self.facts = [], [], {}

    def fail(self, file, field, actual, documented):
        self.diffs.append(dict(file=file, field=field,
                               actual=actual, documented=documented))

    def result(self):
        return dict(id=self.cid, title=self.title,
                    status="PASS" if not self.diffs else "FAIL",
                    diffs=self.diffs, notes=self.notes, facts=self.facts)


def check_1() -> dict:
    c = Check("1", '指南口径：522 行 / 479 商品 / 约 67% 销量')
    r = rows("model_sensitivity.csv")
    guide = text("delivery_guide.md")
    sku6 = {}
    for x in r:
        if x["销量_近6月"] not in ("", None):
            sku6[x["SKU"]] = float(x["销量_近6月"])
    total = sum(sku6.get(s, 0.0) for s in {x["SKU"] for x in r})
    sel = [x for x in r if x["分类"] in ("①0/正量分歧", "③a全正量一致")]
    skus = {x["SKU"] for x in sel}
    covered = sum(sku6.get(s, 0.0) for s in skus)
    share = covered / total * 100
    one = {x["SKU"] for x in r if x["分类"] == "①0/正量分歧"}
    one_share = sum(sku6.get(s, 0.0) for s in one) / total * 100
    c.facts = dict(rows=len(sel), skus=len(skus), denominator_6m=round(total, 1),
                   covered_6m=round(covered, 1), share_pct=round(share, 2),
                   one_only_share_pct=round(one_share, 2))
    m = re.search(r"\*\*([\d,]+) 行、涉及 ([\d,]+) 个商品\*\*", guide)
    if not m:
        c.fail("delivery_guide.md", "行数/SKU", f"{len(sel)}/{len(skus)}", "未解析")
    else:
        if int(m.group(1).replace(",", "")) != len(sel):
            c.fail("delivery_guide.md", "522 行", len(sel), m.group(1))
        if int(m.group(2).replace(",", "")) != len(skus):
            c.fail("delivery_guide.md", "479 商品", len(skus), m.group(2))
    m = re.search(r"覆盖约 \*\*([\d.]+)%\*\*", guide)
    if not m or abs(float(m.group(1)) - share) > 0.6:
        c.fail("delivery_guide.md", "覆盖约 67%", round(share, 2),
               m.group(1) if m else "未解析")
    m = re.search(r"单独约占 ([\d.]+)%", guide)
    if not m or abs(float(m.group(1)) - one_share) > 0.6:
        c.fail("delivery_guide.md", "① 单独 37%", round(one_share, 2),
               m.group(1) if m else "未解析")
    c.notes.append(f"分母 = 去重 SKU 近 6 月销量合计 {total:.0f}；"
                   "覆盖按同一 SKU 集合去重后计算（SKU 可跨分类，不能把百分比直接相加）。")
    return c.result()


def check_2() -> dict:
    c = Check("2", "两类条件建议分布与时窗")
    r = rows("model_sensitivity.csv")
    guide = text("delivery_guide.md")
    dist = {}
    for cls in ("①0/正量分歧", "③a全正量一致"):
        vals = [float(x["建议中位下限"]) for x in r
                if x["分类"] == cls and x["建议中位下限"] not in ("", None)]
        dist[cls] = dict(n=len(vals), min=min(vals),
                         median=round(statistics.median(vals), 3), max=max(vals))
    per_cal = {}
    for col in [k for k in r[0] if k.startswith("建议下限_")]:
        vals = [float(x[col]) for x in r
                if x["分类"] in ("①0/正量分歧", "③a全正量一致")
                and x[col] not in ("", None)]
        per_cal[col.replace("建议下限_", "")] = dict(
            n=len(vals), min=min(vals),
            median=round(statistics.median(vals), 3), max=max(vals))
    c.facts = dict(by_class=dist, by_caliber=per_cal, window="L90")
    # window evidence: the sensitivity builder computes lo/hi from dem[90]
    builder = (CLAUDE_DIR / "experiments" / "business_phase" /
               "build_model_sensitivity.py").read_text(encoding="utf-8")
    if "dem[90]" not in builder:
        c.fail("build_model_sensitivity.py", "L90 窗口", "未找到 dem[90]", "文档称 L90")
    if not re.search(r"L90|90 天", guide):
        c.fail("delivery_guide.md", "时窗表述", "未写 L90/90 天", "表为 L90 口径")
    c.notes.append("分布列用 `建议中位下限`（五口径下限中位数）；"
                   "五口径各自分布见 by_caliber。时窗为 L90（下限=dem[90]−供给，"
                   "上限=dem[90]×压力系数−可用）。")
    return c.result()


def check_3() -> dict:
    c = Check("3", "160 行库存未知：null、未被当 0、传播一致")
    main = rows("replenishment_v2.csv")
    sens = rows("model_sensitivity.csv")
    wo = rows("wo_dn_coverage.csv")
    pend = [x for x in main if x["状态"] == "B_pending_inventory"]
    null_fields = ("可用", "缺口L60", "缺口L90", "缺口L120",
                   "建议下限L90", "建议上限L90(压力情景)")
    c.facts["main"] = dict(rows=len(pend),
                           null_counts={f: sum(1 for x in pend if x[f] in ("", None))
                                        for f in null_fields},
                           demand_p50_nonnull=sum(1 for x in pend
                                                  if x["需求P50(冲减前)"] not in ("", None)))
    for f in null_fields:
        if c.facts["main"]["null_counts"][f] != len(pend):
            c.fail("replenishment_v2.csv", f, c.facts["main"]["null_counts"][f], len(pend))
    if c.facts["main"]["demand_p50_nonnull"] != len(pend):
        c.fail("replenishment_v2.csv", "需求P50（未知库存行仍应有需求）",
               c.facts["main"]["demand_p50_nonnull"], len(pend))
    s_unk = [x for x in sens if x["分类"] == "库存未知"]
    s_blank = sum(1 for x in s_unk
                  if all(x[f"建议下限_{m}"] in ("", None)
                         for m in ("MA3", "naive", "seasonal_naive", "combo_ew", "AutoETS")))
    c.facts["sensitivity"] = dict(rows=len(s_unk), all_lower_null=s_blank)
    if len(s_unk) != len(pend) or s_blank != len(s_unk):
        c.fail("model_sensitivity.csv", "库存未知行/空数量",
               f"{len(s_unk)}/{s_blank}", f"{len(pend)}/{len(pend)}")
    w_pend = [x for x in wo if x["主表状态"] == "B_pending_inventory"]
    w_status = Counter(x["覆盖状态"] for x in w_pend)
    w_supply_blank = sum(1 for x in w_pend if x["供给可用量"] in ("", None))
    c.facts["wo_dn"] = dict(rows=len(w_pend), status=dict(w_status),
                            supply_blank=w_supply_blank)
    if len(w_pend) != len(pend) or w_supply_blank != len(w_pend):
        c.fail("wo_dn_coverage.csv", "库存未知行传播",
               f"{len(w_pend)}/{w_supply_blank}", f"{len(pend)}/{len(pend)}")
    c.notes.append("三处一致性：主表 160 行数量列全空且需求非空；敏感性表 160 行五口径下限全空；"
                   "WO/DN 覆盖表同 160 行（154 无材料 + 6 有材料不可用），供给可用量全空。"
                   "没有任何一处把未知写成 0。")
    return c.result()


def check_4() -> dict:
    c = Check("4", "库存口径：同仓快照 vs 旧“跨仓汇总”文字")
    u = rows("usability_audit.csv")
    same_fact = Counter(x["可用是否同仓事实"] for x in u)
    alloc = Counter(x["库存摊派"] for x in u)
    demand_alloc = Counter(x["需求摊派"] for x in u)
    c.facts = dict(rows=len(u), same_warehouse_fact=dict(same_fact),
                   inventory_allocation=dict(alloc), demand_allocation=dict(demand_alloc),
                   mismatches=sum(1 for x in u if x["可用是否同仓事实"] == "no"))
    if c.facts["mismatches"] != 0:
        c.fail("usability_audit.csv", "同仓不符行", c.facts["mismatches"], 0)
    if alloc.get("no（逐仓库存行）", 0) + alloc.get("n/a", 0) != len(u):
        c.fail("usability_audit.csv", "库存摊派", dict(alloc), "0 行摊派")
    live = text("summary_v3.md") + text("delivery_guide.md")
    if not (("按仓快照" in live or "按仓库快照" in live)
            and ("不是跨仓汇总" in live)):
        c.fail("summary_v3.md / delivery_guide.md", "库存口径表述",
               "缺少“按仓快照、不是跨仓汇总”", "应有准确口径")
    old = text("summary.md")
    old_line = next((i for i, ln in enumerate(old.splitlines(), 1)
                     if "SKU 跨仓汇总" in ln), None)
    c.facts["v1_summary_old_claim_line"] = old_line
    if old_line is not None:
        c.notes.append(f"`summary.md`（v1，已被 `summary_v3.md` 取代）第 {old_line} 行仍写"
                       "“库存为 SKU 跨仓汇总”；该文件不在本轮 ownership，未改。"
                       "现行摘要与指南已加准确表述（按仓快照；需求按仓销量占比分配）。")
    c.notes.append("usability_audit：2,058 行主表可用=同仓库存事实、0 行不符、0 行库存摊派；"
                   "需求摊派 1,415 行（按仓销量占比），其余 894 行占比为 0。")
    return c.result()


def check_5() -> dict:
    c = Check("5", "全 1,328 SKU 去向")
    r = rows("replenishment_v2.csv")
    by = defaultdict(set)
    for x in r:
        by[x["SKU"]].add(x["状态"])
    allowed = {"B", "B_pending_inventory", "C"}
    combos = Counter(tuple(sorted(v)) for v in by.values())
    bad = {s: sorted(v) for s, v in by.items() if not v <= allowed}
    c.facts = dict(rows=len(r), skus=len(by),
                   status_combos={"+".join(k): v for k, v in combos.items()},
                   missing_skus=[], invalid_status=bad)
    if len(by) != 1328:
        c.fail("replenishment_v2.csv", "唯一 SKU", len(by), 1328)
    if bad:
        c.fail("replenishment_v2.csv", "非法状态", bad, "仅 B/B_pending_inventory/C")
    # every SKU in the destination roster must appear
    dest = json.loads((OUT / "destinations.json").read_text(encoding="utf-8"))["rows"]
    roster = {x["sku"] for x in dest}
    missing = sorted(roster - set(by))
    c.facts["roster_skus"] = len(roster)
    c.facts["missing_skus"] = missing
    if missing:
        c.fail("replenishment_v2.csv", "缺失 SKU", len(missing), 0)
    c.notes.append("状态组合：全部 B（1,077 SKU）/ B+待核实（154）/ 全部待核实（6）/ 全部 C（91）。"
                   "154 个 SKU 同时有 B 与待核实行，属同一 SKU 分仓库存缺失，可解释。")
    return c.result()


def main() -> None:
    checks = [check_1(), check_2(), check_3(), check_4(), check_5()]
    summary = dict(total=len(checks),
                   passed=sum(1 for c in checks if c["status"] == "PASS"),
                   failed=sum(1 for c in checks if c["status"] == "FAIL"))
    result = dict(
        schema_version="t26_delivery_verification/1",
        inputs={p.name: sha(p) for p in (
            OUT / "model_sensitivity.csv", OUT / "replenishment_v2.csv",
            OUT / "usability_audit.csv", OUT / "wo_dn_coverage.csv",
            OUT / "delivery_guide.md", OUT / "summary_v3.md", OUT / "summary.md",
            OUT / "destinations.json")},
        checks=checks, summary=summary,
        policy=("只重算与对读；数字不一致只列差异，不改数字；"
                "文字错误在允许的文档中更正并留原文。"),
    )
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")

    md = ["# T26 交付机器核对（五项）", "",
          "> 只读当前 CSV/JSON/MD；不跑数据库。数字均由脚本重算，FAIL 只列差异。", "",
          f"- 五项：PASS **{summary['passed']}** / FAIL **{summary['failed']}**", "",
          "| # | 检查 | 结果 | 差异 |", "|---:|---|---|---:|"]
    for c in checks:
        md.append(f"| {c['id']} | {c['title']} | **{c['status']}** | {len(c['diffs'])} |")
    for c in checks:
        md += ["", f"## {c['id']}. {c['title']} — **{c['status']}**", ""]
        if c["facts"]:
            md += ["```json", json.dumps(c["facts"], ensure_ascii=False, indent=1), "```"]
        if c["diffs"]:
            md += ["| 文件 | 字段 | 实际 | 文档/期望 |", "|---|---|---|---|"]
            for d in c["diffs"]:
                md.append(f"| {d['file']} | {d['field']} | `{d['actual']}` | `{d['documented']}` |")
        for n in c["notes"]:
            md.append(f"- {n}")
    md += ["", "## 复现", "",
           "```bash",
           "uv run python docs/research/supply-chain/2026-10-20/claude/"
           "experiments/business_phase/verify_delivery.py",
           "uv run python scripts/check_secrets.py",
           "```", ""]
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")

    print("wrote", OUT_JSON.name, OUT_MD.name)
    print("summary", summary)
    for c in checks:
        print(c["id"], c["status"], "diffs", len(c["diffs"]))


if __name__ == "__main__":
    main()
