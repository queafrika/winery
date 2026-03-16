// Copyright (c) 2026, Finesoft Afrika and contributors
// For license information, please see license.txt

frappe.ui.form.on("Fermentation Log", {
	refresh(frm) {
		_show_status_banner(frm);

		if (frm.doc.wine_batch) {
			frm.add_custom_button(__("View Wine Batch"), () => {
				frappe.set_route("Form", "Wine Batch", frm.doc.wine_batch);
			});
		}

		// Quick-add today's temperature button
		if (frm.doc.fermentation_status === "Active" && !frm.doc.__islocal) {
			frm.add_custom_button(__("Add Today's Temperature"), () => {
				_add_todays_temp_row(frm);
			}, __("Quick Entry"));

			frm.add_custom_button(__("Add Weekly Sample"), () => {
				_add_weekly_sample_row(frm);
			}, __("Quick Entry"));
		}
	},

	fermentation_start_date(frm) {
		_update_days(frm);
	},

	batch_process_log(frm) {
		if (!frm.doc.batch_process_log) return;
		frappe.db.get_value("Batch Process Log", frm.doc.batch_process_log, ["vessel", "wine_batch"], (r) => {
			if (!r) return;
			if (r.vessel && !frm.doc.vessel) frm.set_value("vessel", r.vessel);
			if (r.wine_batch && !frm.doc.wine_batch) frm.set_value("wine_batch", r.wine_batch);
		});
	},
});

frappe.ui.form.on("Fermentation Temperature Reading", {
	morning_temp(frm, cdt, cdn) { _calc_avg_temp(frm, cdt, cdn); },
	afternoon_temp(frm, cdt, cdn) { _calc_avg_temp(frm, cdt, cdn); },
	evening_temp(frm, cdt, cdn) { _calc_avg_temp(frm, cdt, cdn); },
});

frappe.ui.form.on("Fermentation Sample", {
	specific_gravity(frm) { _check_stability_live(frm); },
	sample_date(frm, cdt, cdn) { _calc_week_number(frm, cdt, cdn); },
});

// ── Temperature average & out-of-range flag ──────────────────────────────────
function _calc_avg_temp(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const readings = [row.morning_temp, row.afternoon_temp, row.evening_temp].filter(
		(v) => v !== undefined && v !== null && v !== 0
	);
	if (!readings.length) return;

	const avg = flt(readings.reduce((a, b) => a + b, 0) / readings.length, 1);
	frappe.model.set_value(cdt, cdn, "average_temp", avg);

	const min = frm.doc.target_temp_min || 0;
	const max = frm.doc.target_temp_max || 999;
	const out = readings.some((t) => t < min || t > max) ? 1 : 0;
	frappe.model.set_value(cdt, cdn, "out_of_range", out);

	if (out) {
		frappe.show_alert(
			{
				message: `Temperature out of range on ${row.date || "this row"} (target: ${min}–${max}°C)`,
				indicator: "red",
			},
			8
		);
	}
}

// ── Week number from start date ───────────────────────────────────────────────
function _calc_week_number(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!frm.doc.fermentation_start_date || !row.sample_date) return;
	const start = frappe.datetime.str_to_obj(frm.doc.fermentation_start_date);
	const sample = frappe.datetime.str_to_obj(row.sample_date);
	const days = frappe.datetime.get_diff(row.sample_date, frm.doc.fermentation_start_date);
	const week = Math.max(1, Math.floor(days / 7) + 1);
	frappe.model.set_value(cdt, cdn, "week_number", week);
}

// ── Live stability check ──────────────────────────────────────────────────────
function _check_stability_live(frm) {
	const rows = (frm.doc.weekly_samples || []).filter((r) => r.specific_gravity);
	if (rows.length < 3) return;

	const last3 = rows.slice(-3).map((r) => r.specific_gravity);
	const range = Math.max(...last3) - Math.min(...last3);
	if (range <= 0.002) {
		frappe.show_alert(
			{
				message: "Fermentation appears stable — last 3 gravity readings within ±0.002. Consider marking as Complete.",
				indicator: "green",
			},
			10
		);
	}

	// Update latest SG in header
	const latest = rows[rows.length - 1];
	frm.set_value("latest_sg", latest.specific_gravity);
}

// ── Days in fermentation ──────────────────────────────────────────────────────
function _update_days(frm) {
	if (!frm.doc.fermentation_start_date) return;
	const days = frappe.datetime.get_diff(frappe.datetime.get_today(), frm.doc.fermentation_start_date);
	frm.set_value("days_in_fermentation", Math.max(0, days));
}

// ── Status banner ─────────────────────────────────────────────────────────────
function _show_status_banner(frm) {
	if (frm.doc.fermentation_stable && frm.doc.fermentation_status === "Active") {
		frm.dashboard.set_headline_alert(
			`<span class="indicator green">Fermentation is STABLE — ready to proceed to ABV testing and bottling.</span>`
		);
	} else if (frm.doc.fermentation_status === "Active") {
		const days = frm.doc.days_in_fermentation || 0;
		const latest_sg = frm.doc.latest_sg ? ` | Latest SG: ${frm.doc.latest_sg}` : "";
		frm.dashboard.set_headline_alert(
			`<span class="indicator orange">Fermentation ACTIVE — Day ${days}${latest_sg}</span>`
		);
	} else if (frm.doc.fermentation_status === "Complete") {
		frm.dashboard.set_headline_alert(
			`<span class="indicator blue">Fermentation COMPLETE — ${frm.doc.days_in_fermentation || 0} days total.</span>`
		);
	}
}

// ── Quick add today's temperature row ────────────────────────────────────────
function _add_todays_temp_row(frm) {
	const today = frappe.datetime.get_today();
	const existing = (frm.doc.temp_readings || []).find((r) => r.date === today);
	if (existing) {
		frappe.show_alert({ message: "Today's temperature row already exists.", indicator: "orange" }, 5);
		return;
	}
	const row = frm.add_child("temp_readings", { date: today });
	frm.refresh_field("temp_readings");
	frappe.show_alert({ message: "Temperature row added for today. Fill in Morning / Afternoon / Evening.", indicator: "green" }, 5);
}

// ── Quick add weekly sample row ───────────────────────────────────────────────
function _add_weekly_sample_row(frm) {
	const today = frappe.datetime.get_today();
	const row = frm.add_child("weekly_samples", {
		sample_date: today,
		analyst: frappe.session.user,
	});
	frm.refresh_field("weekly_samples");
	frappe.show_alert({ message: "Weekly sample row added. Enter Specific Gravity and pH.", indicator: "green" }, 5);
}
