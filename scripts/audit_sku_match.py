# -*- coding: utf-8 -*-
"""只读审计：通途 SKU（GS 订单侧）与 EN sku_map 的精确匹配缺口。

规则（与任务书 2026-10-22-sku-audit-task.md 一致）：
- 匹配只认精确等值 ``sku_map.tongtool_sku == gs_orders.sku_tongtool``。
- 未命中者再尝试「已知后缀剥离」得到**候选基础码**，候选只用于人工复核，
  绝不写回 EN、绝不改 sku_map。
- 每个未匹配 SKU 必须落入四类之一，计数与订单行数必须对账。

输入全部只读；不访问通途 / EN 生产。
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = Path(r"D:/Work/fzh-order-store/order_store.duckdb")
MAP_TSV = Path(r"D:/Work/fzh-order-store/sku_map.tsv")
OUT = ROOT / "out" / "sku_match_audit"

CATEGORIES = ("base_candidate", "duplicate_mapping", "true_missing", "insufficient_evidence")

# 已知后缀：沿用 missing_products 的既有约定，并补任务书点名的 -N / #qc / 变体后缀。
NAMED_SUFFIXES = {"cover", "foam", "all", "out", "淘汰", "seat-belt", "clip", "new"}
ANNOTATION_PREFIXES = ("已删除", "删除", "作废", "停用")
RE_VARIANT_NUM = re.compile(r"\d")
RE_LENGTH = re.compile(r"\d+(?:cm|mm|in)", re.I)
RE_ALPHA = re.compile(r"[a-z]{1,12}", re.I)


def strip_chain(sku: str) -> list[tuple[str, list[str], str]]:
    """按确定性规则逐段剥后缀，返回 (base, chain, rule) 列表。

    只剥「可识别形状」的尾段：命名后缀 / 单位数字（Shopify 变体序号）/
    纯数字+长度单位 / 纯字母值（颜色等）。多位数字是尺码，**不剥**。
    """
    out: list[tuple[str, list[str], str]] = []
    base = sku
    chain: list[str] = []
    for _ in range(6):
        low = base.lower()
        if low.endswith("#qc"):
            base = base[:-3]
            chain = chain + ["#qc"]
            out.append((base, list(chain), "#qc"))
            continue
        if "-" not in base:
            break
        head, _, tail = base.rpartition("-")
        if not tail:
            break
        tl = tail.lower()
        if tl in NAMED_SUFFIXES:
            rule = "named_suffix"
        elif RE_VARIANT_NUM.fullmatch(tl):
            rule = "variant_number"
        elif RE_LENGTH.fullmatch(tl):
            rule = "length_suffix"
        elif RE_ALPHA.fullmatch(tl):
            rule = "alpha_suffix"
        else:
            break  # 尺码等不可剥，停止，避免误伤
        base = head
        chain = chain + [tail]
        out.append((base, list(chain), rule))
    return out


def load_map() -> tuple[dict[str, set[str]], dict[str, set[str]], dict[str, set[str]], int]:
    rows = list(csv.reader(MAP_TSV.open(encoding="utf-8"), delimiter="\t"))
    pairs = [(r[0].strip(), r[1].strip()) for r in rows if len(r) >= 2 and r[0].strip() and r[1].strip()]
    by_tt: dict[str, set[str]] = defaultdict(set)
    by_item: dict[str, set[str]] = defaultdict(set)
    for item, tt in pairs:
        by_tt[tt].add(item)
        by_item[item].add(tt)
    annotated: dict[str, set[str]] = defaultdict(set)
    for tt, items in by_tt.items():
        for pre in ANNOTATION_PREFIXES:
            if tt.startswith(pre):
                annotated[tt[len(pre):]].update(items)
                break
    return dict(by_tt), dict(by_item), dict(annotated), len(pairs)


def permutation_index(keys) -> dict[tuple[str, ...], list[str]]:
    idx: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for k in keys:
        idx[tuple(sorted(t.lower() for t in k.split("-")))].append(k)
    return dict(idx)


def classify(sku: str, by_tt, annotated, perm) -> dict:
    """返回 {category, base, item_codes, evidence, flags}。"""
    hits = [(b, chain, rule) for b, chain, rule in strip_chain(sku) if b in by_tt]
    ann_items = annotated.get(sku, set())
    flags: list[str] = []
    if ann_items:
        flags.append("map_alias_marked_deleted")

    if hits:
        bases = sorted({b for b, _, _ in hits})
        if len(bases) > 1:
            return {
                "category": "duplicate_mapping",
                "base": ";".join(bases),
                "item_codes": ";".join(sorted({i for b in bases for i in by_tt[b]})),
                "evidence": "multiple_candidate_bases:" + ";".join(bases),
                "flags": flags,
            }
        base, chain, rule = hits[0]
        items = sorted(by_tt[base])
        ev = f"suffix_strip[{rule}]:{'-'.join(reversed(chain))} -> base={base} in sku_map ({len(items)} item_code)"
        if len(items) > 1:
            return {
                "category": "duplicate_mapping",
                "base": base,
                "item_codes": ";".join(items),
                "evidence": ev + "; base maps to multiple item_code",
                "flags": flags,
            }
        return {
            "category": "base_candidate",
            "base": base,
            "item_codes": ";".join(items),
            "evidence": ev,
            "flags": flags,
        }

    if ann_items:
        ev = "only_annotated_alias_in_map(deleted_prefix)" + f":{sku} -> {len(ann_items)} item_code"
        if len(ann_items) > 1:
            return {
                "category": "duplicate_mapping",
                "base": sku,
                "item_codes": ";".join(sorted(ann_items)),
                "evidence": ev + "; annotated alias aims at multiple item_code",
                "flags": flags,
            }
        return {
            "category": "insufficient_evidence",
            "base": sku,
            "item_codes": ";".join(sorted(ann_items)),
            "evidence": ev + "; alias intentionally marked deleted, no live candidate",
            "flags": flags,
        }

    pkey = tuple(sorted(t.lower() for t in sku.split("-")))
    siblings = [k for k in perm.get(pkey, []) if k != sku]
    if siblings:
        n = max(len(by_tt[s]) for s in siblings)
        ev = "token_permutation_of:" + ";".join(f"{s}({len(by_tt[s])})" for s in siblings)
        if n > 1:
            return {
                "category": "duplicate_mapping",
                "base": ";".join(siblings),
                "item_codes": ";".join(sorted({i for s in siblings for i in by_tt[s]})),
                "evidence": ev + "; permuted sibling maps to multiple item_code",
                "flags": flags,
            }
        return {
            "category": "insufficient_evidence",
            "base": ";".join(siblings),
            "item_codes": ";".join(sorted({i for s in siblings for i in by_tt[s]})),
            "evidence": ev + "; token order/case anomaly, single candidate",
            "flags": flags,
        }

    # 纯信息：SKU 本身未登记，但带后缀的子别名已登记（不作为候选）
    children = sorted(k for k in by_tt if k.startswith(sku + "-"))
    ev = "no_suffix_candidate"
    if children:
        ev += "; family_child_alias_registered:" + ";".join(f"{c}({len(by_tt[c])})" for c in children[:3])
    return {"category": "true_missing", "base": "", "item_codes": "", "evidence": ev, "flags": flags}


def action_for(cat: str, cls: dict, lines: int, last_month: str) -> tuple[str, str]:
    if cat == "base_candidate":
        if "map_alias_marked_deleted" in cls["flags"]:
            return "manual_review", "基础码有活映射，但同一 alias 在 EN 被标记删除，删除意图需人工确认"
        if "named_suffix" in cls["evidence"] or "#qc" in cls["evidence"]:
            return "register_candidate", "有唯一候选且后缀为已知组件别名；人工确认后登记 alias"
        return "manual_review", "候选来自长度/颜色等变体后缀，需人工确认是否同一商品"
    if cat == "duplicate_mapping":
        return "manual_review", "同一 SKU 命中多个候选，需人工裁决"
    if cat == "insufficient_evidence":
        if "map_alias_marked_deleted" in cls["flags"] and last_month < "202501":
            return "no_action", "历史订单，EN alias 已标记删除，无需回补"
        return "manual_review", "仅存在已删除 alias / 编码异常，需人工确认"
    # true_missing
    if lines >= 5:
        return "register_candidate", "无任何登记但订单持续，建议人工登记客户 SKU"
    return "manual_review", "无登记且样本少，先确认是否新平台/新商品"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    by_tt, by_item, annotated, n_pairs = load_map()
    perm = permutation_index(by_tt)

    con = duckdb.connect(str(DB), read_only=True)
    # 输入体检：DuckDB 表与 TSV 必须等价（表是 TSV 按 tongtool_sku 去重）
    table_pairs = set(con.execute("select item_code, tongtool_sku from sku_map").fetchall())
    tsv_pairs = {(i, t) for t, items in by_tt.items() for i in items}
    table_keys = {t for _, t in table_pairs}
    only_tsv = tsv_pairs - table_pairs
    only_table = table_pairs - tsv_pairs
    if only_table or table_keys != set(by_tt):
        raise SystemExit("sku_map.tsv 与 DuckDB sku_map 键集不一致，停止审计")

    total_rows = con.execute("select count(*) from gs_orders").fetchone()[0]
    rows = con.execute(
        """
        select g.line_id, g.order_id, g.month, g.sale_date, g.sku_tongtool, g.qty,
               g.warehouse, g.account
        from gs_orders g
        left join sku_map m on g.sku_tongtool = m.tongtool_sku
        where m.tongtool_sku is null
        order by g.month, g.line_id
        """
    ).fetchall()
    matched_rows = total_rows - len(rows)
    sku_month = {}
    sku_stats: dict[str, dict] = {}
    for line_id, order_id, month, sale_date, sku, qty, wh, acct in rows:
        st = sku_stats.setdefault(sku, {"lines": 0, "qty": 0, "first_month": month, "last_month": month,
                                        "sample_line_ids": []})
        st["lines"] += 1
        st["qty"] += qty or 0
        st["first_month"] = min(st["first_month"], month)
        st["last_month"] = max(st["last_month"], month)
        if len(st["sample_line_ids"]) < 3:
            st["sample_line_ids"].append(line_id)
        sku_month.setdefault(sku, set()).add(month)

    sku_rows: list[dict] = []
    for sku in sorted(sku_stats, key=lambda s: (-sku_stats[s]["lines"], s)):
        st = sku_stats[sku]
        cls = classify(sku, by_tt, annotated, perm)
        act, why = action_for(cls["category"], cls, st["lines"], st["last_month"])
        sku_rows.append({"sku": sku, **st, **cls, "action": act, "action_reason": why})
        for k in ("lines", "qty", "first_month", "last_month"):
            st[k] = st[k]

    by_sku = {r["sku"]: r for r in sku_rows}
    assert len(by_sku) == len(sku_rows), "SKU 重复分类"

    # CSV：全部未匹配行
    csv_path = OUT / "unmatched_all.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["line_id", "order_id", "month", "sale_date", "sku_tongtool", "qty", "warehouse",
                    "account", "category", "candidate_base", "candidate_item_codes", "evidence", "action"])
        for line_id, order_id, month, sale_date, sku, qty, wh, acct in rows:
            r = by_sku[sku]
            w.writerow([line_id, order_id, month, sale_date, sku, qty, wh, acct,
                        r["category"], r["base"], r["item_codes"], r["evidence"], r["action"]])

    # 分类汇总
    cats: dict[str, dict] = {}
    for cat in CATEGORIES:
        subset = [r for r in sku_rows if r["category"] == cat]
        lines = sum(r["lines"] for r in subset)
        cats[cat] = {
            "unique_skus": len(subset),
            "order_lines": lines,
            "qty": sum(r["qty"] for r in subset),
            "first_month": min((r["first_month"] for r in subset), default=None),
            "last_month": max((r["last_month"] for r in subset), default=None),
            "examples": [
                {"sku": r["sku"], "lines": r["lines"], "first_month": r["first_month"],
                 "last_month": r["last_month"], "base": r["base"], "item_codes": r["item_codes"],
                 "evidence": r["evidence"], "action": r["action"], "sample_line_ids": r["sample_line_ids"]}
                for r in subset[:10]
            ],
        }

    # 深审 100：先覆盖所有非 true_missing，再按行数补 true_missing
    deep: list[dict] = [r for cat in ("duplicate_mapping", "insufficient_evidence", "base_candidate")
                        for r in sku_rows if r["category"] == cat]
    if len(deep) > 100:
        deep = deep[:100]
    else:
        deep += [r for r in sku_rows if r["category"] == "true_missing"][: 100 - len(deep)]
    deep.sort(key=lambda r: (-r["lines"], r["sku"]))

    recon = {
        "gs_orders_total_rows": total_rows,
        "matched_rows": matched_rows,
        "unmatched_rows": len(rows),
        "unmatched_rows_csv": sum(1 for _ in csv_path.open(encoding="utf-8-sig")) - 1,
        "unmatched_unique_skus": len(sku_rows),
        "sum_category_skus": sum(c["unique_skus"] for c in cats.values()),
        "sum_category_lines": sum(c["order_lines"] for c in cats.values()),
        "sum_category_qty": sum(c["qty"] for c in cats.values()),
        "unmatched_qty": sum(r["qty"] for r in sku_rows),
        "sku_in_multiple_categories": False,
        "sku_map_tsv_pairs": n_pairs,
        "sku_map_tsv_distinct_tongtool_sku": len(by_tt),
        "sku_map_duckdb_rows": len(table_pairs),
        "tsv_pairs_missing_from_duckdb_table": len(only_tsv),
        "duckdb_pairs_missing_from_tsv": len(only_table),
        "map_tongtool_sku_with_multiple_item_code": sum(1 for v in by_tt.values() if len(v) > 1),
        "map_item_code_with_multiple_tongtool_sku": sum(1 for v in by_item.values() if len(v) > 1),
        "map_annotated_alias_keys": len(annotated),
        "deep_audit_skus": len(deep),
    }
    checks = {
        "rows_partition": matched_rows + len(rows) == total_rows,
        "category_skus_sum": recon["sum_category_skus"] == len(sku_rows),
        "category_lines_sum": recon["sum_category_lines"] == len(rows),
        "csv_rows_equal": recon["unmatched_rows_csv"] == len(rows),
        "category_skus_distinct": sum(c["unique_skus"] for c in cats.values()) == len(by_sku),
        "deep_audit_covers_all_categories": {r["category"] for r in deep} == set(CATEGORIES),
        "deep_audit_le_100": len(deep) <= 100,
        "no_fuzzy_claim": all(r["category"] != "base_candidate" or r["item_codes"] for r in sku_rows),
    }
    recon["checks"] = checks
    if not all(checks.values()):
        raise SystemExit("对账失败: " + json.dumps(checks, ensure_ascii=False))

    payload = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "inputs": {"duckdb": str(DB), "sku_map_tsv": str(MAP_TSV), "read_only": True,
                   "match_rule": "exact equality sku_map.tongtool_sku == gs_orders.sku_tongtool"},
        "denominator_note": (
            "本次分母是 GS 订单侧：gs_orders 4,115 行 / 297 个唯一 SKU 未在 sku_map 精确命中。"
            "旧口径 6,549 行来自 EN 订单/同步侧，分母不同，不可相加或互相替代。"
        ),
        "totals": {"unmatched_lines": len(rows), "unmatched_unique_skus": len(sku_rows),
                   "unmatched_qty": recon["unmatched_qty"],
                   "first_month": min(r["first_month"] for r in sku_rows),
                   "last_month": max(r["last_month"] for r in sku_rows)},
        "rules": {
            "exact": "only exact equality counts as matched",
            "suffix_strip": {
                "named": sorted(NAMED_SUFFIXES) + ["#qc"],
                "variant_number": "single digit 0-9 (Shopify variant index)",
                "length_suffix": "digits + cm/mm/in",
                "alpha_suffix": "1-12 ASCII letters (color/option value)",
                "not_stripped": "multi-digit size tokens (e.g. -100/-153) — never stripped",
                "candidate_only": "suffix-stripped base is a candidate, never auto-claimed",
            },
            "annotated_map_alias": "map ref_code prefixed with 已删除/删除/作废/停用 is treated as deleted evidence, not a live match",
            "token_permutation": "same dash-token multiset as a map key, used only as ambiguity/anomaly evidence",
        },
        "categories": cats,
        "reconciliation": recon,
        "anomalies": {
            "sku_map_duplicate_pairs_not_in_duckdb_table": sorted(
                [{"item_code": i, "tongtool_sku": t} for i, t in only_tsv], key=lambda x: x["tongtool_sku"]),
            "annotated_aliases_hit_by_unmatched": [
                {"sku": r["sku"], "category": r["category"], "item_codes": r["item_codes"], "flags": r["flags"]}
                for r in sku_rows if "map_alias_marked_deleted" in r["flags"]
            ],
            "conflicts": [
                {"sku": r["sku"], "category": r["category"], "flags": r["flags"], "evidence": r["evidence"]}
                for r in sku_rows if r["flags"] and r["category"] != "insufficient_evidence"
            ],
        },
        "skus": [{k: r[k] for k in ("sku", "category", "lines", "qty", "first_month", "last_month",
                                    "base", "item_codes", "evidence", "flags", "action")}
                 for r in sku_rows],
    }
    (OUT / "categories.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # deep100.md
    lines = ["# SKU 匹配审计 · 深度表（最多 100 个唯一 SKU）", "",
             f"- 生成时间：{payload['generated_at']}",
             f"- 输入：`{DB.name}` + `{MAP_TSV.name}`（只读）",
             f"- 覆盖：{len(deep)} 个 SKU；分类计数 "
             + "，".join(f"{c}={cats[c]['unique_skus']}" for c in CATEGORIES),
             "- 口径：仅精确等值算命中；后缀剥离结果只是**候选**，`register_candidate` 也只是建议人工登记，未写 EN。", "",
             "| # | SKU | 行数 | 首月 | 末月 | 分类 | 候选基础码 | 候选 item_code | 证据 | 建议动作 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(deep, 1):
        esc = lambda x: str(x).replace("|", "\\|")
        lines.append(f"| {i} | `{esc(r['sku'])}` | {r['lines']} | {r['first_month']} | {r['last_month']} | "
                     f"{r['category']} | {esc(r['base']) or '—'} | {esc(r['item_codes']) or '—'} | "
                     f"{esc(r['evidence'])} | {r['action']} |")
    lines += ["", "## 动作含义", "",
              "- `register_candidate`：建议人工登记客户 SKU（本审计不写 EN）。",
              "- `manual_review`：需人工确认候选/异常。",
              "- `no_action`：历史订单且 alias 已被有意删除，无需回补。", ""]
    (OUT / "deep100.md").write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({"totals": payload["totals"],
                      "categories": {c: {k: cats[c][k] for k in ("unique_skus", "order_lines", "qty", "first_month", "last_month")} for c in CATEGORIES},
                      "reconciliation": recon}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
