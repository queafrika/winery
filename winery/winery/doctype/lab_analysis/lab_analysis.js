// Copyright (c) 2026, Finesoft Afrika and contributors
// For license information, please see license.txt

frappe.ui.form.on("Lab Analysis", {
	refresh(frm) {
		_show_due_alert(frm);

		if (frm.doc.wine_batch) {
			frm.add_custom_button(__("View Wine Batch"), () => {
				frappe.set_route("Form", "Wine Batch", frm.doc.wine_batch);
			});
		}
	},

	wine_batch(frm) {
		if (!frm.doc.wine_batch || frm.doc.test_type) return;
		_suggest_test_type_from_recipe(frm);
	},

	batch_process_log(frm) {
		if (frm.doc.batch_process_log) {
			frappe.db.get_value(
				"Batch Process Log",
				frm.doc.batch_process_log,
				["vessel", "wine_batch"],
				(r) => {
					if (r) {
						if (r.vessel && !frm.doc.vessel) frm.set_value("vessel", r.vessel);
						if (r.wine_batch && !frm.doc.wine_batch)
							frm.set_value("wine_batch", r.wine_batch);
					}
				}
			);
		}
	},

	// ── Residual Sugar ──────────────────────────────────────────────
	rs_reading_1(frm) { _calc_residual_sugar(frm); },
	rs_reading_2(frm) { _calc_residual_sugar(frm); },
	rs_reading_3(frm) { _calc_residual_sugar(frm); },
	rs_temp_correction(frm) { _calc_residual_sugar(frm); },

	// ── Brix ────────────────────────────────────────────────────────
	brix_reading_1(frm) { _calc_brix(frm); },
	brix_reading_2(frm) { _calc_brix(frm); },
	brix_reading_3(frm) { _calc_brix(frm); },

	// ── ABV ─────────────────────────────────────────────────────────
	abv_reading_1(frm) { _calc_abv(frm); },
	abv_reading_2(frm) { _calc_abv(frm); },
	abv_reading_3(frm) { _calc_abv(frm); },
	abv_correction_factor(frm) { _calc_abv(frm); },

	// ── Temperature Test ─────────────────────────────────────────────
	temp_reading_1(frm) { _calc_temp(frm); },
	temp_reading_2(frm) { _calc_temp(frm); },
	temp_reading_3(frm) { _calc_temp(frm); },
	temp_target_min(frm) { _calc_temp(frm); },
	temp_target_max(frm) { _calc_temp(frm); },

	// ── pH Test ───────────────────────────────────────────────────────
	ph_stage(frm) { _set_ph_targets(frm); _calc_ph(frm); },
	ph_reading_1(frm) { _calc_ph(frm); },
	ph_reading_2(frm) { _calc_ph(frm); },
	ph_reading_3(frm) { _calc_ph(frm); },
	ph_cal_buffer_4_pass(frm) { _calc_ph_calibration(frm); },
	ph_cal_buffer_7_pass(frm) { _calc_ph_calibration(frm); },
	ph_cal_buffer_10_pass(frm) { _calc_ph_calibration(frm); },
});

frappe.ui.form.on("Lab Analysis Taster Score", {
	score(frm) { _calc_sensory_average(frm); },
	sens_taster_scores_remove(frm) { _calc_sensory_average(frm); },
});

frappe.ui.form.on("Lab Analysis Reading", {
	parameter(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.parameter) {
			frappe.db.get_value(
				"Lab Test Parameter",
				row.parameter,
				["default_uom", "min_value", "max_value"],
				(r) => {
					if (r && r.default_uom) {
						frappe.model.set_value(cdt, cdn, "unit", r.default_uom);
					}
				}
			);
		}
	},

	value(frm, cdt, cdn) {
		_check_range(cdt, cdn);
	},
});

