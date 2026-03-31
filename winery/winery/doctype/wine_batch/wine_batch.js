// Copyright (c) 2026, Finesoft Afrika and contributors
// For license information, please see license.txt

let _recalc_timer = null;

frappe.ui.form.on("Wine Batch", {
	recipe(frm) {
		_debounced_recalculate(frm);
	},

	target_batch_size(frm) {
		_debounced_recalculate(frm);
	},

	abv_percentage(frm) {
		if (!frm.doc.abv_percentage) {
			frm.set_value("abv_tax_band", null);
			frm.set_value("excise_duty_per_litre", 0);
			return;
		}
		frappe.call({
			method: "winery.winery.doctype.wine_batch.wine_batch.get_abv_tax_band",
			args: { abv_percentage: frm.doc.abv_percentage },
			callback(r) {
				if (r.message && r.message.name) {
					frm.set_value("abv_tax_band", r.message.name);
					frm.set_value("excise_duty_per_litre", r.message.excise_duty_per_litre);
				} else {
					frm.set_value("abv_tax_band", null);
					frm.set_value("excise_duty_per_litre", 0);
					frappe.msgprint(__("No ABV Tax Band found for {0}% ABV. Please configure ABV Tax Bands in Setup.", [frm.doc.abv_percentage]));
				}
			},
		});
	},

	refresh(frm) {
		frm.get_field("required_materials").grid.cannot_add_rows = true;
		frm.get_field("required_materials").grid.cannot_delete_rows = true;

		if (frm.doc.recipe && !frm.is_new()) {
			_show_progress(frm);
		}

		_fetch_and_render_availability(frm);

		frm.add_custom_button(__("View Cellar Operations"), () => {
			frappe.set_route("List", "Cellar Operation", { wine_batch: frm.doc.name });
		});

		frm.add_custom_button(__("View Lab Analyses"), () => {
			frappe.set_route("List", "Lab Analysis", { wine_batch: frm.doc.name });
		});

		if (frm.doc.docstatus === 1 && !frm.is_new()) {
			frm.add_custom_button(__("New Rebottling"), () => {
				frappe.new_doc("Wine Batch Rebottling", { wine_batch: frm.doc.name });
			}).addClass("btn-warning");

			frm.add_custom_button(__("View Rebottlings"), () => {
				frappe.set_route("List", "Wine Batch Rebottling", { wine_batch: frm.doc.name });
			});
		}

		if (frm.doc.docstatus === 1 && !frm.is_new()) {
			_render_cellar_ops_tab(frm);
			_render_lab_analyses_tab(frm);
			_render_bottling_buttons(frm);
		}
	},
});

// ─────────────────────────────────────────────────────────────────────────────
// Cellar Operations Tab — Column View
// ─────────────────────────────────────────────────────────────────────────────

async function _render_cellar_ops_tab(frm) {
	const html_field = frm.get_field("cellar_ops_html");
	if (!html_field) return;

	const $wrapper = html_field.$wrapper;
	$wrapper.html(`<div class="text-muted p-3">${__("Loading operations…")}</div>`);

	// 1. Fetch all Cellar Operations for this batch first
	const cellar_ops = await frappe.db.get_list("Cellar Operation", {
		filters: { wine_batch: frm.doc.name, docstatus: ["!=", 2] },
		fields: [
			"name", "operation_type", "status", "vessel", "supervisor",
			"start_time", "expected_end_time", "end_time", "duration",
			"transfer_entry", "recipe_stage_idx",
		],
		order_by: "recipe_stage_idx asc",
		limit: 20,
	});

	// 2. Build ordered_ops from Recipe Stage — the complete ordered list of all stages
	const recipe = await frappe.db.get_doc("Recipe", frm.doc.recipe).catch(() => null);
	const ordered_ops = [];

	if (recipe && recipe.stages && recipe.stages.length) {
		[...recipe.stages]
			.sort((a, b) => (a.idx || 0) - (b.idx || 0))
			.forEach((s) => {
				if (s.operation_type && !ordered_ops.includes(s.operation_type))
					ordered_ops.push(s.operation_type);
			});
	}

	// Add any existing cellar operations not already in ordered_ops (preserves existing batches)
	cellar_ops.forEach((co) => {
		if (co.operation_type && !ordered_ops.includes(co.operation_type)) {
			ordered_ops.push(co.operation_type);
		}
	});

	if (!ordered_ops.length) {
		$wrapper.html(`<div class="text-muted p-3">${__("No operations found for this batch.")}</div>`);
		return;
	}

	// Map operation_type → cellar operation record
	const co_map = {};
	cellar_ops.forEach((co) => { co_map[co.operation_type] = co; });

	// 3. Build columns HTML
	const next_stage = (frm.doc.current_stage_number || 0) + 1;

	let cols_html = `
		<style>
			.co-col-row { display: flex; gap: 12px; overflow-x: auto; padding: 12px 4px 16px; }
			.co-card {
				flex: 1 1 0; min-width: 180px; max-width: 260px;
				border: 1px solid var(--border-color, #d1d8dd);
				border-radius: 8px; overflow: hidden;
				display: flex; flex-direction: column;
				background: var(--card-bg, #fff);
			}
			.co-card-header {
				padding: 10px 12px 8px;
				border-bottom: 1px solid var(--border-color, #d1d8dd);
				background: var(--subtle-fg, #f5f7fa);
			}
			.co-card-header .op-name {
				font-weight: 600; font-size: 13px;
				white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
			}
			.co-card-body { padding: 10px 12px; flex: 1; font-size: 12px; }
			.co-row { display: flex; justify-content: space-between; margin-bottom: 4px; gap: 6px; }
			.co-row .co-label { color: var(--text-muted, #8d99a6); white-space: nowrap; }
			.co-row .co-val { font-weight: 500; text-align: right; word-break: break-word; }
			.co-card-footer { padding: 8px 12px 10px; display: flex; flex-direction: column; gap: 6px; }
			.co-card-footer .btn { font-size: 11px; padding: 3px 10px; width: 100%; }
			.badge-not-started { background: #e4e9ed; color: #6c7a89; }
		</style>
		<div class="co-col-row">
	`;

	ordered_ops.forEach((op_type, i) => {
		const co = co_map[op_type] || null;
		const stage_num = i + 1;
		const is_next = stage_num === next_stage;
		cols_html += _build_op_card(op_type, co, is_next, stage_num, frm);
	});

	cols_html += `</div>`;
	$wrapper.html(cols_html);

	// 4. Bind button click handlers
	_bind_cellar_op_buttons(frm);
}

