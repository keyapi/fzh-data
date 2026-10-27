# -*- coding: utf-8 -*-
"""把 97 张开放 SO 的 W1 阶段余额做成「有条件、带日期」的工厂供给层。

只读 W1 缓存与审计产物，不改净额/决策包任何数字。输出：

- ``so_supply_tranches.csv``：每条 SO 行 × 阶段一行（目标分公司/SKU/数量/ETA/依据/置信度/春节/去重）
- ``so_conditional_by_key.csv``：SKU×分公司仓×UOM 汇总 + 90/150 天缺口「含/不含」工厂条件供给
- ``report.md``：假设、守恒标记、去重未证

日期规则（审计日 = W1 ``as_of``，2026-10-27）：
- 完工待发运 ``produced_pending_dn`` = 审计日 + 发运 7 天 + 海运假设（美东 35 / 波兰 40，assumed）
- 在产 ``in_production`` = 审计日 + 生产 60 天 + 发运 7 + 海运
- 在途 ``shipped_in_transit`` = 剩余海运 unknown → 不给日期
- 路径穿越 2027-02-06 窗口（锚点 ±30 天）→ 最晚 ETA 加 60 天（最早 ETA 不加）

守恒：``so_open_audit_2026-10-27.csv`` 的「守恒」列；不守恒的单不进「权威条件量」，
只作证据/敏感性，绝不作为抵扣。
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from supply_netting.so_backlog import (CUSTOMER_BRANCH, SPRING_FESTIVAL_ANCHOR,
                                       finished_item, festival_window)

SHIP_DAYS = 7
PRODUCTION_DAYS = 60
SEA_DAYS = {"美东-CENTRADE": 35, "美中-FZH-DANEEY": 35, "波兰-FZHPoland-covers": 40}
SPRING_BUFFER_DAYS = 60
PRODUCTIVE_STAGES = ("produced_pending_dn", "in_production", "shipped_in_transit")
LAYER_ORDER = {"shipped_in_transit": 0, "produced_pending_dn": 1, "in_production": 2}


CUSTOMER_ALIASES = {
    "美东-CENTRADE": ("CENTRADE", "CENTADE"),   # W1 实际拼写为 CENTADE
    "美中-FZH-DANEEY": ("DANEEY",),
    "波兰-FZHPoland-covers": ("波兰",),
}


def _branch(customer: str) -> tuple[str | None, str]:
    """W1 客户名 → (分公司仓, 角色)。容错 CENTRADE/CENTADE 两种拼写。"""
    text = str(customer or "").upper()
    if "FBA" in text:
        return None, "fba_external"
    for branch, keys in CUSTOMER_ALIASES.items():
        if any(key.upper() in text for key in keys):
            return branch, "finished"
    return None, "unknown"


def _sea_days(branch: str | None) -> int | None:
    return SEA_DAYS.get(branch or "")


def _crosses_festival(start: date, end: date, anchor: date = SPRING_FESTIVAL_ANCHOR) -> bool:
    window_start, window_end = festival_window(anchor)
    return start <= window_end and end >= window_start


def plan_dates(stage: str, audit_date: date, branch: str | None) -> dict:
    """返回 earliest/latest ETA、依据与置信度（全部 assumed / unknown，绝不 confirmed）。"""
    sea = _sea_days(branch)
    if stage == "produced_pending_dn" and sea is not None:
        base = audit_date + timedelta(days=SHIP_DAYS + sea)
        basis = f"审计日+发运{SHIP_DAYS}天+海运{sea}天（assumed）"
        confidence = "assumed"
    elif stage == "in_production" and sea is not None:
        base = audit_date + timedelta(days=PRODUCTION_DAYS + SHIP_DAYS + sea)
        basis = (f"审计日+生产{PRODUCTION_DAYS}天+发运{SHIP_DAYS}天+海运{sea}天（assumed）")
        confidence = "assumed"
    elif stage == "shipped_in_transit":
        return dict(eta_earliest=None, eta_latest=None, eta_basis="在途剩余海运未证（unknown）",
                    confidence="unknown", spring_buffer_days=None, spring_crossing=None)
    else:
        return dict(eta_earliest=None, eta_latest=None, eta_basis="非可供给阶段，不给日期",
                    confidence="unknown", spring_buffer_days=None, spring_crossing=None)
    spring = _crosses_festival(audit_date, base)
    latest = base + timedelta(days=SPRING_BUFFER_DAYS) if spring else base
    if spring:
        basis = f"{basis}；路径穿越 2027-02-06 窗口，最晚 +{SPRING_BUFFER_DAYS} 天"
    return dict(eta_earliest=base.isoformat(), eta_latest=latest.isoformat(), eta_basis=basis,
                confidence=confidence, spring_buffer_days=SPRING_BUFFER_DAYS if spring else 0,
                spring_crossing=bool(spring))


def load_w1(path: str | Path) -> list[dict]:
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]
    for row in rows:
        if not isinstance(row.get("payload"), dict):
            raise ValueError("W1 缓存结构异常：缺 payload")
    return rows


def load_conservation(audit_csv: str | Path | None) -> dict[str, bool]:
    """SO → 是否守恒。缺文件时返回空（全部按未证处理，不冒充守恒）。"""
    if not audit_csv or not Path(audit_csv).exists():
        return {}
    frame = pd.read_csv(audit_csv, encoding="utf-8-sig")
    if "SO" not in frame.columns or "守恒" not in frame.columns:
        return {}
    return {str(row.SO): str(row.守恒).strip() == "是" for row in frame.itertuples(index=False)}


def build_tranches(w1_rows: list[dict], conservation: dict[str, bool]) -> pd.DataFrame:
    records = []
    for row in w1_rows:
        payload = row["payload"]
        audit_date = date.fromisoformat(str(payload.get("as_of")))
        lines = {line.get("so_line"): line for line in payload.get("lines", [])}
        so_id = row.get("so") or payload.get("so")
        conserved = conservation.get(str(so_id), None)
        for balance in payload.get("stage_balances", []):
            line = lines.get(balance.get("so_line_id"), {})
            customer = line.get("customer")
            branch, role = _branch(customer)
            raw_sku = str(balance.get("item_code") or line.get("item_code") or "")
            sku, converted = finished_item(raw_sku)
            stage = balance.get("stage")
            qty = balance.get("qty")
            qty_known = balance.get("qty_status") == "known" and qty is not None
            scope = balance.get("scope")
            dates = plan_dates(stage, audit_date, branch)
            excluded = balance.get("exclusion_reason") or ""
            blocking_exclusion = bool(excluded) and excluded not in ("缺出库单",)
            basis = str(balance.get("qty_basis") or "")
            if not qty_known:
                qty_evidence = "unknown"
            elif basis == "job_card_first_op":
                qty_evidence = "estimated_first_op"      # 只证明首工序，不等于可发运
            else:
                qty_evidence = "measured"
            # v2：权威量必须 in_house + 守恒 + 有分公司目标 + 已证数量 + 非首工序推断
            authoritative = bool(
                conserved is True and qty_known and scope == "in_house"
                and branch is not None and role == "finished"
                and stage in ("produced_pending_dn", "in_production")
                and qty_evidence == "measured"
                and not blocking_exclusion
            )
            records.append(dict(
                so=balance.get("so"), so_line_id=balance.get("so_line_id"),
                item_code_raw=raw_sku, canonical_sku=sku, conversion_assumed=converted,
                customer=customer, branch_warehouse=branch, role=role,
                factory_warehouse=balance.get("warehouse"), uom=balance.get("uom"),
                stage=stage, stage_detail=balance.get("stage_detail"),
                qty=qty, qty_status=balance.get("qty_status"),
                qty_basis=balance.get("qty_basis"),
                batch_key=balance.get("batch_key"),
                source_record=balance.get("source_record"),
                included_in_stock=balance.get("included_in_stock"),
                scope=scope,
                so_conserved=conserved,
                qty_evidence=qty_evidence,
                authoritative_offset=authoritative,
                **dates,
                dedup_status=("po_in_transit_unproven"
                              + (";batch_key_present" if balance.get("batch_key")
                                 else ";no_batch_key")),
                exclusion_reason=excluded,
            ))
    frame = pd.DataFrame(records)
    if frame.empty:
        return frame
    # 同一 SO 行的多层阶段：只标重叠，不擅自合并
    overlap = (frame[frame["stage"].isin(PRODUCTIVE_STAGES)]
               .groupby(["so", "so_line_id"])["stage"].nunique())
    multi = set(overlap[overlap > 1].index)
    frame["layer_overlap_unproven"] = [
        (row.so, row.so_line_id) in multi for row in frame.itertuples(index=False)]
    return frame


def build_by_key(tranches: pd.DataFrame, windows_keys: pd.DataFrame | None,
                 window_days=(90, 150)) -> pd.DataFrame:
    key = ["canonical_sku", "branch_warehouse", "uom"]
    usable = tranches[(tranches["scope"] == "in_house")
                      & (tranches["qty_status"] == "known")
                      & tranches["stage"].isin(PRODUCTIVE_STAGES)].copy()
    if usable.empty:
        return pd.DataFrame(columns=key + ["in_production_qty", "produced_pending_dn_qty",
                                           "shipped_in_transit_qty", "earliest_eta",
                                           "conditional_dated_qty", "conditional_dated_qty_all",
                                           "in_transit_qty_no_eta"])
    usable["qty"] = pd.to_numeric(usable["qty"], errors="coerce").fillna(0.0)

    def _stage_sum(frame, stage):
        return (frame[frame["stage"] == stage].groupby(key)["qty"].sum()
                .rename(f"{stage}_qty"))

    grouped = pd.concat([_stage_sum(usable, s) for s in PRODUCTIVE_STAGES], axis=1).fillna(0.0)
    dated = usable[usable["stage"].isin(("produced_pending_dn", "in_production"))].copy()
    dated["eta_earliest_date"] = pd.to_datetime(dated["eta_earliest"], errors="coerce", utc=True)
    dated["eta_latest_date"] = pd.to_datetime(dated["eta_latest"], errors="coerce", utc=True)
    earliest = (dated[dated["authoritative_offset"]].groupby(key)["eta_earliest_date"].min()
                .rename("earliest_eta"))
    earliest_any = dated.groupby(key)["eta_earliest_date"].min().rename("earliest_eta_any")
    dated_qty = (dated[dated["authoritative_offset"]].groupby(key)["qty"].sum()
                 .rename("conditional_dated_qty"))
    estimated_qty = (dated[dated["so_conserved"].fillna(False).astype(bool)
                           & dated["authoritative_offset"].eq(False)
                           & dated["qty_evidence"].eq("estimated_first_op")]
                     .groupby(key)["qty"].sum().rename("conditional_dated_qty_estimated"))
    dated_qty_all = dated.groupby(key)["qty"].sum().rename("conditional_dated_qty_all")
    transit_qty = (usable[usable["stage"] == "shipped_in_transit"]
                   .groupby(key)["qty"].sum().rename("in_transit_qty_no_eta"))
    frame = (grouped.join([earliest, earliest_any, dated_qty, estimated_qty,
                           dated_qty_all, transit_qty], how="outer")
             .fillna({c: 0.0 for c in ("conditional_dated_qty",
                                       "conditional_dated_qty_estimated",
                                       "conditional_dated_qty_all",
                                       "in_transit_qty_no_eta")})
             .reset_index())
    frame["earliest_eta"] = frame["earliest_eta"].dt.strftime("%Y-%m-%d")
    frame["earliest_eta_any"] = frame["earliest_eta_any"].dt.strftime("%Y-%m-%d")

    # 缺口对比：来自多窗口切片（cum_unserved，按真实桶边界）
    for days in window_days:
        frame[f"gap{days}_base"] = None
        frame[f"gap{days}_with"] = None
        frame[f"gap{days}_with_optimistic"] = None
    if windows_keys is not None and len(windows_keys):
        wk = windows_keys.rename(columns={"canonical_warehouse": "branch_warehouse"})
        for days in window_days:
            part = wk[wk["window_days"] == days]
            if part.empty:
                continue
            bucket_end = pd.to_datetime(part["bucket_end"].iloc[0], utc=True)
            gaps = part.set_index(["canonical_sku", "branch_warehouse", "canonical_uom"])[
                "cum_unserved"]
            frame[f"gap{days}_base"] = frame.set_index(key).index.map(gaps)
            latest_mask = (dated["eta_latest_date"] <= bucket_end) & dated["authoritative_offset"]
            earliest_mask = (dated["eta_earliest_date"] <= bucket_end) & dated["authoritative_offset"]
            arriving_latest = dated.loc[latest_mask].groupby(key)["qty"].sum()
            arriving_earliest = dated.loc[earliest_mask].groupby(key)["qty"].sum()
            latest_qty = frame.set_index(key).index.map(arriving_latest).fillna(0.0)
            earliest_qty = frame.set_index(key).index.map(arriving_earliest).fillna(0.0)
            base = pd.to_numeric(frame[f"gap{days}_base"], errors="coerce")
            frame[f"gap{days}_with"] = (base - latest_qty).clip(lower=0).where(base.notna())
            frame[f"gap{days}_with_optimistic"] = (base - earliest_qty).clip(lower=0).where(
                base.notna())
    frame["netting_key_present"] = frame["gap90_base"].notna()
    frame["conservation_note"] = ("只计守恒 SO 的权威条件量；不守恒单见 tranches"
                                  if "authoritative_offset" in tranches.columns else "")
    return frame


def _uom_table(frame: pd.DataFrame, value: str, group: str | None = None) -> list[str]:
    """按 UOM 汇总；绝不产生跨 UOM 的总计行。"""
    if frame.empty or value not in frame.columns:
        return ["（无数据）"]
    numeric = frame.assign(qty=pd.to_numeric(frame[value], errors="coerce").fillna(0.0))
    uom_col = "uom" if "uom" in numeric.columns else "canonical_uom"
    grouped = numeric.groupby([uom_col] + ([group] if group else []), as_index=False)["qty"].sum()
    lines = ["| " + " | ".join(grouped.columns) + " |",
             "|" + "|".join("---" for _ in grouped.columns) + "|"]
    for row in grouped.itertuples(index=False):
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return lines


def write_report(tranches: pd.DataFrame, by_key: pd.DataFrame, meta: dict, out: Path) -> None:
    total = len(tranches)
    known = int((tranches["qty_status"] == "known").sum())
    auth = int(tranches["authoritative_offset"].sum())
    non_conserved = sorted({row.so for row in tranches.itertuples(index=False)
                            if row.so_conserved is False})
    fba = tranches[tranches["branch_warehouse"].isna()]
    first_op = int((tranches["qty_evidence"] == "estimated_first_op").sum())
    stage_qty = (tranches[tranches["qty_status"] == "known"]
                 .groupby(["uom", "stage"], as_index=False)["qty"].sum().round(3))
    lines = [
        "# SO 工厂条件供给层 v2（W1 阶段余额 → 有条件、带日期）",
        "",
        f"- 生成时间：{meta['generated_at']}；W1 as_of：{meta['as_of']}；规则版本：{meta['rule_version']}",
        f"- 输入：`{meta['w1']}`（{meta['so_count']} 张 SO / {total} 条阶段余额）",
        f"- 守恒证据：`{meta['audit_csv']}`（{len(non_conserved)} 单不守恒）",
        "",
        "## v2 修正（相对 v1）",
        "",
        "1. **权威条件量必须 `scope=in_house` 且 SO 守恒且目标分公司非空**；"
        f"FBA 客户行 {len(fba)} 条全部排除（v1 曾把 794 件 FBA 算进“权威”）。",
        f"2. `qty_basis=job_card_first_op` 的行 {first_op} 条标 `estimated_first_op`："
        "只证明首工序，**不称可发运、不进权威抵扣**。",
        "3. 所有汇总按 **UOM 分列**；本报告不出现跨 UOM 合计。",
        "4. 90/150 天缺口对比也按 UOM 匹配，不混合计量单位。",
        "",
        "## 日期规则（全部 assumed / unknown，无一条 confirmed）",
        "",
        f"- 完工待发运：审计日 + 发运 {SHIP_DAYS} 天 + 海运（美东/美中 35、波兰 40，assumed）",
        f"- 在产：审计日 + 生产 {PRODUCTION_DAYS} 天 + 发运 {SHIP_DAYS} + 海运",
        "- 在途：剩余海运 unknown → 不给日期（不计入任何时点覆盖）",
        f"- 春节：路径穿越 {SPRING_FESTIVAL_ANCHOR.isoformat()} 窗口（锚点 ±30 天）→ 最晚 ETA +{SPRING_BUFFER_DAYS} 天，最早 ETA 不加",
        "",
        "## 守恒标记",
        "",
        f"- 不守恒 SO：**{len(non_conserved)} 张**；这些单 `authoritative_offset=false`，"
        "只进敏感性（`conditional_dated_qty_all`），**不得作为权威抵扣**。",
        f"- 可作权威条件量的行：{auth} / {known} 条已知量行。",
        "",
        "## 分 UOM 条件量（不跨 UOM 相加）",
        "",
        "权威（in_house + 守恒 + 已证数量）：",
        "",
        *_uom_table(by_key, "conditional_dated_qty"),
        "",
        "首工序推断（estimated，不抵扣）：",
        "",
        *_uom_table(by_key, "conditional_dated_qty_estimated"),
        "",
        "敏感性上限（含不守恒 SO，仅参考）：",
        "",
        *_uom_table(by_key, "conditional_dated_qty_all"),
        "",
        "在途无 ETA（不计任何时点覆盖）：",
        "",
        *_uom_table(by_key, "in_transit_qty_no_eta"),
        "",
        "## 阶段量（已知数量，按 UOM）",
        "",
        "| uom | stage | qty |",
        "|---|---|---|",
    ]
    for row in stage_qty.sort_values(["uom", "qty"], ascending=[True, False])             .itertuples(index=False):
        lines.append(f"| {row.uom} | {row.stage} | {round(float(row.qty), 3)} |")
    lines += [
        "",
        "## 90 / 150 天缺口对比（按 UOM 匹配，含 / 不含工厂条件供给）",
        "",
    ]
    if len(by_key):
        for days in (90, 150):
            base_col, with_col = f"gap{days}_base", f"gap{days}_with"
            if base_col not in by_key.columns:
                continue
            frame = by_key.assign(
                _base=pd.to_numeric(by_key[base_col], errors="coerce"),
                _with=pd.to_numeric(by_key[with_col], errors="coerce"))
            frame = frame[frame["_base"].notna()]
            if frame.empty:
                continue
            lines.append(f"**{days} 天**")
            lines.append("")
            lines.append("| uom | 基线缺口 | 含条件供给 | 减少 | 变化键/可比键 |")
            lines.append("|---|---:|---:|---:|---|")
            for uom, group in frame.groupby("uom", sort=True):
                reduced = int((group["_with"] < group["_base"]).sum())
                lines.append(f"| {uom} | {group['_base'].sum():.0f} | "
                             f"{group['_with'].sum():.0f} | "
                             f"{group['_base'].sum() - group['_with'].sum():.0f} | "
                             f"{reduced} / {len(group)} |")
            lines.append("")
        lines.append("只覆盖有净额键的 SKU×仓×UOM；未匹配的键 gap 为 null，不写 0。")
    lines += [
        "",
        "## 去重状态",
        "",
        "- 与通途 PO/在途去重**未证**：所有行 `dedup_status=po_in_transit_unproven`；"
        "有 `batch_key` 只标存在，不升级为已证同批。",
        "- 同一 SO 行多层阶段标 `layer_overlap_unproven`，不擅自合并；"
        "`included_in_stock` 全部 unknown。",
        "",
        "## 输出",
        "",
        "- `so_supply_tranches.csv`：SO 行 × 阶段明细（含 `qty_evidence`）",
        "- `so_conditional_by_key.csv`：SKU×分公司仓×UOM 汇总 + 90/150 天缺口含/不含对比",
        "",
        "**只作条件附件**：不改 r6/h180 净额数字，不写 confirmed，不能直接当采购抵扣。",
        "",
    ]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="SO 工厂条件供给层（W1 阶段余额 → 条件 ETA）")
    parser.add_argument("--w1", default="D:/Work/fzh-order-store/w1_supply_facts_v2/supply_facts_raw.jsonl")
    parser.add_argument("--audit-csv",
                        default="D:/Work/fzh-order-store/en-demand-v1/supply-netting/"
                                "so-open-audit-2026-10-27/so_open_audit_2026-10-27.csv")
    parser.add_argument("--windows-keys",
                        default="D:/Work/fzh-order-store/en-demand-v1/supply-netting/"
                                "horizon-windows-2026-10-29/horizon_windows_keys.csv")
    parser.add_argument("--out", default="D:/Work/fzh-order-store/en-demand-v1/supply-netting/"
                                         "so-conditional-supply-2026-10-27-v2")
    args = parser.parse_args(argv)

    w1 = load_w1(args.w1)
    conservation = load_conservation(args.audit_csv)
    tranches = build_tranches(w1, conservation)
    windows = (pd.read_csv(args.windows_keys, encoding="utf-8-sig")
               if args.windows_keys and Path(args.windows_keys).exists() else None)
    by_key = build_by_key(tranches, windows)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tranches.to_csv(out / "so_supply_tranches.csv", index=False, encoding="utf-8-sig")
    by_key.to_csv(out / "so_conditional_by_key.csv", index=False, encoding="utf-8-sig")
    meta = dict(
        schema_version="so-conditional-supply/v1",
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        as_of=w1[0]["payload"].get("as_of") if w1 else None,
        rule_version=w1[0]["payload"].get("rule_version") if w1 else None,
        w1=str(args.w1), so_count=len(w1), audit_csv=str(args.audit_csv),
        windows_keys=str(args.windows_keys) if windows is not None else None,
        rows=len(tranches), keys=len(by_key),
        rules=dict(ship_days=SHIP_DAYS, production_days=PRODUCTION_DAYS, sea_days=SEA_DAYS,
                   spring_buffer_days=SPRING_BUFFER_DAYS,
                   spring_anchor=SPRING_FESTIVAL_ANCHOR.isoformat(),
                   confidence="assumed/unknown only; never confirmed"),
        note="条件情景，不改净额/决策包数字",
    )
    (out / "so_conditional_supply_manifest.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(tranches, by_key, meta, out)
    print(json.dumps(dict(rows=len(tranches), keys=len(by_key),
                          authoritative=int(tranches["authoritative_offset"].sum()),
                          out=str(out)), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
