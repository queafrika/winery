// Copyright (c) 2026, Finesoft Afrika and contributors
// For license information, please see license.txt

frappe.ui.form.on("Compliance License", {
	compliance_type(frm) {
		if (!frm.doc.compliance_type) return;

		frappe.db.get_doc("Compliance Type", frm.doc.compliance_type).then((ct) => {
			frm.set_value("issuing_authority", ct.issuing_authority || "");
			frm.set_value("payment_frequency", ct.payment_frequency || "");
			frm.set_value("amount_source", ct.amount_source || "");

			if (ct.amount_source === "Fixed" && ct.default_amount) {
				frm.set_value("amount", ct.default_amount);
			}

			// Copy default reminder rules from the Compliance Type
			frm.clear_table("reminder_rules");
			(ct.default_reminder_rules || []).forEach((rule) => {
				let row = frm.add_child("reminder_rules");
				row.days_before = rule.days_before;
				row.reminder_sent = 0;
			});
			frm.refresh_field("reminder_rules");
		});
	},

	refresh(frm) {
		_toggle_calculate_button(frm);
	},

	amount_source(frm) {
		_toggle_calculate_button(frm);
	},
});

function _toggle_calculate_button(frm) {
	frm.remove_custom_button(__("Calculate Amount"));
	if (frm.doc.amount_source === "Query" && !frm.doc.__islocal) {
		frm.add_custom_button(__("Calculate Amount"), () => {
			frappe.call({
				method: "calculate_amount",
				doc: frm.doc,
				freeze: true,
				freeze_message: __("Calculating…"),
				callback(r) {
					if (r.message) {
						frm.set_value("amount", r.message.amount);
						frm.set_value("calculated_period", r.message.period);
						frappe.show_alert({
							message: __("Amount calculated: {0} for period {1}", [
								format_currency(r.message.amount),
								r.message.period,
							]),
							indicator: "green",
						});
					}
				},
			});
		});
	}
}
