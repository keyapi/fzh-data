# -*- coding: utf-8 -*-
"""EN 开放 SO → 工厂交付管线（``in_production`` / ``finished_waiting_shipment``）。

口径（2026-10-27 工头确认）：

- SO 是**公司向绍兴工厂下的生产/交付单**，是上游管线，不是终端消费需求；
  **不能加到海外仓可用**，只能作为条件供给单独成层。
- ``customer`` 是分公司（CENTRADE / DANEEY / 波兰公司 / 美国FBA仓）；
  ``customer_item_code`` 是通途 SKU；``warehouse`` 是工厂仓；``delivery_date`` 是工厂计划交付日。
- 皮壳 ``PK#`` 前缀去掉即对应成品（EN 既有规则），标 ``conversion_assumed=true``。
- 到分公司还要头程/清关/上架：用假设提前期，``date_confidence=estimated``，不写 confirmed。
- 包材仓是包装物料，不是成品，单列不进口径。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

COVER_PREFIX = "PK#"
DELETED_PREFIXES = ("删除",)

CUSTOMER_BRANCH = {
    "CENTRADE": ("美东-CENTRADE", "finished"),
    "DANEEY": ("美中-FZH-DANEEY", "finished"),
    "波兰公司": ("波兰-FZHPoland-covers", "finished"),
    "美国FBA仓": (None, "fba_external"),
}

WAREHOUSE_STAGE = {
    "北京委外成品仓": ("outsourced_finished", "finished_waiting_shipment", True),
    "半成品仓": ("semi", "in_production", True),
    "成品仓": ("finished", "finished_waiting_shipment", True),
    "包材仓": ("packaging", "packaging_material", False),
    "仓库": ("unknown", "unattributed", False),
}

# 绍兴生产周期业务口径（用户 2026-10-27 确认）：下单 → 国外分公司能发货约 3 个月；
# 近期 PB 实测有提前约 2 周的情况，所以取 90 天 baseline、范围 75–90 天。
BASELINE_ORDER_TO_BRANCH_DAYS = 90
BASELINE_RANGE_DAYS = (75, 90)
# 春节：工厂放假约 1 个月 + 恢复产能约 1 个月 → 路径穿越停工窗口加 60 天缓冲。
SPRING_FESTIVAL_ANCHOR = date(2027, 2, 6)      # 2027 年春节
SPRING_FESTIVAL_SHUTDOWN_DAYS = 30
SPRING_FESTIVAL_RECOVERY_DAYS = 30
SPRING_FESTIVAL_BUFFER_DAYS = SPRING_FESTIVAL_SHUTDOWN_DAYS + SPRING_FESTIVAL_RECOVERY_DAYS
# 停工 1 月 + 恢复 1 月：锚点前后各 30 天为受影响窗口
SPRING_FESTIVAL_WINDOW_DAYS = 30


STAGE_ETA_ASSUMPTION_DAYS = 14   # 完工待发运 -> 到仓的假设值（发运/运输/入库），未实测


def festival_window(anchor: date = SPRING_FESTIVAL_ANCHOR) -> tuple[date, date]:
    """受影响窗口：锚点（春节）前 30 天 ~ 后 30 天。"""
    return (anchor - timedelta(days=SPRING_FESTIVAL_WINDOW_DAYS),
            anchor + timedelta(days=SPRING_FESTIVAL_WINDOW_DAYS))


def _legacy_month_applicable(delivery: date) -> bool:
    """2027 年以前的旧口径：生产窗口跨 1–2 月即算（保持历史报告可复现）。"""
    start = delivery - timedelta(days=BASELINE_ORDER_TO_BRANCH_DAYS)
    for year in (start.year, delivery.year):
        for month in (1, 2):
            window_start = date(year, month, 1)
            window_end = date(year, month + 1, 1) if month < 12 else date(year, 12, 31)
            if start <= window_end and delivery >= window_start:
                return True
    return False


def _path_applicable(delivery: date, anchor: date, *, include_branch: bool) -> bool:
    """路径 [交付日-90, 交付日(+90)] 是否与春节窗口相交。

    ``include_branch=True`` 覆盖「生产 + 发运」整条路径（默认）；
    ``False`` 只看生产段 [交付日-90, 交付日]。
    """
    start = delivery - timedelta(days=BASELINE_ORDER_TO_BRANCH_DAYS)
    end = delivery + timedelta(days=BASELINE_ORDER_TO_BRANCH_DAYS) if include_branch else delivery
    window_start, window_end = festival_window(anchor)
    return start <= window_end and end >= window_start


def _festival_applicable(delivery: date | None, anchor: date | None = None) -> bool:
    """逐行判定：2027 起按锚点整条路径；更早年份沿用旧 1–2 月口径。"""
    if delivery is None:
        return False
    if anchor is None and delivery.year < 2027:
        return _legacy_month_applicable(delivery)
    return _path_applicable(delivery, anchor or SPRING_FESTIVAL_ANCHOR, include_branch=True)


def spring_festival_status(delivery: date | None,
                           anchor: date | None = None) -> tuple[str, int]:
    """返回 (applicability, buffer_days)；无交付日时 applicability=unknown。"""
    if delivery is None:
        return "unknown", 0
    if _festival_applicable(delivery, anchor):
        return "applicable", SPRING_FESTIVAL_BUFFER_DAYS
    return "not_applicable", 0


def spring_festival_buffer(delivery: date | None) -> int:
    """兼容旧接口：applicable 时返回 60，否则 0。"""
    return spring_festival_status(delivery)[1]


def customer_branch(customer: str) -> tuple[str | None, str]:
    """客户 → (分公司仓, 角色)。任何 *FBA* 客户都属外部范围，不进分公司管线。"""
    name = str(customer or "").strip()
    if name in CUSTOMER_BRANCH:
        return CUSTOMER_BRANCH[name]
    if "FBA" in name.upper():
        return None, "fba_external"
    return None, "unknown"


def clean_sku(value) -> str | None:
    """去掉「删除」等标记前缀后的通途 SKU。"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    for prefix in DELETED_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text or None


