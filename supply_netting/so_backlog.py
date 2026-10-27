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

DEFAULT_TRANSIT_DAYS = 45   # 假设值：出厂 → 分公司可上架；未实测，标 estimated


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
                     transit_days: int = DEFAULT_TRANSIT_DAYS) -> pd.DataFrame:
    """开放 SO 行 → 管线行。返回列含阶段、分支仓、计划/预计日期与资格标记。"""
    if not len(rows):
        return pd.DataFrame(columns=["so", "customer", "branch_warehouse", "factory_warehouse",
                                     "item_code", "finished_item", "tongtool_sku", "stage", "quantity",
                                     "scheduled_delivery", "estimated_branch_date",
                                     "date_confidence", "conversion_assumed", "overdue",
                                     "role", "excluded_reason"])
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
        estimated = scheduled + timedelta(days=transit_days) if scheduled else None
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
            tongtool_sku=clean_sku(getattr(record, "customer_item_code", None)),
            stage=stage, quantity=float(record.open_qty),
            scheduled_delivery=scheduled.isoformat() if scheduled else None,
            estimated_branch_date=estimated.isoformat() if estimated else None,
            date_confidence="estimated" if scheduled else "unknown",
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
        "transit_days_assumed": DEFAULT_TRANSIT_DAYS,
        "date_confidence": "estimated（工厂交付日 + 假设提前期）；未实测",
        "note": "上游管线，不计入海外仓可用；不得与预测需求相加",
    }


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
