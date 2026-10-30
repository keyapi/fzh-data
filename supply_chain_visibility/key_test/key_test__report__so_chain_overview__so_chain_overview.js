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
		{ fieldname: "include_delivered", label: __("含已出库完成"), fieldtype: "Check" },
	],

	_chain: { ready: null, cache: {}, loading: {}, logistics: { cache: {}, loading: {} } },

	onload: function (report) {
		const cfg = frappe.query_reports["SO Chain Overview"];
		cfg._chain.ready = frappe.require("/assets/key_test/js/sales_order.js").catch(function () {
			return null;
		});
		if (!document.getElementById("so-chain-report-css")) {
			const style = document.createElement("style");
			style.id = "so-chain-report-css";
			style.textContent =
				".so-chain-report-open,.so-chain-logistics-open{text-decoration:none;font-weight:600}" +
				".so-chain-report-open:hover,.so-chain-logistics-open:hover{text-decoration:underline}";
			document.head.appendChild(style);
		}
		$(report.page.wrapper)
			.off("click.soChainReport")
			.on("click.soChainReport", ".so-chain-report-open", function (e) {
				e.preventDefault();
				e.stopPropagation();
				cfg._open($(this).attr("data-so"), $(this).attr("data-line"));
			})
			.on("click.soChainReport", ".so-chain-logistics-open", function (e) {
				e.preventDefault();
				e.stopPropagation();
				cfg._open_logistics($(this).attr("data-so"), $(this).attr("data-line"));
			});
	},

	formatter: function (value, row, column, data, default_formatter) {
		const cfg = frappe.query_reports["SO Chain Overview"];
		const field = column ? (column.fieldname || column.id) : "";
		if (field === "item_code" && value) {
			let url;
			try {
				url = frappe.utils.get_form_link("Item", value);
			} catch (e) {
				url = "/app/item/" + encodeURIComponent(value);
			}
			return '<a href="' + cfg._esc(url) + '" target="_blank" rel="noopener noreferrer" style="color:#0a6ed1">' +
				cfg._esc(value) + "</a>";
		}
		if (field === "prod_chain" || field === "dn_chain" || field === "head_leg") {
			const text = (value === null || value === undefined || value === "") ? "—" : String(value);
			if (text === "—") return cfg._esc(text);
			const color = field === "prod_chain" ? "#0d7a3f" : (field === "dn_chain" ? "#0a6ed1" : "#6f42c1");
			const cls = field === "head_leg" ? "so-chain-logistics-open" : "so-chain-report-open";
			return '<a href="#" class="' + cls + '" data-so="' + cfg._esc(data.so) +
				'" data-line="' + cfg._esc(data.so_line) + '" style="color:' + color + '">' +
				cfg._esc(text) + ' <span style="font-size:10px">⤢</span></a>';
		}
		return default_formatter(value, row, column, data);
	},

	_esc: function (value) {
		return frappe.utils.escape_html(value === null || value === undefined ? "" : String(value));
	},

	_open: function (so, line) {
		const cfg = frappe.query_reports["SO Chain Overview"];
		if (!so) return;
		const show = function (lines) {
			const target = (lines || []).find(function (item) { return item.so_line === line; }) ||
				(lines || []).find(function (item) { return item.item_code === line; });
			if (!target) {
				frappe.msgprint(__("未找到该订单行，或没有链条读取权限。"));
				return;
			}
			if (typeof so_chain_show_detail === "function") {
				so_chain_show_detail(target, so);
			} else {
				frappe.msgprint(__("链条渲染脚本未加载，请刷新报表后重试。"));
			}
		};
		if (cfg._chain.cache[so]) {
			show(cfg._chain.cache[so]);
			return;
		}
		if (cfg._chain.loading[so]) return;
		cfg._chain.loading[so] = true;
		frappe.show_alert({ message: __("加载链条明细…"), indicator: "blue" });
		Promise.resolve(cfg._chain.ready || frappe.require("/assets/key_test/js/sales_order.js"))
			.then(function () {
				frappe.call({
					method: "key_test.so_chain.get_so_chain",
					args: { sales_order: so },
					callback: function (response) {
						delete cfg._chain.loading[so];
						const lines = (response && response.message && response.message.lines) || [];
						cfg._chain.cache[so] = lines;
						show(lines);
					},
					error: function () {
						delete cfg._chain.loading[so];
						frappe.msgprint(__("加载链条明细失败，或没有读取权限。"));
					},
				});
			})
			.catch(function () {
				delete cfg._chain.loading[so];
				frappe.msgprint(__("链条渲染脚本加载失败，请刷新后重试。"));
			});
	},

	_open_logistics: function (so, line) {
		const cfg = frappe.query_reports["SO Chain Overview"];
		if (!so || !line) return;
		const state = cfg._chain.logistics;
		const key = so + "|" + line;
		const show = function (data) {
			if (typeof so_chain_show_logistics === "function") {
				so_chain_show_logistics(data, so);
			} else {
				frappe.msgprint(__("物流渲染脚本未加载，请刷新报表后重试。"));
			}
		};
		if (state.cache[key]) {
			show(state.cache[key]);
			return;
		}
		if (state.loading[key]) return;
		state.loading[key] = true;
		frappe.show_alert({ message: __("加载头程物流…"), indicator: "blue" });
		Promise.resolve(cfg._chain.ready || frappe.require("/assets/key_test/js/sales_order.js"))
			.then(function () {
				frappe.call({
					method: "key_test.so_chain.get_so_line_logistics",
					args: { sales_order: so, so_line: line },
					callback: function (response) {
						delete state.loading[key];
						const data = response && response.message;
						if (!data) {
							frappe.msgprint(__("加载头程物流失败，或没有读取权限。"));
							return;
						}
						state.cache[key] = data;
						show(data);
					},
					error: function () {
						delete state.loading[key];
						frappe.msgprint(__("加载头程物流失败，或没有读取权限。"));
					},
				});
			})
			.catch(function () {
				delete state.loading[key];
				frappe.msgprint(__("物流渲染脚本加载失败，请刷新后重试。"));
			});
	},
};
