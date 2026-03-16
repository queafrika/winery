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
			frm.add_custom_button(__("Start Next Stage"), () => {
				_start_next_stage(frm);
			}).addClass("btn-primary");

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

		if (frm.doc.docstatus === 1 && frm.doc.recipe && frm.doc.status === "Active") {
			frm.add_custom_button(__("Create Required Lab Tests"), () => {
				_create_required_lab_tests(frm);
			}, __("Lab"));
		}
	},
});

function _debounced_recalculate(frm) {
	if (_recalc_timer) clearTimeout(_recalc_timer);
	_recalc_timer = setTimeout(() => _recalculate_materials(frm), 300);
}

function _recalculate_materials(frm) {
	if (!frm.doc.recipe || !frm.doc.target_batch_size) return;

	frappe.db.get_doc("Recipe", frm.doc.recipe).then((recipe) => {
		if (!recipe.base_batch_size || !recipe.raw_materials || !recipe.raw_materials.length) return;

		const scale = frm.doc.target_batch_size / recipe.base_batch_size;

		// Show scaling factor as a hint
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

function _start_next_stage(frm) {
	frappe.call({
		method: "start_next_stage",
		doc: frm.doc,
		callback(r) {
			if (r.message) {
				frappe.set_route("Form", "Cellar Operation", r.message);
			}
		},
	});
}

function _create_required_lab_tests(frm) {
	frappe.db.get_doc("Recipe", frm.doc.recipe).then((recipe) => {
		if (!recipe.lab_analyses || !recipe.lab_analyses.length) {
			frappe.msgprint("No lab tests defined in the Recipe for this batch.");
			return;
		}

		const current_stage = frm.doc.current_stage_name || "";
		const matching = recipe.lab_analyses.filter(
			(r) => !r.stage_name || r.stage_name === current_stage
		);

		if (!matching.length) {
			frappe.msgprint(`No lab tests defined in Recipe for stage "<b>${current_stage}</b>".`);
			return;
		}

		const mandatory = matching.filter((r) => r.is_mandatory);
		const optional = matching.filter((r) => !r.is_mandatory);

		let msg = `<b>Stage: ${current_stage || "All Stages"}</b><br><br>`;
		if (mandatory.length) {
			msg += `<b>Mandatory Tests:</b><ul>${mandatory.map((r) => `<li>${r.test_type}</li>`).join("")}</ul>`;
		}
		if (optional.length) {
			msg += `<b>Optional Tests:</b><ul>${optional.map((r) => `<li>${r.test_type}</li>`).join("")}</ul>`;
		}
		msg += "<br>Create Lab Analysis documents for all mandatory tests?";

		frappe.confirm(msg, () => {
			let created = 0;
			const promises = mandatory.map((r) =>
				frappe.db.insert({
					doctype: "Lab Analysis",
					wine_batch: frm.doc.name,
					test_type: r.test_type,
					analysis_date: frappe.datetime.now_datetime(),
				}).then(() => { created++; })
			);

			Promise.all(promises).then(() => {
				frappe.show_alert({
					message: `${created} Lab Analysis document(s) created for stage "${current_stage}".`,
					indicator: "green",
				}, 6);
				frappe.set_route("List", "Lab Analysis", { wine_batch: frm.doc.name });
			});
		});
	});
}

function _show_progress(frm) {
	if (!frm.doc.recipe) return;

	frappe.db.get_doc("Recipe", frm.doc.recipe).then((process) => {
		const total = process.stages.length;
		const current = frm.doc.current_stage_number || 0;
		const pct = total > 0 ? Math.round((current / total) * 100) : 0;

		frm.dashboard.add_progress(
			__("Production Progress: Stage {0} of {1}", [current, total]),
			pct
		);
	});
}

function _check_bottling_button(frm) {
	// Show "Create Bottling & Packaging" only when all Cellar Operations are Completed
	frappe.db.get_list("Cellar Operation", {
		filters: { wine_batch: frm.doc.name, docstatus: 1 },
		fields: ["name", "status"],
	}).then((ops) => {
		if (!ops.length) return;
		const all_done = ops.every((op) => op.status === "Completed");
		if (!all_done) return;

		// Check no existing Bottling for this batch
		frappe.db.get_value("Bottling", { wine_batch: frm.doc.name, docstatus: ["!=", 2] }, "name")
			.then((r) => {
				if (r && r.message && r.message.name) {
					// Already exists — show view button
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
