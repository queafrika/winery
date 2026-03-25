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

		if (info.has_batch_no && !uom_mismatch) {
			// UOM-mismatch batch items use the HTML table below instead
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

		if (uom_mismatch && info.has_batch_no) {
			// Multi-batch: dynamic HTML table — one row per batch
			fields.push({
				fieldname: `batch_table_${idx}`,
				fieldtype: "HTML",
				options: `
					<table class="table table-bordered table-sm" style="margin-bottom:6px">
						<thead><tr>
							<th>${__("Batch No")}</th>
							<th style="width:140px">${stock_uom} ${__("Count")}</th>
							<th style="width:36px"></th>
						</tr></thead>
						<tbody class="bt-tbody"></tbody>
					</table>
					<button class="btn btn-xs btn-default bt-add" type="button">
						+ ${__("Add Row")}
					</button>
					<div class="bt-total" style="color:#555;font-size:12px;margin-top:6px">
						${__("Total")}: 0 ${stock_uom} (${__("represents")} ${item.quantity} ${req_uom})
					</div>`,
			});
		} else if (uom_mismatch) {
			// No batch tracking: single total stock-uom qty field
			const default_stock_qty = parseFloat(((item.quantity || 0) * default_cf).toFixed(3));
			fields.push({
				fieldname: `actual_qty_${idx}`,
				fieldtype: "Float",
				label: __(`Total ${stock_uom} to Transfer`),
				default: default_stock_qty || null,
				reqd: 1,
				description: __(`Enter the actual ${stock_uom} count being transferred. The system treats this as ${item.quantity} ${req_uom}.`),
			});
			fields.push({
				fieldname: `eff_qty_${idx}`,
				fieldtype: "HTML",
				options: `<div style="color:#555;font-size:12px;padding-bottom:4px">
					${__("Represents")}: ${item.quantity} ${req_uom}
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
			const transfer_items = [];
			let validation_failed = false;

			stock_items.forEach((item, idx) => {
				if (validation_failed) return;
				const info = item_map[item.item];
				const conv = conv_map[item.item] || {};
				const stock_uom = conv.stock_uom || info.stock_uom;
				const uom_mismatch = item.uom && stock_uom && item.uom !== stock_uom;
				const s_warehouse = values[`s_warehouse_${idx}`];

				if (uom_mismatch && info.has_batch_no) {
					// Multi-batch: read rows from the HTML table
					const tbody = dialog.fields_dict[`batch_table_${idx}`].$wrapper.find(".bt-tbody")[0];
					let has_entry = false;
					tbody.querySelectorAll("tr").forEach(row => {
						const batch_no = row.querySelector(".b-no").value.trim();
						const batch_qty = parseFloat(row.querySelector(".b-qty").value) || 0;
						if (!batch_no || !batch_qty) return;
						has_entry = true;
						transfer_items.push({
							item_code: item.item,
							qty: batch_qty,
							uom: stock_uom,
							s_warehouse,
							batch_no,
							conversion_factor: 1,
						});
					});
					if (!has_entry) {
						frappe.msgprint(__(
							`Please enter at least one batch and ${stock_uom} count for ${item.item}.`
						));
						validation_failed = true;
					}
				} else if (uom_mismatch) {
					// Single line, transact in stock_uom
					transfer_items.push({
						item_code: item.item,
						qty: parseFloat(values[`actual_qty_${idx}`]) || 0,
						uom: stock_uom,
						s_warehouse,
						batch_no: values[`batch_no_${idx}`] || null,
						serial_no: values[`serial_no_${idx}`] || null,
						conversion_factor: 1,
					});
				} else {
					// No UOM mismatch — original behaviour
					transfer_items.push({
						item_code: item.item,
						qty: item.quantity,
						uom: item.uom || null,
						s_warehouse,
						batch_no: values[`batch_no_${idx}`] || null,
						serial_no: values[`serial_no_${idx}`] || null,
						conversion_factor: 1,
					});
				}
			});

			if (validation_failed) return;

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

	// Init batch tables before show — fields_dict.$wrapper is populated during Dialog construction
	stock_items.forEach((item, idx) => {
		const info = item_map[item.item];
		const conv = conv_map[item.item] || {};
		const stock_uom = conv.stock_uom || info.stock_uom;
		const req_uom = item.uom;
		if (!req_uom || !stock_uom || req_uom === stock_uom) return;
		if (!info.has_batch_no) return;
		_init_batch_table(dialog, idx, item, stock_uom, req_uom);
	});

	dialog.show();
}

function _init_batch_table(dialog, idx, item, stock_uom, req_uom) {
	const $field = dialog.fields_dict[`batch_table_${idx}`].$wrapper;
	let availableBatches = [];

	function buildBatchOptions() {
		let html = `<option value="">— ${__("Select Batch")} —</option>`;
		availableBatches.forEach(b => {
			html += `<option value="${b.batch_no}">${b.batch_no} (${parseFloat(b.qty).toFixed(0)} ${stock_uom})</option>`;
		});
		return html;
	}

	function populateBatchSelects() {
		const optHtml = buildBatchOptions();
		$field.find(".b-no").each(function () {
			const cur = this.value;
			this.innerHTML = optHtml;
			if (cur) this.value = cur;  // restore selection if still valid
		});
	}

	function loadBatches(warehouse) {
		if (!warehouse) return;
		frappe.call({
			method: "winery.winery.doctype.cellar_operation.cellar_operation.get_batches_for_item_warehouse",
			args: { item_code: item.item, warehouse },
		}).then(r => {
			availableBatches = r.message || [];
			populateBatchSelects();
		});
	}

	// Watch the source warehouse field — df.onchange is called with this = field control
	const wfDict = dialog.fields_dict[`s_warehouse_${idx}`];
	if (wfDict) {
		const orig = wfDict.df.onchange;
		wfDict.df.onchange = function () {
			orig?.call(this);
			loadBatches(this.value);
		};
	}

	const tbody   = $field.find(".bt-tbody")[0];
	const totalEl = $field.find(".bt-total")[0];
	const addBtn  = $field.find(".bt-add")[0];

	function recalcTotal() {
		let total = 0;
		tbody.querySelectorAll(".b-qty").forEach(inp => {
			total += parseFloat(inp.value) || 0;
		});
		totalEl.textContent =
			`${__("Total")}: ${total.toFixed(0)} ${stock_uom} (${__("represents")} ${item.quantity} ${req_uom})`;
	}

	function addRow(removable) {
		const tr = document.createElement("tr");
		tr.innerHTML = `
			<td>
				<select class="form-control form-control-sm b-no">
					<option value="">— ${__("Select Batch")} —</option>
				</select>
			</td>
			<td>
				<input type="number" class="form-control form-control-sm b-qty"
				       placeholder="0" min="0" step="1">
			</td>
			<td style="text-align:center;vertical-align:middle">
				${removable
					? `<button class="btn btn-xs btn-danger rm-row" type="button"
					           style="line-height:1;padding:2px 7px">&times;</button>`
					: ""}
			</td>`;
		tbody.appendChild(tr);
		tr.querySelector(".b-no").innerHTML = buildBatchOptions();
		tr.querySelector(".b-qty").addEventListener("input", recalcTotal);
		if (removable) {
			tr.querySelector(".rm-row").addEventListener("click", () => {
				tr.remove();
				recalcTotal();
			});
		}
	}

	addRow(false);  // first row is non-removable
	addBtn.addEventListener("click", () => addRow(true));
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
				test_type: task ? task.test_type : null,
				analysis_date: frappe.datetime.get_today(),
				analyzed_by: frappe.session.user,
				expected_sample_size: task ? task.expected_sample_size : null,
				expected_sample_uom: task ? task.expected_sample_uom : null,
			});
			dialog.hide();
		},
	});
	dialog.show();
}