function _build_op_card(op_type, co, is_next, stage_num) {
	const status = co ? co.status : null;
	const badge = _status_badge(status, is_next);
	const co_name = co ? co.name : null;

	// Body rows
	let body = "";
	if (co) {
		if (co.vessel) body += _co_row("Vessel", co.vessel);
		if (co.start_time) body += _co_row("Started", frappe.datetime.str_to_user(co.start_time));
		if (co.expected_end_time && status !== "Completed")
			body += _co_row("Exp. End", frappe.datetime.str_to_user(co.expected_end_time));
		if (co.end_time) body += _co_row("Ended", frappe.datetime.str_to_user(co.end_time));
		if (co.duration) body += _co_row("Duration", `${flt(co.duration, 1)} hrs`);
		if (co.supervisor) body += _co_row("Supervisor", co.supervisor.split("@")[0]);
	} else {
		body = `<div class="text-muted" style="font-size:11px;font-style:italic">${__("Not yet created")}</div>`;
	}

	// Footer buttons
	let footer = "";
	if (!co && is_next) {
		footer = `<button class="btn btn-primary btn-xs co-btn-create" data-op="${op_type}">
			${__("▶ Create Stage")}
		</button>`;
	} else if (!co) {
		footer = `<div class="text-muted" style="font-size:11px;text-align:center;padding:4px 0">
			${__("Complete prior stages first")}
		</div>`;
	} else if (status === "Planned") {
		if (!co.transfer_entry) {
			footer = `
				<button class="btn btn-warning btn-xs co-btn-transfer" data-name="${co_name}">
					${__("Transfer Stock")}
				</button>
				<button class="btn btn-default btn-xs co-btn-start" data-name="${co_name}">
					${__("Start")}
				</button>`;
		} else {
			footer = `<button class="btn btn-primary btn-xs co-btn-start" data-name="${co_name}">
				${__("▶ Start")}
			</button>`;
		}
	} else if (status === "In Progress") {
		footer = `
			<button class="btn btn-success btn-xs co-btn-complete" data-name="${co_name}">
				${__("✓ Complete")}
			</button>
			<button class="btn btn-default btn-xs co-btn-lab" data-name="${co_name}">
				${__("+ Lab Analysis")}
			</button>`;
	} else if (status === "Completed" || status === "Cancelled") {
		footer = `<button class="btn btn-default btn-xs co-btn-view" data-name="${co_name}">
			${__("View →")}
		</button>`;
	}

	return `
		<div class="co-card">
			<div class="co-card-header">
				<div class="op-name" title="${frappe.utils.escape_html(op_type)}">${stage_num}. ${frappe.utils.escape_html(op_type)}</div>
				<div style="margin-top:4px">${badge}</div>
			</div>
			<div class="co-card-body">${body}</div>
			<div class="co-card-footer">${footer}</div>
		</div>`;
}

function _co_row(label, value) {
	return `<div class="co-row">
		<span class="co-label">${__(label)}</span>
		<span class="co-val">${frappe.utils.escape_html(String(value))}</span>
	</div>`;
}

function _status_badge(status, is_next) {
	const map = {
		"Planned":     ["secondary", "Planned"],
		"In Progress": ["warning",   "In Progress"],
		"Completed":   ["success",   "Completed"],
		"Cancelled":   ["danger",    "Cancelled"],
	};
	if (!status) {
		return is_next
			? `<span class="badge badge-primary">${__("Next Up")}</span>`
			: `<span class="badge badge-not-started">${__("Waiting")}</span>`;
	}
	const [cls, label] = map[status] || ["secondary", status];
	return `<span class="badge badge-${cls}">${__(label)}</span>`;
}

