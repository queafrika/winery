// Copyright (c) 2026, Finesoft Afrika and contributors
// For license information, please see license.txt

frappe.ui.form.on("Farmer", {
	refresh(frm) {
		// Filter farm dropdown to only show farms belonging to this farmer
		frm.set_query("farm_name", () => ({
			filters: { farmer: frm.doc.name },
		}));
	},
});
