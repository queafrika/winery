// Copyright (c) 2026, Finesoft Afrika and contributors
// For license information, please see license.txt

frappe.ui.form.on("Cellar Operation", {
	refresh(frm) {
		frm.trigger("_render_buttons");
	},

	_render_buttons(frm) {
		if (frm.doc.docstatus !== 1) return;

		const has_materials = (frm.doc.details || []).some((r) => r.item);
		const transfer_done = !!frm.doc.transfer_entry;

		if (frm.doc.status === "Planned") {
			if (has_materials && !transfer_done) {
				// Must transfer stock before starting
				frm.add_custom_button(__("Transfer Stock to WIP"), () => {
					_show_transfer_dialog(frm);
				}).addClass("btn-warning");
			} else {
				// No materials needed, or transfer already done
				frm.add_custom_button(__("Start Operation"), () => {
					_show_start_dialog(frm);
				}).addClass("btn-primary");
			}
		}

		if (frm.doc.status === "In Progress") {
			frm.add_custom_button(__("Complete Operation"), () => {
				frappe.confirm(
					__("Mark this operation as completed? All lab test tasks must be done."),
					() => {
						frm.call("complete_operation").then(() => frm.reload_doc());
					}
				);
			}).addClass("btn-success");

			frm.add_custom_button(__("New Lab Analysis"), () => {
				_create_lab_analysis(frm);
			}, __("Actions"));
		}

		if (frm.doc.wine_batch) {
			frm.add_custom_button(__("View Wine Batch"), () => {
				frappe.set_route("Form", "Wine Batch", frm.doc.wine_batch);
			});
		}

		if (frm.doc.transfer_entry) {
			frm.add_custom_button(__("View Transfer Entry"), () => {
				frappe.set_route("Form", "Stock Entry", frm.doc.transfer_entry);
			}, __("Stock Entries"));
		}
		if (frm.doc.stock_entry) {
			frm.add_custom_button(__("View Manufacture Entry"), () => {
				frappe.set_route("Form", "Stock Entry", frm.doc.stock_entry);
			}, __("Stock Entries"));
		}
	},
});

function _show_transfer_dialog(frm) {
	const raw_items = (frm.doc.details || []).filter((r) => r.item);
	if (!raw_items.length) {
		frappe.msgprint(__("No materials listed for this operation."));
		return;
	}

	const item_codes = [...new Set(raw_items.map((r) => r.item))];

	// Step 1: fetch item master data (stock item flag, batch/serial, stock UOM)
	frappe.db.get_list("Item", {
		filters: [["name", "in", item_codes]],
		fields: ["name", "is_stock_item", "has_batch_no", "has_serial_no", "stock_uom"],
		limit: item_codes.length,
	}).then((item_data) => {
		const item_map = {};
		item_data.forEach((d) => { item_map[d.name] = d; });

		const stock_items = raw_items.filter((r) => item_map[r.item] && item_map[r.item].is_stock_item);

		if (!stock_items.length) {
			frappe.msgprint(__("None of the listed materials are stock items. No transfer needed."));
			return;
		}

		// Step 2: for items where required UOM ≠ stock UOM, fetch conversion factor
		const conversion_promises = stock_items.map((item) => {
			const stock_uom = item_map[item.item].stock_uom;
			const req_uom = item.uom;
			if (req_uom && stock_uom && req_uom !== stock_uom) {
				return frappe.call({
					method: "winery.winery.doctype.cellar_operation.cellar_operation.get_uom_conversion",
					args: { item_code: item.item, from_uom: req_uom },
				}).then((r) => ({ item: item.item, ...(r.message || {}) }));
			}
			return Promise.resolve({ item: item.item, stock_uom, conversion_factor: 1.0 });
		});

		Promise.all(conversion_promises).then((conv_results) => {
			const conv_map = {};
			conv_results.forEach((r) => { conv_map[r.item] = r; });

			_build_transfer_dialog(frm, stock_items, item_map, conv_map);
		});
	});
}

