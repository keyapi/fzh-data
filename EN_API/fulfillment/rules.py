"""异常（蓝图 §8 结构）与下一行动（§8.1 十条 V1 规则）。

引擎 `classify_anomalies` 已产出 {level, kind, key, message}；本模块把它升级为 §8 结构
（severity/code/affected_qty/fact/impact/evidence/owner_role/recommended_action），
并补两条引擎未覆盖的规则：有计划无工单、DN 草稿停留。判定逻辑仍以引擎为准。
"""
from __future__ import annotations

from datetime import date

from item_shipment_status import is_active_doc, num, op_progress, parse_date

from .model import Anomaly

DEFAULT_STALL_DAYS = 14   # 在产工单最后一次真实报工超过 N 天 → 工序停滞

# kind（引擎口径）→ (code, owner_role, recommended_action, impact 模板)
RULE_MAP = {
    "已改单": ("AMENDED", "销售/系统", "关联后继单并排除原单", "不计入有效需求"),
    "已取消未发": ("CANCELLED_UNSHIPPED", "销售", "确认是否仍需交付或关单", "未发量滞留"),
    "死单": ("CLOSED_UNSHIPPED", "计划", "确认剩余量作废、重复或仍需交付", "客户承诺风险"),
    "无生产计划": ("NO_PRODUCTION_PLAN", "计划", "排产或确认库存交付", "不会进入生产"),
    "工单未开工": ("WORK_NOT_STARTED", "生产", "确认开工日期", "交期风险"),
    "工单状态未回写": ("WO_HEADER_LAG", "生产/系统", "修正回写或按工序卡展示", "状态误导"),
    "工序完成量超计划": ("OVER_PRODUCTION", "计划/生产", "确认补产或余量归属", "数量偏差"),
    "超出交付约定": ("LEAD_OVERDUE", "销售/计划", "评估交期并告知客户", "交期已过"),
    "疑似重复下单": ("DUP_ORDER_SUSPECT", "销售", "核实是否重复下单", "可能重复"),
    "有计划无工单": ("PLAN_NO_WORK_ORDER", "计划", "下达工单", "计划未落地"),
    "DN草稿停留": ("DN_DRAFT_STALL", "仓库", "审核、提交或取消草稿出库单", "出库未确认"),
    "交期逾期": ("DELIVERY_OVERDUE", "计划/销售", "确认能否按期发，否则调整客户交期", "交期已过"),
    "工序停滞": ("OP_STALL", "生产", "查瓶颈、缺料或异常，确认是否仍在推进", "生产停摆"),
}

_SEVERITY_ORDER = {"error": 0, "warn": 1, "info": 2}


def _index(so_rows, wos):
    by_so = {}
    for r in so_rows:
        by_so.setdefault(r["so"], []).append(r)
    by_wo = {w["name"]: w for w in wos}
    return by_so, by_wo


def _affected_qty(key, kind, by_so, by_wo):
    if "|" in key:
        return sum(num(r["qty"]) for so in key.split("|") for r in by_so.get(so, []))
    if key in by_so:
        return sum(num(r["open_qty"]) or num(r["qty"]) for r in by_so[key])
    if key in by_wo:
        w = by_wo[key]
        return max(0.0, num(w.get("produced_qty")))
    return 0.0


