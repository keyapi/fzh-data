frappe.query_reports["Supply Timeline"] = {
    filters: [
        {
            fieldname: "sku",
            label: __("SKU（逗号分隔，最多 9 个）"),
            fieldtype: "Data",
        },
        {
            fieldname: "warehouse_name",
            label: __("通途仓库名"),
            fieldtype: "Data",
        },
        {
            fieldname: "stage",
            label: __("阶段"),
            fieldtype: "Select",
            options: ["", "on_hand", "shipped_in_transit", "unknown"],
        },
        {
            fieldname: "snapshot_date",
            label: __("库存快照日期"),
            fieldtype: "Data",
            default: "latest",
        },
    ],
};
