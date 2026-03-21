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

	refresh(frm) {
		frm.get_field("required_materials").grid.cannot_add_rows = true;
		frm.get_field("required_materials").grid.cannot_delete_rows = true;

		if (frm.doc.docstatus === 1 && frm.doc.status === "Active") {
			_check_bottling_button(frm);
		}

		if (frm.doc.recipe && !frm.is_new()) {
			_show_progress(frm);
		}

		frm.add_custom_button(__("View Cellar Operations"), () => {
			frappe.set_route("List", "Cellar Operation", { wine_batch: frm.doc.name });
		});

		frm.add_custom_button(__("View Lab Analyses"), () => {
			frappe.set_route("List", "Lab Analysis", { wine_batch: frm.doc.name });
		});

		if (frm.doc.docstatus === 1 && !frm.is_new()) {
			_render_cellar_ops_tab(frm);
			_render_lab_analyses_tab(frm);
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

	// 2. Build ordered_ops — prefer recipe lab_analyses order, fall back to existing operations
	const recipe = await frappe.db.get_doc("Recipe", frm.doc.recipe).catch(() => null);
	const ordered_ops = [];

	if (recipe && recipe.lab_analyses && recipe.lab_analyses.length) {
		(recipe.lab_analyses || []).forEach((la) => {
			if (la.operation_type && !ordered_ops.includes(la.operation_type)) {
				ordered_ops.push(la.operation_type);
			}
		});
	}

	// Fallback: query Recipe Stage table directly (still in DB even if removed from form)
	if (!ordered_ops.length) {
		const stages = await frappe.db.get_list("Recipe Stage", {
			filters: { parent: frm.doc.recipe },
			fields: ["operation_type", "idx"],
			order_by: "idx asc",
			limit: 20,
		});
		stages.forEach((s) => {
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
	_bind_cellar_op_buttons(frm, co_map, next_stage);
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

function _bind_cellar_op_buttons(frm, co_map, next_stage) {
	const $wrapper = frm.get_field("cellar_ops_html").$wrapper;

	// Create Stage
	$wrapper.find(".co-btn-create").on("click", function () {
		frappe.call({
			method: "start_next_stage",
			doc: frm.doc,
			btn: $(this),
			callback(r) {
				if (!r.exc) frm.reload_doc();
			},
		});
	});

	// Transfer Stock → redirect to Cellar Operation form where the dialog lives
	$wrapper.find(".co-btn-transfer").on("click", function () {
		frappe.set_route("Form", "Cellar Operation", $(this).data("name"));
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
					method: "frappe.client.get",
					args: { doctype: "Cellar Operation", name: co_name },
					callback(res) {
						if (!res.message) return;
						frappe.call({
							method: "start_operation",
							doc: res.message,
							args: { employee: values.employee },
							callback(r) {
								if (!r.exc) { dialog.hide(); frm.reload_doc(); }
							},
						});
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
					method: "frappe.client.get",
					args: { doctype: "Cellar Operation", name: co_name },
					callback(res) {
						if (!res.message) return;
						frappe.call({
							method: "complete_operation",
							doc: res.message,
							callback(r) {
								if (!r.exc) frm.reload_doc();
							},
						});
					},
				});
			}
		);
	});

	// New Lab Analysis
	$wrapper.find(".co-btn-lab").on("click", function () {
		frappe.new_doc("Lab Analysis", {
			cellar_operation: $(this).data("name"),
			wine_batch: frm.doc.name,
		});
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
// Bottling button
// ─────────────────────────────────────────────────────────────────────────────

function _check_bottling_button(frm) {
	frappe.db.get_list("Cellar Operation", {
		filters: { wine_batch: frm.doc.name, docstatus: 1 },
		fields: ["name", "status"],
	}).then((ops) => {
		if (!ops.length) return;
		const all_done = ops.every((op) => op.status === "Completed");
		if (!all_done) return;

		frappe.db.get_value("Bottling", { wine_batch: frm.doc.name, docstatus: ["!=", 2] }, "name")
			.then((r) => {
				if (r && r.message && r.message.name) {
					frm.add_custom_button(__("View Bottling & Packaging"), () => {
						frappe.set_route("Form", "Bottling", r.message.name);
					}).addClass("btn-info");
				} else {
					frm.add_custom_button(__("Create Bottling & Packaging"), () => {
						_start_bottling(frm);
					}).addClass("btn-success");
				}
			});
	});
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
			fields: ["name", "test_type", "analysis_date", "analyzed_by",
			         "cellar_operation", "status", "docstatus"],
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
		frappe.new_doc("Lab Analysis", {
			wine_batch: frm.doc.name,
			cellar_operation: $(this).data("co"),
		});
	});
}

function _build_la_card(la) {
	const badge = _la_status_badge(la.status, la.docstatus);
	const date_str = la.analysis_date
		? frappe.datetime.str_to_user(la.analysis_date)
		: "—";
	const analyst = la.analyzed_by ? la.analyzed_by.split("@")[0] : "—";

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
			<div class="la-row">
				<span class="la-label">${__("Result")}</span>
				<span class="la-val">${badge}</span>
			</div>
		</div>
		<div class="la-card-footer">
			<button class="btn btn-default btn-xs la-btn-view" data-name="${la.name}">${__("View →")}</button>
		</div>
	</div>`;
}

function _la_status_badge(status, docstatus) {
	if (String(docstatus) === "0") {
		return `<span class="badge badge-secondary">${__("Draft")}</span>`;
	}
	if (status === "Passed") {
		return `<span class="badge badge-success">${__("Passed")}</span>`;
	}
	if (status === "Failed") {
		return `<span class="badge badge-danger">${__("Failed")}</span>`;
	}
	return `<span class="badge badge-secondary">${frappe.utils.escape_html(status || "—")}</span>`;
}

function _start_bottling(frm) {
	frappe.call({
		method: "winery.winery.doctype.bottling.bottling.create_bottling",
		args: { wine_batch: frm.doc.name },
		callback(r) {
			if (!r.message) return;
			if (r.message.existing) {
				frappe.set_route("Form", "Bottling", r.message.existing);
			} else {
				frappe.new_doc("Bottling", r.message);
			}
		},
	});
}
