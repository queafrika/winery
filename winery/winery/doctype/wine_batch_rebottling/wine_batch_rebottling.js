// Copyright (c) 2026, Finesoft Afrika and contributors
// For license information, please see license.txt

frappe.ui.form.on("Wine Batch Rebottling", {
    refresh(frm) {
        _render_rebottling_buttons(frm);
    },

    onload(frm) {
        if (frm.is_new()) return;
        _render_rebottling_buttons(frm);
    },
});

// ---------------------------------------------------------------------------
// Child table handlers — Rebottling Lines
// ---------------------------------------------------------------------------
frappe.ui.form.on("Wine Batch Rebottling Line", {
    planned_bottles(frm, cdt, cdn) { _recalc_rebottling_line(frm, cdt, cdn); },
    bottle_size_ml(frm, cdt, cdn)  { _recalc_rebottling_line(frm, cdt, cdn); },
});

function _recalc_rebottling_line(frm, cdt, cdn) {
    const row = frappe.get_doc(cdt, cdn);
    const vol = ((row.planned_bottles || 0) * (row.bottle_size_ml || 0)) / 1000;
    frappe.model.set_value(cdt, cdn, "planned_volume_litres", Math.round(vol * 10000) / 10000);
    _validate_repackaging_balance(frm);
}

// ---------------------------------------------------------------------------
// Child table handlers — Repackaging Lines
// ---------------------------------------------------------------------------
frappe.ui.form.on("Wine Batch Repackaging Line", {
    bottle_size_ml(frm, cdt, cdn) {
        _autocalc_repackaging_cartons(frm, cdt, cdn);
        _validate_repackaging_balance(frm);
    },
    bottles_per_carton(frm, cdt, cdn) {
        _autocalc_repackaging_cartons(frm, cdt, cdn);
        _validate_repackaging_balance(frm);
    },
    cartons(frm, cdt, cdn) {
        _recalc_repackaging_planned(frm, cdt, cdn);
        _validate_repackaging_balance(frm);
    },
});

function _autocalc_repackaging_cartons(frm, cdt, cdn) {
    const row = frappe.get_doc(cdt, cdn);
    const sz = cint(row.bottle_size_ml);
    const bpc = cint(row.bottles_per_carton);
    if (!sz || !bpc) return;

    // Sum planned_bottles for this bottle size across all rebottling lines
    let total_planned = 0;
    (frm.doc.rebottling_lines || []).forEach(r => {
        if (cint(r.bottle_size_ml) === sz) total_planned += cint(r.planned_bottles);
    });
    const cartons = Math.floor(total_planned / bpc);
    frappe.model.set_value(cdt, cdn, "cartons", cartons);
    frappe.model.set_value(cdt, cdn, "total_bottles", cartons * bpc);
}

function _recalc_repackaging_planned(frm, cdt, cdn) {
    const row = frappe.get_doc(cdt, cdn);
    const total = cint(row.cartons) * cint(row.bottles_per_carton);
    frappe.model.set_value(cdt, cdn, "total_bottles", total);
}

function _validate_repackaging_balance(frm) {
    const planned = {};
    (frm.doc.rebottling_lines || []).forEach(r => {
        if (r.bottle_size_ml) {
            planned[r.bottle_size_ml] = (planned[r.bottle_size_ml] || 0) + cint(r.planned_bottles);
        }
    });
    const packaged = {};
    (frm.doc.repackaging_lines || []).forEach(r => {
        if (r.bottle_size_ml) {
            packaged[r.bottle_size_ml] = (packaged[r.bottle_size_ml] || 0) + cint(r.total_bottles);
        }
    });
    const mismatches = Object.keys(packaged).filter(
        sz => packaged[sz] !== (planned[sz] || 0)
    );
    if (mismatches.length) {
        const msgs = mismatches.map(sz =>
            `${sz}ml: planned ${planned[sz] || 0} bottles, packaging covers ${packaged[sz]} bottles`
        );
        frappe.show_alert({
            message: __("Repackaging balance mismatch: ") + msgs.join("; "),
            indicator: "orange",
        });
    }
}

