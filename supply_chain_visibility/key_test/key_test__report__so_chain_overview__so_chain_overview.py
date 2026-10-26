# -*- coding: utf-8 -*-
"""SO Chain Overview report; query joins live in the permission-aware service."""
import frappe
from frappe import _
from frappe.utils import getdate, today

from key_test.supply_query import get_report_data

filters = [
    {"fieldname": "customer", "label": _("客户"), "fieldtype": "Link", "options": "Customer"},
    {"fieldname": "from_date", "label": _("SO下单日期从"), "fieldtype": "Date"},
    {"fieldname": "to_date", "label": _("SO下单日期至"), "fieldtype": "Date"},
    {"fieldname": "sales_order", "label": _("销售订单"), "fieldtype": "Link", "options": "Sales Order"},
    {"fieldname": "delivery_note", "label": _("指定出库单"), "fieldtype": "Link", "options": "Delivery Note"},
    {"fieldname": "item_code", "label": _("物料"), "fieldtype": "Link", "options": "Item"},
    {"fieldname": "customer_item_code", "label": _("客户物料号"), "fieldtype": "Data"},
    {"fieldname": "warehouse", "label": _("SO行交货仓"), "fieldtype": "Link", "options": "Warehouse"},
    {"fieldname": "dn_from_date", "label": _("DN过账日期从"), "fieldtype": "Date"},
    {"fieldname": "dn_to_date", "label": _("DN过账日期至"), "fieldtype": "Date"},
    {"fieldname": "only_overdue", "label": _("只看交期已过"), "fieldtype": "Check"},
]

COLS = [
    ("Sales Order", "so", "Link", "Sales Order", 120),
    (_("客户"), "customer", "Data", None, 150),
    (_("物料"), "item_code", "Link", "Item", 200),
    (_("客户物料号"), "customer_item_code", "Data", None, 160),
    (_("单位"), "uom", "Link", "UOM", 70),
    (_("交货日期"), "delivery_date", "Date", None, 95),
    (_("订单量"), "qty", "Float", None, 80),
    (_("SO全周期已发"), "shipped", "Float", None, 105),
    (_("所选DN/日期净发量"), "selected_dn_qty", "Float", None, 110),
    (_("未发"), "open_qty", "Float", None, 80),
    (_("阶段"), "stage_txt", "Data", None, 130),
    (_("工单数"), "wo_n", "Int", None, 70),
    (_("菲号数"), "tn_n", "Int", None, 70),
    (_("异常"), "flags", "Data", None, 200),
]


def _columns():
    return [{"label": label, "fieldname": fieldname, "fieldtype": fieldtype,
             "options": options, "width": width}
            for label, fieldname, fieldtype, options, width in COLS]


