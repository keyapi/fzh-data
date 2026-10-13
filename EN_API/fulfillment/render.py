"""渲染适配器：JSON（权威）/ 控制台 / Excel（蓝图 §9.3）。"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import item_shipment_status as iss
from openpyxl import Workbook

from .report import build_partitions, build_summary, headline


def to_dict(result) -> dict:
    """JSON 权威结果（蓝图 §9）—— 排除仅供内部的 ctx 原始层。"""
    return {
        "inputs": result.inputs_text,
        "summary": result.summary,
        "headline": headline(result),
        "resolutions": [asdict(r) for r in result.resolutions],
        "lines": [asdict(ln) for ln in result.lines],
        "anomalies": [asdict(a) for a in result.anomalies],
        "totals": result.totals,
        "partitions": result.partitions,
    }


def write_json(result, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_dict(result), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def render_console(result):
    iss.rule("查询范围")
    for r in result.resolutions:
        if r.miss_reason:
            print(f"  [未命中] {r.raw}（{r.kind}） — {r.miss_reason}")
        else:
            extra = "，登记物料 " + ", ".join(r.resolved_items) if r.kind == "customer_code" else ""
            print(f"  [命中]   {r.raw}（{r.kind}） → {len(r.hit_sos)} 张 SO / {len(r.hit_lines)} 行{extra}")

    print("\n  " + headline(result))

    iss.rule("业务摘要")
    s = result.summary
    for k, label in (("demand", "需求"), ("stage_dist", "阶段分布"),
                     ("risk", "风险"), ("availability", "预计可用"), ("next_actions", "下一行动")):
        if s.get(k):
            print(f"  {label}: {s[k]}")

    iss.rule(f"履约行 ({len(result.lines)} 行 / {len({l.so for l in result.lines})} 张 SO)")
    rows = []
    for ln in sorted(result.lines, key=lambda x: (x.delivery_date or "", x.so)):
        rows.append([ln.so, ln.item_code, ln.so_status, ln.delivery_date or "-",
                     iss.fmt_qty(ln.ordered_qty), iss.fmt_qty(ln.shipped_qty),
                     iss.fmt_qty(ln.open_qty), f"{ln.stage.stage} {ln.stage.substate}"])
    iss.print_table(["SO", "订单行物料", "SO状态", "交货日期", "订单量", "已发", "未发", "阶段"],
                    rows, aligns=["left", "left", "left", "left", "right", "right", "right", "left"])

    t = result.totals
    print(f"\n  订单量 {iss.fmt_qty(t.get('order_qty', 0))} = 有效 {iss.fmt_qty(t.get('valid_qty', 0))}"
          + (f" + 已改单(作废) {iss.fmt_qty(t['voided_qty'])}" if t.get("voided_qty") else "")
          + (f" + 已取消 {iss.fmt_qty(t['cancelled_qty'])}" if t.get("cancelled_qty") else ""))
    print(f"  已发 {iss.fmt_qty(t.get('shipped_qty', 0))} / 未发 {iss.fmt_qty(t.get('open_qty', 0))}")

    iss.rule(f"异常与下一行动 ({len(result.anomalies)})")
    if result.anomalies:
        for a in result.anomalies:
            print(f"  [{a.severity}] {a.fact}")
            print(f"          责任: {a.owner_role}｜影响: {a.impact}｜建议: {a.recommended_action}")
    else:
        print("  无")


def build_workbook(result, legacy: bool = False) -> Workbook:
    wb = Workbook()
    if legacy:
        (h1, r1), (h2, r2), (h3, r3) = iss.build_sheets(result.ctx)
        iss._write_sheet(wb, "订单发货状态", h1, r1, group_col=0, first=True,
                         number_cols=(16, 17, 18, 21, 27))
        iss._write_sheet(wb, "出库明细", h2, r2, group_col=0, number_cols=(13, 15, 16))
        iss._write_sheet(wb, "工单与工序", h3, r3, group_col=0, number_cols=(3, 4, 13))
        return wb

    # Sheet1 履约总览
    s = result.summary
    rows = [[k, v] for k, v in (
        ("查询", s["query"]), ("结论", headline(result)), ("需求", s["demand"]),
        ("阶段分布", s["stage_dist"]), ("风险", s["risk"]),
        ("预计可用", s["availability"]), ("下一行动", s["next_actions"]))]
    iss._write_sheet(wb, "履约总览", [("项目", 16), ("内容", 90)], rows, first=True)

    # Sheet2 订单行与阶段数量
    h2 = [("SO", 15), ("订单行ID", 13), ("物料", 27), ("SO状态", 18), ("交货日期", 12),
          ("订单量", 9), ("已发", 9), ("未发", 9), ("草稿出库", 10), ("阶段", 6),
          ("子状态", 22), ("对账", 7), ("命中输入", 24)]
    r2 = [[ln.so, ln.so_line_id, ln.item_code, ln.so_status, ln.delivery_date,
           ln.ordered_qty, ln.shipped_qty, ln.open_qty, ln.draft_qty,
           ln.stage.stage, ln.stage.substate,
           "OK" if ln.quantities.get("reconcile_ok") else "差异",
           ", ".join(ln.input_sources)] for ln in result.lines]
    iss._write_sheet(wb, "订单行与阶段数量", h2, r2, number_cols=(6, 7, 8, 9))

    # Sheet3 生产计划与工单
    h3 = [("工单", 15), ("WO状态", 12), ("WO数量", 9), ("WO已产", 9), ("关联SO", 15),
          ("物料", 27), ("工序进度", 44)]
    r3 = []
    for w in result.wos:
        r3.append([w["name"], w.get("status"), w.get("qty"), w.get("produced_qty"),
                   w.get("sales_order"), w.get("production_item"),
                   iss.progress_text([w], result.jc_map)])
    iss._write_sheet(wb, "生产计划与工单", h3, r3, number_cols=(3, 4))

    # Sheet4 工序卡明细
    h4 = [("工单", 15), ("工序", 20), ("工序卡", 34), ("状态", 12), ("批次量", 9),
          ("完工量", 10), ("完工时间", 20)]
    r4 = []
    for wo, jcs in result.jc_map.items():
        for j in jcs:
            r4.append([wo, j.get("operation"), j.get("name"), j.get("status"),
                       j.get("for_quantity"), j.get("total_completed_qty"),
                       str(j.get("actual_end_date") or "")[:19]])
    iss._write_sheet(wb, "工序卡明细", h4, r4, number_cols=(5, 6))

    # Sheet5 工厂出库明细
    h5 = [("SO", 15), ("SO行ID", 13), ("DN", 15), ("DN状态", 12), ("docstatus", 9),
          ("DN日期", 12), ("物料", 27), ("数量", 9), ("匹配方式", 10)]
    r5 = [[d["so"], d["so_line_id"], d["dn"], d["dn_status"], d["dn_docstatus"],
           d["dn_date"], d["item_code"], d["qty"], d["match_by"]] for d in result.dn_rows]
    iss._write_sheet(wb, "工厂出库明细", h5, r5, number_cols=(8,))

    # Sheet6 头程与国外仓（占位 —— 数据在钉钉表，V2 接入）
    iss._write_sheet(wb, "头程与国外仓", [("说明", 90)], [
        ["阶段 4–8（待头程/在途/到港/国外仓上架）不在 EN。",
         "数据在钉钉「2026年下单表 / 发货信息总表」，按 EN销售订单编号 匹配（蓝图 §5.1 V2）。"],
        ["当前不产出 —— 预留分区。"]])

    # Sheet7 事件时间线（占位）
    iss._write_sheet(wb, "事件时间线", [("说明", 90)], [["事实事件时间线待 V2/V3 接入头程后启用。"]])

    # Sheet8 异常与下一行动
    h8 = [("严重度", 9), ("代码", 22), ("影响数量", 10), ("事实", 60), ("影响", 18),
          ("责任角色", 12), ("建议行动", 34)]
    r8 = [[a.severity, a.code, a.affected_qty, a.fact, a.impact, a.owner_role,
           a.recommended_action] for a in result.anomalies]
    iss._write_sheet(wb, "异常与下一行动", h8, r8, number_cols=(3,))

    # Sheet9 未匹配与数据质量
    h9 = [("输入", 30), ("类型", 14), ("结果", 60)]
    r9 = []
    for r in result.resolutions:
        r9.append([r.raw, r.kind, r.miss_reason or f"命中 {len(r.hit_lines)} 行"])
    for ln in result.lines:
        if not ln.quantities.get("reconcile_ok"):
            r9.append([f"{ln.so}/{ln.so_line_id}", "对账", "有效需求 ≠ 已出库 + 未出库"])
    iss._write_sheet(wb, "未匹配与数据质量", h9, r9)
    return wb


def default_output_path(result, out_dir: Path, legacy: bool) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = "履约" if not legacy else "发货状态"
    return out_dir / f"{iss.slugify(result.inputs_text)}_{tag}_{ts}.xlsx"
