"""Permission-aware, batched data access for SO Chain Overview."""
import frappe


def _permitted_names(doctype, filters):
    """Use get_list so parent-document permissions and user permissions apply."""
    return [row.name for row in frappe.get_list(
        doctype, filters=filters, fields=["name"], limit_page_length=0
    )]


def _permitted_rows(doctype, filters, fields, or_filters=None):
    return frappe.get_list(
        doctype, filters=filters, or_filters=or_filters, fields=fields, limit_page_length=0
    )


def _has_read_permission(doctype):
    return frappe.has_permission(doctype, "read")


# Canonical order of Shipment.custom_zmt_status11 (14 states).
STATUS11_ORDER = (
    "已订舱", "已入仓", "已装柜", "报关中", "已报关", "已离港",
    "运输中", "已到港", "清关中", "已清关", "已转运", "派送中",
    "已签收", "已上传POD",
)
UNKNOWN_STATUS = "状态未知"


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def fmt_qty(value):
    """Mirror the SO form's so_chain_num: 3 decimals, trailing zeros stripped."""
    number = _num(value)
    if not number:
        return "0"
    return ("%.3f" % number).rstrip("0").rstrip(".")


def format_head_leg(status_counts):
    """Render the first-leg summary: 1运单·status / n运单·cA/cB."""
    counts = {status: int(count) for status, count in (status_counts or {}).items() if count}
    total = sum(counts.values())
    if not total:
        return ""
    ordered = [(status, counts[status]) for status in STATUS11_ORDER if counts.get(status)]
    ordered += sorted(
        ((status, count) for status, count in counts.items() if status not in STATUS11_ORDER),
        key=lambda item: (item[0] != UNKNOWN_STATUS, -item[1], item[0]),
    )
    if total == 1:
        return "1运单·" + ordered[0][0]
    return "%d运单·%s" % (total, "/".join("%d%s" % (count, status) for status, count in ordered))


def _candidate_delivery_notes(line_ids, filters=None):
    """Find only DNs linked to target SO rows; parent read permission is checked later."""
    if not line_ids:
        return []
    filters = frappe._dict(filters or {})
    conditions = ["dni.so_detail in %(so_lines)s", "dn.docstatus = 1"]
    values = {"so_lines": tuple(line_ids)}
    if filters.get("delivery_note"):
        conditions.append("dn.name = %(delivery_note)s")
        values["delivery_note"] = filters.delivery_note
    if filters.get("dn_from_date"):
        conditions.append("dn.posting_date >= %(dn_from_date)s")
        values["dn_from_date"] = filters.dn_from_date
    if filters.get("dn_to_date"):
        conditions.append("dn.posting_date <= %(dn_to_date)s")
        values["dn_to_date"] = filters.dn_to_date
    return [row.name for row in frappe.db.sql(
        f"""select distinct dn.name as name
            from `tabDelivery Note Item` dni
            join `tabDelivery Note` dn on dn.name = dni.parent
            where {' and '.join(conditions)}""",
        values, as_dict=True,
    )]


def _readable_delivery_notes(candidate_names, filters=None):
    if not candidate_names:
        return []
    filters = frappe._dict(filters or {})
    conditions = [["name", "in", candidate_names], ["docstatus", "=", 1]]
    if filters.get("dn_from_date"):
        conditions.append(["posting_date", ">=", filters.dn_from_date])
    if filters.get("dn_to_date"):
        conditions.append(["posting_date", "<=", filters.dn_to_date])
    return _permitted_names("Delivery Note", conditions)


def _quantities_with_matching_uom(rows, line_uom, value_field):
    grouped = {}
    mismatches = set()
    for row in rows:
        grouped.setdefault(row.so_line, []).append(row)
    values = {}
    for line, records in grouped.items():
        expected_uom = line_uom.get(line)
        if not expected_uom or any(record.uom != expected_uom for record in records):
            mismatches.add(line)
            values[line] = None
        else:
            values[line] = sum(float(getattr(record, value_field) or 0) for record in records)
    return values, mismatches


def _line_dn_scope(rows):
    line_meta = {}
    for row in rows:
        line_meta[row.so_line] = (row.so, row.item_code, row.uom)
    return line_meta


