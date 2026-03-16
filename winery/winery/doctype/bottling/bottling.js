// Copyright (c) 2026, Finesoft Afrika and contributors
// For license information, please see license.txt

frappe.ui.form.on("Bottling", {
	refresh(frm) {
		if (frm.doc.stock_entry) {
			frm.add_custom_button(__("View Stock Entry"), () => {
				frappe.set_route("Form", "Stock Entry", frm.doc.stock_entry);
			});
		}
		if (frm.doc.wine_batch) {
			frm.add_custom_button(__("View Wine Batch"), () => {
				frappe.set_route("Form", "Wine Batch", frm.doc.wine_batch);
			});
		}
		_render_yield_indicator(frm);
	},

	input_quantity(frm) { _compute_summary(frm); },
	abv_percentage(frm) { _lookup_abv_band(frm); },
	excise_duty_per_litre(frm) { _compute_excise(frm); },
});

// Recompute when any bottling line changes
frappe.ui.form.on("Bottling Line", {
	actual_bottles(frm) { _compute_summary(frm); },
	bottle_size_ml(frm) { _compute_summary(frm); },
	qc_bottles(frm) { _compute_summary(frm); },
	bottling_lines_remove(frm) { _compute_summary(frm); },
});

// Recompute when any packaging line changes
frappe.ui.form.on("Packaging Line", {
	cartons(frm) { _compute_packaging_totals(frm); },
	bottles_per_carton(frm) { _compute_packaging_totals(frm); },
	packaging_lines_remove(frm) { _compute_packaging_totals(frm); },
});

// --------------------------------------------------------------------------
// Bottling line totals
// --------------------------------------------------------------------------

function _compute_summary(frm) {
	let total_volume = 0;

	(frm.doc.bottling_lines || []).forEach((row) => {
		const actual = cint(row.actual_bottles);
		const size_ml = cint(row.bottle_size_ml);
		const qc = cint(row.qc_bottles);
		const net = Math.max(actual - qc, 0);
		const volume = size_ml ? Math.round(actual * size_ml / 1000 * 10000) / 10000 : 0;

		frappe.model.set_value(row.doctype, row.name, "net_bottles", net);
		frappe.model.set_value(row.doctype, row.name, "volume_litres", volume);
		total_volume += volume;
	});

	total_volume = Math.round(total_volume * 10000) / 10000;
	const input_vol = frm.doc.input_quantity || 0;
	const loss = Math.round(Math.max(input_vol - total_volume, 0) * 10000) / 10000;
	const efficiency = input_vol ? Math.round((total_volume / input_vol) * 10000) / 100 : 0;

	frm.set_value("total_volume_bottled", total_volume);
	frm.set_value("process_loss", loss);
	frm.set_value("yield_efficiency_pct", efficiency);

	_compute_excise(frm);
	_render_yield_indicator(frm);
}

function _compute_packaging_totals(frm) {
	(frm.doc.packaging_lines || []).forEach((row) => {
		const total = cint(row.cartons) * cint(row.bottles_per_carton);
		frappe.model.set_value(row.doctype, row.name, "total_bottles", total);
	});
	frm.refresh_field("packaging_lines");
}

// --------------------------------------------------------------------------
// ABV & excise
// --------------------------------------------------------------------------

function _compute_excise(frm) {
	const rate = frm.doc.excise_duty_per_litre || 0;
	const vol = frm.doc.total_volume_bottled || 0;
	frm.set_value("excise_duty_amount", Math.round(vol * rate * 10000) / 10000);
}

function _lookup_abv_band(frm) {
	const abv = frm.doc.abv_percentage;
	if (!abv) {
		frm.set_value("abv_tax_band", "");
		frm.set_value("excise_duty_per_litre", 0);
		frm.set_value("excise_duty_amount", 0);
		return;
	}
	frappe.call({
		method: "winery.winery.doctype.bottling.bottling.get_abv_tax_band",
		args: { abv_percentage: abv },
		callback(r) {
			if (r.message && r.message.name) {
				frm.set_value("abv_tax_band", r.message.name);
				frm.set_value("excise_duty_per_litre", r.message.excise_duty_per_litre);
				_compute_excise(frm);
			} else {
				frm.set_value("abv_tax_band", "");
				frappe.msgprint({
					title: __("No Tax Band Found"),
					message: __(`No ABV Tax Band configured for ${abv}%. Please add one in Setup → ABV Tax Band.`),
					indicator: "orange",
				});
			}
		},
	});
}

// --------------------------------------------------------------------------
// Yield indicator
// --------------------------------------------------------------------------

function _render_yield_indicator(frm) {
	const eff = frm.doc.yield_efficiency_pct || 0;
	if (!eff) return;
	const color = eff >= 95 ? "green" : eff >= 80 ? "orange" : "red";
	const label = eff >= 95 ? "Good" : eff >= 80 ? "Acceptable" : "Review Required";
	frm.dashboard.set_headline_alert(
		`<span class="indicator-pill ${color}" style="font-size:13px">
			Yield Efficiency: ${eff}% — ${label}
		</span>`
	);
}