function _bind_cellar_op_buttons(frm) {
	const $wrapper = frm.get_field("cellar_ops_html").$wrapper;

	// Create Stage
	$wrapper.find(".co-btn-create").on("click", function () {
		frappe.call({
			method: "winery.winery.doctype.wine_batch.wine_batch.start_next_stage",
			args: { name: frm.doc.name },
			btn: $(this),
			callback(r) {
				if (!r.exc) frm.reload_doc();
			},
		});
	});

	// Transfer Stock → open dialog inline
	$wrapper.find(".co-btn-transfer").on("click", function () {
		_show_co_transfer_dialog($(this).data("name"), frm);
	});

	// Start Operation
	$wrapper.find(".co-btn-start").on("click", function () {
		const co_name = $(this).data("name");
		const dialog = new frappe.ui.Dialog({
			title: __("Start Operation"),
			fields: [{
				fieldname: "employee",
				fieldtype: "Link",
				label: __("Employee Starting Operation"),
				options: "Employee",
				reqd: 1,
			}],
			primary_action_label: __("Start"),
			primary_action(values) {
				frappe.call({
					method: "winery.winery.doctype.cellar_operation.cellar_operation.start_cellar_operation",
					args: { name: co_name, employee: values.employee },
					callback(r) {
						if (!r.exc) { dialog.hide(); frm.reload_doc(); }
					},
				});
			},
		});
		dialog.show();
	});

	// Complete Operation
	$wrapper.find(".co-btn-complete").on("click", function () {
		const co_name = $(this).data("name");
		frappe.confirm(
			__("Mark this operation as complete? All mandatory lab analyses must be submitted."),
			() => {
				frappe.call({
					method: "winery.winery.doctype.cellar_operation.cellar_operation.complete_cellar_operation",
					args: { name: co_name },
					callback(r) {
						if (!r.exc) frm.reload_doc();
					},
				});
			}
		);
	});

	// New Lab Analysis
	$wrapper.find(".co-btn-lab").on("click", function () {
		_create_lab_analysis_for_op($(this).data("name"), frm.doc.name);
	});

	// View Cellar Operation
	$wrapper.find(".co-btn-view").on("click", function () {
		frappe.set_route("Form", "Cellar Operation", $(this).data("name"));
	});
}

// ─────────────────────────────────────────────────────────────────────────────
// Materials recalculation
// ─────────────────────────────────────────────────────────────────────────────

function _debounced_recalculate(frm) {
	if (_recalc_timer) clearTimeout(_recalc_timer);
	_recalc_timer = setTimeout(() => _recalculate_materials(frm), 300);
}

function _recalculate_materials(frm) {
	if (!frm.doc.recipe || !frm.doc.target_batch_size) return;

	frappe.db.get_doc("Recipe", frm.doc.recipe).then((recipe) => {
		if (!recipe.base_batch_size || !recipe.raw_materials || !recipe.raw_materials.length) return;

		const scale = frm.doc.target_batch_size / recipe.base_batch_size;

		frm.set_intro(
			`Recipe base: <b>${recipe.base_batch_size} ${recipe.base_uom}</b> — ` +
			`Target: <b>${frm.doc.target_batch_size} ${frm.doc.target_uom || recipe.base_uom}</b> — ` +
			`Scale factor: <b>${scale.toFixed(2)}×</b> — All material quantities scaled automatically.`,
			"blue"
		);

		frm.clear_table("required_materials");
		recipe.raw_materials.forEach((row) => {
			frm.add_child("required_materials", {
				stage_name: row.stage_name,
				item: row.item,
				quantity: flt(row.quantity * scale, 3),
				uom: row.uom,
				notes: row.notes,
			});
		});
		frm.refresh_field("required_materials");
	});
}

// ─────────────────────────────────────────────────────────────────────────────
// Progress bar
// ─────────────────────────────────────────────────────────────────────────────

function _show_progress(frm) {
	if (!frm.doc.recipe) return;

	frappe.db.get_doc("Recipe", frm.doc.recipe).then((recipe) => {
		const ops = (recipe.lab_analyses || []).map((r) => r.operation_type).filter(Boolean);
		const total = new Set(ops).size;
		const current = frm.doc.current_stage_number || 0;
		const pct = total > 0 ? Math.round((current / total) * 100) : 0;

		frm.dashboard.add_progress(
			__("Production Progress: Stage {0} of {1}", [current, total]),
			pct
		);
	});
}

// ─────────────────────────────────────────────────────────────────────────────
// ─────────────────────────────────────────────────────────────────────────────
// Bottling & Packaging child table calculations
// ─────────────────────────────────────────────────────────────────────────────

frappe.ui.form.on("Wine Batch Bottling Line", {
	planned_bottles(frm, cdt, cdn) { _recalc_bottling_line(frm, cdt, cdn); },
	bottle_size_ml(frm, cdt, cdn)  { _recalc_bottling_line(frm, cdt, cdn); },
});

function _recalc_bottling_line(_frm, cdt, cdn) {
	const row      = locals[cdt][cdn];
	const size     = cint(row.bottle_size_ml);
	const planned  = cint(row.planned_bottles);
	const planned_vol = Math.round(planned * size / 1000 * 10000) / 10000;
	frappe.model.set_value(cdt, cdn, "planned_volume_litres", planned_vol);
}

frappe.ui.form.on("Wine Batch Packaging Line", {
	bottle_size_ml(frm, cdt, cdn) {
		_autocalc_cartons(frm, cdt, cdn);
		_validate_packaging_balance(frm);
	},
	bottles_per_carton(frm, cdt, cdn) {
		_autocalc_cartons(frm, cdt, cdn);
		_validate_packaging_balance(frm);
	},
	cartons(frm, cdt, cdn) {
		_recalc_packaging_planned(frm, cdt, cdn);
		_validate_packaging_balance(frm);
	},
});

function _autocalc_cartons(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const sz  = cint(row.bottle_size_ml);
	const bpc = cint(row.bottles_per_carton);
	if (!sz || !bpc) return;

	// Sum planned_bottles from all bottling lines with matching bottle_size_ml
	let total_planned = 0;
	(frm.doc.bottling_lines || []).forEach(bl => {
		if (cint(bl.bottle_size_ml) === sz) total_planned += cint(bl.planned_bottles);
	});

	const cartons = Math.floor(total_planned / bpc);
	frappe.model.set_value(cdt, cdn, "cartons", cartons);
	frappe.model.set_value(cdt, cdn, "total_bottles", cartons * bpc);
}

function _recalc_packaging_planned(_frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "total_bottles",
		cint(row.cartons) * cint(row.bottles_per_carton));
}

