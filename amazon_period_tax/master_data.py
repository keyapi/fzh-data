# -*- coding: utf-8 -*-
"""渠道主数据门禁（C1）：快照 metadata + live/snapshot 业务投影一致 + 未知别名候选。

对应 gate_remediation_plan_20261120.md U-C 与 gate_audit_20261120.md M03/T03：

- 发布时 **live（Google 表当期视图）是权威**；快照必须带真实抓取时间、source 标识和
  内容 hash，且在本批所需投影（渠道账号、别名、当期运营人员）上与 live 严格一致。
- 任一不一致 → FAIL，**不退回旧快照发布**；live 读不到也不允许用快照替代。
- 未知别名只输出 candidate 报告（``unknown_alias_candidates``），本模块**没有任何写回
  主表的路径**。
- TTL 未获业务批准，采用保守默认 24h（``snapshot.DEFAULT_TTL_HOURS``）；过期/缺
  metadata 一律视为不可发布。
- 收款归属对 Tax/附加费-only 行 **不适用**：本模块只校验业务账号、渠道/平台与当期人员，
  不假装校验一个 Tax 行根本没有的归属字段。
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from amounts import is_blank_value
from channel_account_sync.snapshot import (
    DEFAULT_TTL_HOURS,
    business_projection,
    norm_alias,
    validate_snapshot,
)

# 主数据里 Tax 业务账号必须落在 Amazon 渠道（Tax txt 只来自 Amazon）。
AMAZON_CHANNEL = "Amazon"


@dataclass
class MasterGateResult:
    problems: list[str] = field(default_factory=list)
    unknown_alias_candidates: list[dict] = field(default_factory=list)
    snapshot_meta: dict | None = None
    live_projection: list[dict] | None = None
    snapshot_projection: list[dict] | None = None


def _clean(value) -> str | None:
    if is_blank_value(value):
        return None
    return str(value).strip() or None


def live_projection(acct_view: pd.DataFrame | None, df_explode: pd.DataFrame | None) -> list[dict]:
    """live 渠道主表 → 本批业务投影（与快照同口径，可直接比较/hash）。"""
    if acct_view is None or acct_view.empty:
        return []
    aliases: dict[str, set[str]] = defaultdict(set)
    if df_explode is not None and not df_explode.empty:
        for canon, alias in zip(df_explode["渠道账号"], df_explode["渠道账号别名"]):
            c, a = _clean(canon), _clean(alias)
            if c and a:
                aliases[c].add(norm_alias(a))
    rows: list[dict] = []
    for _, row in acct_view.iterrows():
        account = _clean(row.get("渠道账号"))
        if not account:
            continue
        rows.append(
            {
                "渠道": _clean(row.get("渠道")),
                "渠道账号": account,
                "aliases": sorted(aliases.get(account, set()) | {norm_alias(account)}),
                "运营人员": _clean(row.get("运营人员")),
            }
        )
    rows.sort(key=lambda r: (r["渠道账号"].upper(), r["渠道"] or "", r["运营人员"] or "", r["aliases"]))
    return rows


def snapshot_projection(snapshot: dict | None, exchange_month: str) -> list[dict]:
    """快照原始表 → 本批业务投影；缺当期人员列返回 []。"""
    if not snapshot:
        return []
    return business_projection(snapshot.get("header") or [], snapshot.get("rows") or [], exchange_month)


def _by_account(projection: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for row in projection:
        out[row["渠道账号"]].append(row)
    return out


def _alias_owners(projection: list[dict]) -> dict[str, set[str]]:
    owners: dict[str, set[str]] = defaultdict(set)
    for row in projection:
        for alias in row["aliases"]:
            owners[alias].add(row["渠道账号"])
    return owners


def projection_differences(live: list[dict], snap: list[dict], *, label_live="live", label_snap="snapshot") -> list[str]:
    """比较两份业务投影：账号集合、别名集合、渠道、当期运营人员。返回差异清单。"""
    problems: list[str] = []
    live_by, snap_by = _by_account(live), _by_account(snap)
    for name, group in [(label_live, live_by), (label_snap, snap_by)]:
        for acct, rows in group.items():
            if len(rows) > 1 and any(r != rows[0] for r in rows[1:]):
                problems.append(f"{name} 账号 {acct} 重复且渠道/人员/别名不一致")
    for acct in sorted(set(snap_by) - set(live_by)):
        problems.append(f"账号 {acct} 只在快照、不在 {label_live} 主表")
    for acct in sorted(set(live_by) - set(snap_by)):
        problems.append(f"账号 {acct} 在 {label_live} 主表、不在快照（快照过期）")
    for acct in sorted(set(live_by) & set(snap_by)):
        lv, sp = live_by[acct][0], snap_by[acct][0]
        for field in ("渠道", "运营人员"):
            if lv[field] != sp[field]:
                problems.append(f"账号 {acct} {field}: {label_live}={lv[field]!r} vs {label_snap}={sp[field]!r}")
        if lv["aliases"] != sp["aliases"]:
            only_live = sorted(set(lv["aliases"]) - set(sp["aliases"]))
            only_snap = sorted(set(sp["aliases"]) - set(lv["aliases"]))
            problems.append(f"账号 {acct} 别名不一致: {label_live}独有={only_live} {label_snap}独有={only_snap}")
    for name, proj in [(label_live, live), (label_snap, snap)]:
        for alias, owners in sorted(_alias_owners(proj).items()):
            if len(owners) > 1:
                problems.append(f"{name} 别名 {alias} 指向多个渠道账号: {sorted(owners)}")
    return problems


def master_dimension_problems(acct_view: pd.DataFrame | None, accounts) -> list[str]:
    """本批用到的账号在主表里的维度完整性（Tax/附加费口径）。"""
    if acct_view is None:
        return []
    wanted = {str(a).strip() for a in (accounts or []) if _clean(a)}
    if not wanted:
        return []
    problems: list[str] = []
    view = acct_view.copy()
    view["_acct"] = view["渠道账号"].map(_clean)
    for acct in sorted(wanted):
        rows = view.loc[view["_acct"] == acct]
        if rows.empty:
            problems.append(f"批次账号 {acct} 不在 live 渠道主表")
            continue
        channel = _clean(rows.iloc[0].get("渠道"))
        staff = _clean(rows.iloc[0].get("运营人员"))
        if channel is None:
            problems.append(f"账号 {acct} 渠道/平台为空")
        elif channel != AMAZON_CHANNEL:
            problems.append(f"账号 {acct} 渠道={channel!r}，Tax 业务账号应为 Amazon")
        if staff is None:
            problems.append(f"账号 {acct} 当期运营人员为空")
    return problems


def unknown_alias_candidates(
    values,
    *,
    known_accounts,
    known_aliases,
) -> list[dict]:
    """未知别名 → candidate 报告（**只报告，不写回主表**）。

    候选按「规范化后互相包含」给出提示，仅为人工快速定位；不自动选择、不自动写入。
    """
    known_accounts = {str(a).strip() for a in (known_accounts or []) if _clean(a)}
    known_alias_keys = {norm_alias(a) for a in (known_aliases or []) if _clean(a)}
    known_alias_keys |= {norm_alias(a) for a in known_accounts}
    out: list[dict] = []
    for raw in sorted({str(v).strip() for v in (values or []) if _clean(v)}):
        key = norm_alias(raw)
        if raw in known_accounts or key in known_alias_keys:
            continue
        hints = sorted(
            a for a in known_alias_keys if key and (key in a or a in key) and a != key
        )[:5]
        out.append(
            {
                "alias": raw,
                "normalized": key,
                "candidates": hints,
                "reason": "alias-not-in-master",
                "action": "needs_business_owner_approval",
            }
        )
    return out


def default_expected_source() -> dict:
    try:
        from channel_account_sync.fetch_sources import SHEET_ID  # noqa: WPS433

        return {"kind": "google_sheet", "spreadsheet_id": SHEET_ID}
    except Exception:  # pragma: no cover - 环境缺依赖时只校验 kind
        return {"kind": "google_sheet"}


def publish_gate_problems(
    *,
    exchange_month: str,
    acct_view: pd.DataFrame | None,
    df_explode: pd.DataFrame | None = None,
    snapshot: dict | None = None,
    snapshot_error: str | None = None,
    batch_accounts=None,
    batch_aliases=None,
    now: datetime | None = None,
    ttl_hours: float | None = DEFAULT_TTL_HOURS,
    expected_source: dict | None = None,
) -> MasterGateResult:
    """发布前主数据门禁：返回所有阻断问题与未知别名候选（不抛错，由调用方决定写前拒绝）。"""
    result = MasterGateResult()
    if snapshot_error:
        result.problems.append(f"渠道账号快照不可用: {snapshot_error}")
    if snapshot is None:
        if not snapshot_error:
            result.problems.append("渠道账号快照缺失，无法证明主数据来源与新鲜度")
    else:
        result.snapshot_meta = snapshot.get("snapshot")
        for problem in validate_snapshot(
            snapshot,
            exchange_month=exchange_month,
            now=now,
            ttl_hours=ttl_hours,
            expected_source=expected_source,
        ):
            result.problems.append(f"快照: {problem}")

    if acct_view is None or (hasattr(acct_view, "empty") and acct_view.empty):
        result.problems.append("live 渠道主表不可读/为空，禁止退回旧快照发布")
        return result

    result.live_projection = live_projection(acct_view, df_explode)
    result.snapshot_projection = snapshot_projection(snapshot, exchange_month)
    if snapshot is not None:
        if not result.snapshot_projection:
            result.problems.append(
                f"快照缺当期运营人员列（运营人员{exchange_month}），无法与 live 对照"
            )
        else:
            for problem in projection_differences(result.live_projection, result.snapshot_projection):
                result.problems.append(f"live≠snapshot: {problem}")

    result.problems.extend(master_dimension_problems(acct_view, batch_accounts))

    if batch_aliases is not None:
        result.unknown_alias_candidates = unknown_alias_candidates(
            batch_aliases,
            known_accounts={r["渠道账号"] for r in result.live_projection},
            known_aliases={a for r in result.live_projection for a in r["aliases"]},
        )
        if result.unknown_alias_candidates:
            result.problems.append(
                f"未知别名 {len(result.unknown_alias_candidates)} 个（仅候选报告，需业务负责人批准后维护主表）"
            )
    return result
