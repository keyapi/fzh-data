"""版本化默认配置：加载 / 校验 / 哈希 / 说明。

参数口径来自 `decision-defaults.md`（2026-11-24），默认值落在
`supply_copilot/config/defaults.json`。本模块只提供配置对象与校验，
**不改变任何决策行为**（`decide.py` / `refresh.py` 暂不消费）。

用法：
    from supply_copilot.config import load_config
    cfg = load_config("my-config.json")
    cfg["moq"]              # 取值（只读）
    cfg.config_hash         # 内容哈希（规范化 JSON 的 sha256）
    cfg.explain()           # 每个参数的值/来源/默认值/范围/作用域
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Optional

SCHEMA_VERSION = "supply-config/v1"
DEFAULTS_PATH = Path(__file__).resolve().parent / "config" / "defaults.json"

# 作用域层级字段（优先级：SKU 例外 > 分公司×商品分型 > 分公司 > 全局）
SCOPE_FIELDS = ("branch", "segment", "sku", "route", "supplier", "row", "period")
# SKU 例外必须同时带这些维度，避免跨仓/形态/UOM/期间串用
SKU_EXCEPTION_FIELDS = ("warehouse_pool", "physical_form", "uom")
# 条目包装器：{"value": ..., "scope": {...}, "expires_at": ...}
WRAPPER_KEYS = frozenset({
    "value", "scope", "effective_at", "expires_at", "reason", "evidence", "author", "approver",
})
FILE_TOP_KEYS = frozenset({"schema_version", "config_version", "scope", "values"})
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ConfigError(ValueError):
    """配置非法（结构 / 类型 / 范围 / 枚举 / 作用域 / 受保护项）。"""


# ---------------------------------------------------------------------------
# 参数规格树
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Node:
    """一个值节点的类型约束（可嵌套对象/列表）。"""

    kind: str  # bool|int|float|number|str|time|null|object|list
    description: str = ""
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    choices: Optional[tuple] = None
    nullable: bool = False
    fields: Optional[Mapping[str, "Node"]] = None
    required: tuple = ()
    items: Optional["Node"] = None


@dataclass(frozen=True)
class Param:
    key: str
    node: Node
    scopes: tuple = ()          # 允许的作用域层级；() = 仅全局
    unit: Optional[str] = None
    description: str = ""
    protected: bool = False


def _obj(fields: Mapping[str, Node], description: str = "", *, nullable: bool = False) -> Node:
    return Node("object", description, fields=dict(fields), required=tuple(fields),
                nullable=nullable)


def _num(description: str, *, lo=None, hi=None, unit=None, nullable=False, kind="number") -> Node:
    return Node(kind, description, minimum=lo, maximum=hi, nullable=nullable)


def _str(description: str, *, choices=None) -> Node:
    return Node("str", description, choices=tuple(choices) if choices else None)


def _int(description: str, *, lo=None, hi=None) -> Node:
    return Node("int", description, minimum=lo, maximum=hi)


def _float(description: str, *, lo=None, hi=None) -> Node:
    return Node("float", description, minimum=lo, maximum=hi)


def _bool(description: str, *, choices=None) -> Node:
    return Node("bool", description, choices=tuple(choices) if choices else None)


def _int_list(description: str, *, lo=None, hi=None) -> Node:
    return Node("list", description, items=Node("int", minimum=lo, maximum=hi))


def _str_list(description: str, *, choices=None) -> Node:
    return Node("list", description,
                items=Node("str", choices=tuple(choices) if choices else None))


PARAMS: dict[str, Param] = {p.key: p for p in [
    # --- 不可突破的硬约束（受保护，允许集合恒 {false}） ---
    Param("auto_order", _bool("禁止自动下单", choices=(False,)), protected=True,
          description="硬约束：永不自动下单"),
    Param("write_en_business", _bool("禁止写 EN 业务数据", choices=(False,)), protected=True,
          description="硬约束：只读 EN，不回写业务单据"),
    Param("allow_self_approval", _bool("禁止自批", choices=(False,)), protected=True,
          description="硬约束：提交者不得审核自己的提案"),
    Param("unknown_as_zero", _bool("未知不填 0", choices=(False,)), protected=True,
          description="硬约束：未知事实不得当 0"),

    # --- 分型 ---
    Param("segmentation_basis", _str("分型依据", choices=("frozen_abc_xyz", "unknown")),
          scopes=("global", "branch", "segment"),
          description="优先复用已冻结 ABC×XYZ→A/B/C/D；无有效映射标 unknown"),
    Param("abc_breaks", _obj({
        "sales_share": Node("list", "两有序分界（0–1）", items=_float("分界", lo=0.0, hi=1.0)),
    }), scopes=("branch", "segment"),
          description="ABC 按已证全渠道销量累计 80%/95% 分界"),
    Param("xyz_basis", _obj({
        "method": _str("XYZ 判定方法", choices=("trained_pattern_labels", "cv_thresholds")),
        "labels": _str_list("波动标签", choices=("smooth", "intermittent", "lumpy", "erratic", "n/a")),
    }), scopes=("branch", "segment"),
          description="XYZ 复用训练期 smooth/intermittent/lumpy 等标签；不新造 CV 阈值"),
    Param("service_beta_target", _obj({
        "A": _float("A 档 β 目标", lo=0.80, hi=0.99),
        "B": _float("B 档 β 目标", lo=0.80, hi=0.99),
        "C": _float("C 档 β 目标", lo=0.80, hi=0.99),
        "D": _float("D 档 β 目标", lo=0.80, hi=0.99),
    }), scopes=("branch", "segment"),
          description="β 目标（即时满足单位/有效需求单位）；不达标报缺口，禁自动调 q 凑目标"),
    Param("service_alpha_target", _obj({
        "A": _float("A 档 α 目标", lo=0.80, hi=0.99),
        "B": _float("B 档 α 目标", lo=0.80, hi=0.99),
        "C": _float("C 档 α 目标", lo=0.80, hi=0.99),
        "D": _float("D 档 α 目标", lo=0.80, hi=0.99),
    }, "周期满足率 α 目标（null = 不设硬门槛）", nullable=True),
          scopes=("branch", "segment"),
          description="有有效周期时辅报 α；不得由 β/q 换算"),
    Param("quantile_preset", _obj({
        "name": _str("预设名", choices=("balance",)),
        "A": _float("A 分位", lo=0.0, hi=1.0),
        "B": _float("B 分位", lo=0.0, hi=1.0),
        "C": _float("C 分位", lo=0.0, hi=1.0),
        "D": _float("D 分位", lo=0.0, hi=1.0),
    }), scopes=("branch", "segment", "sku"),
          description="balance：A q95、B q90、C q85、D q85；分型 unknown 则 HOLD"),
    Param("q95_downgrade_gate", _obj({
        "min_observations": _int("最少周评次数", lo=2, hi=4),
        "max_observations": _int("最多周评次数", lo=2, hi=4),
        "improvement_min": _float("改善下限", lo=0.0, hi=0.30),
        "improvement_max": _float("改善上限", lo=0.0, hi=0.30),
        "inventory_alert_ratio": _float("库存告警比", lo=1.1, hi=3.0),
        "max_steps": _int("一次最多降档", lo=1, hi=1),
    }), scopes=("branch", "segment"),
          description="仅触发降档提案，不自动降；未达 β 目标不能称等服务节省"),
    Param("hard_service_infeasible", _obj({
        "committed_beta": Node("float", "硬承诺 β（null = 不承诺）", minimum=0.80,
                               maximum=0.99, nullable=True),
        "grid": _obj({
            "beta": Node("list", "β 网格", items=_float("β", lo=0.0, hi=1.0)),
            "lead_days": _int_list("交期网格（天）", lo=1, hi=365),
            "review_days": _int_list("复核期网格（天）", lo=1, hi=90),
        }),
    }), scopes=("global", "segment"),
          description="不承诺硬 95%；并列展示服务—库存前沿"),
    Param("inventory_policy", _str("库存策略", choices=(
        "order_up_to_weekly", "rop", "proven_demand", "manual_observe")),
          scopes=("branch", "segment"),
          description="每周周期复核 order-up-to 参照；ROP 仅并列告警"),
    Param("review_period_R", _int("复核期 R（自然日）", lo=1, hi=30), unit="day",
          scopes=("branch", "segment"),
          description="R=7 自然日"),
    Param("protection_period", _str("保护期", choices=("L+R",)), unit="day",
          scopes=("branch", "segment"),
          description="保护期 = 交期 L + 复核期 R，随 L 重算"),
    Param("safety_stock_method", _str("安全库存方法", choices=(
        "protection_period_quantile", "empirical", "calibrated_quantile")),
          scopes=("segment",),
          description="累计保护期需求分位形成 S；SS=max(0,S−同窗期望需求)；不再叠固定安全天数"),
    Param("history_fallback", _obj({
        "short_history_months": _int("短史阈值（月）", lo=6, hi=24),
        "strategy": _str("短史策略", choices=("short_history_D", "analog_borrow")),
        "analog_borrow": _bool("允许已证类比借力"),
    }), scopes=("segment", "sku"),
          description="<12 月标短史 D；无类比只给已接订单下界+未知增量，不写补 0"),

    # --- 约束 ---
    Param("hard_budget", Node("number", "硬预算（null = 无截断）", minimum=0, nullable=True),
          scopes=("branch",), unit="CNY",
          description="null 无硬预算截断；缺成本金额为 unknown，不得因 null 取得采购授权"),
    Param("soft_budget_warning", _obj({
        "amount_ratio": _num("金额告警比", lo=1.1, hi=2.0),
        "qty_ratio": _num("数量告警比", lo=1.1, hi=2.0),
        "threshold_min": _float("阈值下限", lo=0.10, hi=1.00),
        "threshold_max": _float("阈值上限", lo=0.10, hi=1.00),
    }), scopes=("branch", "segment"),
          description="相对最近已批同范围周计划 >120% 告警；软提示不自动削量"),
    Param("moq", Node("int", "最小起订量（null = 无约束）", minimum=0, nullable=True),
          scopes=("branch", "sku", "supplier"), unit="unit",
          description="自有工厂无 MOQ（默认 null）；外购合同最低量才启用；不得当采购授权"),
    Param("order_multiple", Node("int", "订货倍数（null = 不凑整）", minimum=1, nullable=True),
          scopes=("branch", "sku", "supplier"), unit="unit",
          description="箱倍数 null，不强制凑箱；取整须保留原净需求与增量原因"),

    # --- 交期 / ETA ---
    Param("lead_time_quantile", _obj({
        "quantile": _float("L 分位", lo=0.50, hi=0.95),
        "calendar": _str("日历口径", choices=("natural_days", "business_days")),
        "basis": _str("统计口径", choices=("end_to_end", "segment_sum")),
    }), scopes=("branch", "route", "segment"),
          description="同路线/模式/目的可售仓的端到端 L p90；不叠加各段 p90"),
    Param("lead_time_evidence", _obj({
        "lookback_months": _int("回看月数", lo=6, hi=24),
        "min_samples": _int("最低样本数", lo=10, hi=50),
        "fallback_scenarios_days": _int_list("无证据情景交期（天）", lo=1, hi=365),
    }), scopes=("branch", "route"),
          description="最近 12 月 ≥20 条已完成可比交期才直接作经验 p90；不足先借同级证据，再无则用情景"),
    Param("eta_unknown", _bool("缺证据 ETA=unknown"),
          scopes=("global", "branch"),
          description="分段缺头程/到仓/上架证据则 ETA=unknown"),
    Param("po_on_time", _str("PO 准时口径", choices=("three_state_eta_le_need_date",)),
          scopes=("branch",),
          description="仅 ETA可售 ≤ 需要日 且数量/仓/UOM 已证才 true；比较口径受保护"),

    # --- 新鲜度 / 刷新 ---
    Param("inventory_refresh", _obj({
        "times_per_day": _int("每日刷新次数", lo=1, hi=24),
        "snapshot_at": Node("time", "快照时间 HH:MM"),
        "check_after": Node("time", "完成检查时间 HH:MM"),
        "timezone": _str("时区", choices=("Asia/Shanghai",)),
        "grace_minutes_min": _int("完成宽限下限（分）", lo=15, hi=120),
        "grace_minutes_max": _int("完成宽限上限（分）", lo=15, hi=120),
    }), scopes=("branch",),
          description="每日 05:17 快照，05:45 检查完成；库存龄用源快照业务时点"),
    Param("demand_recommend_refresh", _obj({
        "weekday": _str("刷新星期", choices=("mon", "tue", "wed", "thu", "fri", "sat", "sun")),
        "at": Node("time", "刷新时间 HH:MM"),
        "min_interval_days": _int("最短间隔（天）", lo=1, hi=14),
        "max_interval_days": _int("最长间隔（天）", lo=1, hi=14),
        "on_event": _bool("事件/审核前按需重算"),
    }), scopes=("branch", "segment"),
          description="每周一 06:00 刷新需求/建议；失败保留旧版并显式陈旧"),
    Param("inventory_age", _obj({
        "ok_max_hours": _num("可用上限（h）", lo=0, hi=24),
        "warn_max_hours": _num("条件上限（h）", lo=0, hi=72),
        "hold_after_hours": _num("HOLD 阈值（h）", lo=0, hi=72),
        "warn_hours_min": _num("警告下限（h）", lo=12, hi=24),
        "warn_hours_max": _num("警告上限（h）", lo=12, hi=24),
        "hold_hours_min": _num("HOLD 下限（h）", lo=24, hi=72),
        "hold_hours_max": _num("HOLD 上限（h）", lo=24, hi=72),
    }), scopes=("branch",), unit="hour",
          description="≤24h 可用；>24h WARN/条件；>48h HOLD"),
    Param("forecast_age", _obj({
        "ok_max_days": _num("可用上限（d）", lo=0, hi=7),
        "warn_max_days": _num("条件上限（d）", lo=0, hi=28),
        "hold_after_days": _num("HOLD 阈值（d）", lo=0, hi=28),
        "warn_days_min": _num("警告下限（d）", lo=1, hi=7),
        "warn_days_max": _num("警告上限（d）", lo=1, hi=7),
        "hold_days_min": _num("HOLD 下限（d）", lo=7, hi=28),
        "hold_days_max": _num("HOLD 上限（d）", lo=7, hi=28),
    }), scopes=("branch", "segment"), unit="day",
          description="≤7d 可用；>7d WARN/条件；>14d HOLD；同时检验目标期间"),
    Param("so_evidence_age", _obj({
        "ok_max_days": _num("可用上限（d）", lo=0, hi=7),
        "warn_max_days": _num("条件上限（d）", lo=0, hi=21),
        "hold_after_days": _num("HOLD 阈值（d）", lo=0, hi=21),
        "warn_days_min": _num("警告下限（d）", lo=1, hi=7),
        "warn_days_max": _num("警告上限（d）", lo=1, hi=7),
        "hold_days_min": _num("HOLD 下限（d）", lo=7, hi=21),
        "hold_days_max": _num("HOLD 上限（d）", lo=7, hi=21),
    }), scopes=("branch",), unit="day",
          description="≤7d 可用；>7d WARN/条件；>14d HOLD；证据龄按抽取覆盖时点"),
    Param("critical_unknown", _str("关键未知处理", choices=("hold",)),
          scopes=("global", "branch"),
          description="必要身份/库存/源期间/供需去重/可售 ETA 未闭合则 HOLD"),
    Param("readiness", _str("就绪状态", choices=("research", "conditional", "confirmed")),
          scopes=("branch",),
          description="警告最多“条件”；采购资格本试点恒 false"),

    # --- 身份 / 范围 ---
    Param("operator_scope", _obj({
        "branches": _str_list("授权分公司"),
        "segments": _str_list("授权商品分型"),
        "owners": _str_list("授权负责人"),
        "empty_scope": _str("空范围语义", choices=("deny",)),
    }), scopes=("branch", "segment"),
          description="O 仅在显式交集内读写提案；空范围=拒绝，禁止通配继承"),
    Param("reviewer_scope", _obj({
        "branches": _str_list("授权分公司"),
        "segments": _str_list("授权商品分型"),
        "empty_scope": _str("空范围语义", choices=("deny",)),
        "allow_self_approval": _bool("自批开关（恒 false）", choices=(False,)),
    }), scopes=("branch", "segment"),
          description="R 仅审核授权范围且 actor≠提交者；兼任也禁自批"),
    Param("system_manager_scope", _obj({
        "branches": _str_list("授权分公司"),
        "empty_scope": _str("空范围语义", choices=("deny",)),
    }), scopes=("global", "branch"),
          description="M 管配置/账号/审计；默认无全量业务读权与审批权"),

    # --- 试点 ---
    Param("pilot_scope", _obj({
        "branches": _str_list("试点分公司"),
        "row_list_ref": Node("str", "版本化行名单引用（数据不进仓库）", nullable=True),
        "frozen": _bool("名单冻结"),
    }), scopes=("branch", "sku"),
          description="冻结 USNJ 296 行源名单；逐行分合格/条件/HOLD/拒收"),
    Param("pilot_window", _obj({
        "shadow_weeks": _int("影子协作周数", lo=4, hi=8),
        "max_weeks": _int("最长周数", lo=4, hi=8),
        "checkpoints_weeks": _int_list("复核切点（周）", lo=1, hi=8),
        "weeks_min": _int("允许下限（周）", lo=4, hi=8),
        "weeks_max": _int("允许上限（周）", lo=4, hi=8),
    }), scopes=("branch",),
          description="6 周影子协作；第 2/4/6 周复核；不足延至 8 周"),
    Param("special_cny_owner_hold", _bool("特殊品/CNY/归属待定默认 HOLD"),
          scopes=("branch", "segment", "sku"),
          description="逐行隔离默认 HOLD；按证据逐行解除，不得一键全放行"),

    # --- 评估 ---
    Param("fva_window", _obj({
        "frozen_horizon_weeks": _int("冻结后滚动周数", lo=1, hi=12),
        "review_weeks": _int("累计复核周数", lo=1, hi=12),
        "min_mature_cutpoints": _int("最少成熟切点", lo=1, hi=12),
        "weeks_min": _int("允许下限（周）", lo=4, hi=12),
        "weeks_max": _int("允许上限（周）", lo=4, hi=12),
    }), scopes=("branch", "segment"),
          description="冻结后滚动 4 个完整周，累计 8 周复核；同 SKU/仓/UOM/跨度成对比较"),
    Param("fva_metric", _obj({
        "primary": _str("主报指标", choices=("fva_wape",)),
        "secondary": _str_list("辅报指标"),
        "frozen": _bool("指标冻结"),
        "allowed_extra": _str_list("可增补指标", choices=("mase", "pinball")),
    }), scopes=("global", "segment"),
          description="主报 FVA_WAPE=WAPE_auto−WAPE_final；不可事后换冠军指标"),
    Param("override_degradation", _obj({
        "consecutive_windows": _int("连续窗口数", lo=2, hi=4),
        "beta_drop_pct_points": _num("β 下降容忍（百分点）", lo=0, hi=5),
        "inventory_high_ratio": _num("库存偏高比", lo=1.1, hi=1.5),
        "beta_tolerance_min": _num("β 容忍下限", lo=0, hi=5),
        "beta_tolerance_max": _num("β 容忍上限", lo=0, hi=5),
        "inventory_ratio_min": _num("库存比下限", lo=0.10, hi=0.50),
        "inventory_ratio_max": _num("库存比上限", lo=0.10, hi=0.50),
    }), scopes=("branch", "segment"),
          description="连续 2 次成熟 4 周窗 FVA<0 提醒复核；不按个人小样本处罚"),

    # --- 写入 / 审批 ---
    Param("accept_auto", _str("接受自动草稿", choices=("explicit_accept_only",)),
          scopes=("branch", "row"),
          description="默认无改量草稿；运营须显式“接受”提交，仍异人审核"),
    Param("override_quantity", _obj({
        "require_total_delta": _bool("须说明总量/增量"),
        "require_reason": _bool("须说明原因"),
        "require_evidence": _bool("须附证据"),
        "require_period": _bool("须说明有效期间"),
        "allow_negative_final": _bool("允许负最终量（恒 false）", choices=(False,)),
    }), scopes=("row", "period"),
          description="改量须总量/增量/比例、原因、证据、有效期间；禁止负补货量"),
    Param("override_priority_threshold", _obj({
        "abs_ratio": _num("改动比例阈值", lo=0.10, hi=1.00),
        "ratio_min": _num("允许下限", lo=0.10, hi=1.00),
        "ratio_max": _num("允许上限", lo=0.10, hi=1.00),
        "zero_baseline_rule": _str("零基准规则", choices=("priority_review",)),
    }), scopes=("branch", "segment"),
          description="绝对比例 20% 或零基准新增 → 优先复核；任何改量仍须异人审核"),
    Param("event_only", _str("只报事件", choices=("event_without_quantity",)),
          scopes=("row", "segment"),
          description="只报事件不强迫估量，默认不改数字；同事件 ID 去重"),
    Param("period_override", _str("改期间", choices=("recompute_before_shift",)),
          scopes=("row", "segment"),
          description="改期间先重算，不平移总量；不可凭整期均分周"),
    Param("weekly_grain", _obj({
        "min_days": _int("最小粒度（天）", lo=7, hi=28),
        "allowed_days": _int_list("允许粒度（天）", lo=1, hi=28),
        "enabled": _bool("功能开关（试点期禁用）"),
    }), scopes=("branch", "segment"),
          description="最小 7 自然日，周一至周日；无周依据只看整期，功能未完成前禁用"),
    Param("weekly_freeze", _obj({
        "freeze_weekday": _str("冻结星期", choices=("mon", "tue", "wed", "thu", "fri")),
        "freeze_at": Node("time", "冻结时间 HH:MM"),
        "submit_by": _str("提交截止（星期_时:分）"),
        "review_deadline": _str("审核截止（星期_时:分）"),
        "timezone": _str("时区", choices=("Asia/Shanghai",)),
    }), scopes=("branch",),
          description="周三 12:00 冻结；周二 18:00 提交、周三 11:00 审核截止"),
    Param("reapproval", _obj({
        "validity_days": _int("审批有效期（天）", lo=1, hi=7),
        "validity_min": _int("允许下限（天）", lo=1, hi=7),
        "validity_max": _int("允许上限（天）", lo=1, hi=7),
        "on_input_version_change": _bool("输入源版本变更即重审"),
    }), scopes=("branch", "row"),
          description="任一数值/期间/归属/配置/输入源版本改变，或审批后 >7 天未采用 → 需重审"),
]}


# ---------------------------------------------------------------------------
# 校验原语
# ---------------------------------------------------------------------------

def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, (list, tuple)):
        return "list"
    return type(value).__name__


def _range_error(node: Node, value: float) -> Optional[str]:
    if node.minimum is not None and value < node.minimum:
        return f"{value} 小于允许下限 {node.minimum}"
    if node.maximum is not None and value > node.maximum:
        return f"{value} 大于允许上限 {node.maximum}"
    return None


def _validate(node: Node, value: Any, path: str, errors: list) -> Any:
    """校验并规范化一个值；错误 append 到 errors，返回 None 表示该值不可用。"""
    if value is None:
        if node.nullable or node.kind == "null":
            return None
        errors.append(f"{path}: 不允许为 null")
        return None
    if node.kind == "null":
        errors.append(f"{path}: 只允许 null")
        return None

    if node.kind == "bool":
        if not isinstance(value, bool):
            errors.append(f"{path}: 需要布尔值，得到 {_type_name(value)}")
            return None
        if node.choices is not None and value not in node.choices:
            errors.append(f"{path}: 受保护，只允许 {list(node.choices)}（得到 {value}）")
            return None
        return value

    if node.kind in ("int", "float", "number"):
        if node.kind == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                errors.append(f"{path}: 需要整数，得到 {_type_name(value)}")
                return None
        elif isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(f"{path}: 需要数值，得到 {_type_name(value)}")
            return None
        normalized = float(value) if node.kind == "float" else value
        msg = _range_error(node, normalized)
        if msg:
            errors.append(f"{path}: {msg}")
            return None
        return normalized

    if node.kind == "str":
        if not isinstance(value, str):
            errors.append(f"{path}: 需要字符串，得到 {_type_name(value)}")
            return None
        if node.choices is not None and value not in node.choices:
            errors.append(f"{path}: 只允许 {list(node.choices)}（得到 {value!r}）")
            return None
        return value

    if node.kind == "time":
        if not isinstance(value, str) or not _TIME_RE.match(value):
            errors.append(f"{path}: 需要 HH:MM 24 小时制时间，得到 {value!r}")
            return None
        return value

    if node.kind == "object":
        if not isinstance(value, dict):
            errors.append(f"{path}: 需要对象，得到 {_type_name(value)}")
            return None
        assert node.fields is not None
        unknown = sorted(k for k in value if k not in node.fields)
        if unknown:
            errors.append(f"{path}: 未知字段 {unknown}；允许 {sorted(node.fields)}")
        missing = [k for k in node.required if k not in value]
        if missing:
            errors.append(f"{path}: 缺少字段 {missing}")
        out = {}
        for name, child in node.fields.items():
            if name in value:
                out[name] = _validate(child, value[name], f"{path}.{name}", errors)
        return out

    if node.kind == "list":
        if not isinstance(value, (list, tuple)):
            errors.append(f"{path}: 需要列表，得到 {_type_name(value)}")
            return None
        out = []
        for index, item in enumerate(value):
            if node.choices is not None:
                if not isinstance(item, str) or item not in node.choices:
                    errors.append(f"{path}[{index}]: 只允许 {list(node.choices)}（得到 {item!r}）")
                    continue
            if node.items is None:
                out.append(item)
                continue
            normalized = _validate(node.items, item, f"{path}[{index}]", errors)
            if normalized is not None or item is None:
                out.append(normalized)
        return tuple(out)

    errors.append(f"{path}: 未知节点类型 {node.kind}")
    return None


# --- 跨字段不变式 -----------------------------------------------------------

def _all(*checks: Callable[[Mapping], list[str]]) -> Callable[[Mapping], list[str]]:
    def run(value):
        errors = []
        for check in checks:
            errors.extend(check(value))
        return errors
    return run


def _inv_age_triple(ok: str, warn: str, hold: str) -> Callable[[Mapping], list[str]]:
    """ok ≤ warn < hold：同一阈值可同时是“可用/条件”边界，HOLD 必须更晚。"""
    def check(value):
        errors = []
        ov, wv, hv = value.get(ok), value.get(warn), value.get(hold)
        if ov is not None and wv is not None and ov > wv:
            errors.append(f"{ok}={ov} 必须 ≤ {warn}={wv}")
        if wv is not None and hv is not None and not wv < hv:
            errors.append(f"{warn}={wv} 必须小于 {hold}={hv}")
        return errors
    return check


def _inv_ascending_list(field_name: str) -> Callable[[Mapping], list[str]]:
    def check(value):
        items = value.get(field_name) or ()
        return [f"{field_name}[{i}]={items[i]} 必须小于 {field_name}[{i + 1}]={items[i + 1]}"
                for i in range(len(items) - 1) if not items[i] < items[i + 1]]
    return check


def _inv_abc_breaks(value):
    bars = value.get("sales_share") or ()
    if len(bars) != 2:
        return [f"sales_share 必须是恰好两个分界（得到 {len(bars)} 个）"]
    if not (0.0 < bars[0] < bars[1] < 1.0):
        return [f"sales_share 必须是两个 0–1 之间严格递增的分界（得到 {list(bars)}）"]
    return []


def _inv_pair_lte(low: str, high: str) -> Callable[[Mapping], list[str]]:
    def check(value):
        a, b = value.get(low), value.get(high)
        if a is None or b is None or a <= b:
            return []
        return [f"{low}={a} 必须 ≤ {high}={b}"]
    return check


def _inv_quantile_choices(value):
    allowed = (0.85, 0.90, 0.95)
    return [f"{grade} 分位 {value[grade]} 不在 {list(allowed)}（新增分位须校准及新版本）"
            for grade in ("A", "B", "C", "D")
            if value.get(grade) is not None and value[grade] not in allowed]


def _inv_weekly_grain(value):
    days = value.get("allowed_days") or ()
    if not days or value.get("min_days") is None:
        return []
    errors = []
    if 7 not in days:
        errors.append(f"allowed_days 必须包含 7（得到 {list(days)}）")
    if value["min_days"] > min(days):
        errors.append(f"min_days={value['min_days']} 不能大于最小粒度 {min(days)}")
    return errors


def _inv_pilot_window(value):
    errors = _inv_ascending_list("checkpoints_weeks")(value)
    if value.get("shadow_weeks") is not None and value.get("max_weeks") is not None \
            and value["shadow_weeks"] > value["max_weeks"]:
        errors.append(f"shadow_weeks={value['shadow_weeks']} 必须 ≤ max_weeks={value['max_weeks']}")
    return errors


_INVARIANTS: dict[str, Callable[[Mapping], list[str]]] = {
    "abc_breaks": _inv_abc_breaks,
    "quantile_preset": _inv_quantile_choices,
    "q95_downgrade_gate": _all(_inv_pair_lte("improvement_min", "improvement_max"),
                               _inv_pair_lte("min_observations", "max_observations")),
    "soft_budget_warning": _inv_pair_lte("threshold_min", "threshold_max"),
    "inventory_age": _all(_inv_age_triple("ok_max_hours", "warn_max_hours", "hold_after_hours"),
                          _inv_pair_lte("warn_hours_min", "warn_hours_max"),
                          _inv_pair_lte("hold_hours_min", "hold_hours_max")),
    "forecast_age": _all(_inv_age_triple("ok_max_days", "warn_max_days", "hold_after_days"),
                         _inv_pair_lte("warn_days_min", "warn_days_max"),
                         _inv_pair_lte("hold_days_min", "hold_days_max")),
    "so_evidence_age": _all(_inv_age_triple("ok_max_days", "warn_max_days", "hold_after_days"),
                            _inv_pair_lte("warn_days_min", "warn_days_max"),
                            _inv_pair_lte("hold_days_min", "hold_days_max")),
    "lead_time_evidence": _inv_ascending_list("fallback_scenarios_days"),
    "pilot_window": _inv_pilot_window,
    "fva_window": _inv_pair_lte("frozen_horizon_weeks", "review_weeks"),
    "override_degradation": _all(_inv_pair_lte("beta_tolerance_min", "beta_tolerance_max"),
                                 _inv_pair_lte("inventory_ratio_min", "inventory_ratio_max")),
    "weekly_grain": _inv_weekly_grain,
    "reapproval": _inv_pair_lte("validity_min", "validity_max"),
}


def _run_invariants(values: Mapping, errors: list) -> None:
    for key, check in _INVARIANTS.items():
        if key not in values or values[key] is None:
            continue
        for msg in check(values[key]):
            errors.append(f"{key}: {msg}")


# ---------------------------------------------------------------------------
# 作用域
# ---------------------------------------------------------------------------

def scope_rank(scope: Mapping | None) -> int:
    """作用域优先级：SKU 例外 > 分公司×商品分型 > 分公司 > 全局。"""
    scope = scope or {}
    if "sku" in scope:
        return 3
    if "branch" in scope and "segment" in scope:
        return 2
    if "branch" in scope:
        return 1
    return 0


def _validate_scope(param: Param, scope: Mapping, base_scope: Mapping, path: str,
                    errors: list) -> Mapping:
    effective = dict(base_scope or {})
    effective.update(scope or {})
    allowed_keys = set(SCOPE_FIELDS) | set(SKU_EXCEPTION_FIELDS)
    unknown = sorted(k for k in effective if k not in allowed_keys)
    if unknown:
        errors.append(f"{path}.scope: 未知作用域字段 {unknown}；允许 {sorted(allowed_keys)}")
        return MappingProxyType({})
    if not effective:
        if "global" not in param.scopes and param.scopes:
            errors.append(f"{path}.scope: 该参数不能全局设置，须声明作用域 "
                          f"{list(param.scopes)}（不写作用域的条目只允许在默认层）")
        return MappingProxyType({})
    errors_before = len(errors)
    for name, value in effective.items():
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(f"{path}.scope.{name}: 不能为空")
        if name in SKU_EXCEPTION_FIELDS:
            if "sku" not in effective:
                errors.append(f"{path}.scope.{name}: 只在 SKU 例外（含 sku）里允许")
            continue
        if name == "period" and "sku" in effective:
            continue  # SKU 例外的期间维度
        if name not in param.scopes:
            errors.append(f"{path}.scope.{name}: 参数 {param.key} 不允许该作用域层级 "
                          f"（允许 {list(param.scopes) or ['global']}）")
    if "sku" in effective:
        missing = [k for k in SKU_EXCEPTION_FIELDS if k not in effective] + \
                  ([] if "period" in effective else ["period"])
        if missing:
            errors.append(f"{path}.scope: SKU 例外必须同时带仓/形态/UOM/期间，缺少 {missing}")
    return MappingProxyType(dict(sorted(effective.items()))) if len(errors) == errors_before \
        else MappingProxyType({})


# ---------------------------------------------------------------------------
# 冻结 / 解冻 / 哈希
# ---------------------------------------------------------------------------

def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _thaw(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(v) for v in value]
    return value


def _canonical_bytes(values: Mapping) -> bytes:
    payload = {"schema_version": SCHEMA_VERSION, "values": _thaw(values)}
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return text.encode("utf-8")


def _hash_values(values: Mapping) -> str:
    return hashlib.sha256(_canonical_bytes(values)).hexdigest()


def _validate_schema(version: Any, path: str, errors: list) -> None:
    if not isinstance(version, str):
        errors.append(f"{path}: 缺少 schema_version（应为 {SCHEMA_VERSION}）")
        return
    if version == SCHEMA_VERSION or version.startswith(SCHEMA_VERSION + "."):
        return
    if version.startswith("supply-config/"):
        errors.append(f"{path}: unsupported_schema: 需要 {SCHEMA_VERSION} 主版本（得到 {version}）")
        return
    errors.append(f"{path}: 无法识别的 schema_version {version!r}（应为 {SCHEMA_VERSION}）")


# ---------------------------------------------------------------------------
# 公开对象
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Config:
    """不可变的生效配置。"""

    schema_version: str
    config_version: Optional[str]
    values: Mapping[str, Any]
    sources: Mapping[str, str]      # default | file | override
    scopes: Mapping[str, Mapping]   # 文件层声明的作用域（默认层为空）
    defaulted: tuple[str, ...]
    path: Optional[str]
    config_hash: str

    def __getitem__(self, key: str) -> Any:
        return self.values[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def keys(self):
        return tuple(self.values)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "config_version": self.config_version,
            "values": _thaw(self.values),
        }

    def explain(self) -> list[dict]:
        _, defaults = _defaults()
        rows = []
        for key, param in PARAMS.items():
            node = param.node
            rows.append({
                "key": key,
                "value": _thaw(self.values[key]),
                "source": self.sources[key],
                "default": _thaw(defaults[key]),
                "scopes": list(param.scopes) or ["global"],
                "scope": _thaw(self.scopes.get(key, {})),
                "range": _range_text(node),
                "choices": list(node.choices) if node.choices is not None else None,
                "unit": param.unit,
                "nullable": node.nullable or node.kind == "null",
                "protected": param.protected,
                "description": param.description or node.description,
            })
        return rows


def _range_text(node: Node) -> str:
    if node.minimum is not None and node.maximum is not None:
        return f"{node.minimum}–{node.maximum}"
    if node.minimum is not None:
        return f"≥{node.minimum}"
    if node.maximum is not None:
        return f"≤{node.maximum}"
    return ""


def _load_json(path: Path) -> dict:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"无法读取配置文件 {path}: {exc}") from exc
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"配置文件不是合法 JSON（{path}）: {exc}") from exc
    if not isinstance(doc, dict):
        raise ConfigError(f"配置文件顶层必须是对象（{path}）")
    return doc


_DEFAULT_VALUES: Mapping[str, Any] = {}
_DEFAULT_CONFIG_VERSION: Optional[str] = None
_DEFAULTS_LOADED = False


def _defaults() -> tuple[Optional[str], Mapping[str, Any]]:
    """加载并校验内置默认（模块级缓存）。"""
    global _DEFAULT_VALUES, _DEFAULT_CONFIG_VERSION, _DEFAULTS_LOADED
    if _DEFAULTS_LOADED:
        return _DEFAULT_CONFIG_VERSION, _DEFAULT_VALUES
    doc = _load_json(DEFAULTS_PATH)
    errors: list[str] = []
    _validate_schema(doc.get("schema_version"), "defaults.json", errors)
    values = doc.get("values")
    if not isinstance(values, dict):
        errors.append("defaults.json: values 必须是对象")
        values = {}
    unknown = sorted(k for k in values if k not in PARAMS)
    if unknown:
        errors.append(f"defaults.json: 未知参数 {unknown}")
    normalized = {}
    for key, param in PARAMS.items():
        if key not in values:
            errors.append(f"defaults.json: 缺少参数 {key}")
            continue
        normalized[key] = _validate(param.node, values[key], key, errors)
    _run_invariants(normalized, errors)
    if errors:
        raise ConfigError("内置默认配置非法：\n- " + "\n- ".join(errors))
    _DEFAULT_VALUES = MappingProxyType(_freeze(normalized))
    _DEFAULT_CONFIG_VERSION = doc.get("config_version")
    _DEFAULTS_LOADED = True
    return _DEFAULT_CONFIG_VERSION, _DEFAULT_VALUES


def _suggest(key: str) -> str:
    lowered = {k.lower(): k for k in PARAMS}
    matches = difflib.get_close_matches(key.lower(), list(lowered), n=2, cutoff=0.6)
    return f"；是不是 {[lowered[m] for m in matches]}" if matches else ""


def _is_wrapper(raw: Any) -> bool:
    return isinstance(raw, dict) and bool(raw) and set(raw) <= WRAPPER_KEYS \
        and ("value" in raw or "scope" in raw)


def load_config(path: Any = None, overrides: Optional[Mapping] = None) -> Config:
    """加载配置。

    - `path=None`：只用内置默认（`config/defaults.json`）。
    - `path`：文件覆盖默认；未出现的参数记为 `defaulted`。
    - `overrides`：程序化覆盖（最高优先级，记 `override`），不做作用域声明。
    """
    default_version, defaults = _defaults()
    errors: list[str] = []
    file_values: dict[str, Any] = {}
    file_scopes: dict[str, Mapping] = {}
    config_version = default_version
    file_scope: Mapping = {}

    if path is not None:
        file_path = Path(path).expanduser()
        doc = _load_json(file_path)
        _validate_schema(doc.get("schema_version"), str(file_path), errors)
        extra = sorted(set(doc) - FILE_TOP_KEYS)
        if extra:
            errors.append(f"{file_path}: 未知顶层键 {extra}；允许 {sorted(FILE_TOP_KEYS)}")
        config_version = doc.get("config_version") or config_version
        if doc.get("config_version") is not None \
                and not isinstance(doc.get("config_version"), str):
            errors.append(f"{file_path}: config_version 必须是字符串")
        file_scope_raw = doc.get("scope") or {}
        if not isinstance(file_scope_raw, dict):
            errors.append(f"{file_path}: scope 必须是对象")
            file_scope_raw = {}
        file_scope = file_scope_raw
        raw_values = doc.get("values")
        if not isinstance(raw_values, dict):
            errors.append(f"{file_path}: values 必须是对象")
            raw_values = {}
        for key, raw in raw_values.items():
            param = PARAMS.get(key)
            if param is None:
                errors.append(f"{file_path}: 未知参数 {key}{_suggest(key)}")
                continue
            if param.protected:
                errors.append(f"{file_path}: {key} 是受保护硬约束，不允许通过配置修改")
                continue
            if _is_wrapper(raw):
                value = raw.get("value") if "value" in raw else None
                entry_scope = raw.get("scope") or {}
                if not isinstance(entry_scope, dict):
                    errors.append(f"{key}.scope: 必须是对象")
                    entry_scope = {}
                declared = _validate_scope(param, entry_scope, file_scope, key, errors)
            else:
                value = raw
                declared = _validate_scope(param, {}, file_scope, key, errors)
            normalized = _validate(param.node, value, key, errors)
            file_values[key] = normalized
            file_scopes[key] = declared

    override_keys = set()
    if overrides:
        if not isinstance(overrides, Mapping):
            errors.append("overrides: 必须是映射")
            overrides = {}
        for key, value in overrides.items():
            param = PARAMS.get(key)
            if param is None:
                errors.append(f"overrides: 未知参数 {key}{_suggest(key)}")
                continue
            if param.protected:
                errors.append(f"overrides: {key} 是受保护硬约束，不允许覆盖")
                continue
            file_values[key] = _validate(param.node, value, key, errors)
            file_scopes[key] = MappingProxyType({})
            override_keys.add(key)

    merged = dict(_thaw(defaults))
    sources = {key: "default" for key in PARAMS}
    for key, value in file_values.items():
        merged[key] = value
        sources[key] = "override" if key in override_keys else "file"
    _run_invariants(merged, errors)

    if errors:
        raise ConfigError("配置校验失败：\n- " + "\n- ".join(errors))

    freeze_sources = MappingProxyType(dict(sources))
    freeze_scopes = MappingProxyType(dict(file_scopes))
    defaulted = tuple(k for k in PARAMS if sources[k] == "default")
    return Config(
        schema_version=SCHEMA_VERSION,
        config_version=config_version,
        values=MappingProxyType(_freeze(merged)),
        sources=freeze_sources,
        scopes=freeze_scopes,
        defaulted=defaulted,
        path=str(Path(path).expanduser()) if path is not None else None,
        config_hash=_hash_values(merged),
    )
