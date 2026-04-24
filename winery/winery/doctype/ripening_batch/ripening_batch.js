// Copyright (c) 2026, Finesoft Afrika and contributors
// For license information, please see license.txt

frappe.ui.form.on("Ripening Batch", {
	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("End Ripening"), () => {
				show_end_ripening_dialog(frm);
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

		// Show end-ripening Repack stock entries (may be multiple for partial transfers)
		frappe.db.get_list("Stock Entry", {
			filters: {
				remarks: ["like", `%End ripening for ${frm.doc.name}%`],
				docstatus: ["!=", 2],
			},
			fields: ["name", "posting_date"],
			order_by: "posting_date asc",
		}).then((entries) => {
			entries.forEach((entry) => {
				frm.add_custom_button(
					__("End Ripening — {0}", [entry.posting_date]),
					() => frappe.set_route("Form", "Stock Entry", entry.name),
					__("Stock Entries")
				);
			});
		});

		// Filter banana_item to only show Raw Banana Finger variants
		frappe.db.get_single_value("Winery Settings", "raw_banana_finger_template").then((tpl) => {
			if (tpl) {
				frm.set_query("banana_item", () => ({ filters: { variant_of: tpl } }));
			}
		});

		// Filter batch_no dropdown to only show batches for the selected banana item
		_set_batch_no_query(frm);
	},

	banana_item(frm) {
		// Re-apply the filter so the dropdown reflects the new item
		_set_batch_no_query(frm);

		// Clear child rows that no longer match the newly selected item
		(frm.doc.banana_grading_batches || []).forEach((row) => {
			if (row.batch_no) {
				frappe.model.set_value(row.doctype, row.name, "batch_no", "");
				frappe.model.set_value(row.doctype, row.name, "available_fingers", 0);
				frappe.model.set_value(row.doctype, row.name, "quality_grade", "");
				frappe.model.set_value(row.doctype, row.name, "farm", "");
				frappe.model.set_value(row.doctype, row.name, "variety", "");
			}
		});
	},

	start_date(frm) { _compute_expected_end_date(frm); },
	ripening_days(frm) { _compute_expected_end_date(frm); },

	source_warehouse(frm) {
		// Re-fetch available fingers for all rows now that warehouse is known
		(frm.doc.banana_grading_batches || []).forEach((row) => {
			if (row.batch_no) {
				frappe.call({
					method: "winery.winery.doctype.ripening_batch.ripening_batch.get_batch_details_for_ripening",
					args: {
						batch_no: row.batch_no,
						source_warehouse: frm.doc.source_warehouse || "",
						banana_item: frm.doc.banana_item || "",
					},
					callback(r) {
						if (r.message) {
							frappe.model.set_value(row.doctype, row.name, "available_fingers", r.message.available_fingers || 0);
						}
					},
				});
			}
		});
	},
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
		frappe.model.set_value(cdt, cdn, "farm", "");
		frappe.model.set_value(cdt, cdn, "variety", "");

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
		if (!row.batch_no) return;

		frappe.call({
			method: "winery.winery.doctype.ripening_batch.ripening_batch.get_batch_details_for_ripening",
			args: {
				batch_no: row.batch_no,
				source_warehouse: frm.doc.source_warehouse || "",
				banana_item: frm.doc.banana_item || "",
			},
			callback(r) {
				if (r.message) {
					const d = r.message;
					frappe.model.set_value(cdt, cdn, "quality_grade", d.quality_grade || "");
					frappe.model.set_value(cdt, cdn, "farm", d.farm || "");
					frappe.model.set_value(cdt, cdn, "variety", d.variety || "");
					frappe.model.set_value(cdt, cdn, "available_fingers", d.available_fingers || 0);
					if (!row.fingers_for_ripening) {
						frappe.model.set_value(cdt, cdn, "fingers_for_ripening", d.available_fingers || 0);
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

			// Build one field-group per batch — show farm/variety/grade for clarity
			const batch_fields = [];
			batches.forEach((b, idx) => {
				if (idx > 0) batch_fields.push({ fieldtype: "Column Break" });
				const meta = [
					b.quality_grade ? `Grade: <b>${b.quality_grade}</b>` : "",
					b.farm          ? `Farm: <b>${b.farm}</b>`           : "",
					b.variety       ? `Variety: <b>${b.variety}</b>`     : "",
				].filter(Boolean).join(" &nbsp;|&nbsp; ");
				batch_fields.push(
					{
						fieldtype: "HTML",
						options: `<div class="form-group">
							<label class="control-label">${b.batch_no}</label>
							<p class="help-box small text-muted">${meta}</p>
							<p class="help-box small text-muted">${b.fingers_in_rack} fingers currently in rack</p>
						</div>`,
					},
					{
						fieldname: `xfer_${idx}`,
						fieldtype: "Int",
						label: `Transfer (max ${b.fingers_in_rack})`,
						default: b.fingers_in_rack,
					}
				);
			});

			const dialog = new frappe.ui.Dialog({
				title: __("End Ripening — Transfer to Warehouse"),
				fields: [
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
						description: __("Ripe item is auto-matched per variety. Leave at max to transfer all; enter fewer to split — the remainder stays in the rack under a new batch number."),
					},
					...batch_fields,
				],
				primary_action_label: __("Transfer"),
				primary_action(values) {
					const transfers = batches.map((b, idx) => ({
						batch_no: b.batch_no,
						fingers_in_rack: b.fingers_in_rack,
						fingers_to_transfer: values[`xfer_${idx}`] || 0,
					}));

					const invalid = transfers.find(
						(t) => t.fingers_to_transfer < 0 || t.fingers_to_transfer > t.fingers_in_rack
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

function _set_batch_no_query(frm) {
	frm.fields_dict["banana_grading_batches"].grid.get_field("batch_no").get_query = function () {
		return {
			query: "winery.winery.doctype.ripening_batch.ripening_batch.get_batches_with_stock",
			filters: {
				item: frm.doc.banana_item || "",
				warehouse: frm.doc.source_warehouse || "",
			},
		};
	};
}

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