// ── Residual Sugar calculation ───────────────────────────────────────────────
function _calc_residual_sugar(frm) {
	const readings = [frm.doc.rs_reading_1, frm.doc.rs_reading_2, frm.doc.rs_reading_3].filter(
		(v) => v !== undefined && v !== null && v !== 0
	);
	if (!readings.length) return;

	const avg = readings.reduce((a, b) => a + b, 0) / readings.length;
	frm.set_value("rs_average_fg", flt(avg, 3));

	const correction = frm.doc.rs_temp_correction || 0;
	const corrected = flt(avg + correction, 3);
	frm.set_value("rs_corrected_fg", corrected);

	const rs = flt((corrected - 1.0) * 1000, 2);
	frm.set_value("rs_residual_sugar_gl", rs);

	// Auto-classify wine
	let classification = "";
	if (corrected < 1.001) {
		classification = "Bone Dry (<1 g/L)";
		frm.set_value("rs_fg_below_1000", 1);
	} else if (rs < 2) {
		classification = "Very Dry (1-2 g/L)";
	} else if (rs < 5) {
		classification = "Dry (2-5 g/L)";
	} else if (rs < 10) {
		classification = "Off-Dry (5-10 g/L)";
	} else if (rs < 15) {
		classification = "Medium Sweet (10-15 g/L)";
	} else if (rs < 25) {
		classification = "Sweet (15-25 g/L)";
	} else {
		classification = "Very Sweet (>25 g/L)";
	}
	frm.set_value("rs_wine_classification", classification);
}

// ── Brix calculation ─────────────────────────────────────────────────────────
function _calc_brix(frm) {
	const readings = [frm.doc.brix_reading_1, frm.doc.brix_reading_2, frm.doc.brix_reading_3].filter(
		(v) => v !== undefined && v !== null && v !== 0
	);
	if (!readings.length) return;

	const avg = flt(readings.reduce((a, b) => a + b, 0) / readings.length, 2);
	frm.set_value("brix_average", avg);
	frm.set_value("brix_potential_abv", flt(avg * 0.59, 2));
}

// ── ABV calculation ──────────────────────────────────────────────────────────
function _calc_abv(frm) {
	const readings = [frm.doc.abv_reading_1, frm.doc.abv_reading_2, frm.doc.abv_reading_3].filter(
		(v) => v !== undefined && v !== null && v !== 0
	);
	if (!readings.length) return;

	const avg = flt(readings.reduce((a, b) => a + b, 0) / readings.length, 2);
	frm.set_value("abv_average_abv", avg);

	const correction = frm.doc.abv_correction_factor || 0;
	frm.set_value("abv_corrected_abv", flt(avg + correction, 2));
}

// ── Temperature Test calculation ─────────────────────────────────────────────
function _calc_temp(frm) {
	const readings = [frm.doc.temp_reading_1, frm.doc.temp_reading_2, frm.doc.temp_reading_3].filter(
		(v) => v !== undefined && v !== null && v !== 0
	);
	if (!readings.length) return;

	const avg = flt(readings.reduce((a, b) => a + b, 0) / readings.length, 1);
	frm.set_value("temp_average", avg);

	const min = frm.doc.temp_target_min;
	const max = frm.doc.temp_target_max;
	const out_of_range = (min !== null && min !== undefined && readings.some(t => t < min)) ||
	                     (max !== null && max !== undefined && readings.some(t => t > max));

	frm.set_value("temp_out_of_range", out_of_range ? 1 : 0);

	if (out_of_range) {
		frappe.show_alert({
			message: `Temperature out of range! Average: ${avg}°C (target: ${min ?? "?"}–${max ?? "?"}°C)`,
			indicator: "red",
		}, 8);
	}
}

// ── Sensory average score ────────────────────────────────────────────────────
function _calc_sensory_average(frm) {
	const rows = frm.doc.sens_taster_scores || [];
	const scores = rows.map((r) => r.score).filter((s) => s !== undefined && s !== null);
	if (!scores.length) return;

	const avg = flt(scores.reduce((a, b) => a + b, 0) / scores.length, 1);
	frm.set_value("sens_average_score", avg);

	let classification = "";
	if (avg >= 9) classification = "Excellent (9-10)";
	else if (avg >= 7) classification = "Very Good (7-8)";
	else if (avg >= 5) classification = "Acceptable (5-6)";
	else if (avg >= 3) classification = "Below Standard (3-4)";
	else classification = "Unacceptable (0-2)";
	frm.set_value("sens_quality_classification", classification);
}

// ── pH Test ──────────────────────────────────────────────────────────────────
function _set_ph_targets(frm) {
	if (frm.doc.ph_stage === "Pre-Production") {
		frm.set_value("ph_target_min", 6.5);
		frm.set_value("ph_target_max", 7.5);
	} else if (frm.doc.ph_stage === "Post-Production") {
		frm.set_value("ph_target_min", 3.2);
		frm.set_value("ph_target_max", 4.0);
	}
}

