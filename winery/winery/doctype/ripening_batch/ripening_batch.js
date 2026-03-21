// Copyright (c) 2026, Finesoft Afrika and contributors
// For license information, please see license.txt

frappe.ui.form.on("Ripening Batch", {
	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("End Ripening"), () => {
				show_end_ripening_dialog(frm);
			}, __("Actions"));

			frm.add_custom_button(__("Start Wine Production"), () => {
				frappe.new_doc("Wine Batch", { ripening_batch: frm.doc.name });
			}, __("Actions"));
		}
		if (frm.doc.rack) {
			frm.add_custom_button(__("View Rack"), () => {
				frappe.set_route("Form", "Ripening Rack", frm.doc.rack);
			});
		}
		if (frm.doc.stock_entry) {
			frm.add_custom_button(__("Banana Transfer Entry"), () => {
				frappe.set_route("Form", "Stock Entry", frm.doc.stock_entry);
			}, __("Stock Entries"));
		}
	},

	start_date(frm) { _compute_expected_end_date(frm); },
	ripening_days(frm) { _compute_expected_end_date(frm); },
});

frappe.ui.form.on("Ripening Additives", {
	ripening_materials_remove(frm) {
		// total_materials_cost is computed server-side on save
		frm.dirty();
	},
});

frappe.ui.form.on("Ripening Batch Source", {
	banana_grading(frm, cdt, cdn) {
		frappe.model.set_value(cdt, cdn, "batch_no", "");
		frappe.model.set_value(cdt, cdn, "available_fingers", 0);
		frappe.model.set_value(cdt, cdn, "quality_grade", "");

		const row = locals[cdt][cdn];
		if (row.banana_grading) {
			frappe.db.get_value("Banana Grading", row.banana_grading, ["banana_item", "warehouse"]).then((r) => {
				if (r && r.message) {
					if (r.message.banana_item && !frm.doc.banana_item) frm.set_value("banana_item", r.message.banana_item);
					if (r.message.warehouse && !frm.doc.source_warehouse) frm.set_value("source_warehouse", r.message.warehouse);
				}
			});
		}
	},

	batch_no(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.batch_no || !row.banana_grading) return;

		frappe.call({
			method: "winery.winery.doctype.ripening_batch.ripening_batch.get_grading_batch_details",
			args: { banana_grading: row.banana_grading, batch_no: row.batch_no },
			callback(r) {
				if (r.message) {
					frappe.model.set_value(cdt, cdn, "available_fingers", r.message.fingers || 0);
					frappe.model.set_value(cdt, cdn, "quality_grade", r.message.quality_grade || "");
					if (!row.fingers_for_ripening) {
						frappe.model.set_value(cdt, cdn, "fingers_for_ripening", r.message.fingers || 0);
					}
					_compute_totals(frm);
				}
			},
		});
	},

	fingers_for_ripening(frm, cdt, cdn) {
		_validate_fingers(cdt, cdn);
		_compute_totals(frm);
	},

	banana_grading_batches_remove(frm) { _compute_totals(frm); },
});

// --------------------------------------------------------------------------
// End Ripening dialog
// --------------------------------------------------------------------------

function show_end_ripening_dialog(frm) {
	frappe.call({
		method: "winery.winery.doctype.ripening_batch.ripening_batch.get_batch_quantities_in_rack",
		args: { ripening_batch: frm.doc.name },
		callback(r) {
			if (!r.message) return;
			const { batches } = r.message;

			if (!batches || !batches.length) return;

			// Build one set of fields per batch row
			const batch_fields = [];
			batches.forEach((b, idx) => {
				if (idx > 0) batch_fields.push({ fieldtype: "Column Break" });
				batch_fields.push(
					{
						fieldtype: "HTML",
						options: `<div class="form-group">
							<label class="control-label">${b.batch_no}</label>
							<p class="help-box small text-muted">${b.fingers_in_rack} fingers currently in rack</p>
						</div>`,
					},
					{
						fieldname: `xfer_${idx}`,
						fieldtype: "Int",
						label: `Transfer (max ${b.fingers_in_rack})`,
						default: b.fingers_in_rack,
						description: b.quality_grade ? `Grade: ${b.quality_grade}` : "",
					}
				);
			});

			const dialog = new frappe.ui.Dialog({
				title: __("End Ripening — Transfer to Warehouse"),
				fields: [
					{
						fieldname: "ripe_item",
						fieldtype: "Link",
						label: __("Ripe Banana Item"),
						options: "Item",
						reqd: 1,
					},
					{ fieldtype: "Column Break" },
					{
						fieldname: "destination_warehouse",
						fieldtype: "Link",
						label: __("Destination Warehouse"),
						options: "Warehouse",
						reqd: 1,
					},
					{ fieldtype: "Column Break" },
					{
						fieldname: "end_date",
						fieldtype: "Date",
						label: __("Transfer Date"),
						default: frappe.datetime.get_today(),
						reqd: 1,
					},
					{
						fieldtype: "Section Break",
						label: __("Fingers to Transfer per Batch"),
						description: __("Leave at max to transfer all. Enter fewer to split — the remainder stays in the rack under a new batch number."),
					},
					...batch_fields,
				],
				primary_action_label: __("Transfer"),
				primary_action(values) {
					// Build transfers array from dynamic fields
					const transfers = batches.map((b, idx) => ({
						batch_no: b.batch_no,
						fingers_in_rack: b.fingers_in_rack,
						fingers_to_transfer: values[`xfer_${idx}`] || 0,
					}));

					const invalid = transfers.find(
						(t) => t.fingers_to_transfer <= 0 || t.fingers_to_transfer > t.fingers_in_rack
					);
					if (invalid) {
						frappe.msgprint(
							__(`Batch ${invalid.batch_no}: transfer amount must be between 1 and ${invalid.fingers_in_rack}.`)
						);
						return;
					}

					frappe.call({
						method: "winery.winery.doctype.ripening_batch.ripening_batch.end_ripening",
						args: {
							ripening_batch: frm.doc.name,
							ripe_item: values.ripe_item,
							destination_warehouse: values.destination_warehouse,
							end_date: values.end_date,
							transfers: JSON.stringify(transfers),
						},
						freeze: true,
						freeze_message: __("Processing ripening transfer…"),
						callback(r) {
							if (!r.exc) {
								dialog.hide();
								frm.reload_doc();
							}
						},
					});
				},
			});

			dialog.show();
		},
	});
}

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------

function _validate_fingers(cdt, cdn) {
	const row = locals[cdt][cdn];
	const available = row.available_fingers || 0;
	const going = row.fingers_for_ripening || 0;
	if (available && going > available) {
		frappe.msgprint({
			title: __("Exceeds Available"),
			message: __(`Batch <b>${row.batch_no}</b>: ${going} entered but only ${available} available.`),
			indicator: "orange",
		});
	}
}

function _compute_totals(frm) {
	const total = (frm.doc.banana_grading_batches || []).reduce(
		(sum, row) => sum + (row.fingers_for_ripening || 0), 0
	);
	frm.set_value("total_fingers_ripening", total);
}


function _compute_expected_end_date(frm) {
	if (frm.doc.start_date && frm.doc.ripening_days) {
		const expected = frappe.datetime.add_days(frm.doc.start_date, frm.doc.ripening_days);
		frm.set_value("expected_end_date", expected);
	}
}
