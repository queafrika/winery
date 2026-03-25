// Copyright (c) 2026, Finesoft Afrika and contributors
// For license information, please see license.txt

frappe.ui.form.on("Lab Analysis", {
	refresh(frm) {
		if (frm.doc.wine_batch) {
			frm.add_custom_button(__("View Wine Batch"), () => {
				frappe.set_route("Form", "Wine Batch", frm.doc.wine_batch);
			});
		}
		if (frm.doc.item_batch) {
			frm.add_custom_button(__("View Item Batch"), () => {
				frappe.set_route("Form", "Batch", frm.doc.item_batch);
			});
		}
		_render_batch_qa_status(frm);
	},

	analysis_source(frm) {
		// Clear the irrelevant link fields when switching source
		if (frm.doc.analysis_source === "Purchased Item") {
			frm.set_value("wine_batch", null);
			frm.set_value("cellar_operation", null);
			frm.set_value("cellar_operation_task", null);
		} else {
			frm.set_value("item_batch", null);
			frm.set_value("item", null);
			frm.set_value("supplier", null);
		}
	},

	item_batch(frm) {
		if (frm.doc.item_batch) {
			frm.set_value("wine_batch", null);
			frm.set_value("cellar_operation", null);
		}
		_render_batch_qa_status(frm);
	},

	wine_batch(frm) {
		if (!frm.doc.wine_batch || frm.doc.test_type) return;
		_suggest_test_type_from_recipe(frm);
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
	ph_reading_1(frm) { _calc_ph(frm); },
	ph_reading_2(frm) { _calc_ph(frm); },
	ph_reading_3(frm) { _calc_ph(frm); },
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

// ── pH Test ──────────────────────────────────────────────────────────────────
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

// ── Batch QA status panel (Purchased Item analyses) ─────────────────────────
function _render_batch_qa_status(frm) {
	frm.set_intro("");
	if (frm.doc.analysis_source !== "Purchased Item" || !frm.doc.item_batch || !frm.doc.item) return;

	Promise.all([
		frappe.db.get_list("Item Lab Test Requirement", {
			filters: { parent: frm.doc.item },
			fields: ["test_type", "is_mandatory"],
		}),
		frappe.db.get_list("Lab Analysis", {
			filters: { item_batch: frm.doc.item_batch, docstatus: 1 },
			fields: ["test_type"],
		}),
		frappe.db.get_value("Batch", frm.doc.item_batch, "qa_status"),
	]).then(([requirements, done_analyses, batch_r]) => {
		if (!requirements.length) return;

		const done_types = new Set(done_analyses.map((r) => r.test_type));
		const qa_status = batch_r && batch_r.message ? batch_r.message.qa_status : null;

		const status_badge = qa_status === "Released"
			? `<span class="badge badge-success">${__("Released")}</span>`
			: `<span class="badge badge-warning">${__("Pending QA")}</span>`;

		let rows = requirements.map((r) => {
			const done = done_types.has(r.test_type);
			const icon = done ? "✓" : "✗";
			const color = done ? "green" : (r.is_mandatory ? "red" : "#888");
			const mandatory = r.is_mandatory ? ` <small>(${__("mandatory")})</small>` : ` <small>(${__("optional")})</small>`;
			return `<span style="margin-right:14px;color:${color}">${icon} ${r.test_type}${mandatory}</span>`;
		}).join("");

		frm.set_intro(
			`<b>${__("Batch QA Status")}:</b> ${status_badge} &nbsp;&nbsp; ${rows}`,
			qa_status === "Released" ? "green" : "orange"
		);
	});
}
