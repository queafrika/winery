// Copyright (c) 2026, Finesoft Afrika and contributors
// For license information, please see license.txt

frappe.ui.form.on("Compliance Task", {
	refresh(frm) {
		_toggle_calculate_button(frm);
	},

	task_type(frm) {
		_toggle_calculate_button(frm);
	},

	amount_source(frm) {
		_toggle_calculate_button(frm);
	},
});

function _toggle_calculate_button(frm) {
	frm.remove_custom_button(__("Calculate Amount"));
	if (
		frm.doc.task_type === "Payment" &&
		frm.doc.amount_source === "SQL Query" &&
		!frm.doc.__islocal
	) {
		frm.add_custom_button(__("Calculate Amount"), () => {
			frappe.confirm(
				__(
					"This will run the stored SQL query and overwrite the current amount. Continue?"
				),
				() => {
					frappe.call({
						method: "calculate_amount",
						doc: frm.doc,
						freeze: true,
						freeze_message: __("Running SQL query…"),
						callback(r) {
							if (r.message) {
								frm.set_value("amount", r.message.amount);
								frappe.show_alert({
									message: __(
										"Amount calculated: {0}",
										[format_currency(r.message.amount)]
									),
									indicator: "green",
								});
							}
						},
					});
				}
			);
		});
	}
}