def _map_dn_rows(dn_rows, line_meta, extra=None):
    """Attach DN item rows to SO lines; blank so_detail maps only when unambiguous."""
    by_so_item = {}
    for line, (so, item_code, _uom) in line_meta.items():
        by_so_item.setdefault((so, item_code), []).append(line)
    grouped = {}
    for dn in dn_rows:
        if dn.so_detail and dn.so_detail in line_meta:
            grouped.setdefault(dn.so_detail, []).append(dn)
        elif not dn.so_detail:
            targets = by_so_item.get((dn.against_sales_order, dn.item_code), [])
            if len(targets) == 1:
                grouped.setdefault(targets[0], []).append(dn)
            elif targets and extra is not None:
                extra["blank_so_detail_ambiguous_lines"].update(targets)
    if extra is not None:
        for line in extra["blank_so_detail_ambiguous_lines"]:
            extra["dn_unknown_lines"].add(line)
    return grouped


def _dn_rows_for_lines(rows):
    line_meta = _line_dn_scope(rows)
    if not line_meta:
        return []
    values = {
        "sos": tuple({row.so for row in rows}),
        "lines": tuple(line_meta),
        "items": tuple({row.item_code for row in rows}),
    }
    return frappe.db.sql(
        """select dn.name as dn, dn.docstatus as docstatus, ifnull(dn.is_return, 0) as is_return,
                  dni.so_detail as so_detail, dni.against_sales_order as against_sales_order,
                  dni.item_code as item_code, dni.qty as qty, dni.uom as uom
           from `tabDelivery Note Item` dni
           join `tabDelivery Note` dn on dn.name = dni.parent
           where dni.against_sales_order in %(sos)s
             and (dni.so_detail in %(lines)s
                  or (ifnull(dni.so_detail, '') = '' and dni.item_code in %(items)s))
             and dn.docstatus in (0, 1)""",
        values, as_dict=True,
    )


def _lines_with_dns(rows):
    """Lines that carry at least one non-cancelled DN; used by include_delivered."""
    line_meta = _line_dn_scope(rows)
    by_so_item = {}
    for line, (so, item_code, _uom) in line_meta.items():
        by_so_item.setdefault((so, item_code), []).append(line)
    found = set()
    for dn in _dn_rows_for_lines(rows):
        if dn.so_detail in line_meta:
            found.add(dn.so_detail)
        elif not dn.so_detail:
            targets = by_so_item.get((dn.against_sales_order, dn.item_code), [])
            if len(targets) == 1:
                found.add(targets[0])
    return found


def dn_logistic_numbers(dn_names):
    numbers_by_dn = {}
    seen = set()
    if dn_names and frappe.db.table_exists("Delivery Note Logistics Number"):
        child_rows = frappe.db.sql(
            """select parent as dn, logistic_number as number, ifnull(is_primary, 0) as is_primary
               from `tabDelivery Note Logistics Number`
               where parent in %(dns)s and ifnull(logistic_number, '') != ''""",
            {"dns": tuple(dn_names)}, as_dict=True,
        )
        for row in child_rows:
            key = (row.dn, row.number)
            if key not in seen:
                seen.add(key)
                numbers_by_dn.setdefault(row.dn, []).append(
                    {"number": row.number, "primary": int(row.is_primary or 0)})
    if dn_names and frappe.db.has_column("Delivery Note", "logistic_number"):
        for row in frappe.db.sql(
            """select name as dn, logistic_number as number
               from `tabDelivery Note`
               where name in %(dns)s and ifnull(logistic_number, '') != ''""",
            {"dns": tuple(dn_names)}, as_dict=True,
        ):
            key = (row.dn, row.number)
            if key not in seen:
                seen.add(key)
                numbers_by_dn.setdefault(row.dn, []).append({"number": row.number, "primary": 1})
    return numbers_by_dn