function _validate_packaging_balance(frm) {
	const planned = {};
	(frm.doc.bottling_lines || []).forEach(r => {
		if (r.bottle_size_ml)
			planned[r.bottle_size_ml] = (planned[r.bottle_size_ml] || 0) + cint(r.planned_bottles);
	});
	const packaged = {};
	(frm.doc.packaging_lines || []).forEach(r => {
		if (r.bottle_size_ml)
			packaged[r.bottle_size_ml] = (packaged[r.bottle_size_ml] || 0) + cint(r.total_bottles);
	});
	const mismatches = Object.keys(packaged).filter(sz => packaged[sz] !== (planned[sz] || 0));
	if (mismatches.length) {
		const msgs = mismatches.map(sz =>
			`${sz}ml: planned ${planned[sz] || 0} bottles, packaging covers ${packaged[sz]} bottles`
		);
		frappe.show_alert({
			message: __("Packaging balance mismatch: ") + msgs.join("; "),
			indicator: "orange",
		});
	}
}

// ─────────────────────────────────────────────────────────────────────────────
// Bottling & Packaging action buttons
// ─────────────────────────────────────────────────────────────────────────────

function _render_bottling_buttons(frm) {
	const status = frm.doc.bottling_status;

	if (status === "Completed") {
		if (frm.doc.bottling_stock_entry) {
			const se_names = frm.doc.bottling_stock_entry.trim().split("\n").filter(Boolean);
			if (se_names.length === 1) {
				frm.add_custom_button(__("View Stock Entry"), () =>
					frappe.set_route("Form", "Stock Entry", se_names[0])
				).addClass("btn-info");
			} else {
				frm.add_custom_button(__("View Stock Entries"), () => {
					const links = se_names.map(n =>
						`<li><a href="/app/stock-entry/${n}" target="_blank">${n}</a></li>`
					).join("");
					frappe.msgprint({
						title: __("Bottling Stock Entries"),
						message: `<ul>${links}</ul>`,
					});
				}).addClass("btn-info");
			}
		}
		frm.add_custom_button(__("Cancel Bottling"), () => {
			frappe.confirm(
				__("Cancel Bottling & Packaging? This will cancel the stock entry and revert the batch to Active."),
				() => frappe.call({
					method: "winery.winery.doctype.wine_batch.wine_batch.cancel_bottling",
					args: { wine_batch: frm.doc.name },
					callback() { frm.reload_doc(); },
				})
			);
		}).addClass("btn-danger");
		return;
	}

	frappe.db.get_list("Cellar Operation", {
		filters: { wine_batch: frm.doc.name, docstatus: 1 },
		fields: ["name", "status"],
	}).then((ops) => {
		if (!ops.length || !ops.every(op => op.status === "Completed")) return;

		// Complete Bottling (or Re-enter)
		if (status === "Pending" || status === "Bottling Completed") {
			const label = status === "Bottling Completed"
				? __("Re-enter Bottling Details") : __("Complete Bottling");
			frm.add_custom_button(label, () => _show_bottling_modal(frm))
				.addClass("btn-primary");
		}

		// Complete Packaging (or Re-enter) + Reset
		if (status === "Bottling Completed" || status === "Packaging Completed") {
			const plabel = status === "Packaging Completed"
				? __("Re-enter Packaging Details") : __("Complete Packaging");
			frm.add_custom_button(plabel, () => _show_packaging_modal(frm))
				.addClass("btn-primary");

			frm.add_custom_button(__("Reset to Planning"), () => {
				frappe.confirm(__("Clear all bottling/packaging actuals and return to Planning?"), () =>
					frappe.call({
						method: "winery.winery.doctype.wine_batch.wine_batch.reset_bottling_actuals",
						args: { wine_batch: frm.doc.name },
						callback() { frm.reload_doc(); },
					})
				);
			}).addClass("btn-danger");
		}

		// Close Wine Batch
		if (status === "Packaging Completed") {
			frm.add_custom_button(__("Close Wine Batch"), () => {
				frappe.confirm(
					__("Create Stock Entry and complete this wine batch?"),
					() => frappe.call({
						method: "winery.winery.doctype.wine_batch.wine_batch.close_wine_batch",
						args: { wine_batch: frm.doc.name },
						callback(r) { if (r.message) frm.reload_doc(); },
					})
				);
			}).addClass("btn-success");
		}
	});
}

