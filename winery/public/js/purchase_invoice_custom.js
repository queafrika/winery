// Winery: Custom behaviours on Purchase Invoice

frappe.ui.form.on("Purchase Invoice", {
	// Auto-enable update_stock when an agent is selected so banana bunches
	// are received into stock immediately on PI submission.
	agent(frm) {
		if (frm.doc.agent && !frm.doc.update_stock) {
			frm.set_value("update_stock", 1);
		}
	},

	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		// --- Banana Grading button (existing behaviour) ---
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

		// --- Agent Delivery Receipt button (only for agent-linked invoices) ---
		if (!frm.doc.agent) return;

		frappe.call({
			method: "winery.winery.doctype.agent_delivery_receipt.agent_delivery_receipt.get_adr_for_invoice",
			args: { purchase_invoice: frm.doc.name },
			callback(r) {
				const adr = r.message;
				if (adr) {
					frm.add_custom_button(
						__("View Agent Delivery Receipt"),
						() => frappe.set_route("Form", "Agent Delivery Receipt", adr),
						__("Winery")
					);
				} else {
					frm.add_custom_button(
						__("Create Agent Delivery Receipt"),
						() => {
							frappe.new_doc("Agent Delivery Receipt", {
								agent: frm.doc.agent,
								invoices: [{ purchase_invoice: frm.doc.name }],
							});
						},
						__("Winery")
					);
				}
			},
		});
	},
});