def get_dn_and_logistics(rows):
    """Per-line DN counts/quantities and first-leg shipment status distribution.

    Returns (dn_summary, logistics_summary, extra); None means not visible.
    """
    extra = {
        "dn_unit_mismatch_lines": set(),
        "dn_unknown_lines": set(),
        "shipment_restricted_lines": set(),
        "blank_so_detail_ambiguous_lines": set(),
        "has_shipment_permission": True,
    }
    if not rows:
        return {}, {}, extra
    if not _has_read_permission("Delivery Note"):
        return None, None, extra

    line_meta = _line_dn_scope(rows)
    dn_rows = _dn_rows_for_lines(rows)
    grouped = _map_dn_rows(dn_rows, line_meta, extra)

    dn_names = sorted({dn.dn for dn in dn_rows})
    permitted = set(_permitted_names(
        "Delivery Note", [["name", "in", dn_names], ["docstatus", "in", (0, 1)]]))
    if set(dn_names) != permitted:
        return None, None, extra

    dn_summary = {}
    for line, records in grouped.items():
        uom = line_meta[line][2]
        if not uom or any(record.uom != uom for record in records):
            extra["dn_unit_mismatch_lines"].add(line)
            dn_summary[line] = None
            continue
        dn_summary[line] = {
            "dns": len({record.dn for record in records}),
            "shipped": sum(_num(record.qty) for record in records
                           if record.docstatus == 1 and not int(record.is_return or 0)),
            "returned": sum(_num(record.qty) for record in records
                            if record.docstatus == 1 and int(record.is_return or 0)),
        }
    for line in extra["dn_unknown_lines"]:
        dn_summary[line] = None

    if not (_has_read_permission("Shipment")
            and frappe.db.has_column("Shipment", "custom_zmt_logistic_number")):
        extra["has_shipment_permission"] = False
        return dn_summary, None, extra

    numbers_by_dn = dn_logistic_numbers(dn_names)
    all_numbers = sorted({item["number"] for values in numbers_by_dn.values() for item in values})
    shipment_by_number = {}
    restricted_numbers = set()
    if all_numbers:
        candidates = frappe.db.sql(
            """select name, custom_zmt_logistic_number as number, custom_zmt_status11 as status11
               from `tabShipment`
               where custom_zmt_logistic_number in %(numbers)s and docstatus in (0, 1)""",
            {"numbers": tuple(all_numbers)}, as_dict=True,
        )
        permitted_shipments = set(_permitted_names(
            "Shipment", [["custom_zmt_logistic_number", "in", all_numbers],
                         ["docstatus", "in", (0, 1)]]))
        for candidate in candidates:
            if candidate.name in permitted_shipments:
                shipment_by_number[candidate.number] = candidate
            else:
                restricted_numbers.add(candidate.number)

    logistics_summary = {}
    for line, records in grouped.items():
        numbers = []
        for dn in sorted({record.dn for record in records}):
            numbers.extend(item["number"] for item in numbers_by_dn.get(dn, []))
        numbers = list(dict.fromkeys(numbers))
        if any(number in restricted_numbers for number in numbers):
            extra["shipment_restricted_lines"].add(line)
            logistics_summary[line] = None
            continue
        counts = {}
        for number in numbers:
            status = (getattr(shipment_by_number.get(number), "status11", None)
                      or UNKNOWN_STATUS)
            counts[status] = counts.get(status, 0) + 1
        logistics_summary[line] = {"numbers": len(numbers), "status_counts": counts}

    return dn_summary, logistics_summary, extra


