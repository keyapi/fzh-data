# -*- coding: utf-8 -*-
"""key_test app：Script Report「订单链条总览」(SO Chain Overview)

每个「还未发完」的订单行一行，给阶段 / 未发量 / 异常，顶部出 KPI 汇总（report_summary）+ 阶段分布图。
口径与 key_test.so_chain.get_so_chain 一致：已发按出库单 item_code 净额（退货抵扣）；
WO.status 不作事实（本报表只用「有无工单」粗判，细粒度工序进度看 SO 表单内嵌区块）。

落点：key_test/key_test/report/so_chain_overview/so_chain_overview.{json,py,js}
依赖：Report 记录由 bench migrate 生成（report_type=Script Report）。
"""
import frappe
from frappe import _
from frappe.utils import getdate, today

# 模块级 `filters` 变量：Frappe 的 filter 自动发现对自定义报表会静默失败
# （见 docs/fac-dev-notes.md Lesson 64），显式声明可绕过。
filters = [
    {"fieldname": "customer", "label": _("客户"), "fieldtype": "Link", "options": "Customer"},
    {"fieldname": "from_date", "label": _("下单日期 ≥"), "fieldtype": "Date"},
    {"fieldname": "only_overdue", "label": _("只看交期已过"), "fieldtype": "Check"},
]

COLS = [
    ("Sales Order", "so", "Link", "Sales Order", 120),
    ("客户", "customer", "Data", None, 150),
    ("物料", "item_code", "Link", "Item", 200),
    ("客户物料号", "customer_item_code", "Data", None, 160),
    ("交货日期", "delivery_date", "Date", None, 95),
    ("订单量", "qty", "Float", None, 80),
    ("已发", "shipped", "Float", None, 80),
    ("未发", "open_qty", "Float", None, 80),
    ("阶段", "stage_txt", "Data", None, 130),
    ("工单数", "wo_n", "Int", None, 70),
    ("菲号数", "tn_n", "Int", None, 70),
    ("异常", "flags", "Data", None, 200),
]


def _columns():
    return [{"label": _(c[0]), "fieldname": c[1], "fieldtype": c[2], "options": c[3],
             "width": c[4]} for c in COLS]


def execute(filters=None):
    filters = frappe._dict(filters or {})
    cond = ["so.docstatus = 1", "(soi.qty - soi.delivered_qty) > 0"]
    val = {}
    if filters.get("customer"):
        cond.append("so.customer = %(customer)s")
        val["customer"] = filters.customer
    if filters.get("from_date"):
        cond.append("so.transaction_date >= %(from_date)s")
        val["from_date"] = filters.from_date
    where = " and ".join(cond)

    rows = frappe.db.sql(
        f"""select so.name as so, so.customer_name as customer, so.status as so_status,
                   so.delivery_date as delivery_date,
                   soi.name as so_line,
                   soi.item_code, soi.customer_item_code,
                   soi.qty, soi.delivered_qty, (soi.qty - soi.delivered_qty) as open_qty
            from `tabSales Order` so
            join `tabSales Order Item` soi on soi.parent = so.name
            where {where}""", val, as_dict=True)

    # 每 (SO, 物料) 的：出库净额
    dn = frappe.db.sql(
        """select dni.against_sales_order as so, dni.item_code as item_code,
                  sum(dni.qty) as shipped
           from `tabDelivery Note Item` dni
           join `tabDelivery Note` d on d.name = dni.parent
           where d.docstatus = 1
           group by dni.against_sales_order, dni.item_code""", as_dict=True)
    ship_map = {(r.so, r.item_code): (r.shipped or 0) for r in dn}

    # 每 SO 行有无工单：**用行级外键 Work Order.sales_order_item**（复合键会让同 SO 同 item_code
    # 的多行互串，生产实测 1464 张工单重复挂）。兜底 production_plan_item→PP.sales_order_item / fg_sales_order_item。
    wo_res = frappe.db.sql(
        """select w.name as wo, w.sales_order_item as soi_a,
                  ppi.sales_order_item as soi_b, w.fg_sales_order_item as soi_c
           from `tabWork Order` w
           left join `tabProduction Plan Item` ppi on ppi.name = w.production_plan_item
           where w.docstatus = 1""", as_dict=True)
    wo_map, wo_to_line = {}, {}
    for w in wo_res:
        line = w.soi_a or w.soi_b or w.soi_c
        if line:
            wo_map[line] = wo_map.get(line, 0) + 1
            wo_to_line[w.wo] = line
    tn_res = frappe.db.sql(
        """select work_order, count(*) as n from `tabTracking Number`
           where ifnull(work_order, '') != '' group by work_order""", as_dict=True)
    tn_map = {}
    for t in tn_res:
        line = wo_to_line.get(t.work_order)
        if line:
            tn_map[line] = tn_map.get(line, 0) + (t.n or 0)

    tday = getdate(today())
    data, stages = [], {}
    n_overdue = n_dead = 0
    for r in rows:
        shipped = round(float(ship_map.get((r.so, r.item_code), 0) or 0), 3)
        open_qty = round(float(r.open_qty or 0), 3)
        has_wo = wo_map.get(r.so_line, 0) > 0
        flags = []
        if r.so_status == "Closed":
            stage, sub = 3, "Closed未发(死单)"
            n_dead += 1
            flags.append("死单")
        elif shipped + 1e-6 >= float(r.qty or 0):
            stage, sub = 3, "已出库完成"
        elif not has_wo:
            stage, sub = 1, "未排产(无工单)"
            flags.append("无工单")
        else:
            stage, sub = 2, "生产中/待发"
        dd = r.delivery_date and getdate(r.delivery_date)
        if dd and dd < tday and r.so_status != "Closed":
            n_overdue += 1
            flags.append("交期已过")
        if filters.get("only_overdue") and "交期已过" not in flags:
            continue
        stages[stage] = stages.get(stage, 0.0) + open_qty
        data.append({
            "so": r.so, "customer": r.customer, "item_code": r.item_code,
            "customer_item_code": r.customer_item_code, "delivery_date": r.delivery_date,
            "qty": float(r.qty or 0), "shipped": shipped, "open_qty": open_qty,
            "stage_txt": f"{stage} {sub}", "flags": " / ".join(flags),
            "wo_n": wo_map.get(r.so_line, 0), "tn_n": tn_map.get(r.so_line, 0),
        })

    total_open = round(sum(d["open_qty"] for d in data), 3)
    summary = [
        {"label": _("行数(未发完)"), "value": len(data), "datatype": "Int"},
        {"label": _("未发总量"), "value": total_open, "datatype": "Float"},
        {"label": _("交期已过(行)"), "value": n_overdue, "datatype": "Int", "indicator": "Red" if n_overdue else "Green"},
        {"label": _("死单(Closed未发)"), "value": n_dead, "datatype": "Int", "indicator": "Red" if n_dead else "Green"},
    ]
    chart = {
        "data": {"labels": [f"阶段{k}" for k in sorted(stages)],
                 "datasets": [{"name": _("未发量"), "values": [stages[k] for k in sorted(stages)]}]},
        "type": "bar",
    }
    return _columns(), data, None, chart, summary