function _show_bottling_modal(frm) {
	const lines = frm.doc.bottling_lines || [];
	if (!lines.length) {
		frappe.msgprint(__("Please add Bottling Lines before completing bottling."));
		return;
	}

	const fields = [
		{
			label: __("Bottling Date"), fieldname: "bottling_date",
			fieldtype: "Date", reqd: 1,
			default: frm.doc.bottling_date || frappe.datetime.get_today(),
		},
		{
			label: __("ABV (%)"), fieldname: "abv_percentage",
			fieldtype: "Float", reqd: 1,
			default: frm.doc.abv_percentage || 0,
		},
	];

	lines.forEach((row, i) => {
		fields.push({
			label: `${row.bottle_item || "Line " + (i + 1)} — ${row.bottle_size_ml}ml — Planned: ${row.planned_bottles} bottles`,
			fieldtype: "Section Break",
			fieldname: `section_line_${i}`,
		});
		fields.push({
			label: __("Actual Bottles"), fieldname: `actual_bottles_${i}`,
			fieldtype: "Int", reqd: 1, default: row.actual_bottles || 0,
		});
		fields.push({
			label: __("Bottled Wine Item"), fieldname: `bottled_wine_item_${i}`,
			fieldtype: "Link", options: "Item",
			description: __("Filled bottle item — used for samples and remainder stock"),
			default: row.bottled_wine_item || "",
		});
		fields.push({ fieldtype: "Column Break", fieldname: `col_${i}_1` });
		fields.push({
			label: __("QC Bottles Reserved"), fieldname: `qc_bottles_${i}`,
			fieldtype: "Int", default: row.qc_bottles || 0,
		});
		fields.push({
			label: __("Sample Bottles"), fieldname: `sample_bottles_${i}`,
			fieldtype: "Int", default: row.sample_bottles != null ? row.sample_bottles : 1,
		});
		fields.push({
			label: __("Bottle Warehouse"), fieldname: `bottle_source_warehouse_${i}`,
			fieldtype: "Link", options: "Warehouse", reqd: 1,
			default: row.bottle_source_warehouse || "",
		});
		fields.push({
			label: __("Sealing Item"), fieldname: `sealing_item_${i}`,
			fieldtype: "Link", options: "Item",
			default: row.sealing_item || "",
		});
		fields.push({
			label: __("Sealing Warehouse"), fieldname: `sealing_source_warehouse_${i}`,
			fieldtype: "Link", options: "Warehouse",
			default: row.sealing_source_warehouse || "",
			depends_on: `eval:doc.sealing_item_${i}`,
		});
	});

	const d = new frappe.ui.Dialog({
		title: __("Complete Bottling"),
		fields,
		primary_action_label: __("Save Bottling Actuals"),
		primary_action(values) {
			const bottling_lines = lines.map((row, i) => ({
				name: row.name,
				actual_bottles: values[`actual_bottles_${i}`] || 0,
				bottled_wine_item: values[`bottled_wine_item_${i}`] || "",
				qc_bottles: values[`qc_bottles_${i}`] || 0,
				sample_bottles: values[`sample_bottles_${i}`] != null ? values[`sample_bottles_${i}`] : 1,
				bottle_source_warehouse: values[`bottle_source_warehouse_${i}`] || "",
				sealing_item: values[`sealing_item_${i}`] || "",
				sealing_source_warehouse: values[`sealing_source_warehouse_${i}`] || "",
			}));

			frappe.call({
				method: "winery.winery.doctype.wine_batch.wine_batch.submit_bottling_actuals",
				args: {
					wine_batch: frm.doc.name,
					bottling_date: values.bottling_date,
					abv_percentage: values.abv_percentage,
					lines: JSON.stringify(bottling_lines),
				},
				callback(r) {
					if (!r.exc) {
						d.hide();
						frm.reload_doc();
					}
				},
			});
		},
	});
	d.show();
}

function _show_packaging_modal(frm) {
	const lines = frm.doc.packaging_lines || [];
	if (!lines.length) {
		frappe.msgprint(__("Please add Packaging Lines before completing packaging."));
		return;
	}

	const fields = [];
	lines.forEach((row, i) => {
		fields.push({
			label: `${row.pack_size || "Line " + (i + 1)} — ${row.bottle_size_ml}ml — Planned: ${row.cartons} cartons`,
			fieldtype: "Section Break",
			fieldname: `section_pkg_${i}`,
		});
		fields.push({
			label: __("Actual Cartons"), fieldname: `actual_cartons_${i}`,
			fieldtype: "Int", reqd: 1, default: row.actual_cartons || 0,
		});
		fields.push({ fieldtype: "Column Break", fieldname: `col_pkg_${i}` });
		fields.push({
			label: __("Output Item"), fieldname: `output_item_${i}`,
			fieldtype: "Link", options: "Item", reqd: 1,
			default: row.output_item || "",
		});
		fields.push({
			label: __("Output Warehouse"), fieldname: `output_warehouse_${i}`,
			fieldtype: "Link", options: "Warehouse", reqd: 1,
			default: row.output_warehouse || "",
		});
	});

	const d = new frappe.ui.Dialog({
		title: __("Complete Packaging"),
		fields,
		primary_action_label: __("Save Packaging Actuals"),
		primary_action(values) {
			const packaging_lines = lines.map((row, i) => ({
				name: row.name,
				actual_cartons: values[`actual_cartons_${i}`] || 0,
				output_item: values[`output_item_${i}`] || "",
				output_warehouse: values[`output_warehouse_${i}`] || "",
			}));

			frappe.call({
				method: "winery.winery.doctype.wine_batch.wine_batch.submit_packaging_actuals",
				args: {
					wine_batch: frm.doc.name,
					lines: JSON.stringify(packaging_lines),
				},
				callback(r) {
					if (!r.exc) {
						d.hide();
						frm.reload_doc();
					}
				},
			});
		},
	});
	d.show();
}

// ─────────────────────────────────────────────────────────────────────────────
// Lab Analyses Tab
// ─────────────────────────────────────────────────────────────────────────────