def finished_item(item_code: str) -> tuple[str, bool]:
    """皮壳 ``PK#`` → 成品（1:1 假设）；返回 (成品编码, 是否假设转换)。"""
    text = str(item_code or "").strip()
    if text.startswith(COVER_PREFIX):
        return text[len(COVER_PREFIX):], True
    return text, False


def build_so_backlog(rows: pd.DataFrame, *, as_of: date,
                     order_to_branch_days: int = BASELINE_ORDER_TO_BRANCH_DAYS,
                     date_basis: str = "assumed_business_90d",
                     festival_anchor: date | None = None) -> pd.DataFrame:
    """开放 SO 行 → 管线行。返回列含阶段、分支仓、计划/预计日期与资格标记。"""
    if not len(rows):
        return pd.DataFrame(columns=["so", "customer", "branch_warehouse", "factory_warehouse",
                                     "item_code", "finished_item", "tongtool_sku", "stage", "quantity",
                                     "scheduled_delivery", "plan_based_branch_date",
                                     "estimated_branch_date",
                                     "date_confidence", "date_basis", "order_to_branch_days",
                                     "spring_festival_buffer_days",
                                     "spring_festival_applicability",
                                     "stage_eta_assumption_days", "conversion_assumed",
                                     "overdue", "role", "excluded_reason"])
    frame = rows.copy()
    frame["open_qty"] = pd.to_numeric(frame["open_qty"], errors="coerce").fillna(0.0)
    frame = frame[frame["open_qty"] > 0].copy()

    out = []
    for record in frame.itertuples(index=False):
        customer = str(getattr(record, "customer", "") or "")
        branch, customer_role = customer_branch(customer)
        warehouse = str(getattr(record, "warehouse", "") or "")
        role, stage, countable = "unknown", "unattributed", False
        for key, (role_value, stage_value, ok) in WAREHOUSE_STAGE.items():
            if key in warehouse:
                role, stage, countable = role_value, stage_value, ok
                break
        finished, assumed = finished_item(getattr(record, "item_code", ""))
        delivery = getattr(record, "delivery_date", None)
        scheduled = pd.to_datetime(delivery).date() if delivery else None
        applicability, festival = spring_festival_status(scheduled, anchor=festival_anchor)
        plan_based = (scheduled + timedelta(days=order_to_branch_days + festival)
                      if scheduled else None)
        # G4：已逾期的交付日不再往上加 90 天当“预计到仓”；无阶段证据时留 null + unknown
        if plan_based is None:
            estimated, basis = None, "unknown"
        elif scheduled < as_of:
            estimated, basis = None, "unknown"
        else:
            estimated, basis = plan_based, "plan_based"
        overdue = bool(scheduled and scheduled < as_of)
        excluded = ""
        if not countable:
            excluded = f"warehouse_role_{role}"
        elif customer_role == "fba_external":
            excluded = "fba_external_scope"
        elif branch is None:
            excluded = "branch_unmapped"
        out.append(dict(
            so=record.so, customer=customer, branch_warehouse=branch,
            factory_warehouse=warehouse,
            item_code=record.item_code, finished_item=finished,
            # 客户物料号通常是通途 SKU；没有就回退成品编码，不阻塞
            tongtool_sku=clean_sku(getattr(record, "customer_item_code", None)) or finished,
            tongtool_sku_basis=("customer_item_code"
                                if clean_sku(getattr(record, "customer_item_code", None))
                                else "item_code_fallback"),
            stage=stage, quantity=float(record.open_qty),
            scheduled_delivery=scheduled.isoformat() if scheduled else None,
            plan_based_branch_date=plan_based.isoformat() if plan_based else None,
            estimated_branch_date=estimated.isoformat() if estimated else None,
            date_confidence="estimated" if estimated else "unknown",
            date_basis=basis,
            order_to_branch_days=order_to_branch_days,
            spring_festival_buffer_days=festival,
            spring_festival_applicability=applicability,
            stage_eta_assumption_days=STAGE_ETA_ASSUMPTION_DAYS,
            conversion_assumed=bool(assumed), overdue=overdue,
            role=role, excluded_reason=excluded,
        ))
    return pd.DataFrame(out)