def get_report_data(filters):
    filters = frappe._dict(filters or {})
    visibility = dict(
        sales_orders=_has_read_permission("Sales Order"),
        delivery_notes=_has_read_permission("Delivery Note"),
        work_orders=_has_read_permission("Work Order"),
        production_plans=_has_read_permission("Production Plan"),
        tracking_numbers=_has_read_permission("Tracking Number"),
    )
    if not visibility["sales_orders"]:
        frappe.throw("No permission for Sales Order", frappe.PermissionError)
    so_filters = [["docstatus", "=", 1]]
    for field, operator in (("customer", "="), ("sales_order", "=")):
        if filters.get(field):
            so_filters.append(["name" if field == "sales_order" else field, operator, filters[field]])
    if filters.get("from_date"):
        so_filters.append(["transaction_date", ">=", filters.from_date])
    if filters.get("to_date"):
        so_filters.append(["transaction_date", "<=", filters.to_date])
    sales_orders = _permitted_names("Sales Order", so_filters)
    if not sales_orders:
        return [], {}, {}, {}, {}, visibility

    sql_filters = ["soi.parent in %(sales_orders)s"]
    if not filters.get("include_delivered"):
        sql_filters.append("(soi.qty - soi.delivered_qty) > 0")
    values = {"sales_orders": tuple(sales_orders)}
    for field in ("item_code", "customer_item_code"):
        if filters.get(field):
            sql_filters.append(f"soi.{field} = %({field})s")
            values[field] = filters[field]
    if filters.get("warehouse"):
        sql_filters.append("soi.warehouse = %(warehouse)s")
        values["warehouse"] = filters.warehouse
    rows = frappe.db.sql(
        f"""select so.name as so, so.customer_name as customer, so.status as so_status,
                   soi.delivery_date, so.transaction_date, soi.name as so_line,
                   soi.item_code, soi.customer_item_code, soi.uom, soi.qty, soi.delivered_qty,
                   (soi.qty - soi.delivered_qty) as open_qty
            from `tabSales Order` so
            join `tabSales Order Item` soi on soi.parent = so.name
            where {' and '.join(sql_filters)}""",
        values, as_dict=True,
    )
    if not rows:
        return [], {}, {}, {}, {}, visibility

    if filters.get("include_delivered"):
        # Keep fully delivered lines only when they actually carry a DN; never
        # expand the report to every historical SO line.
        with_dns = _lines_with_dns(rows) if visibility["delivery_notes"] else set()
        rows = [row for row in rows
                if _num(row.open_qty) > 1e-9 or row.so_line in with_dns]
        if not rows:
            return [], {}, {}, {}, {}, visibility

    line_ids = list(dict.fromkeys(row.so_line for row in rows))
    line_uom = {row.so_line: row.uom for row in rows}
    visibility["shipped_unit_mismatch_lines"] = set()
    visibility["selected_unit_mismatch_lines"] = set()
    # Warehouse means SO Item warehouse (the order row's destination), not a DN
    # source warehouse. DN matching uses only the confirmed so_detail foreign key.
    constrained_dn = bool(filters.get("delivery_note") or filters.get("dn_from_date") or
                          filters.get("dn_to_date"))
    dn_line_ids = set()
    if constrained_dn and not visibility["delivery_notes"]:
        frappe.throw("No permission for Delivery Note", frappe.PermissionError)
    selected_candidates = (
        _candidate_delivery_notes(line_ids, filters if constrained_dn else None)
        if visibility["delivery_notes"] else []
    )
    permitted_dns = (
        _readable_delivery_notes(selected_candidates, filters if constrained_dn else None)
        if visibility["delivery_notes"] else []
    )
    selected_dn_access_complete = set(selected_candidates) == set(permitted_dns)
    if constrained_dn and selected_candidates and not selected_dn_access_complete:
        frappe.throw("No permission for one or more matching Delivery Notes", frappe.PermissionError)
    if constrained_dn and not permitted_dns:
        return [], {}, {}, {}, {}, visibility
    if constrained_dn:
        dn_line_ids = {row.so_detail for row in frappe.db.sql(
            """select distinct dni.so_detail from `tabDelivery Note Item` dni
               where dni.parent in %(delivery_notes)s and dni.so_detail in %(so_lines)s""",
            {"delivery_notes": tuple(permitted_dns), "so_lines": tuple(line_ids)}, as_dict=True,
        )}
        rows = [row for row in rows if row.so_line in dn_line_ids]
        if not rows:
            return [], {}, {}, {}, {}, visibility
        line_ids = [row.so_line for row in rows]

    # All-time signed delivery quantity is distinct from quantity on the
    # selected DN(s)/posting-date window. Both are grouped by SO Item.name.
    has_dn_date_or_selection = bool(
        filters.get("delivery_note") or filters.get("dn_from_date") or filters.get("dn_to_date")
    )
    all_dn_names = []
    all_dn_candidates = []
    if visibility["delivery_notes"]:
        all_dn_candidates = (
            _candidate_delivery_notes(line_ids)
            if has_dn_date_or_selection
            else selected_candidates
        )
        all_dn_names = (
            _readable_delivery_notes(all_dn_candidates)
            if has_dn_date_or_selection
            else permitted_dns
        )
    all_dn_access_complete = set(all_dn_candidates) == set(all_dn_names)
    ship_map = None if not (visibility["delivery_notes"] and all_dn_access_complete) else {}
    if all_dn_names and ship_map is not None:
        shipped = frappe.db.sql(
            """select dni.so_detail as so_line, dni.uom as uom, sum(dni.qty) as shipped
               from `tabDelivery Note Item` dni
               where dni.parent in %(delivery_notes)s and dni.so_detail in %(so_lines)s
               group by dni.so_detail, dni.uom""",
            {"delivery_notes": tuple(all_dn_names), "so_lines": tuple(line_ids)}, as_dict=True,
        )
        ship_map, mismatches = _quantities_with_matching_uom(shipped, line_uom, "shipped")
        visibility["shipped_unit_mismatch_lines"].update(mismatches)

    selected_map = None if not (visibility["delivery_notes"] and selected_dn_access_complete) else {}
    if selected_map is not None and (filters.get("delivery_note") or filters.get("dn_from_date") or filters.get("dn_to_date")):
        if permitted_dns:
            selected_where = [
                "dni.parent in %(delivery_notes)s",
                "dni.so_detail in %(so_lines)s",
            ]
            selected_values = {
                "delivery_notes": tuple(permitted_dns),
                "so_lines": tuple(line_ids),
            }
            selected = frappe.db.sql(
                f"""select dni.so_detail as so_line, dni.uom as uom,
                           sum(dni.qty) as selected_dn_qty
                    from `tabDelivery Note Item` dni
                    where {' and '.join(selected_where)}
                    group by dni.so_detail, dni.uom""",
                selected_values, as_dict=True,
            )
            selected_map, mismatches = _quantities_with_matching_uom(
                selected, line_uom, "selected_dn_qty"
            )
            visibility["selected_unit_mismatch_lines"].update(mismatches)

    # Fetch only visible Work Orders / plan rows, then associate by SO Item
    # foreign keys. This preserves row-level permissions for these doctypes.
    ppi_candidates = []
    visible_pps = []
    if visibility["production_plans"]:
        ppi_candidates = frappe.db.sql(
            """select ppi.name, ppi.parent, ppi.sales_order_item
               from `tabProduction Plan Item` ppi
               where ppi.sales_order_item in %(so_lines)s""",
            {"so_lines": tuple(line_ids)}, as_dict=True,
        )
        ppi_candidate_parents = list({row.parent for row in ppi_candidates})
        if ppi_candidate_parents:
            visible_pps = _permitted_names(
                "Production Plan", [["name", "in", ppi_candidate_parents]]
            )
    ppi_access_complete = (
        visibility["production_plans"]
        and {row.parent for row in ppi_candidates} == set(visible_pps)
    )
    ppi_rows = [row for row in ppi_candidates if row.parent in set(visible_pps)]
    ppi_to_line = {row.name: row.sales_order_item for row in ppi_rows if row.sales_order_item}
    work_order_candidates = []
    work_orders = []
    if visibility["work_orders"]:
        wo_conditions = [
            "w.docstatus = 1",
            "(w.sales_order_item in %(so_lines)s or w.fg_sales_order_item in %(so_lines)s",
        ]
        wo_values = {"so_lines": tuple(line_ids)}
        if ppi_to_line:
            wo_conditions[1] += " or w.production_plan_item in %(plan_items)s"
            wo_values["plan_items"] = tuple(ppi_to_line)
        wo_conditions[1] += ")"
        work_order_candidates = frappe.db.sql(
            f"""select w.name, w.sales_order_item, w.fg_sales_order_item, w.production_plan_item
                from `tabWork Order` w where {' and '.join(wo_conditions)}""",
            wo_values, as_dict=True,
        )
        candidate_wo_names = [row.name for row in work_order_candidates]
        if candidate_wo_names:
            work_orders = _permitted_rows(
                "Work Order", [["name", "in", candidate_wo_names], ["docstatus", "=", 1]],
                ["name", "sales_order_item", "fg_sales_order_item", "production_plan_item"],
            )
    work_order_access_complete = (
        visibility["work_orders"]
        and ppi_access_complete
        and {row.name for row in work_order_candidates} == {row.name for row in work_orders}
    )
    line_wo = {}
    wo_names = []
    for wo in work_orders:
        line = wo.sales_order_item or ppi_to_line.get(wo.production_plan_item) or wo.fg_sales_order_item
        if line in line_ids:
            line_wo.setdefault(line, []).append(wo.name)
            wo_names.append(wo.name)
    tracking_candidates = []
    tracking_rows = []
    if wo_names and visibility["tracking_numbers"]:
        tracking_candidates = frappe.db.sql(
            """select name, work_order from `tabTracking Number`
               where work_order in %(work_orders)s""",
            {"work_orders": tuple(wo_names)}, as_dict=True,
        )
        candidate_tn_names = [row.name for row in tracking_candidates]
        if candidate_tn_names:
            tracking_rows = _permitted_rows(
                "Tracking Number", [["name", "in", candidate_tn_names]], ["name", "work_order"]
            )
    tracking_access_complete = (
        visibility["tracking_numbers"] and work_order_access_complete
        and {row.name for row in tracking_candidates} == {row.name for row in tracking_rows}
    )
    wo_to_line = {wo_name: line for line, names in line_wo.items() for wo_name in names}
    line_tn = {}
    for tn in tracking_rows:
        line = wo_to_line.get(tn.work_order)
        if line:
            line_tn[line] = line_tn.get(line, 0) + 1

    if not work_order_access_complete:
        line_wo = None
    if not tracking_access_complete:
        line_tn = None
    return rows, ship_map, selected_map, line_wo, line_tn, visibility