def build_anomalies(ctx, today=None, stall_days: int = DEFAULT_STALL_DAYS) -> list:
    so_rows, wos = ctx["so_rows"], ctx["wos"]
    today = today or date.today()
    by_so, by_wo = _index(so_rows, wos)
    out = []

    for a in ctx.get("anomalies") or []:
        code, owner, action, impact = RULE_MAP.get(
            a["kind"], ("OTHER", "系统", "人工核实", "待定"))
        out.append(Anomaly(
            severity=a["level"], code=code,
            affected_qty=_affected_qty(a.get("key", ""), a["kind"], by_so, by_wo),
            fact=a["message"], impact=impact, evidence=a.get("key", ""),
            owner_role=owner, recommended_action=action,
            so=a.get("key", "") if a.get("key", "") in by_so else "",
        ))

    # ── 补规则：有计划无工单（引擎未覆盖）──
    for r in so_rows:
        if r.get("voided") or r.get("cancelled") or num(r.get("open_qty")) <= 0:
            continue
        if not r.get("wos") and r.get("pps") and r.get("so_status") != "Closed":
            code, owner, action, impact = RULE_MAP["有计划无工单"]
            out.append(Anomaly(
                severity="warn", code=code, affected_qty=num(r["open_qty"]),
                fact=f"[有计划无工单] {r['so']} 未发 {num(r['open_qty']):g}, "
                     f"已有生产计划 {', '.join(p['pp'] for p in r['pps'])} 但未下达工单",
                impact=impact, evidence=r["so"], owner_role=owner,
                recommended_action=action, so=r["so"]))

    # ── 补规则：DN 草稿停留 ──
    for r in so_rows:
        if num(r.get("draft_dn")) <= 0:
            continue
        code, owner, action, impact = RULE_MAP["DN草稿停留"]
        out.append(Anomaly(
            severity="warn", code=code, affected_qty=num(r["draft_dn"]),
            fact=f"[DN草稿停留] {r['so']} 有 {num(r['draft_dn']):g} 件草稿出库未提交",
            impact=impact, evidence=r["so"], owner_role=owner,
            recommended_action=action, so=r["so"]))

    # ── 补规则：交期逾期（真实 SO 交期已过仍未发；与引擎「下单+3月」估算不同）──
    for r in so_rows:
        if r.get("voided") or r.get("cancelled") or num(r.get("open_qty")) <= 0:
            continue
        if r.get("so_status") == "Closed":       # 死单已单独报
            continue
        dd = parse_date(r.get("delivery_date"))
        if dd and dd < today:
            code, owner, action, impact = RULE_MAP["交期逾期"]
            out.append(Anomaly(
                severity="warn", code=code, affected_qty=num(r["open_qty"]),
                fact=f"[交期逾期] {r['so']} 交期 {r['delivery_date']} 已过，仍未发 "
                     f"{num(r['open_qty']):g} 件（{r.get('progress') or '-'}）",
                impact=impact, evidence=r["so"], owner_role=owner,
                recommended_action=action, so=r["so"]))

    # ── 补规则：工序停滞（在产工单最后一次真实报工超阈值）──
    for r in so_rows:
        for w in r.get("wos") or []:
            if not is_active_doc(w):
                continue
            p = op_progress(w, ctx["jc_map"].get(w["name"], []))
            if p["jc_count"] == 0:                       # 未开工由别处报
                continue
            if p["done_qty"] + 1e-6 >= num(w.get("qty")):  # 已完工
                continue
            last = parse_date(p["last_end"])
            if last and (today - last).days > stall_days:
                code, owner, action, impact = RULE_MAP["工序停滞"]
                out.append(Anomaly(
                    severity="warn", code=code, affected_qty=num(w.get("qty")),
                    fact=f"[工序停滞] {w['name']}（{r['so']}）自 {last.isoformat()} 起 "
                         f"{(today - last).days} 天无新报工，完成 {num(p['done_qty']):g}/"
                         f"{num(w.get('qty')):g}",
                    impact=impact, evidence=w["name"], owner_role=owner,
                    recommended_action=action, so=r["so"]))

    return sorted(out, key=lambda x: _SEVERITY_ORDER.get(x.severity, 9))


def next_actions(anomalies) -> dict:
    """按责任角色聚合下一行动（蓝图 §9.1「下一行动」行）。"""
    agg = {}
    for a in anomalies:
        if a.severity == "info":
            continue
        agg.setdefault(a.owner_role, 0)
        agg[a.owner_role] += 1
    return agg
