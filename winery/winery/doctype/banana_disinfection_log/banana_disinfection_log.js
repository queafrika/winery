frappe.ui.form.on("Banana Disinfection Log", {
	refresh(frm) {
		if (frm.doc.stock_entry) {
			frm.add_custom_button(__("View Stock Entry"), () => {
				frappe.set_route("Form", "Stock Entry", frm.doc.stock_entry);
			});
		}
	},

	disinfectant_item(frm) {
		if (frm.doc.disinfectant_item) {
			frappe.db.get_value("Item", frm.doc.disinfectant_item, "stock_uom", (r) => {
				if (r && r.stock_uom) {
					frm.set_value("uom", r.stock_uom);
				}
			});
		}
	},
});