function _calc_ph_calibration(frm) {
	const all_pass = frm.doc.ph_cal_buffer_4_pass && frm.doc.ph_cal_buffer_7_pass && frm.doc.ph_cal_buffer_10_pass;
	frm.set_value("ph_calibration_pass", all_pass ? "PASS" : "FAIL");
}

function _calc_ph(frm) {
	const readings = [frm.doc.ph_reading_1, frm.doc.ph_reading_2, frm.doc.ph_reading_3].filter(
		(v) => v !== undefined && v !== null && v !== 0
	);
	if (!readings.length) return;

	const avg = flt(readings.reduce((a, b) => a + b, 0) / readings.length, 2);
	frm.set_value("ph_average", avg);

	const min = frm.doc.ph_target_min;
	const max = frm.doc.ph_target_max;
	if (min !== null && min !== undefined && max !== null && max !== undefined) {
		const result = (avg >= min && avg <= max) ? "PASS" : "FAIL";
		frm.set_value("ph_result", result);
		frappe.show_alert({
			message: `pH ${avg} — ${result} (target ${min}–${max})`,
			indicator: result === "PASS" ? "green" : "red",
		}, 6);
	}
}

// ── Auto-suggest test type from Recipe ───────────────────────────────────────
function _suggest_test_type_from_recipe(frm) {
	frappe.db.get_value("Wine Batch", frm.doc.wine_batch, ["recipe", "current_stage_name"], (wb) => {
		if (!wb || !wb.recipe) return;

		frappe.db.get_doc("Recipe", wb.recipe).then((recipe) => {
			if (!recipe.lab_analyses || !recipe.lab_analyses.length) return;

			const current_stage = wb.current_stage_name || "";
			// Filter tests for current stage, or all if no stage yet
			const matching = recipe.lab_analyses.filter(
				(r) => !r.stage_name || r.stage_name === current_stage
			);

			if (!matching.length) return;

			if (matching.length === 1) {
				// Only one test — auto-fill it
				frm.set_value("test_type", matching[0].test_type);
				frappe.show_alert({
					message: `Test type set from Recipe: <b>${matching[0].test_type}</b>`,
					indicator: "green",
				}, 5);
			} else {
				// Multiple tests — show a dialog to pick
				const options = matching.map((r) => ({
					label: `${r.test_type}${r.is_mandatory ? " (Mandatory)" : " (Optional)"}${r.stage_name ? " — Stage: " + r.stage_name : ""}`,
					value: r.test_type,
				}));

				frappe.prompt(
					[{
						fieldname: "test_type",
						fieldtype: "Select",
						label: "Select Test Type",
						options: options.map((o) => o.value).join("\n"),
						reqd: 1,
						description: `Recipe "${wb.recipe}" defines these tests for stage "${current_stage || "any"}"`,
					}],
					(values) => {
						frm.set_value("test_type", values.test_type);
					},
					__("Select Lab Test from Recipe"),
					__("Apply")
				);
			}
		});
	});
}

// ── Due alert banner ─────────────────────────────────────────────────────────
function _show_due_alert(frm) {
	if (!frm.doc.next_analysis_date || frm.doc.docstatus === 2) return;

	const today = frappe.datetime.get_today();
	const due = frm.doc.next_analysis_date;
	const days_diff = frappe.datetime.get_diff(due, today);

	if (days_diff < 0) {
		frm.dashboard.set_headline_alert(
			`<span class="indicator red">Next analysis was due ${Math.abs(days_diff)} day(s) ago (${due}). Please take measurements immediately.</span>`
		);
	} else if (days_diff === 0) {
		frm.dashboard.set_headline_alert(
			`<span class="indicator orange">Next analysis is due TODAY (${due}). Please take measurements.</span>`
		);
	} else if (days_diff <= (frm.doc.alert_before_days || 1)) {
		frm.dashboard.set_headline_alert(
			`<span class="indicator yellow">Next analysis due in ${days_diff} day(s) on ${due}.</span>`
		);
	}
}

// ── Range check for measurement table ────────────────────────────────────────
function _check_range(cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.parameter || row.value === undefined) return;

	frappe.db.get_value(
		"Lab Test Parameter",
		row.parameter,
		["min_value", "max_value"],
		(r) => {
			if (!r) return;
			const within =
				(r.min_value === null || row.value >= r.min_value) &&
				(r.max_value === null || row.value <= r.max_value);
			frappe.model.set_value(cdt, cdn, "within_range", within ? 1 : 0);
		}
	);
}
