// Copyright (c) 2026, Finesoft Afrika and contributors
// For license information, please see license.txt

frappe.ui.form.on("Batch Process Log", {
	refresh(frm) {
		if (frm.doc.stock_entry) {
			frm.add_custom_button(__("View Stock Entry"), () => {
				frappe.set_route("Form", "Stock Entry", frm.doc.stock_entry);
			});
		}
		if (frm.doc.wine_batch && frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Add Lab Analysis"), () => {
				frappe.new_doc("Lab Analysis", {
					wine_batch: frm.doc.wine_batch,
					batch_process_log: frm.doc.name,
					vessel: frm.doc.vessel,
				});
			});
		}
	},

	end_time(frm) {
		_compute_bpl_duration(frm);
	},

	start_time(frm) {
		_compute_bpl_duration(frm);
	},

	output_quantity(frm) {
		_compute_loss(frm);
	},

	input_quantity(frm) {
		_compute_loss(frm);
	},
});

frappe.ui.form.on("Batch Process Additives", {
	additive(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.additive) {
			frappe.db.get_value("Item", row.additive, "stock_uom", (r) => {
				if (r && r.stock_uom) {
					frappe.model.set_value(cdt, cdn, "uom", r.stock_uom);
				}
			});
		}
	},
});

function _compute_bpl_duration(frm) {
	if (frm.doc.start_time && frm.doc.end_time) {
		const start = frappe.datetime.str_to_moment(frm.doc.start_time);
		const end = frappe.datetime.str_to_moment(frm.doc.end_time);
		const diff = end.diff(start, "hours", true);
		if (diff >= 0) {
			frm.set_value("duration", Math.round(diff * 100) / 100);
		}
	}
}

function _compute_loss(frm) {
	const input = frm.doc.input_quantity || 0;
	const output = frm.doc.output_quantity || 0;
	const loss = Math.max(0, input - output);
	frm.set_value("material_loss", loss);
	frm.set_value("material_loss_pct", input > 0 ? (loss / input) * 100 : 0);
}