def execute(filters=None):
    filters = frappe._dict(filters or {})
    rows, ship_map, selected_map, line_wo, line_tn, _visibility = get_report_data(filters)

    tday = getdate(today())
    data, stages = [], {}
    n_overdue = n_dead = 0
    for row in rows:
        shipped = (round(float(ship_map.get(row.so_line, 0) or 0), 3)
                   if ship_map is not None else None)
        has_dn_selection = bool(filters.get("delivery_note") or filters.get("dn_from_date") or filters.get("dn_to_date"))
        selected_dn_qty = (
            round(float(selected_map.get(row.so_line, 0) or 0), 3)
            if has_dn_selection and selected_map is not None else None
        )
        open_qty = round(float(row.open_qty or 0), 3) if shipped is not None else None
        unit_known = bool(row.uom)
        shipped_unit_mismatch = row.so_line in _visibility.get("shipped_unit_mismatch_lines", set())
        selected_unit_mismatch = row.so_line in _visibility.get("selected_unit_mismatch_lines", set())
        if shipped_unit_mismatch:
            shipped = None
        if not unit_known:
            shipped = selected_dn_qty = open_qty = None
        elif shipped_unit_mismatch:
            open_qty = None
        if selected_unit_mismatch:
            selected_dn_qty = None
        flags = []
        if row.so_status == "Closed":
            stage, sub = 3, _("Closed未发(死单)")
            flags.append(_("死单"))
            if shipped is None:
                sub = _("Closed，出库信息不可见")
        elif not unit_known:
            stage, sub = 0, _("订单单位未知")
        elif shipped_unit_mismatch:
            stage, sub = 0, _("DN单位与SO单位不一致")
        elif shipped is None:
            stage, sub = 0, _("数量/出库信息不可见")
        elif shipped + 1e-6 >= float(row.qty or 0):
            stage, sub = 3, _("已出库完成")
        elif line_wo is None:
            stage, sub = 0, _("生产信息不可见")
        elif not line_wo.get(row.so_line):
            stage, sub = 1, _("未排产(无工单)")
            flags.append(_("无工单"))
        else:
            stage, sub = 2, _("生产中/待发")
        due_date = row.delivery_date and getdate(row.delivery_date)
        if due_date and due_date < tday and row.so_status != "Closed":
            n_overdue += 1
            flags.append(_("交期已过"))
        if line_wo is None:
            flags.append(_("工单/计划信息无权限，数量未知"))
        if line_tn is None:
            flags.append(_("菲号信息无权限，数量未知"))
        if ship_map is None:
            flags.append(_("出库信息无权限，已发量未知"))
        if shipped_unit_mismatch:
            flags.append(_("DN行UOM与SO行UOM不一致，已发量/未发量未知"))
        if selected_unit_mismatch:
            flags.append(_("所选DN行UOM与SO行UOM不一致，所选净发量未知"))
        if not unit_known:
            flags.append(_("订单单位缺失，数量未知"))
        if line_wo is None:
            flags.append(_("工单/计划信息无权限，数量未知"))
        if line_tn is None:
            flags.append(_("菲号信息无权限，数量未知"))
        if filters.get("only_overdue") and _("交期已过") not in flags:
            continue
        if row.so_status == "Closed":
            n_dead += 1
        stages[stage] = stages.get(stage, 0) + 1
        data.append({
            "so": row.so, "customer": row.customer, "item_code": row.item_code,
            "customer_item_code": row.customer_item_code, "uom": row.uom,
            "delivery_date": row.delivery_date,
            "qty": float(row.qty or 0) if unit_known else None,
            "shipped": shipped, "selected_dn_qty": selected_dn_qty,
            "open_qty": open_qty, "stage_txt": f"{stage} {sub}", "flags": " / ".join(flags),
            "wo_n": len(line_wo.get(row.so_line, [])) if line_wo is not None else None,
            "tn_n": line_tn.get(row.so_line, 0) if line_tn is not None else None,
        })

    open_by_unit = {}
    for item in data:
        if item["open_qty"] is not None and item["uom"]:
            open_by_unit[item["uom"]] = open_by_unit.get(item["uom"], 0.0) + item["open_qty"]
    unknown_qty_count = sum(item["open_qty"] is None for item in data)
    summary = [
        {"label": _("行数(未发完)"), "value": len(data), "datatype": "Int"},
        *[{"label": _("未发总量（{0}）").format(uom), "value": round(open_by_unit[uom], 3), "datatype": "Float"}
          for uom in sorted(open_by_unit)],
        {"label": _("未发量未知行（权限/单位受限）"), "value": unknown_qty_count, "datatype": "Int",
         "indicator": "Red" if unknown_qty_count else "Green"},
        {"label": _("交期已过(行)"), "value": n_overdue, "datatype": "Int", "indicator": "Red" if n_overdue else "Green"},
        {"label": _("死单(Closed未发)"), "value": n_dead, "datatype": "Int", "indicator": "Red" if n_dead else "Green"},
    ]
    chart_stages = [
        (0, _("信息不可见")),
        (1, _("未排产")),
        (2, _("生产中/待发")),
        (3, _("已发完成/Closed未发")),
    ]
    chart = {
        "data": {
            "labels": [label for _, label in chart_stages],
            "datasets": [{
                "name": _("未发SO行数"),
                "values": [stages.get(key, 0) for key, _ in chart_stages],
            }],
        },
        "type": "bar",
    }
    return _columns(), data, None, chart, summary
