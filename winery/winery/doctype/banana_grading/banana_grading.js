// Copyright (c) 2026, Finesoft Afrika and contributors
// For license information, please see license.txt

frappe.ui.form.on("Banana Grading", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.damaged_warehouse) {
			frappe.db.get_single_value("Winery Settings", "damaged_warehouse").then((wh) => {
				if (wh) frm.set_value("damaged_warehouse", wh);
			});
		}
	},

	refresh(frm) {
		_toggle_sections(frm);

		// Disinfection log button — visible on any saved/submitted grading
		if (frm.doc.name && !frm.doc.__islocal) {
			frappe.call({
				method: "frappe.client.get_count",
				args: {
					doctype: "Banana Disinfection Log",
					filters: { banana_grading: frm.doc.name },
				},
				callback(r) {
					const count = r.message || 0;
					if (count > 0) {
						frm.add_custom_button(__("Disinfection Logs (" + count + ")"), () => {
							frappe.set_route("List", "Banana Disinfection Log", {
								banana_grading: frm.doc.name,
							});
						});
					} else {
						frm.add_custom_button(__("Add Disinfection Log"), () => {
							frappe.new_doc("Banana Disinfection Log", {
								banana_grading: frm.doc.name,
								date: frappe.datetime.get_today(),
							});
						});
					}
				},
			});
		}

		// ADR-mode tracking button
		if (frm.doc.stock_entry) {
			frm.add_custom_button(__("View Repack Entry"), () => {
				frappe.set_route("Form", "Stock Entry", frm.doc.stock_entry);
			});
		}

		// PI-mode buttons (only when no ADR linked)
		if (!frm.doc.agent_delivery_receipt) {
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
		}
	},

	agent_delivery_receipt(frm) {
		if (!frm.doc.agent_delivery_receipt) {
			_toggle_sections(frm);
			return;
		}
		_toggle_sections(frm);
		_populate_grading_items(frm);
		// Auto-fill source_warehouse from the ADR's receiving_warehouse
		frappe.db.get_value(
			"Agent Delivery Receipt",
			frm.doc.agent_delivery_receipt,
			"receiving_warehouse",
			(r) => {
				if (r && r.receiving_warehouse) {
					frm.set_value("source_warehouse", r.receiving_warehouse);
					frm.set_value("target_warehouse", r.receiving_warehouse);
				}
			}
		);
	},
});

// PI-mode child table row handlers (unchanged)
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

// Fields only relevant when grading is linked to a Purchase Invoice
const PI_ONLY_FIELDS = [
	"purchase_invoice", "banana_item", "farmer", "farm", "agent", "warehouse",
];
// Fields only relevant in ADR mode
const ADR_ONLY_FIELDS = [
	"agent_delivery_receipt", "source_warehouse", "target_warehouse",
	"section_break_grading_items", "grading_items",
];

function _toggle_sections(frm) {
	const adr_mode = !!frm.doc.agent_delivery_receipt;

	PI_ONLY_FIELDS.forEach((f) => frm.toggle_display(f, !adr_mode));
	ADR_ONLY_FIELDS.forEach((f) => frm.toggle_display(f, adr_mode));

	frm.toggle_display("section_break_batches", !adr_mode);
	frm.toggle_display("batches", !adr_mode);
}

function _populate_grading_items(frm) {
	frappe.call({
		method: "winery.winery.doctype.banana_grading.banana_grading.get_adr_items_for_grading",
		args: { adr_name: frm.doc.agent_delivery_receipt },
		callback(r) {
			const rows = r.message || [];
			frm.clear_table("grading_items");
			rows.forEach((it) => {
				const row = frm.add_child("grading_items");
				row.banana_item      = it.banana_item;
				row.item_name        = it.item_name;
				row.farm             = it.farm;
				row.bunches_received = it.bunches_received;
			});
			frm.refresh_field("grading_items");
		},
	});
}

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
