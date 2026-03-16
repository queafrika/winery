// Winery: Custom button on Purchase Invoice to open new Banana Grading form

frappe.ui.form.on("Purchase Invoice", {
	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			frappe.call({
				method: "winery.winery.doctype.banana_grading.banana_grading.get_invoice_prefill",
				args: { purchase_invoice: frm.doc.name },
				callback(r) {
					if (!r.message) return;

					if (r.message.existing) {
						frm.add_custom_button(
							__("View Banana Grading"),
							() => frappe.set_route("Form", "Banana Grading", r.message.existing),
							__("Winery")
						);
					} else {
						frm.add_custom_button(
							__("Create Banana Grading"),
							() => frappe.new_doc("Banana Grading", r.message),
							__("Winery")
						).addClass("btn-primary");
					}
				},
			});
		}
	},
});
