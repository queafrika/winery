// Copyright (c) 2026, Finesoft Afrika and contributors
// For license information, please see license.txt

frappe.ui.form.on("Banana Grading", {
	refresh(frm) {
		if (frm.doc.purchase_receipt) {
			frm.add_custom_button(__("View Purchase Receipt"), () => {
				frappe.set_route("Form", "Purchase Receipt", frm.doc.purchase_receipt);
			});
		}
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Create Ripening Batch"), () => {
				frappe.new_doc("Ripening Batch", {
					procurement: frm.doc.name,
					banana_item: frm.doc.banana_item,
					source_warehouse: frm.doc.warehouse,
				});
			});
		}
	},
});

frappe.ui.form.on("Banana Grading Batch", {
	fingers(frm, cdt, cdn) {
		_compute_row(frm, cdt, cdn);
	},
	rate(frm, cdt, cdn) {
		_compute_row(frm, cdt, cdn);
	},
	damaged_fingers(frm, cdt, cdn) {
		_compute_row(frm, cdt, cdn);
	},
	damaged_rate(frm, cdt, cdn) {
		_compute_row(frm, cdt, cdn);
	},
	batches_remove(frm) {
		_compute_totals(frm);
	},
});

function _compute_row(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "amount", (row.fingers || 0) * (row.rate || 0));
	frappe.model.set_value(cdt, cdn, "damaged_amount", (row.damaged_fingers || 0) * (row.damaged_rate || 0));
	_compute_totals(frm);
}

function _compute_totals(frm) {
	let total_fingers = 0, total_amount = 0;
	(frm.doc.batches || []).forEach((row) => {
		total_fingers += row.fingers || 0;
		total_amount += (row.amount || 0) + (row.damaged_amount || 0);
	});
	frm.set_value("total_fingers", total_fingers);
	frm.set_value("total_amount", total_amount);
}
