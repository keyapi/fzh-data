# -*- coding: utf-8 -*-
"""盈利审计产出：对账闸门 + JSON + Excel 证据簿 + 管理摘要（U7 / R25–R27）。

原则：
- **闸门不过就不给管理结论**（fail closed）；诊断文件照出，但结论写"已阻断"。
- 输出只写本地 `out/`（gitignore），**绝不回写 Google Sheet / EN**。
- 技术修正 / 财务口径 / 主数据缺口 **三份清单分开**。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from tongtool_order_cost.profitability_audit import (
    Finding,
    MetricRecord,
    OWNER_FINANCE,
    OWNER_MASTER,
    OWNER_TECH,
    summarize_findings,
)

# 必需工作表（顺序即写入顺序）
REQUIRED_SHEETS = [
    "00_管理摘要", "01_指标口径", "02_数据源清单", "03_数量对账", "04_收入利润对账",
    "05_产品成本瀑布", "06_运费瀑布", "07_利润倒挂", "08_产品成本异常", "09_运费异常",
    "10_汇率税费异常", "11_FBA非FBA", "12_仓库账号渠道", "13_特殊规则事件",
    "14_行级血缘", "15_未匹配失败排除", "16_决策清单",
]

# 对账/复现阈值
CURRENCY_TOL = 0.01        # 单分区
WHOLE_MONTH_TOL = 0.10     # 全月取整
RATE_TOL = 0.0001


@dataclass
class GateResult:
    name: str
    passed: bool
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AuditReport:
    run_id: str
    created_at: str
    sources: list[dict] = field(default_factory=list)
    metrics: list[dict] = field(default_factory=list)
    reconciliation: dict[str, Any] = field(default_factory=dict)
    findings: list[dict] = field(default_factory=list)
    cohorts: dict[str, list[dict]] = field(default_factory=dict)
    gates: list[dict] = field(default_factory=list)
    conclusions_blocked: bool = False
    questions: dict[str, str] = field(default_factory=dict)
    decision_lists: dict[str, list[dict]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# 对账闸门
# ---------------------------------------------------------------------------


def reconcile_gates(
    *,
    row_conservation: dict,
    revenue_ordinary: float,
    cost_ordinary: float,
    profit_ordinary: float,
    reported_profit_ordinary: float,
    currency_tol: float = CURRENCY_TOL,
    whole_month_tol: float = WHOLE_MONTH_TOL,
) -> list[GateResult]:
    """行守恒 + 利润恒等式两关；不过则阻断管理结论。"""
    gates: list[GateResult] = []
    gates.append(GateResult(
        "row_conservation",
        bool(row_conservation.get("closes")),
        f"input={row_conservation.get('input')} "
        f"matched+unmatched+failed+excluded="
        f"{row_conservation.get('matched',0)+row_conservation.get('unmatched',0)+row_conservation.get('failed',0)+row_conservation.get('excluded',0)}",
    ))
    derived = revenue_ordinary - cost_ordinary
    diff = abs(derived - profit_ordinary)
    gates.append(GateResult(
        "profit_identity",
        diff <= currency_tol,
        f"售价*汇率-订单总成本={derived:.2f} vs 订单利润={profit_ordinary:.2f} diff={diff:.4f}",
    ))
    diff2 = abs(profit_ordinary - reported_profit_ordinary)
    gates.append(GateResult(
        "reported_profit_match",
        diff2 <= whole_month_tol,
        f"复算={profit_ordinary:.2f} vs 表内={reported_profit_ordinary:.2f} diff={diff2:.4f}",
    ))
    return gates


def build_report(
    *,
    run_id: str,
    sources: Sequence[dict] = (),
    metrics: Sequence[MetricRecord] = (),
    row_conservation: dict | None = None,
    findings: Sequence[Finding] = (),
    cohorts: dict[str, list[dict]] | None = None,
    gates: Sequence[GateResult] = (),
    questions: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
    now: str | None = None,
) -> AuditReport:
    findings = list(findings)
    blocked = any(not g.passed for g in gates) if gates else True
    decision = _split_decisions(findings)
    return AuditReport(
        run_id=run_id,
        created_at=now or datetime.now().isoformat(timespec="seconds"),
        sources=list(sources),
        metrics=[m.to_dict() if isinstance(m, MetricRecord) else m for m in metrics],
        reconciliation={**(row_conservation or {}), **(extra or {})},
        findings=[f.to_dict() if isinstance(f, Finding) else f for f in findings],
        cohorts=cohorts or {},
        gates=[g.to_dict() for g in gates],
        conclusions_blocked=blocked,
        questions=questions or {},
        decision_lists=decision,
    )


def _split_decisions(findings: Sequence[Finding]) -> dict[str, list[dict]]:
    """只有**需要处置**的发现进决策清单；`severity=info` 的常态项不进。"""
    out: dict[str, list[dict]] = {OWNER_TECH: [], OWNER_FINANCE: [], OWNER_MASTER: []}
    for f in findings:
        if getattr(f, "severity", "") == "info":
            continue
        owner = f.decision_owner if f.decision_owner in out else OWNER_TECH
        out[owner].append(f.to_dict())
    return out


# ---------------------------------------------------------------------------
# 写出
# ---------------------------------------------------------------------------


def new_run_dir(root: Path | str, label: str, *, now: datetime | None = None) -> Path:
    """永远新建**带时间戳**目录，绝不覆盖历史产出。"""
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    path = Path(root) / f"{label}_{stamp}"
    if path.exists():
        raise FileExistsError(f"输出目录已存在（拒绝覆盖）: {path}")
    path.mkdir(parents=True, exist_ok=False)
    return path


def write_json(report: AuditReport, path: Path | str) -> Path:
    import json

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _df(rows: Sequence[dict]) -> pd.DataFrame:
    return pd.DataFrame(list(rows)) if rows else pd.DataFrame()


def build_sheets(report: AuditReport) -> dict[str, pd.DataFrame]:
    """把报告摊成 17 张表，供 Excel 写入与行数对账。"""
    q = report.questions
    summary = [
        {"问题": "1", "结论": q.get("product_cost", ""), "状态": "已阻断" if report.conclusions_blocked else "可给结论"},
        {"问题": "2", "结论": q.get("freight", ""), "状态": "已阻断" if report.conclusions_blocked else "可给结论"},
        {"问题": "3", "结论": q.get("profit_inversion", ""), "状态": "已阻断" if report.conclusions_blocked else "可给结论"},
    ]
    sheets: dict[str, pd.DataFrame] = {
        "00_管理摘要": pd.DataFrame(summary),
        "01_指标口径": _df(report.metrics),
        "02_数据源清单": _df(report.sources),
        "03_数量对账": pd.DataFrame([report.reconciliation.get("conservation", {})]),
        "04_收入利润对账": pd.DataFrame([{
            k: v for k, v in report.reconciliation.items() if not isinstance(v, (list, dict))
        }]),
        "05_产品成本瀑布": _df(report.cohorts.get("product_cost_waterfall", [])),
        "06_运费瀑布": _df(report.cohorts.get("freight_waterfall", [])),
        "07_利润倒挂": _df([f for f in report.findings if f.get("category") == "profit_inversion"]),
        "08_产品成本异常": _df([f for f in report.findings if str(f.get("category", "")).startswith("cost_")]),
        "09_运费异常": _df([f for f in report.findings if str(f.get("category", "")).startswith("freight_")]),
        "10_汇率税费异常": _df([f for f in report.findings if "column_all_zero" in str(f.get("category", ""))
                              or str(f.get("category", "")).startswith("profit_track")]),
        "11_FBA非FBA": _df(report.cohorts.get("fba_scope", [])),
        "12_仓库账号渠道": _df(report.cohorts.get("by_account", [])),
        "13_特殊规则事件": _df(report.cohorts.get("rule_events", [])),
        "14_行级血缘": _df(report.cohorts.get("lineage", [])),
        "15_未匹配失败排除": _df(report.cohorts.get("exceptions", [])),
        "16_决策清单": _df([
            {**d, "owner": owner}
            for owner, items in report.decision_lists.items()
            for d in items
        ]),
    }
    missing = [s for s in REQUIRED_SHEETS if s not in sheets]
    if missing:
        raise ValueError(f"缺少必需工作表: {missing}")
    return sheets


def write_workbook(report: AuditReport, path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sheets = build_sheets(report)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name in REQUIRED_SHEETS:
            sheets[name].to_excel(writer, sheet_name=name, index=False)
    return path


def render_memo(report: AuditReport) -> str:
    q = report.questions
    lines = [f"# 2026-07 通途订单盈利审计（管理摘要）", ""]
    lines.append(f"- run_id: `{report.run_id}`  （生成于 {report.created_at}）")
    lines.append(f"- 结论状态: **{'已阻断（对账未过）' if report.conclusions_blocked else '可给结论'}**")
    lines.append("")
    lines.append("## 三个问题")
    for i, key in enumerate(("product_cost", "freight", "profit_inversion"), start=1):
        lines.append(f"{i}. {q.get(key, '（未复现）')}")
    lines.append("")
    lines.append("## 对账闸门")
    for g in report.gates:
        lines.append(f"- {'✅' if g.get('passed') else '❌'} {g.get('name')}: {g.get('detail')}")
    lines.append("")
    lines.append("## 决策清单（技术 / 财务 / 主数据）")
    for owner, items in report.decision_lists.items():
        lines.append(f"- **{owner}**: {len(items)} 条")
    return "\n".join(lines) + "\n"


def write_memo(report: AuditReport, path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_memo(report), encoding="utf-8")
    return path


def write_all(report: AuditReport, out_dir: Path | str) -> dict[str, str]:
    out_dir = Path(out_dir)
    return {
        "json": str(write_json(report, out_dir / "audit.json")),
        "xlsx": str(write_workbook(report, out_dir / "audit.xlsx")),
        "memo": str(write_memo(report, out_dir / "管理摘要.md")),
    }


def summarize_findings_for_report(findings: Sequence[Finding]) -> dict[str, dict]:
    return summarize_findings(findings)
