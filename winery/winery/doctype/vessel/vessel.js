// Copyright (c) 2026, Finesoft Afrika and contributors
// For license information, please see license.txt

frappe.ui.form.on("Vessel", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("View Batch Process Logs"), () => {
				frappe.set_route("List", "Batch Process Log", { vessel: frm.doc.name });
			});
			frm.add_custom_button(__("View Cellar Operations"), () => {
				frappe.set_route("List", "Cellar Operation", { vessel: frm.doc.name });
			});
		}
	},

	current_volume(frm) {
		if (frm.doc.capacity && frm.doc.current_volume > frm.doc.capacity) {
			frappe.msgprint({
				title: __("Warning"),
				message: __("Current Volume exceeds Capacity."),
				indicator: "orange",
			});
		}
	},
});