function _build_transfer_dialog(frm, stock_items, item_map, conv_map) {
	const fields = [
		{
			fieldname: "wip_warehouse",
			fieldtype: "Link",
			label: __("WIP Warehouse (Destination)"),
			options: "Warehouse",
			reqd: 1,
		},
		{
			fieldname: "items_section",
			fieldtype: "Section Break",
			label: __("Source Details"),
		},
	];

	stock_items.forEach((item, idx) => {
		const info = item_map[item.item];
		const conv = conv_map[item.item] || {};
		const stock_uom = conv.stock_uom || info.stock_uom;
		const req_uom = item.uom;
		const uom_mismatch = req_uom && stock_uom && req_uom !== stock_uom;
		const default_cf = conv.conversion_factor || 1.0;

		// Item header
		fields.push({
			fieldname: `item_label_${idx}`,
			fieldtype: "HTML",
			options: `<div style="font-weight:600;padding:4px 0">
				${item.item} &mdash; ${item.quantity || ""} ${req_uom || ""}
				${uom_mismatch ? `<span style="color:#888;font-weight:400;font-size:12px"> &nbsp;(stock UOM: ${stock_uom})</span>` : ""}
			</div>`,
		});

		fields.push({
			fieldname: `s_warehouse_${idx}`,
			fieldtype: "Link",
			label: __("Source Warehouse"),
			options: "Warehouse",
			reqd: 1,
		});

		if (info.has_batch_no) {
			fields.push({
				fieldname: `batch_no_${idx}`,
				fieldtype: "Link",
				label: __("Batch No"),
				options: "Batch",
				reqd: 1,
				get_query() {
					return { filters: { item: item.item } };
				},
			});
		}

		if (info.has_serial_no) {
			fields.push({
				fieldname: `serial_no_${idx}`,
				fieldtype: "Small Text",
				label: __("Serial No(s)"),
				reqd: 1,
				description: __("One serial number per line"),
			});
		}

		if (uom_mismatch) {
			fields.push({
				fieldname: `cf_${idx}`,
				fieldtype: "Float",
				label: __(`Conversion Factor (1 ${req_uom} = ? ${stock_uom})`),
				default: default_cf,
				reqd: 1,
				description: default_cf && default_cf !== 1
					? __(`Pre-filled from UOM table. Adjust if this batch has a different weight.`)
					: __(`Enter how many ${stock_uom} equals 1 ${req_uom} for this specific batch.`),
			});
			// Placeholder for effective qty hint — updated live
			fields.push({
				fieldname: `eff_qty_${idx}`,
				fieldtype: "HTML",
				options: `<div id="eff_qty_${idx}" style="color:#555;font-size:12px;padding-bottom:4px">
					Effective qty: ${_fmt_eff_qty(item.quantity, default_cf, stock_uom)}
				</div>`,
			});
		}

		if (idx < stock_items.length - 1) {
			fields.push({ fieldname: `sec_${idx}`, fieldtype: "Section Break" });
		}
	});

	const dialog = new frappe.ui.Dialog({
		title: __("Transfer Stock to WIP"),
		fields,
		primary_action_label: __("Transfer"),
		primary_action(values) {
			const transfer_items = stock_items.map((item, idx) => {
				const info = item_map[item.item];
				const conv = conv_map[item.item] || {};
				const stock_uom = conv.stock_uom || info.stock_uom;
				const uom_mismatch = item.uom && stock_uom && item.uom !== stock_uom;
				return {
					item_code: item.item,
					qty: item.quantity,
					uom: item.uom || null,
					s_warehouse: values[`s_warehouse_${idx}`],
					batch_no: values[`batch_no_${idx}`] || null,
					serial_no: values[`serial_no_${idx}`] || null,
					conversion_factor: uom_mismatch ? (values[`cf_${idx}`] || 1) : 1,
				};
			});

			frm.call("transfer_materials", {
				wip_warehouse: values.wip_warehouse,
				items: transfer_items,
			}).then((r) => {
				if (!r.exc) {
					dialog.hide();
					frm.reload_doc();
				}
			});
		},
	});

	dialog.show();

	// Live-update effective qty hints when conversion factor changes
	stock_items.forEach((item, idx) => {
		const conv = conv_map[item.item] || {};
		const stock_uom = conv.stock_uom || item_map[item.item].stock_uom;
		const req_uom = item.uom;
		if (!req_uom || !stock_uom || req_uom === stock_uom) return;

		dialog.fields_dict[`cf_${idx}`].$input.on("input change", function () {
			const cf = parseFloat(this.value) || 0;
			const eff = cf ? `${(item.quantity * cf).toFixed(3)} ${stock_uom}` : "—";
			const el = document.getElementById(`eff_qty_${idx}`);
			if (el) el.textContent = `Effective qty: ${eff}`;
		});
	});
}

function _fmt_eff_qty(qty, cf, stock_uom) {
	if (!cf || cf === 1) return "";
	return `${((qty || 0) * cf).toFixed(3)} ${stock_uom}`;
}

function _show_start_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Start Operation"),
		fields: [
			{
				fieldname: "employee",
				fieldtype: "Link",
				label: __("Employee Starting Operation"),
				options: "Employee",
				reqd: 1,
			},
		],
		primary_action_label: __("Start"),
		primary_action(values) {
			frm.call("start_operation", { employee: values.employee })
				.then(() => {
					dialog.hide();
					frm.reload_doc();
				});
		},
	});
	dialog.show();
}

function _create_lab_analysis(frm) {
	const pending = (frm.doc.tasks || []).filter(
		(t) => t.task_type === "Lab Test" && !t.completed
	);

	if (!pending.length) {
		frappe.msgprint(__("No pending lab test tasks on this operation."));
		return;
	}

	const dialog = new frappe.ui.Dialog({
		title: __("Create Lab Analysis"),
		fields: [
			{
				fieldname: "task_name",
				fieldtype: "Select",
				label: __("Lab Test Task"),
				options: pending.map((t) => t.task_name).join("\n"),
				reqd: 1,
				description: __("Select which task this lab analysis fulfils"),
			},
		],
		primary_action_label: __("Create"),
		primary_action(values) {
			const task = pending.find((t) => t.task_name === values.task_name);
			frappe.new_doc("Lab Analysis", {
				cellar_operation: frm.doc.name,
				cellar_operation_task: values.task_name,
				wine_batch: frm.doc.wine_batch,
				expected_sample_size: task ? task.expected_sample_size : null,
				expected_sample_uom: task ? task.expected_sample_uom : null,
			});
			dialog.hide();
		},
	});
	dialog.show();
}
