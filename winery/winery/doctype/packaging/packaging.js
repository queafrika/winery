// Copyright (c) 2026, Finesoft Afrika and contributors
// For license information, please see license.txt

const BOTTLES_PER_CARTON = {
	"6-Pack": 6,
	"8-Pack": 8,
	"12-Pack": 12,
	"24-Pack": 24,
};

frappe.ui.form.on("Packaging", {
	refresh(frm) {
		if (frm.doc.wine_batch) {
			frm.add_custom_button(__("View Wine Batch"), () => {
				frappe.set_route("Form", "Wine Batch", frm.doc.wine_batch);
			});
		}
		if (frm.doc.bottling) {
			frm.add_custom_button(__("View Bottling"), () => {
				frappe.set_route("Form", "Bottling", frm.doc.bottling);
			});
		}
		if (frm.doc.stock_entry) {
			frm.add_custom_button(__("View Stock Entry"), () => {
				frappe.set_route("Form", "Stock Entry", frm.doc.stock_entry);
			});
		}
	},

	bottling(frm) {
		if (!frm.doc.bottling) return;
		frappe.db.get_value(
			"Bottling",
			frm.doc.bottling,
			["net_bottles_for_sale", "output_item", "output_warehouse", "wine_batch"],
			(r) => {
				if (!r) return;
				frm.set_value("available_bottles", r.net_bottles_for_sale || 0);
				if (r.output_item && !frm.doc.input_item)
					frm.set_value("input_item", r.output_item);
				if (r.output_warehouse && !frm.doc.input_warehouse)
					frm.set_value("input_warehouse", r.output_warehouse);
				if (r.wine_batch && !frm.doc.wine_batch)
					frm.set_value("wine_batch", r.wine_batch);
				_recalculate_summary(frm);
			}
		);
	},
});

frappe.ui.form.on("Packaging Line", {
	pack_size(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const bpc = BOTTLES_PER_CARTON[row.pack_size] || 0;
		frappe.model.set_value(cdt, cdn, "bottles_per_carton", bpc);
		frappe.model.set_value(cdt, cdn, "total_bottles", (row.cartons || 0) * bpc);
		_recalculate_summary(frm);
	},

	cartons(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const bpc = row.bottles_per_carton || BOTTLES_PER_CARTON[row.pack_size] || 0;
		frappe.model.set_value(cdt, cdn, "total_bottles", (row.cartons || 0) * bpc);
		_recalculate_summary(frm);
	},

	packaging_lines_remove(frm) {
		_recalculate_summary(frm);
	},
});

function _recalculate_summary(frm) {
	let total_packed = 0;
	(frm.doc.packaging_lines || []).forEach((row) => {
		total_packed += row.total_bottles || 0;
	});
	frm.set_value("total_bottles_packed", total_packed);
	const available = frm.doc.available_bottles || 0;
	frm.set_value("remaining_bottles", Math.max(available - total_packed, 0));
}
