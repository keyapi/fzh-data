"""Finite-coverage native report for stock snapshot supply evidence."""
import frappe
from frappe import _

from key_test.supply_timeline_query import get_report_data


filters = [
    {"fieldname": "sku", "label": _("SKU（逗号分隔，最多 9 个）"), "fieldtype": "Data"},
    {"fieldname": "warehouse_name", "label": _("通途仓库名"), "fieldtype": "Data"},
    {"fieldname": "stage", "label": _("阶段"), "fieldtype": "Select",
     "options": "\non_hand\nshipped_in_transit\nunknown"},
    {"fieldname": "snapshot_date", "label": _("库存快照日期"), "fieldtype": "Data", "default": "latest"},
]


COLUMNS = [
    (_("通途 SKU"), "sku", "Data", None, 190),
    (_("通途仓库"), "warehouse", "Data", None, 180),
    (_("仓库 ID"), "warehouse_id", "Data", None, 105),
    (_("阶段"), "stage", "Data", None, 125),
    (_("快照日期"), "snapshot_date", "Data", None, 105),
    (_("源快照时间"), "snapshot_at", "Datetime", None, 145),
    (_("批次"), "batch", "Data", None, 150),
    (_("批次采集开始"), "run_started_at", "Datetime", None, 145),
    (_("批次采集结束"), "run_finished_at", "Datetime", None, 145),
    (_("本次查询时间"), "query_as_of", "Datetime", None, 145),
    (_("来源键"), "source_key", "Data", None, 300),
    (_("数量证据"), "qty", "Float", None, 100),
    (_("未确认数量证据"), "evidence_qty", "Float", None, 120),
    (_("库存单位"), "uom", "Data", None, 80),
    (_("单位置信度"), "uom_confidence", "Data", None, 100),
    (_("日期置信度"), "date_confidence", "Data", None, 120),
    (_("快照置信度"), "snapshot_confidence", "Data", None, 120),
    (_("可用日期"), "available_date", "Date", None, 100),
    (_("来源桶"), "source_bucket", "Data", None, 130),
    (_("台账"), "ledger", "Data", None, 110),
    (_("重叠状态"), "overlap_status", "Data", None, 100),
    (_("计入供给"), "counted", "Check", None, 80),
    (_("来源覆盖"), "source_coverage", "Data", None, 175),
    (_("数据层"), "source_layer", "Data", None, 130),
    (_("数量状态"), "qty_status", "Data", None, 90),
    (_("证据数量状态"), "evidence_qty_status", "Data", None, 110),
    (_("单位已证"), "uom_proven", "Check", None, 80),
    (_("时区状态"), "timezone_status", "Data", None, 100),
    (_("身份置信度"), "identity_confidence", "Data", None, 115),
    (_("B_min 资格"), "b_min_eligible", "Check", None, 90),
    (_("B_max 资格"), "b_max_eligible", "Check", None, 90),
    (_("排除原因"), "exclusion_reason", "Data", None, 165),
    (_("原因"), "reason", "Data", None, 250),
]


def _columns():
    return [
        {"label": label, "fieldname": fieldname, "fieldtype": fieldtype,
         "options": options, "width": width}
        for label, fieldname, fieldtype, options, width in COLUMNS
    ]


def execute(filters=None):
    rows, message = get_report_data(frappe._dict(filters or {}))
    return _columns(), rows, message, None, []
