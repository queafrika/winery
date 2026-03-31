frappe.ui.form.on("Agent Delivery Receipt", {
	refresh(frm) {
		// Auto-populate on first load of a new doc that already has an agent set
		if (frm.is_new() && frm.doc.agent && !(frm.doc.items && frm.doc.items.length)) {
			_populate_items(frm);
		}

		// Grade Bananas / View Grading button — shown on submitted ADRs
		if (frm.doc.docstatus === 1) {
			frappe.call({
				method: "winery.winery.doctype.banana_grading.banana_grading.get_adr_grading",
				args: { adr_name: frm.doc.name },
				callback(r) {
					if (r.message) {
						frm.add_custom_button(__("View Grading"), () => {
							frappe.set_route("Form", "Banana Grading", r.message);
						}).addClass("btn-default");
					} else if (frm.doc.status === "Received") {
						frm.add_custom_button(__("Grade Bananas"), () => {
							frappe.new_doc("Banana Grading", {
								agent_delivery_receipt: frm.doc.name,
								procurement_date:       frm.doc.delivery_date,
								source_warehouse:       frm.doc.receiving_warehouse,
								target_warehouse:       frm.doc.receiving_warehouse,
							});
						}).addClass("btn-primary");
					}
				},
			});
		}
	},

	agent(frm) {
		if (!frm.doc.agent || frm.doc.docstatus !== 0) return;
		_populate_items(frm);
	},
});

function _populate_items(frm) {
	frappe.call({
		method: "winery.winery.doctype.agent_delivery_receipt"
			+ ".agent_delivery_receipt.get_pending_items_for_agent",
		args: { agent: frm.doc.agent },
		callback(r) {
			const lines = r.message || [];

			frm.clear_table("items");

			lines.forEach((it) => {
				const row = frm.add_child("items");
				row.purchase_invoice = it.purchase_invoice;
				row.posting_date     = it.posting_date;
				row.farmer           = it.farmer;
				row.item_code        = it.item_code;
				row.item_name        = it.item_name;
				row.expected_qty     = it.expected_qty;
				row.received_qty     = it.expected_qty; // default — full delivery
				row.shortage         = 0;
			});

			frm.refresh_field("items");

			if (!lines.length) {
				frappe.msgprint(
					__("No pending Purchase Invoices found for this agent.")
				);
			}
		},
	});
}
