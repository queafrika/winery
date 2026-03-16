// Copyright (c) 2026, Finesoft Afrika and contributors
// For license information, please see license.txt

frappe.ui.form.on("Recipe", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Start Wine Batch"), () => {
				frappe.new_doc("Wine Batch", { recipe: frm.doc.name });
			});
		}
		_update_stage_options(frm);
	},
});

frappe.ui.form.on("Recipe Stage", {
	stage_name(frm) { _update_stage_options(frm); },
	stages_remove(frm) { _update_stage_options(frm); },
});

function _update_stage_options(frm) {
	// Build stage name options from the Stages tab and apply to Lab tab dropdown
	const stage_names = (frm.doc.stages || [])
		.map((r) => r.stage_name)
		.filter(Boolean);

	const options = ["", ...stage_names].join("\n");

	frm.fields_dict.lab_analyses.grid.update_docfield_property(
		"stage_name", "options", options
	);
	frm.fields_dict.lab_analyses.grid.refresh();
}
