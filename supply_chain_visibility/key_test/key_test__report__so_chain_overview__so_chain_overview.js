// Keep filters explicit so Script Report UI, export, and backend use the same contract.
frappe.query_reports["SO Chain Overview"] = {
    filters: [
        { fieldname: "customer", label: __("客户"), fieldtype: "Link", options: "Customer" },
        { fieldname: "from_date", label: __("SO下单日期从"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("SO下单日期至"), fieldtype: "Date" },
        { fieldname: "sales_order", label: __("销售订单"), fieldtype: "Link", options: "Sales Order" },
        { fieldname: "delivery_note", label: __("指定出库单"), fieldtype: "Link", options: "Delivery Note" },
        { fieldname: "item_code", label: __("物料"), fieldtype: "Link", options: "Item" },
        { fieldname: "customer_item_code", label: __("客户物料号"), fieldtype: "Data" },
        { fieldname: "warehouse", label: __("SO行交货仓"), fieldtype: "Link", options: "Warehouse" },
        { fieldname: "dn_from_date", label: __("DN过账日期从"), fieldtype: "Date" },
        { fieldname: "dn_to_date", label: __("DN过账日期至"), fieldtype: "Date" },
        { fieldname: "only_overdue", label: __("只看交期已过"), fieldtype: "Check" },
    ],
};