async function _render_lab_analyses_tab(frm) {
	const html_field = frm.get_field("lab_analyses_html");
	if (!html_field) return;

	const $wrapper = html_field.$wrapper;
	$wrapper.html(`<div class="text-muted p-3">${__("Loading analyses…")}</div>`);

	const [analyses, cellar_ops] = await Promise.all([
		frappe.db.get_list("Lab Analysis", {
			filters: { wine_batch: frm.doc.name, docstatus: ["!=", 2] },
			fields: [
				"name", "test_type", "analysis_date", "analyzed_by",
				"cellar_operation", "docstatus",
				// average / result fields — one per test type
				"rs_residual_sugar_gl",
				"brix_average",
				"average_gravity",
				"abv_corrected_abv",
				"temp_reading_1",
				"ph_average",
				"diss_clarity_white_bg",
				"sens_balance",
			],
			order_by: "analysis_date asc",
			limit: 100,
		}),
		frappe.db.get_list("Cellar Operation", {
			filters: { wine_batch: frm.doc.name, docstatus: ["!=", 2] },
			fields: ["name", "operation_type", "status", "recipe_stage_idx"],
			order_by: "recipe_stage_idx asc",
			limit: 20,
		}),
	]);

	if (!cellar_ops.length && !analyses.length) {
		$wrapper.html(`<div class="text-muted p-3">${__("No lab analyses found for this batch.")}</div>`);
		return;
	}

	// Group analyses by cellar_operation name
	const by_op = {};
	analyses.forEach((la) => {
		const key = la.cellar_operation || "__none__";
		if (!by_op[key]) by_op[key] = [];
		by_op[key].push(la);
	});

	let html = `<style>
		.la-section { margin-bottom: 20px; padding: 4px; }
		.la-section-header {
			font-weight: 600; font-size: 13px; padding: 6px 4px;
			border-bottom: 2px solid var(--border-color, #d1d8dd);
			margin-bottom: 10px; color: var(--heading-color);
		}
		.la-cards { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-start; }
		.la-card {
			width: 180px; border: 1px solid var(--border-color, #d1d8dd);
			border-radius: 8px; overflow: hidden;
			background: var(--card-bg, #fff); font-size: 12px;
		}
		.la-card-header {
			padding: 8px 10px; background: var(--subtle-fg, #f5f7fa);
			border-bottom: 1px solid var(--border-color, #d1d8dd);
			font-weight: 600; font-size: 12px; word-break: break-word;
		}
		.la-card-body { padding: 8px 10px; }
		.la-row { display: flex; justify-content: space-between; margin-bottom: 3px; gap: 4px; }
		.la-label { color: var(--text-muted, #8d99a6); white-space: nowrap; }
		.la-val { font-weight: 500; text-align: right; word-break: break-word; }
		.la-card-footer { padding: 6px 10px 8px; }
		.la-card-footer .btn { font-size: 11px; padding: 2px 8px; width: 100%; }
		.la-new-wrap { display: flex; align-items: flex-end; padding-bottom: 8px; }
	</style><div class="la-wrapper p-3">`;

	cellar_ops.forEach((co, i) => {
		const op_analyses = by_op[co.name] || [];
		html += `<div class="la-section">
			<div class="la-section-header">${i + 1}. ${frappe.utils.escape_html(co.operation_type)}
				<span style="font-weight:400;color:var(--text-muted)">(${__(co.status)})</span>
			</div>
			<div class="la-cards">`;

		if (!op_analyses.length) {
			html += `<div class="text-muted" style="font-size:11px;font-style:italic;padding:4px 0">${__("No analyses yet")}</div>`;
		} else {
			op_analyses.forEach((la) => { html += _build_la_card(la); });
		}

		if (co.status === "In Progress") {
			html += `<div class="la-new-wrap">
				<button class="btn btn-default btn-xs la-btn-new" data-co="${co.name}">
					${__("+ New Analysis")}
				</button>
			</div>`;
		}

		html += `</div></div>`;
	});

	// Unlinked analyses
	const unlinked = by_op["__none__"] || [];
	if (unlinked.length) {
		html += `<div class="la-section">
			<div class="la-section-header">${__("Other Analyses")}</div>
			<div class="la-cards">`;
		unlinked.forEach((la) => { html += _build_la_card(la); });
		html += `</div></div>`;
	}

	html += `</div>`;
	$wrapper.html(html);

	$wrapper.find(".la-btn-view").on("click", function () {
		frappe.set_route("Form", "Lab Analysis", $(this).data("name"));
	});
	$wrapper.find(".la-btn-new").on("click", function () {
		_create_lab_analysis_for_op($(this).data("co"), frm.doc.name);
	});
}

function _build_la_card(la) {
	const badge = _la_status_badge(la.docstatus);
	const date_str = la.analysis_date
		? frappe.datetime.str_to_user(la.analysis_date)
		: "—";
	const analyst = la.analyzed_by ? la.analyzed_by.split("@")[0] : "—";
	const { label: avg_label, value: avg_value } = _la_average(la);

	const avg_row = avg_label
		? `<div class="la-row">
			<span class="la-label">${avg_label}</span>
			<span class="la-val">${frappe.utils.escape_html(String(avg_value ?? "—"))}</span>
		</div>`
		: "";

	return `<div class="la-card">
		<div class="la-card-header">${frappe.utils.escape_html(la.test_type || __("Unknown"))}</div>
		<div class="la-card-body">
			<div class="la-row">
				<span class="la-label">${__("Date")}</span>
				<span class="la-val">${frappe.utils.escape_html(date_str)}</span>
			</div>
			<div class="la-row">
				<span class="la-label">${__("By")}</span>
				<span class="la-val">${frappe.utils.escape_html(analyst)}</span>
			</div>
			${avg_row}
			<div class="la-row">
				<span class="la-label">${__("Status")}</span>
				<span class="la-val">${badge}</span>
			</div>
		</div>
		<div class="la-card-footer">
			<button class="btn btn-default btn-xs la-btn-view" data-name="${la.name}">${__("View →")}</button>
		</div>
	</div>`;
}

function _la_average(la) {
	switch (la.test_type) {
		case "Residual Sugar Test":
			return { label: __("RS (g/L)"), value: la.rs_residual_sugar_gl ?? "—" };
		case "Brix Test":
			return { label: __("Avg (°Brix)"), value: la.brix_average ?? "—" };
		case "Gravity Test":
			return { label: __("Avg Gravity"), value: la.average_gravity ?? "—" };
		case "ABV Test":
			return { label: __("ABV (%)"), value: la.abv_corrected_abv ?? "—" };
		case "Temperature Test":
			return { label: __("Temp (°C)"), value: la.temp_reading_1 ?? "—" };
		case "pH Test":
			return { label: __("Avg pH"), value: la.ph_average ?? "—" };
		case "Dissolution Test":
			return { label: __("Clarity"), value: la.diss_clarity_white_bg ?? "—" };
		case "Sensory Evaluation":
			return { label: __("Balance"), value: la.sens_balance ?? "—" };
		default:
			return { label: null, value: null };
	}
}