def summarize_backlog(frame: pd.DataFrame) -> dict:
    """汇总：可计入管线的量与按分公司/工厂仓/交付月/逾期拆分。"""
    counted = frame[frame["excluded_reason"] == ""]
    excluded = frame[frame["excluded_reason"] != ""]
    delivery = pd.to_datetime(counted["scheduled_delivery"], errors="coerce")
    return {
        "orders": int(counted["so"].nunique()),
        "lines": int(len(counted)),
        "quantity": round(float(counted["quantity"].sum()), 3),
        "overdue_quantity": round(float(counted.loc[counted["overdue"], "quantity"].sum()), 3),
        "by_customer": {k: round(float(v), 3) for k, v in
                        counted.groupby("customer")["quantity"].sum().items()},
        "by_branch": {str(k): round(float(v), 3) for k, v in
                      counted.groupby("branch_warehouse")["quantity"].sum().items()},
        "by_stage": {k: round(float(v), 3) for k, v in
                     counted.groupby("stage")["quantity"].sum().items()},
        "by_factory_warehouse": {str(k): round(float(v), 3) for k, v in
                                 counted.groupby("factory_warehouse")["quantity"].sum().items()},
        "by_delivery_month": {str(k): round(float(v), 3) for k, v in
                              counted.groupby(delivery.dt.strftime("%Y-%m")).quantity.sum().items()},
        "conversion_assumed_quantity": round(
            float(counted.loc[counted["conversion_assumed"], "quantity"].sum()), 3),
        "excluded": {k: round(float(v), 3) for k, v in
                     excluded.groupby("excluded_reason")["quantity"].sum().items()},
        "order_to_branch_days": BASELINE_ORDER_TO_BRANCH_DAYS,
        "order_to_branch_range_days": list(BASELINE_RANGE_DAYS),
        "spring_festival_buffer_days": SPRING_FESTIVAL_BUFFER_DAYS,
        "spring_festival": _festival_stats(frame, counted),
        "spring_festival_applicability": {k: round(float(v), 3) for k, v in
                                          counted.groupby("spring_festival_applicability")
                                          ["quantity"].sum().items()},
        "stage_eta_assumption_days": STAGE_ETA_ASSUMPTION_DAYS,
        "spring_festival_applied_lines": int((counted["spring_festival_buffer_days"] > 0).sum()),
        "spring_festival_applied_quantity": round(
            float(counted.loc[counted["spring_festival_buffer_days"] > 0, "quantity"].sum()), 3),
        "date_confidence": "estimated（工厂交付日 + 90 天业务口径 + 春节缓冲）；未实测",
        "date_basis": "assumed_business_90d（业务口径，不是统计结论）",
        "note": "上游管线，不计入海外仓可用；不得与预测需求相加",
    }


