"""统一履约查询的数据模型（蓝图 §2.3 / §3.1 / §4 / §8 / §9）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── 证据分层（蓝图 §4）──
KIND_FACT = "fact"            # 已提交单据或可验证事件
KIND_DERIVED = "derived"      # 由事实按稳定规则计算
KIND_ESTIMATE = "estimate"    # 对未来日期/状态的预测
KIND_ASSERTION = "assertion"  # 人工确认但暂无系统证据


@dataclass
class FieldValue:
    """每个展示值都带来源类别（蓝图 §4）。"""
    value: Any = None
    kind: str = KIND_FACT
    source: str = ""
    source_record: str = ""
    observed_at: str = ""
    confidence: str = ""

    def to_dict(self) -> dict:
        return {"value": self.value, "kind": self.kind, "source": self.source,
                "source_record": self.source_record, "observed_at": self.observed_at,
                "confidence": self.confidence}


@dataclass
class InputEntity:
    """一个用户输入（客户码 / EN 物料码）。"""
    raw: str
    kind: str = "auto"        # customer_code | item_code | auto


@dataclass
class EntityResolution:
    """逐输入的匹配结果 —— 蓝图 §2.2 禁止「先合成集合后丢失输入来源」。"""
    raw: str
    kind: str
    resolved_items: list = field(default_factory=list)   # 客户码登记在哪些物料上（仅客户码）
    hit_sos: list = field(default_factory=list)
    hit_lines: list = field(default_factory=list)         # so line_id
    miss_reason: str = ""                                 # 非空 = 未命中


@dataclass
class Anomaly:
    """异常（蓝图 §8）。"""
    severity: str             # error | warn | info
    code: str                 # 机器码，见 rules.CODE_*
    affected_qty: float
    fact: str
    impact: str
    evidence: str
    owner_role: str
    recommended_action: str
    so: str = ""


@dataclass
class StageResult:
    """阶段 0–3（蓝图 §3）。"""
    stage: int
    substate: str
    evidence: list = field(default_factory=list)          # list[FieldValue]


@dataclass
class FulfillmentLine:
    """一条履约行 —— 粒度 = Sales Order Item × 需求物料（蓝图 §2.1）。"""
    so: str
    so_line_id: str
    item_code: str
    item_name: str
    customer: str
    company: str
    so_status: str
    so_docstatus: int
    delivery_date: str
    ordered_qty: float
    shipped_qty: float
    open_qty: float
    draft_qty: float
    progress: str
    quantities: dict = field(default_factory=dict)
    stage: StageResult = None
    anomalies: list = field(default_factory=list)          # list[Anomaly]
    input_sources: list = field(default_factory=list)      # 命中本行的输入 raw 列表
    kit: dict = field(default_factory=dict)                # 整单齐套（opt-in scope=full_order_kit）


@dataclass
class FulfillmentQueryResult:
    """统一查询结果（蓝图 §9）。"""
    inputs_text: str = ""
    resolutions: list = field(default_factory=list)        # list[EntityResolution]
    lines: list = field(default_factory=list)              # list[FulfillmentLine]
    anomalies: list = field(default_factory=list)          # list[Anomaly]
    totals: dict = field(default_factory=dict)
    summary: dict = field(default_factory=dict)            # 蓝图 §9.1
    partitions: dict = field(default_factory=dict)         # 蓝图 §9.2
    # 事实层原始数据（供渲染/取证，不重复计算）
    dn_rows: list = field(default_factory=list)
    wos: list = field(default_factory=list)
    jc_map: dict = field(default_factory=dict)
    pp_rows: list = field(default_factory=list)
    item_master: dict = field(default_factory=dict)
    master_items: list = field(default_factory=list)
    ctx: dict = field(default_factory=dict)                # 引擎 ctx（供 --legacy-sheets 复刻旧 3 Sheet）
    empty: bool = False