function _la_status_badge(docstatus) {
	if (String(docstatus) === "0") {
		return `<span class="badge badge-secondary">${__("Draft")}</span>`;
	}
	return `<span class="badge badge-success">${__("Submitted")}</span>`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Lab Analysis creation helper (shared by both tabs)
// ─────────────────────────────────────────────────────────────────────────────

function _create_lab_analysis_for_op(co_name, wine_batch) {
	frappe.db.get_doc("Cellar Operation", co_name).then((co) => {
		const pending = (co.tasks || []).filter(
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
					cellar_operation: co_name,
					cellar_operation_task: values.task_name,
					wine_batch: wine_batch,
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
	});
}

// ─────────────────────────────────────────────────────────────────────────────
// Transfer to WIP dialog — launched inline from the Wine Batch view
// ─────────────────────────────────────────────────────────────────────────────

function _show_co_transfer_dialog(co_name, wine_batch_frm) {
	frappe.db.get_doc("Cellar Operation", co_name).then((co_doc) => {
		const raw_items = (co_doc.details || []).filter((r) => r.item);
		if (!raw_items.length) {
			frappe.msgprint(__("No materials listed for this operation."));
			return;
		}

		const item_codes = [...new Set(raw_items.map((r) => r.item))];

		// Fetch item master data and Winery Settings in parallel
		Promise.all([
			frappe.db.get_list("Item", {
				filters: [["name", "in", item_codes]],
				fields: ["name", "is_stock_item", "has_batch_no", "has_serial_no",
				         "stock_uom", "has_variants", "variant_of"],
				limit: item_codes.length,
			}),
			frappe.db.get_single_value("Winery Settings", "ripe_banana_finger_template"),
		]).then(([item_data, ripe_tpl]) => {
			const item_map = {};
			item_data.forEach((d) => { item_map[d.name] = d; });

			const stock_items = raw_items.filter(
				(r) => item_map[r.item] && item_map[r.item].is_stock_item
			);
			if (!stock_items.length) {
				frappe.msgprint(__("None of the listed materials are stock items. No transfer needed."));
				return;
			}

			// For each item, resolve UOM conversion.
			// The banana template uses a hardcoded 1 Kg = 100 Nos factor.
			const conversion_promises = stock_items.map((item) => {
				const info = item_map[item.item];
				const stock_uom = info.stock_uom;
				const req_uom = item.uom;
				const is_banana = ripe_tpl && item.item === ripe_tpl;

				if (is_banana && req_uom === "Kg" && stock_uom === "Nos") {
					return Promise.resolve({ item: item.item, stock_uom, conversion_factor: 100.0 });
				}
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
				_build_co_transfer_dialog(co_name, stock_items, item_map, conv_map, wine_batch_frm, ripe_tpl, wine_batch_frm.doc.wip_warehouse);
			});
		});
	});
}

function _build_co_transfer_dialog(co_name, stock_items, item_map, conv_map, wine_batch_frm, ripe_tpl, default_wip) {
	const fields = [
		{
			fieldname: "wip_warehouse",
			fieldtype: "Link",
			label: __("WIP Warehouse (Destination)"),
			options: "Warehouse",
			reqd: 1,
			default: default_wip || "",
			read_only: default_wip ? 1 : 0,
			description: default_wip ? __("Defaulted from Wine Batch") : "",
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
		// Banana template always uses multi-batch regardless of UOM match
		const is_banana = ripe_tpl && item.item === ripe_tpl;
		const use_multibatch = info.has_batch_no && (uom_mismatch || is_banana);

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

		if (info.has_batch_no && !use_multibatch) {
			fields.push({
				fieldname: `batch_no_${idx}`,
				fieldtype: "Link",
				label: __("Batch No"),
				options: "Batch",
				reqd: 1,
				get_query() {
					// _init_co_batch_link_field overrides this once a warehouse is selected;
					// before that, show nothing so the user is prompted to pick a warehouse first.
					return { filters: { name: "__select_warehouse_first__" } };
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

		if (use_multibatch) {
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
				const is_banana = ripe_tpl && item.item === ripe_tpl;
				const use_multibatch = info.has_batch_no && (uom_mismatch || is_banana);
				const s_warehouse = values[`s_warehouse_${idx}`];

				if (use_multibatch) {
					const tbody = dialog.fields_dict[`batch_table_${idx}`].$wrapper.find(".bt-tbody")[0];
					let has_entry = false;
					tbody.querySelectorAll("tr").forEach(row => {
						const sel = row.querySelector(".b-no");
						const batch_no = sel.value.trim();
						const batch_qty = parseFloat(row.querySelector(".b-qty").value) || 0;
						if (!batch_no || !batch_qty) return;
						has_entry = true;
						const resolved_item = sel.options[sel.selectedIndex]?.dataset?.item || item.item;
						transfer_items.push({
							item_code: resolved_item,
							qty: batch_qty,
							uom: stock_uom,
							s_warehouse,
							batch_no,
							conversion_factor: 1,
						});
					});
					if (!has_entry) {
						frappe.msgprint(__(`Please enter at least one batch and ${stock_uom} count for ${item.item}.`));
						validation_failed = true;
					}
				} else if (uom_mismatch) {
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

			frappe.call({
				method: "winery.winery.doctype.cellar_operation.cellar_operation.transfer_materials_for_op",
				args: {
					name: co_name,
					wip_warehouse: values.wip_warehouse,
					items: transfer_items,
				},
			}).then((r) => {
				if (!r.exc) {
					dialog.hide();
					wine_batch_frm.reload_doc();
				}
			});
		},
	});

	stock_items.forEach((item, idx) => {
		const info = item_map[item.item];
		const conv = conv_map[item.item] || {};
		const stock_uom = conv.stock_uom || info.stock_uom;
		const req_uom = item.uom;
		const uom_mismatch = req_uom && stock_uom && req_uom !== stock_uom;
		const is_banana = ripe_tpl && item.item === ripe_tpl;
		const use_multibatch = info.has_batch_no && (uom_mismatch || is_banana);
		if (use_multibatch) {
			_init_co_batch_table(dialog, idx, item, stock_uom, req_uom);
		} else if (!use_multibatch && info.has_batch_no) {
			_init_co_batch_link_field(dialog, idx, item);
		}
	});

	dialog.show();
}

function _init_co_batch_table(dialog, idx, item, stock_uom, req_uom) {
	const $field = dialog.fields_dict[`batch_table_${idx}`].$wrapper;
	let availableBatches = [];

	function buildBatchOptions() {
		let html = `<option value="">— ${__("Select Batch")} —</option>`;
		availableBatches.forEach(b => {
			html += `<option value="${b.batch_no}" data-item="${b.item_code || ''}">${b.batch_no} (${parseFloat(b.qty).toFixed(0)} ${stock_uom})</option>`;
		});
		return html;
	}

	function populateBatchSelects() {
		const optHtml = buildBatchOptions();
		$field.find(".b-no").each(function () {
			const cur = this.value;
			this.innerHTML = optHtml;
			if (cur) this.value = cur;
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

	const wfDict = dialog.fields_dict[`s_warehouse_${idx}`];
	if (wfDict) {
		const orig = wfDict.df.onchange;
		wfDict.df.onchange = function () {
			orig?.call(this);
			loadBatches(this.get_value());
		};
	}

	const tbody   = $field.find(".bt-tbody")[0];
	const totalEl = $field.find(".bt-total")[0];
	const addBtn  = $field.find(".bt-add")[0];

	function recalcTotal() {
		let total = 0;
		tbody.querySelectorAll(".b-qty").forEach(inp => { total += parseFloat(inp.value) || 0; });
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
			tr.querySelector(".rm-row").addEventListener("click", () => { tr.remove(); recalcTotal(); });
		}
	}

	addRow(false);
	addBtn.addEventListener("click", () => addRow(true));
}

// ─────────────────────────────────────────────────────────────────────────────
// Required Materials — Stock Availability Indicators
// ─────────────────────────────────────────────────────────────────────────────

function _fetch_and_render_availability(frm) {
	const rows = (frm.doc.required_materials || []).filter(r => r.item);
	if (!rows.length) return;

	const items = rows.map(r => ({ item: r.item, quantity: r.quantity, uom: r.uom }));

	frappe.call({
		method: "winery.winery.doctype.wine_batch.wine_batch.check_materials_availability",
		args: { items: JSON.stringify(items) },
		callback(r) {
			if (!r.message) return;
			frm._material_availability = r.message;
			_apply_availability_formatter(frm);
		},
	});
}

function _apply_availability_formatter(frm) {
	const grid = frm.fields_dict.required_materials.grid;
	if (!grid || !grid.columns || !grid.columns.length) return;

	const item_col = grid.columns.find(c => c.df && c.df.fieldname === "item");
	if (!item_col) return;

	// Install formatter (idempotent — replace on each call so frm ref stays current)
	item_col.df.formatter = function (value) {
		const avail = frm._material_availability || {};
		const info = avail[value];
		const label = frappe.utils.escape_html(value || "");
		if (!info) return label;
		const color = info.available ? "#28a745" : "#e24c4c";
		const title = info.available
			? __("In Stock")
			: __("Insufficient Stock");
		return (
			`<span style="color:${color};font-size:9px;margin-right:4px;vertical-align:middle;" ` +
			`title="${title}">●</span>` +
			label
		);
	};

	grid.refresh();
}

function _init_co_batch_link_field(dialog, idx, item) {
	let validBatchNos = [];

	function refreshBatchQuery() {
		const batchField = dialog.fields_dict[`batch_no_${idx}`];
		if (!batchField) return;
		if (validBatchNos.length) {
			// Filter only by batch name — the batches may belong to a variant item,
			// so do NOT add item: item.item which would block variant batches.
			batchField.df.get_query = () => ({
				filters: { name: ["in", validBatchNos] },
			});
		} else {
			// No stock in selected warehouse — return no results.
			batchField.df.get_query = () => ({ filters: { name: "__no_stock_in_warehouse__" } });
		}
	}

	const wfDict = dialog.fields_dict[`s_warehouse_${idx}`];
	if (!wfDict) return;
	const orig = wfDict.df.onchange;
	wfDict.df.onchange = function () {
		orig?.call(this);
		const warehouse = this.get_value();
		if (!warehouse) {
			validBatchNos = [];
			refreshBatchQuery();
			return;
		}
		frappe.call({
			method: "winery.winery.doctype.cellar_operation.cellar_operation.get_batches_for_item_warehouse",
			args: { item_code: item.item, warehouse },
		}).then(r => {
			validBatchNos = (r.message || []).map(b => b.batch_no);
			refreshBatchQuery();
			dialog.set_value(`batch_no_${idx}`, "");
		});
	};
}

