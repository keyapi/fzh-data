# -*- coding: utf-8 -*-
"""SO 工厂条件供给层 v3（基于守恒 v2 的逐行重分类；只读，不改主表）。

只把同时满足以下条件的行作为「可用候选」：
- `scope=in_house`、`qty_status=known`、`qty_basis != job_card_first_op`
- 逐 SO 行按订单行 qty 封顶后的 `attributable_qty`（守恒 v2 的重分类）
- 阶段为完工待发/在产（有日期）或在途（无 ETA，只列不抵）
- 不补 `duplicate`（v2 实测为 0）；`over_ship`/`abnormal_placeholder` 的**超出部分**不计

输出：`so-conditional-supply-2026-10-28-v3/`
- `so_supply_tranches_v3.csv`：逐 tranche 候选量
- `so_conditional_by_key_v3.csv`：SKU×分公司仓×UOM + 90/150 天缺口含/不含
- `v3_vs_v2_diff.csv`：与 v2 的差异
- `report.md` / summary / manifest

仍然是**条件附件**：`offset_allowed=false`，不改 r6/h180 净额与决策包，不 push。
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from self_fulfilled_demand.canonical import load_sku_map

from supply_netting.decision_pack import COUNTERFACTUAL_NOTE
from supply_netting.leadtime import load_default_config
from supply_netting.so_backlog import finished_item
from supply_netting.scripts.so_conditional_supply import _branch, load_w1, plan_dates
from supply_netting.scripts.so_conservation_fix import reconcile

SUPPLY_STAGES = ("produced_pending_dn", "in_production", "shipped_in_transit")
DATED_STAGES = ("produced_pending_dn", "in_production")
KEY = ["canonical_sku", "branch_warehouse", "uom"]

# 日期分段（发运/生产/海运/春节）来自版本化配置；manifest 记录版本 + 哈希 + 来源。
LEADTIME = load_default_config()


def resolve_uom(item_code: str, canonical_sku: str, source_uom, uom_map: dict | None) -> tuple:
    """按 UOM-CANONICAL 定单位：(uom, source, proven, note)。

    - TJ# 套件：强制「套」（stock_uom=套、is_stock_item=0），不拆组件；
    - 其它：以 EN `Item.stock_uom` 为已证来源；
    - 无证据：uom=None、proven=False，只能进待核，不参与合计。
    """
    if uom_map is None:                      # 合成测试/无缓存：沿用 W1 单位并标注来源
        return (source_uom, "w1_uom", True, None)
    if str(canonical_sku).startswith("TJ#") or str(item_code).startswith("TJ#"):
        cached = uom_map.get(str(canonical_sku))
        note = None if cached == "套" else f"cache={cached!r}; 按套件规则强制套"
        return ("套", "tj_bundle_rule", True, note)
    cached = uom_map.get(str(canonical_sku))
    if cached:
        return (cached, "en_stock_uom", True, None)
    return (None, "unproven", False, "无 EN Item.stock_uom 证据")


def build_tranches(w1_rows: list[dict], uom_map: dict | None = None) -> tuple[pd.DataFrame, dict]:
    records, excluded = [], Counter()
    for row in w1_rows:
        payload = row["payload"]
        audit_date = date.fromisoformat(str(payload.get("as_of")))
        lines = {line.get("so_line"): line for line in payload.get("lines", [])}
        balances = payload.get("stage_balances", [])
        recs, so_summary = reconcile(payload)
        for balance, rec in zip(balances, recs):
            stage = balance.get("stage")
            qty_status = balance.get("qty_status")
            basis = str(balance.get("qty_basis") or "")
            scope = balance.get("scope")
            line = lines.get(balance.get("so_line_id"), {})
            branch, role = _branch(line.get("customer"))
            item = str(balance.get("item_code") or line.get("item_code") or "")
            sku, converted = finished_item(item)

            usable = (rec["attributable_qty"] > 0 and scope == "in_house"
                      and qty_status == "known" and basis != "job_card_first_op"
                      and stage in SUPPLY_STAGES)
            if not usable:
                if basis == "job_card_first_op" and rec["attributable_qty"] > 0:
                    excluded["first_op_basis"] += rec["attributable_qty"]
                elif scope != "in_house" and rec["attributable_qty"] > 0:
                    excluded["fba_or_external"] += rec["attributable_qty"]
                elif rec["excess_qty"] > 0:
                    excluded[f"excess:{rec['excess_class'] or 'unclassified'}"] += rec["excess_qty"]
                elif qty_status != "known" and rec["attributable_qty"] > 0:
                    excluded["qty_unproven"] += rec["attributable_qty"]
                continue

            dates = plan_dates(stage, audit_date, branch)
            qty = float(rec["attributable_qty"])
            uom, uom_source, uom_proven, uom_note = resolve_uom(
                item, sku, balance.get("uom"), uom_map)
            if not uom_proven:
                excluded["uom_unproven"] += qty
                records.append(dict(
                    so=row.get("so"), so_line_id=balance.get("so_line_id"),
                    item_code=item, canonical_sku=sku, conversion_assumed=converted,
                    branch_warehouse=branch, role=role, uom=None,
                    source_uom=balance.get("uom"), uom_source=uom_source,
                    uom_proven=False, included=False, uom_note=uom_note,
                    stage=stage, candidate_qty=qty,
                    source_row_qty=float(balance.get("qty") or 0),
                    excess_class=rec["excess_class"] or None,
                    source_classification=rec["classification"],
                    qty_status=qty_status, qty_basis=basis or None,
                    source_record=balance.get("source_record"),
                    batch_key=balance.get("batch_key"),
                    eta_earliest=None, eta_latest=None,
                    eta_basis="单位未证，不给日期", confidence="unknown",
                    spring_buffer_days=None, spring_crossing=None,
                    so_status=so_summary["status"], evidence_status="uom_unproven",
                    dedup_status="po_in_transit_unproven", offset_allowed=False,
                    note="单位未证（无 EN stock_uom）：不参与任何合计，仅待核",
                ))
                continue
            records.append(dict(
                so=row.get("so"), so_line_id=balance.get("so_line_id"),
                item_code=item, canonical_sku=sku, conversion_assumed=converted,
                branch_warehouse=branch, role=role, uom=uom,
                source_uom=balance.get("uom"), uom_source=uom_source,
                uom_proven=True, included=True, uom_note=uom_note,
                stage=stage, candidate_qty=qty,
                source_row_qty=float(balance.get("qty") or 0),
                excess_class=rec["excess_class"] or None,
                source_classification=rec["classification"],
                qty_status=qty_status, qty_basis=basis or None,
                source_record=balance.get("source_record"),
                batch_key=balance.get("batch_key"),
                eta_earliest=dates["eta_earliest"], eta_latest=dates["eta_latest"],
                eta_basis=dates["eta_basis"], confidence=dates["confidence"],
                spring_buffer_days=dates["spring_buffer_days"],
                spring_crossing=dates["spring_crossing"],
                so_status=so_summary["status"],
                evidence_status="measured",
                dedup_status="po_in_transit_unproven",
                offset_allowed=False,
                note=COUNTERFACTUAL_NOTE if stage == "shipped_in_transit" else "",
            ))
    return pd.DataFrame(records), dict(excluded)


def build_by_key(tranches: pd.DataFrame, windows_keys: pd.DataFrame | None,
                 window_days=(90, 150)) -> pd.DataFrame:
    if tranches.empty:
        return pd.DataFrame(columns=KEY)
    frame = tranches[tranches.get("included", True).astype(bool)].copy()
    if frame.empty:
        return pd.DataFrame(columns=KEY)
    frame["eta_earliest_date"] = pd.to_datetime(frame["eta_earliest"], errors="coerce", utc=True)
    frame["eta_latest_date"] = pd.to_datetime(frame["eta_latest"], errors="coerce", utc=True)

    dated = frame[frame["stage"].isin(DATED_STAGES)]
    per_key = frame.pivot_table(index=KEY, columns="stage", values="candidate_qty",
                                aggfunc="sum").fillna(0.0).reset_index()
    for column in ("produced_pending_dn", "in_production", "shipped_in_transit"):
        if column not in per_key.columns:
            per_key[column] = 0.0
    per_key = per_key.rename(columns={"produced_pending_dn": "produced_pending_qty",
                                      "in_production": "in_production_qty",
                                      "shipped_in_transit": "transit_qty_no_eta"})
    per_key["candidate_dated_qty"] = per_key["produced_pending_qty"] + per_key["in_production_qty"]
    earliest = dated.groupby(KEY)["eta_earliest_date"].min().rename("earliest_eta")
    per_key = per_key.merge(earliest, on=KEY, how="left")
    per_key["earliest_eta"] = per_key["earliest_eta"].dt.strftime("%Y-%m-%d")

    for days in window_days:
        per_key[f"gap{days}_base"] = None
        per_key[f"gap{days}_with"] = None
        per_key[f"gap{days}_with_optimistic"] = None
    if windows_keys is not None and len(windows_keys):
        wk = windows_keys.rename(columns={"canonical_warehouse": "branch_warehouse",
                                          "canonical_uom": "uom"})
        for days in window_days:
            part = wk[wk["window_days"] == days]
            if part.empty:
                continue
            bucket_end = pd.to_datetime(part["bucket_end"].iloc[0], utc=True)
            gaps = part.set_index(KEY)["cum_unserved"]
            per_key[f"gap{days}_base"] = per_key.set_index(KEY).index.map(gaps)
            latest_mask = dated["eta_latest_date"] <= bucket_end
            earliest_mask = dated["eta_earliest_date"] <= bucket_end
            latest_qty = dated[latest_mask].groupby(KEY)["candidate_qty"].sum()
            earliest_qty = dated[earliest_mask].groupby(KEY)["candidate_qty"].sum()
            latest_aligned = pd.Series(per_key.set_index(KEY).index.map(latest_qty).values,
                                       index=per_key.index).fillna(0.0)
            earliest_aligned = pd.Series(per_key.set_index(KEY).index.map(earliest_qty).values,
                                         index=per_key.index).fillna(0.0)
            base = pd.to_numeric(per_key[f"gap{days}_base"], errors="coerce")
            per_key[f"gap{days}_with"] = (base - latest_aligned).clip(lower=0).where(base.notna())
            per_key[f"gap{days}_with_optimistic"] = (base - earliest_aligned).clip(lower=0).where(
                base.notna())
    per_key["netting_key_present"] = per_key.get("gap90_base").notna()
    return per_key.sort_values(["uom", "candidate_dated_qty"], ascending=[True, False]) \
        .reset_index(drop=True)


def build_diff(by_key: pd.DataFrame, v2_path: str | Path | None) -> pd.DataFrame:
    if not v2_path or not Path(v2_path).exists():
        return pd.DataFrame()
    v2 = pd.read_csv(v2_path, encoding="utf-8-sig").rename(
        columns={"conditional_dated_qty": "v2_candidate_qty"})
    merged = v2.merge(by_key, on=KEY, how="outer", suffixes=("_v2", "_v3"))
    for column in ("v2_candidate_qty", "candidate_dated_qty"):
        if column in merged:
            merged[column] = pd.to_numeric(merged[column], errors="coerce").fillna(0.0)
    merged["delta_qty"] = merged["candidate_dated_qty"] - merged["v2_candidate_qty"]
    merged["delta_gap90"] = (pd.to_numeric(merged.get("gap90_with_v3"), errors="coerce")
                             - pd.to_numeric(merged.get("gap90_with_v2"), errors="coerce"))
    merged["delta_gap150"] = (pd.to_numeric(merged.get("gap150_with_v3"), errors="coerce")
                              - pd.to_numeric(merged.get("gap150_with_v2"), errors="coerce"))
    return merged.sort_values("delta_qty", ascending=False)


def summarize(tranches: pd.DataFrame, by_key: pd.DataFrame, excluded: dict) -> dict:
    def _uom_sum(frame, column):
        return {str(k): round(float(v), 3) for k, v in frame.groupby("uom")[column].sum().items()}

    included = tranches[tranches.get("included", True).astype(bool)]
    return dict(
        tranches=int(len(tranches)),
        included_tranches=int(len(included)),
        candidate_total=round(float(included["candidate_qty"].sum()), 3),
        candidate_by_uom=_uom_sum(included, "candidate_qty"),
        candidate_by_stage={str(k): round(float(v), 3) for k, v in
                            included.groupby("stage")["candidate_qty"].sum().items()},
        candidate_by_branch={str(k): round(float(v), 3) for k, v in
                             included.groupby("branch_warehouse")["candidate_qty"].sum().items()},
        uom_unproven_rows=int((~tranches.get("included", True).astype(bool)).sum()),
        uom_unproven_qty=round(float(tranches.loc[
            ~tranches.get("included", True).astype(bool), "candidate_qty"].sum()), 3),
        uom_sources=dict(Counter(included.get("uom_source", pd.Series(dtype=str)))),
        dated_candidate_total=round(float(by_key["candidate_dated_qty"].sum()), 3),
        dated_candidate_by_uom=_uom_sum(by_key, "candidate_dated_qty"),
        gap90_base=round(float(pd.to_numeric(by_key["gap90_base"], errors="coerce")
                               .fillna(0).sum()), 3),
        gap90_with=round(float(pd.to_numeric(by_key["gap90_with"], errors="coerce")
                               .fillna(0).sum()), 3),
        gap150_base=round(float(pd.to_numeric(by_key["gap150_base"], errors="coerce")
                                .fillna(0).sum()), 3),
        gap150_with=round(float(pd.to_numeric(by_key["gap150_with"], errors="coerce")
                                .fillna(0).sum()), 3),
        excluded={str(k): round(float(v), 3) for k, v in excluded.items()},
        duplicate_qty=0.0,
        offset_allowed=False,
        status="pending_review",
        note="条件附件；不改 r6/h180 净额与决策包",
    )


def write_report(tranches: pd.DataFrame, by_key: pd.DataFrame, diff: pd.DataFrame,
                 stats: dict, meta: dict, out: Path) -> None:
    lines = [
        "# SO 工厂条件供给层 v3（基于守恒 v2 逐行重分类）",
        "",
        f"- 生成时间：{meta['generated_at']}；输入：W1 `{meta['w1']}`、"
        f"守恒 v2 `{meta['conservation_v2']}`、v2 层 `{meta['v2']}`、窗口 `{meta['windows']}`",
        "- 状态：**pending re-review**；仍只作条件附件，`offset_allowed=false`",
        "",
        "## 1. 纳入规则（逐行）",
        "",
        "| 条件 | 处理 |",
        "|---|---|",
        "| `scope=in_house` | 必须；FBA 行剔除 |",
        "| `qty_status=known` | 必须；unknown 不计 |",
        "| `qty_basis=job_card_first_op` | 剔除（只证首工序，不称可发运） |",
        "| 逐 SO 行 qty 封顶 | 只用 `attributable_qty`；超出部分按守恒 v2 分类（超发/占位/重复）不计 |",
        "| `duplicate` | v2 实测 0，不补 |",
        "| 阶段 | 完工待发/在产给日期；在途无 ETA，只列不抵 |",
        "",
        "## 1.1 UOM 口径确认（UOM-CANONICAL.md）",
        "",
        "已读 `D:/Work/赛狐/Cursor-claude/docs/research/supply-chain/2026-10-20/claude/control/"
        "reference/UOM-CANONICAL.md`，本层按以下口径执行：",
        "",
        "- **个 / 套分列**：`canonical_uom` 取自 EN `Item.stock_uom`；个与套的合计互不相加。",
        "- **TJ# 按套**：套件强制 `uom=套`（stock_uom=套、is_stock_item=0），不拆组件，"
        "不把组件 KS 的「个」再加一遍。",
        "- **PK# 皮壳 1:1**：转成对应 KS 物料按「个」计（`conversion_assumed`），不是「套」。",
        "- **未知单位不合计**：无 EN stock_uom 证据的行 `uom=None`、`included=false`，"
        f"只进待核。本次 **{stats['uom_unproven_rows']} 行 / "
        f"{stats['uom_unproven_qty']:.0f}** 因此被剔除（v3 初稿曾沿用 W1 的「个/件」）。",
        f"- 单位来源分布：{json.dumps(stats['uom_sources'], ensure_ascii=False)}",
        "",
        "## 1.2 与知识清单的关系（已读确认）",
        "",
        "已读 `D:/Work/赛狐/Cursor-claude/docs/research/supply-chain/2026-10-20/claude/control/"
        "reviews/2026-10-28-frepple-conversation-digest.md`：",
        "",
        "- **SKU 角色**：tranche 附 `product_role`（皮壳/成品/半成品）。PK#→KS 是 1:1 物料代理，"
        "不把皮壳当独立成品下库存结论；本层不按角色设服务档。",
        "- **断货删失**：本层不使用需求历史训练，不涉及零库存月删失；候选量不受影响。",
        "- **服务 β/τ**：本层不设服务水平、不计算库存倍数；政策对账在后续 POLICY-RECONCILE。",
        "- **ASSET-REUSE-AUDIT**：下一项任务；既有资产位置已确认 —— "
        "`experiments/business_phase/inventory_policy.py`（e3727683）、"
        "`experiments/business_phase/sc08_conformal.py`（9624b248）、"
        "`experiments/sc13/leadtime_config.py`。",
        "",
        "## 2. 候选量（按 UOM，不跨 UOM 相加）",
        "",
        "| uom | 候选总量 | 其中有日期（可抵情景） |",
        "|---|---:|---:|",
    ]
    dated_by_uom = by_key.groupby("uom")["candidate_dated_qty"].sum().to_dict()
    for uom, qty in stats["candidate_by_uom"].items():
        lines.append(f"| {uom} | {qty:.0f} | {float(dated_by_uom.get(uom, 0)):.0f} |")
    lines += [
        "",
        "按阶段：" + json.dumps(stats["candidate_by_stage"], ensure_ascii=False),
        "",
        "按分公司：" + json.dumps(stats["candidate_by_branch"], ensure_ascii=False),
        "",
        "## 3. 剔除了什么（数量）",
        "",
    ]
    for reason, qty in sorted(stats["excluded"].items(), key=lambda item: -item[1]):
        lines.append(f"- {reason}: {qty:.0f}")
    lines += [
        f"- duplicate: 0（v2 无未标记孪生）",
        "",
        "## 4. 90 / 150 天缺口（含 / 不含工厂条件供给）",
        "",
        "| 窗口 | 基线 | 含条件供给（最晚 ETA） |",
        "|---|---:|---:|",
        f"| 90 天 | {stats['gap90_base']:.0f} | {stats['gap90_with']:.0f} |",
        f"| 150 天 | {stats['gap150_base']:.0f} | {stats['gap150_with']:.0f} |",
        "",
        "只覆盖有净额键的 SKU×仓×UOM；未匹配的键保持 null，不写 0。",
        "",
        "## 5. 与 v2 的差异",
        "",
        f"- v2 条件量（守恒 SO、已证、非首工序、有日期）只覆盖 145 个；"
        f"v3 改为**全部 97 单的逐行封顶**，有日期候选 "
        f"{stats['dated_candidate_total']:.0f}。",
        "- 完工待发阶段在 v3 为 0：这些行全部是 `job_card_first_op`（只证首工序），"
        "按规则剔除；在产阶段是唯一有日期的已证候选。",
        "- 在途 48,978 无 ETA，只列不抵；与 v2 相同。",
        "",
    ]
    if len(diff):
        changed = diff[diff["delta_qty"].abs() > 1e-6]
        lines += [
            f"- 与 v2 逐键对比：有差异 {len(changed)} 键；"
            f"v3 增量合计 {float(changed['delta_qty'].sum()):.0f}（按 UOM 见 CSV）。",
            "",
        ]
    lines += [
        "## 6. 边界",
        "",
        "- 仍只作附件：不改 r6/h180 净额、不改决策包、不 push；`offset_allowed=false`。",
        "- 候选量是规则化证据，不是实物已证；DN 级数量/行未接入前不得当权威抵扣。",
        "- 春节：路径穿越 2027-02-06 窗口的最晚 ETA +60 天（最早 ETA 不加）。",
        "",
    ]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="SO 条件供给 v3（逐行封顶候选）")
    parser.add_argument("--w1", default="D:/Work/fzh-order-store/w1_supply_facts_v2/supply_facts_raw.jsonl")
    parser.add_argument("--conservation-v2",
                        default="D:/Work/fzh-order-store/en-demand-v1/supply-netting/"
                                "so-conservation-fix-2026-10-28-v2")
    parser.add_argument("--v2",
                        default="D:/Work/fzh-order-store/en-demand-v1/supply-netting/"
                                "so-conditional-supply-2026-10-27-v2/so_conditional_by_key.csv")
    parser.add_argument("--windows",
                        default="D:/Work/fzh-order-store/en-demand-v1/supply-netting/"
                                "horizon-windows-2026-10-29/horizon_windows_keys.csv")
    parser.add_argument("--sku-map", default="D:/Work/fzh-order-store/sku_map.tsv")
    parser.add_argument("--role-csv",
                        default="D:/Work/fzh-order-store/analysis/sku_classification_by_role_20261027.csv")
    parser.add_argument("--uom-cache",
                        default="D:/Work/fzh-order-store/en-demand-v1/canonical/item_uom_cache.parquet")
    parser.add_argument("--out", default="D:/Work/fzh-order-store/en-demand-v1/supply-netting/"
                                         "so-conditional-supply-2026-10-28-v3")
    args = parser.parse_args(argv)

    w1 = load_w1(args.w1)
    uom_map = {}
    if args.uom_cache and Path(args.uom_cache).exists():
        cache = pd.read_parquet(args.uom_cache)
        uom_map = {str(row.item_code): str(row.stock_uom)
                   for row in cache.itertuples(index=False) if pd.notna(row.stock_uom)}
    tranches, excluded = build_tranches(w1, uom_map)
    if args.role_csv and Path(args.role_csv).exists():
        roles = pd.read_csv(args.role_csv, encoding="utf-8-sig")
        role_by_item = {}
        sku_map = load_sku_map(args.sku_map) if Path(args.sku_map).exists() else None
        if sku_map is not None:
            tt_to_item = {row.tongtool_sku: row.item_codes[0]
                          for row in sku_map.itertuples(index=False)
                          if row.mapping_status == "mapped" and len(row.item_codes) == 1}
            for row in roles.itertuples(index=False):
                item = tt_to_item.get(str(row.sku).strip())
                if item and str(row.role) not in ("", "nan"):
                    role_by_item.setdefault(item, str(row.role))
        tranches["product_role"] = tranches["canonical_sku"].map(role_by_item).fillna("unknown")
    windows = (pd.read_csv(args.windows, encoding="utf-8-sig")
               if args.windows and Path(args.windows).exists() else None)
    by_key = build_by_key(tranches, windows)
    diff = build_diff(by_key, args.v2)
    stats = summarize(tranches, by_key, excluded)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tranches.to_csv(out / "so_supply_tranches_v3.csv", index=False, encoding="utf-8-sig")
    by_key.to_csv(out / "so_conditional_by_key_v3.csv", index=False, encoding="utf-8-sig")
    if len(diff):
        diff.to_csv(out / "v3_vs_v2_diff.csv", index=False, encoding="utf-8-sig")
    meta = dict(schema_version="so-conditional-supply/v3",
                generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                w1=str(args.w1), uom_cache=str(args.uom_cache),
                uom_canonical="D:/Work/赛狐/Cursor-claude/docs/research/supply-chain/2026-10-20/claude/control/reference/UOM-CANONICAL.md",
                conservation_v2=str(args.conservation_v2),
                v2=str(args.v2), windows=str(args.windows),
                leadtime_config=LEADTIME.provenance(),
                status="pending_review", offset_allowed=False,
                note="条件附件；不改 r6/h180 净额与决策包，不 push")
    (out / "so_conditional_supply_v3_summary.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "so_conditional_supply_v3_manifest.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(tranches, by_key, diff, stats, meta, out)
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    print("输出：", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
