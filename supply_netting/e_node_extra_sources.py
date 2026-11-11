"""附加本地单据：未关联也展示，但累计 DN 不充当在途余额。"""
import pandas as pd

from .e_nodes import _node, _id, cutoff, WAREHOUSE_CUSTOMER, CUSTOMER_DEST, require, numbers

EN_CUSTOMERS = {"波兰公司": "波兰", "波兰": "波兰", "CENTRADE": "USNJ", "DANEEY": "USTX",
                "美东USNJ": "USNJ", "美中USTX": "USTX", "USNJ": "USNJ", "USTX": "USTX"}


def dn_nodes(payload, as_of, source):
    rows = []
    for record in payload.get("results", []):
        doc = record.get("doc") or {}
        if doc.get("posting_date") and pd.Timestamp(doc["posting_date"]).date() > cutoff(as_of).date():
            raise ValueError("future DN evidence")
        for i, item in enumerate(record.get("items") or [], 1):
            customer = EN_CUSTOMERS.get(doc.get("customer"))
            rows.append(_node(node_id=_id(source, doc.get("name"), item.get("name") or i),
                              sku=item["item_code"], product_id=item["item_code"], warehouse=item.get("warehouse"),
                              destination_warehouse=CUSTOMER_DEST.get(customer), customer=customer,
                              node="dn_delivered_evidence", qty=item.get("qty"), uom=item.get("uom"),
                              uom_status="DN_item_uom", source=source, source_row=i,
                              source_record_id=f"{doc.get('name')}:{item.get('name') or i}",
                              source_as_of=payload.get("fetched_at_utc"), as_of=as_of,
                              voucher_no=doc.get("name") or record.get("dn"), voucher_line_id=item.get("name"),
                              voucher_line_status="DN_item_name" if item.get("name") else "export_only",
                              linkage_status="document_line_proven_SO_unlinked" if not item.get("so_detail") else "document_line_proven",
                              counting_reason="cumulative_delivery_evidence_not_current_stage_balance",
                              event_at=doc.get("posting_date"), against_so=item.get("against_sales_order"),
                              so_line_id=item.get("so_detail"), document_status=str(doc.get("docstatus")),
                              source_timezone="UTC"))
    return pd.DataFrame(rows)


def po_nodes(frame, as_of, source):
    require(frame, ["PONum", "goods_sku", "warehouseName", "open_qty", "purchaseOrderId", "goodsIdKey"], "PO")
    numbers(frame, ["open_qty"], "PO", nonnegative=True)
    rows = []
    for i, r in enumerate(frame.to_dict("records"), 2):
        wh = r["warehouseName"]
        promised = r.get("willArriveDate")
        valid = pd.notna(promised) and str(promised).strip() not in {"", "0", "None"}
        eta = str(promised) if valid else None
        rows.append(_node(node_id=_id(source, i), sku=r["goods_sku"], warehouse=wh,
                          destination_warehouse=wh, customer=WAREHOUSE_CUSTOMER.get(wh),
                          node="po_open", qty=r["open_qty"], uom="个", uom_status="tongtool_pieces_user_confirmed",
                          eta=eta, eta_status="estimated_source_PO" if eta else "unknown",
                          source=source, source_row=i, source_record_id=f"{r['purchaseOrderId']}:{r['goodsIdKey']}:row{i}",
                          voucher_no=r["PONum"], voucher_line_status="goods_id_not_PO_line_id",
                          promised_at=r.get("purchaseArrivalDate") if pd.notna(r.get("purchaseArrivalDate")) else None,
                          linkage_status="unlinked", as_of=as_of, event_at=r.get("purchaseDate"),
                          counting_reason="PO_may_overlap_snapshot_intransit_waiting",
                          source_timezone="Asia/Shanghai"))
    return pd.DataFrame(rows)