// ---------------------------------------------------------------------------
// Button rendering — 4-state logic
// ---------------------------------------------------------------------------
function _render_rebottling_buttons(frm) {
    if (frm.doc.docstatus !== 1) return;

    const status = frm.doc.status;

    if (status === "Completed") {
        if (frm.doc.rebottling_stock_entries) {
            const se_names = frm.doc.rebottling_stock_entries.trim().split("\n").filter(Boolean);
            if (se_names.length === 1) {
                frm.add_custom_button(__("View Stock Entry"), () =>
                    frappe.set_route("Form", "Stock Entry", se_names[0])
                ).addClass("btn-info");
            } else {
                frm.add_custom_button(__("View Stock Entries"), () => {
                    const links = se_names.map(n =>
                        `<li><a href="/app/stock-entry/${n}" target="_blank">${n}</a></li>`
                    ).join("");
                    frappe.msgprint({
                        title: __("Rebottling Stock Entries"),
                        message: `<ul>${links}</ul>`,
                    });
                }).addClass("btn-info");
            }
        }
        frm.add_custom_button(__("Cancel Rebottling"), () => {
            frappe.confirm(__("Cancel all stock entries and revert this rebottling to Pending?"), () => {
                frappe.call({
                    method: "winery.winery.doctype.wine_batch_rebottling.wine_batch_rebottling.cancel_rebottling",
                    args: { rebottling_doc: frm.doc.name },
                    callback() { frm.reload_doc(); },
                });
            });
        }).addClass("btn-danger");
        return;
    }

    // Pending or Rebottling Completed → show Complete Rebottling / Re-enter
    if (status === "Pending" || status === "Rebottling Completed") {
        const label = status === "Rebottling Completed"
            ? __("Re-enter Rebottling Details")
            : __("Complete Rebottling");
        frm.add_custom_button(label, () => _show_rebottling_modal(frm)).addClass("btn-primary");
    }

    // Rebottling or Repackaging Completed → show packaging options + Reset
    if (status === "Rebottling Completed" || status === "Repackaging Completed") {
        const plabel = status === "Repackaging Completed"
            ? __("Re-enter Repackaging Details")
            : __("Complete Repackaging");
        frm.add_custom_button(plabel, () => _show_repackaging_modal(frm)).addClass("btn-primary");

        frm.add_custom_button(__("Reset to Planning"), () => {
            frappe.confirm(
                __("Clear all rebottling/repackaging actuals and return to Planning?"),
                () => frappe.call({
                    method: "winery.winery.doctype.wine_batch_rebottling.wine_batch_rebottling.reset_rebottling_actuals",
                    args: { rebottling_doc: frm.doc.name },
                    callback() { frm.reload_doc(); },
                })
            );
        }).addClass("btn-danger");
    }

    // Repackaging Completed → show Close Rebottling
    if (status === "Repackaging Completed") {
        frm.add_custom_button(__("Close Rebottling"), () => {
            frappe.confirm(
                __("Create Stock Entries and complete this rebottling?"),
                () => frappe.call({
                    method: "winery.winery.doctype.wine_batch_rebottling.wine_batch_rebottling.close_rebottling",
                    args: { rebottling_doc: frm.doc.name },
                    callback(r) {
                        if (r.message) frm.reload_doc();
                    },
                })
            );
        }).addClass("btn-success");
    }
}

