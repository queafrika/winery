// Allow non-depreciating assets (e.g. land) in Asset Value Adjustment.
// ERPNext core restricts the asset query to calculate_depreciation=1, but the
// Python controller handles non-depreciating assets correctly — only the UI
// filter needs widening.
frappe.ui.form.on("Asset Value Adjustment", {
	setup: function (frm) {
		frm.set_query("asset", function () {
			return {
				filters: {
					docstatus: 1,
				},
			};
		});
	},
});
