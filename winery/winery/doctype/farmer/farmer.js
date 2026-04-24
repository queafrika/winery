// Copyright (c) 2026, Finesoft Afrika and contributors
// For license information, please see license.txt

frappe.ui.form.on("Farmer", {
	refresh(frm) {
		// Filter farm dropdown to only show farms belonging to this farmer
		frm.set_query("farm_name", () => ({
			filters: { farmer: frm.doc.name },
		}));

		if (!frm.is_new()) {
			frm.add_custom_button(__("Purchase Bananas"), () => {
				frappe.route_options = { farmer: frm.doc.name };
				frappe.set_route("purchase-bananas");
			}, __("Actions"));
		}
	},
});