def _festival_stats(frame: pd.DataFrame, counted: pd.DataFrame) -> dict:
    """春节穿越统计：按 97 张开放 SO 的交付日与 90 天生产路径判定。

    同时给出「全部开放行」与「计入管线的行」两套计数，避免把 FBA/包材当成品。
    """
    window_start, window_end = festival_window()
    delivery = pd.to_datetime(frame["scheduled_delivery"], errors="coerce").dt.date

    def _counts(part: pd.DataFrame, delivery_series) -> dict:
        if not len(part):
            return dict(orders=0, lines=0, quantity=0.0)
        return dict(orders=int(part["so"].nunique()), lines=int(len(part)),
                    quantity=round(float(part["quantity"].sum()), 3))

    def full_path(d):
        return d is not None and _path_applicable(d, SPRING_FESTIVAL_ANCHOR, include_branch=True)

    def production_only(d):
        return d is not None and _path_applicable(d, SPRING_FESTIVAL_ANCHOR, include_branch=False)

    counted_delivery = pd.to_datetime(counted["scheduled_delivery"], errors="coerce").dt.date
    crossing_all = frame[[full_path(d) for d in delivery]]
    crossing_counted = counted[[full_path(d) for d in counted_delivery]]
    production_crossing = counted[[production_only(d) for d in counted_delivery]]
    monthly = {}
    if len(crossing_counted) and "scheduled_delivery" in crossing_counted.columns:
        monthly = (crossing_counted.assign(month=pd.to_datetime(
            crossing_counted["scheduled_delivery"], errors="coerce").dt.strftime("%Y-%m"))
            .groupby("month")["quantity"].sum().round(3).to_dict())
    return dict(
        anchor=SPRING_FESTIVAL_ANCHOR.isoformat(),
        window=[window_start.isoformat(), window_end.isoformat()],
        shutdown_days=SPRING_FESTIVAL_SHUTDOWN_DAYS,
        recovery_days=SPRING_FESTIVAL_RECOVERY_DAYS,
        buffer_days=SPRING_FESTIVAL_BUFFER_DAYS,
        rule="生产+发运路径 [交付日-90, 交付日+90] 与锚点±30 天窗口相交即加 60 天；"
             "另给只看生产段 [交付日-90, 交付日] 的对照",
        all_open_rows=_counts(frame, delivery),
        crossing_all_open=_counts(crossing_all, None),
        crossing_counted=_counts(crossing_counted, None),
        crossing_production_only=_counts(production_crossing, None),
        crossing_by_delivery_month=monthly,
        note="逐行 buffer 已写入 spring_festival_buffer_days；本统计只用于解释与催办，不改净额",
    )


def attach_to_pack(pack: pd.DataFrame, backlog: pd.DataFrame) -> pd.DataFrame:
    """把 SO 管线量按 (成品编码, 分公司仓) 贴到决策包；单独成列，不并入可用。"""
    counted = backlog[backlog["excluded_reason"] == ""].copy()
    if not len(counted):
        pack["so_pipeline_qty"] = 0.0
        return pack
    counted["quantity"] = pd.to_numeric(counted["quantity"], errors="coerce").fillna(0.0)
    counted["overdue_qty"] = counted["quantity"].where(counted["overdue"].astype(bool), 0.0)
    grouped = counted.groupby(["finished_item", "branch_warehouse"]).agg(
        so_pipeline_qty=("quantity", "sum"),
        so_overdue_qty=("overdue_qty", "sum"),
        so_next_delivery=("scheduled_delivery", "min"),
        so_est_branch_date=("estimated_branch_date", "min"),
    ).reset_index().rename(columns={"finished_item": "canonical_sku",
                                    "branch_warehouse": "canonical_warehouse"})
    return pack.merge(grouped, on=["canonical_sku", "canonical_warehouse"], how="left")


def summarize_raw(frame: pd.DataFrame) -> dict:
    """未做管线分类前的原始口径（全部开放行），用于和业务报数对账。"""
    if not len(frame):
        return {"orders": 0, "lines": 0, "quantity": 0.0, "overdue_quantity": 0.0}
    open_rows = frame[pd.to_numeric(frame["quantity"], errors="coerce").fillna(0) > 0].copy()
    delivery = pd.to_datetime(open_rows["scheduled_delivery"], errors="coerce")
    return {
        "orders": int(open_rows["so"].nunique()),
        "lines": int(len(open_rows)),
        "quantity": round(float(open_rows["quantity"].sum()), 3),
        "overdue_quantity": round(float(open_rows.loc[open_rows["overdue"].astype(bool),
                                                     "quantity"].sum()), 3),
        "by_customer": {str(k): round(float(v), 3) for k, v in
                        open_rows.groupby("customer")["quantity"].sum().items()},
        "by_factory_warehouse": {str(k): round(float(v), 3) for k, v in
                                 open_rows.groupby("factory_warehouse")["quantity"].sum().items()},
        "by_delivery_month": {str(k): round(float(v), 3) for k, v in
                              open_rows.groupby(delivery.dt.strftime("%Y-%m")).quantity.sum().items()},
    }