// ---------------------------------------------------------------------------
// Complete Rebottling modal
// ---------------------------------------------------------------------------
function _show_rebottling_modal(frm) {
    const source_lines = frm.doc.source_lines || [];
    const rebottling_lines = frm.doc.rebottling_lines || [];

    if (!source_lines.length && !rebottling_lines.length) {
        frappe.msgprint(__("Please add source lines and rebottling lines before completing."));
        return;
    }

    const fields = [
        {
            fieldname: "rebottling_date",
            fieldtype: "Date",
            label: __("Rebottling Date"),
            reqd: 1,
            default: frm.doc.rebottling_date || frappe.datetime.get_today(),
        },
        { fieldname: "sb_sources", fieldtype: "Section Break", label: __("Source Quantities") },
    ];

    // Source line fields
    source_lines.forEach((sl, i) => {
        fields.push({
            fieldname: `actual_quantity_${i}`,
            fieldtype: "Float",
            label: `${sl.source_item} — Planned: ${sl.planned_quantity || 0}`,
            default: sl.actual_quantity || sl.planned_quantity || 0,
            reqd: 1,
            description: `Warehouse: ${sl.source_warehouse || ""}`,
        });
    });

    fields.push({ fieldname: "sb_output", fieldtype: "Section Break", label: __("New Bottle Output") });

    // Rebottling line fields
    rebottling_lines.forEach((bl, i) => {
        const heading = `${bl.bottle_item || "Bottle"} — ${bl.bottle_size_ml}ml — Planned: ${bl.planned_bottles || 0} bottles`;
        fields.push(
            { fieldname: `sb_bl_${i}`, fieldtype: "Section Break", label: heading },
            {
                fieldname: `actual_bottles_${i}`,
                fieldtype: "Int",
                label: __("Actual Bottles"),
                reqd: 1,
                default: bl.actual_bottles || bl.planned_bottles || 0,
            },
            {
                fieldname: `bottled_wine_item_${i}`,
                fieldtype: "Link",
                label: __("Bottled Wine Item"),
                options: "Item",
                reqd: 1,
                default: bl.bottled_wine_item || "",
                description: __("Filled but unpackaged bottle item (for samples & remainder)"),
            },
            {
                fieldname: `qc_bottles_${i}`,
                fieldtype: "Int",
                label: __("QC Bottles Reserved"),
                default: bl.qc_bottles || 0,
            },
            {
                fieldname: `sample_bottles_${i}`,
                fieldtype: "Int",
                label: __("Sample Bottles"),
                default: bl.sample_bottles || 1,
                description: __("Minimum 1"),
            },
            { fieldname: `cb_bl_${i}`, fieldtype: "Column Break" },
            {
                fieldname: `bottle_source_warehouse_${i}`,
                fieldtype: "Link",
                label: __("Bottle Warehouse"),
                options: "Warehouse",
                default: bl.bottle_source_warehouse || "",
                depends_on: bl.bottle_item ? `eval:1` : undefined,
            },
            {
                fieldname: `sealing_item_${i}`,
                fieldtype: "Link",
                label: __("Sealing Item"),
                options: "Item",
                default: bl.sealing_item || "",
            },
            {
                fieldname: `sealing_source_warehouse_${i}`,
                fieldtype: "Link",
                label: __("Sealing Warehouse"),
                options: "Warehouse",
                default: bl.sealing_source_warehouse || "",
            }
        );
    });

    const d = new frappe.ui.Dialog({
        title: __("Complete Rebottling"),
        fields: fields,
        primary_action_label: __("Confirm"),
        primary_action(values) {
            const source_actuals = source_lines.map((sl, i) => ({
                name: sl.name,
                actual_quantity: flt(values[`actual_quantity_${i}`] || 0),
            }));
            const line_actuals = rebottling_lines.map((bl, i) => ({
                name: bl.name,
                actual_bottles: cint(values[`actual_bottles_${i}`] || 0),
                bottled_wine_item: values[`bottled_wine_item_${i}`] || "",
                qc_bottles: cint(values[`qc_bottles_${i}`] || 0),
                sample_bottles: cint(values[`sample_bottles_${i}`] || 1),
                bottle_source_warehouse: values[`bottle_source_warehouse_${i}`] || "",
                sealing_item: values[`sealing_item_${i}`] || "",
                sealing_source_warehouse: values[`sealing_source_warehouse_${i}`] || "",
            }));

            // Validate required bottled_wine_item
            for (let i = 0; i < line_actuals.length; i++) {
                if (!line_actuals[i].bottled_wine_item) {
                    frappe.msgprint(__("Bottled Wine Item is required for all rebottling lines."));
                    return;
                }
            }

            frappe.call({
                method: "winery.winery.doctype.wine_batch_rebottling.wine_batch_rebottling.submit_rebottling_actuals",
                args: {
                    rebottling_doc: frm.doc.name,
                    rebottling_date: values.rebottling_date,
                    source_actuals: JSON.stringify(source_actuals),
                    line_actuals: JSON.stringify(line_actuals),
                },
                callback(r) {
                    d.hide();
                    frm.reload_doc();
                },
            });
        },
    });

    d.show();
}

// ---------------------------------------------------------------------------
// Complete Repackaging modal
// ---------------------------------------------------------------------------
function _show_repackaging_modal(frm) {
    const repackaging_lines = frm.doc.repackaging_lines || [];

    if (!repackaging_lines.length) {
        frappe.msgprint(__("Please add repackaging lines before completing."));
        return;
    }

    const fields = [];
    repackaging_lines.forEach((pl, i) => {
        const heading = `${pl.pack_size} — ${pl.bottle_size_ml}ml — Planned: ${pl.cartons || 0} cartons`;
        fields.push(
            { fieldname: `sb_pl_${i}`, fieldtype: "Section Break", label: heading },
            {
                fieldname: `actual_cartons_${i}`,
                fieldtype: "Int",
                label: __("Actual Cartons"),
                reqd: 1,
                default: pl.actual_cartons || pl.cartons || 0,
            },
            {
                fieldname: `output_item_${i}`,
                fieldtype: "Link",
                label: __("Output Item"),
                options: "Item",
                reqd: 1,
                default: pl.output_item || "",
            },
            { fieldname: `cb_pl_${i}`, fieldtype: "Column Break" },
            {
                fieldname: `output_warehouse_${i}`,
                fieldtype: "Link",
                label: __("Output Warehouse"),
                options: "Warehouse",
                reqd: 1,
                default: pl.output_warehouse || "",
            }
        );
    });

    const d = new frappe.ui.Dialog({
        title: __("Complete Repackaging"),
        fields: fields,
        primary_action_label: __("Confirm"),
        primary_action(values) {
            const lines = repackaging_lines.map((pl, i) => ({
                name: pl.name,
                actual_cartons: cint(values[`actual_cartons_${i}`] || 0),
                output_item: values[`output_item_${i}`] || "",
                output_warehouse: values[`output_warehouse_${i}`] || "",
            }));

            frappe.call({
                method: "winery.winery.doctype.wine_batch_rebottling.wine_batch_rebottling.submit_repackaging_actuals",
                args: {
                    rebottling_doc: frm.doc.name,
                    lines: JSON.stringify(lines),
                },
                callback(r) {
                    d.hide();
                    frm.reload_doc();
                },
            });
        },
    });

    d.show();
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function cint(v) { return parseInt(v) || 0; }
function flt(v)  { return parseFloat(v) || 0.0; }
