// Copyright (c) 2026, Finesoft Afrika and contributors
// For license information, please see license.txt

frappe.ui.form.on("Casual Payment", {
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Get Earnings"), () => {
				if (!frm.doc.casual_worker) {
					frappe.msgprint(__("Please select a Casual Worker first."));
					return;
				}
				frm.call({
					doc: frm.doc,
					method: "get_earnings",
					freeze: true,
					freeze_message: __("Loading earnings..."),
					callback: () => {
						frm.refresh_field("earnings");
						frm.refresh_field("total_earnings");
					},
				});
			});

			frm.add_custom_button(__("Apply Tax Template"), () => {
				if (!frm.doc.tax_template) {
					frappe.msgprint(__("Please select a Tax Template first."));
					return;
				}
				frm.call({
					doc: frm.doc,
					method: "apply_tax_template",
					freeze: true,
					freeze_message: __("Calculating taxes..."),
					callback: () => {
						frm.refresh_field("deductions");
						frm.refresh_field("total_deductions");
						frm.refresh_field("net_pay");
					},
				});
			});
		}

		if (frm.doc.journal_entry) {
			frm.add_custom_button(
				__("Journal Entry"),
				() => frappe.set_route("Form", "Journal Entry", frm.doc.journal_entry),
				__("View")
			);
		}
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.company) {
			frm.set_value("company", frappe.defaults.get_user_default("Company"));
		}
		if (frm.is_new() && !frm.doc.payment_account) {
			frappe.db.get_single_value("Winery Settings", "casual_default_payment_account").then((acc) => {
				if (acc) frm.set_value("payment_account", acc);
			});
		}
	},

	tax_template(frm) {
		// Recompute automatically when the template changes on a draft with earnings
		if (frm.doc.docstatus === 0 && frm.doc.tax_template && (frm.doc.earnings || []).length) {
			frm.call({
				doc: frm.doc,
				method: "apply_tax_template",
				callback: () => {
					frm.refresh_field("deductions");
					frm.refresh_field("total_deductions");
					frm.refresh_field("net_pay");
				},
			});
		}
	},

	// Fires when a deduction row is removed
	deductions_remove: recalc_totals,
});

// Recalculate running totals whenever a manual deduction row's amount changes
frappe.ui.form.on("Casual Payment Deduction", {
	amount: recalc_totals,
});

function recalc_totals(frm) {
	let total_deductions = (frm.doc.deductions || []).reduce(
		(sum, r) => sum + flt(r.amount),
		0
	);
	frm.set_value("total_deductions", total_deductions);
	frm.set_value("net_pay", flt(frm.doc.total_earnings) - total_deductions);
}
