# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt, cint, today
from frappe.model.naming import make_autoname

from winery.winery.doctype.wine_batch.wine_batch import _get_bin_rate


class WineBatchRebottling(Document):
    def before_insert(self):
        if not self.is_auto_created:
            frappe.throw(
                "Please create a Rebottling from the Wine Batch form using the "
                "'New Rebottling' button.",
                title="Use Wine Batch Form"
            )

    def validate(self):
        self._validate_source_lines()
        self._recalc_source_volume()
        self._recalc_rebottling_planned()
        self._recalc_repackaging_planned()

    def _validate_source_lines(self):
        for row in self.source_lines:
            if cint(row.bottles_per_unit) < 1:
                row.bottles_per_unit = 1
            if flt(row.planned_quantity) > cint(row.available_quantity):
                frappe.throw(
                    f"Planned quantity ({row.planned_quantity}) for "
                    f"<b>{row.source_item}</b> exceeds available quantity "
                    f"({row.available_quantity})."
                )

    def _recalc_source_volume(self):
        total_ml = sum(
            flt(r.planned_quantity) * cint(r.bottles_per_unit) * cint(r.bottle_size_ml)
            for r in self.source_lines
        )
        self.planned_wine_volume_litres = round(total_ml / 1000, 4)

    def _recalc_rebottling_planned(self):
        for row in self.rebottling_lines:
            row.planned_volume_litres = round(
                cint(row.planned_bottles) * cint(row.bottle_size_ml) / 1000, 4
            )

    def _recalc_repackaging_planned(self):
        for row in self.repackaging_lines:
            row.total_bottles = cint(row.cartons) * cint(row.bottles_per_carton)


# ---------------------------------------------------------------------------
# Whitelisted API functions
# ---------------------------------------------------------------------------

@frappe.whitelist()
def submit_rebottling_actuals(rebottling_doc, rebottling_date, line_actuals):
    """
    Save rebottling line actuals from the Complete Rebottling modal.
    Source quantities are taken directly from source_lines.planned_quantity.
    Sets status to "Rebottling Completed".
    """
    import json as _json
    if isinstance(line_actuals, str):
        line_actuals = _json.loads(line_actuals)

    rb = frappe.get_doc("Wine Batch Rebottling", rebottling_doc)

    if rb.status not in ("Pending", "Rebottling Completed"):
        frappe.throw("Cannot update rebottling actuals at this stage.")

    # If repackaging was already done, roll it back
    if rb.status == "Rebottling Completed":
        _clear_repackaging_actuals(rb)
        frappe.db.set_value("Wine Batch Rebottling", rebottling_doc, {
            "packaging_process_loss": 0,
            "packaging_yield_pct": 0,
        })

    # Save rebottling line actuals
    for ld in line_actuals:
        bl_name = ld.get("name")
        row = next((r for r in rb.rebottling_lines if r.name == bl_name), None)
        if not row:
            continue
        actual = cint(ld.get("actual_bottles", 0))
        qc = cint(ld.get("qc_bottles", 0))
        sample = max(cint(ld.get("sample_bottles", 1)), 1)
        net = max(actual - qc - sample, 0)
        vol = round(actual * cint(row.bottle_size_ml) / 1000, 4)
        planned_vol = round(cint(row.planned_bottles) * cint(row.bottle_size_ml) / 1000, 4)
        frappe.db.set_value("Wine Batch Rebottling Line", bl_name, {
            "actual_bottles": actual,
            "qc_bottles": qc,
            "sample_bottles": sample,
            "net_bottles": net,
            "volume_litres": vol,
            "remaining_volume_litres": round(max(planned_vol - vol, 0), 4),
            "bottled_wine_item": ld.get("bottled_wine_item") or None,
            "bottle_source_warehouse": ld.get("bottle_source_warehouse") or None,
            "sealing_item": ld.get("sealing_item") or None,
            "sealing_source_warehouse": ld.get("sealing_source_warehouse") or None,
        })

    rb.reload()

    # Compute process loss: source wine volume vs actual output volume
    total_source_vol = sum(
        flt(r.planned_quantity) * cint(r.bottles_per_unit) * cint(r.bottle_size_ml) / 1000
        for r in rb.source_lines
    )
    total_source_bottles = sum(
        int(flt(r.planned_quantity) * cint(r.bottles_per_unit))
        for r in rb.source_lines
    )
    total_output_bottles = sum(cint(r.actual_bottles) for r in rb.rebottling_lines)
    total_output_vol = sum(flt(r.volume_litres) for r in rb.rebottling_lines)

    process_loss_bottles = max(total_source_bottles - total_output_bottles, 0)
    process_loss_litres = round(max(total_source_vol - total_output_vol, 0), 4)
    yield_pct = round((total_output_vol / total_source_vol) * 100, 2) if total_source_vol else 0.0

    frappe.db.set_value("Wine Batch Rebottling", rebottling_doc, {
        "rebottling_date": rebottling_date,
        "status": "Rebottling Completed",
        "process_loss_bottles": process_loss_bottles,
        "process_loss_litres": process_loss_litres,
        "yield_pct": yield_pct,
    })

    return {
        "process_loss_bottles": process_loss_bottles,
        "process_loss_litres": process_loss_litres,
        "yield_pct": yield_pct,
    }


@frappe.whitelist()
def submit_repackaging_actuals(rebottling_doc, lines):
    """
    Save repackaging actuals from the Complete Repackaging modal.
    Sets status to "Repackaging Completed".
    """
    import json as _json
    if isinstance(lines, str):
        lines = _json.loads(lines)

    rb = frappe.get_doc("Wine Batch Rebottling", rebottling_doc)

    if rb.status not in ("Rebottling Completed", "Repackaging Completed"):
        frappe.throw("Please complete rebottling before entering repackaging actuals.")

    for ld in lines:
        pl_name = ld.get("name")
        row = next((r for r in rb.repackaging_lines if r.name == pl_name), None)
        if not row:
            continue
        actual_cartons = cint(ld.get("actual_cartons", 0))
        output_item = ld.get("output_item")
        output_warehouse = ld.get("output_warehouse")
        if not output_item or not output_warehouse:
            frappe.throw(
                "Output Item and Output Warehouse are required for all repackaging lines."
            )
        frappe.db.set_value("Wine Batch Repackaging Line", pl_name, {
            "actual_cartons": actual_cartons,
            "actual_total_bottles": actual_cartons * cint(row.bottles_per_carton),
            "output_item": output_item,
            "output_warehouse": output_warehouse,
        })

    rb.reload()

    # Compute remaining bottles per size
    net_by_size = {}
    for row in rb.rebottling_lines:
        sz = cint(row.bottle_size_ml)
        net_by_size[sz] = net_by_size.get(sz, 0) + cint(row.net_bottles)

    packaged_by_size = {}
    for row in rb.repackaging_lines:
        sz = cint(row.bottle_size_ml)
        packaged_by_size[sz] = packaged_by_size.get(sz, 0) + cint(row.actual_total_bottles)

    for row in rb.repackaging_lines:
        sz = cint(row.bottle_size_ml)
        frappe.db.set_value("Wine Batch Repackaging Line", row.name, "remaining_bottles",
            max(net_by_size.get(sz, 0) - packaged_by_size.get(sz, 0), 0))

    total_net = sum(cint(r.net_bottles) for r in rb.rebottling_lines)
    total_packed = sum(cint(r.actual_total_bottles) for r in rb.repackaging_lines)
    pkg_loss = max(total_net - total_packed, 0)
    pkg_yield = round((total_packed / total_net) * 100, 2) if total_net else 0.0

    frappe.db.set_value("Wine Batch Rebottling", rebottling_doc, {
        "status": "Repackaging Completed",
        "packaging_process_loss": pkg_loss,
        "packaging_yield_pct": pkg_yield,
    })

    return {"packaging_process_loss": pkg_loss, "packaging_yield_pct": pkg_yield}


@frappe.whitelist()
def reset_rebottling_actuals(rebottling_doc):
    """Clear all actuals and return status to Pending."""
    rb = frappe.get_doc("Wine Batch Rebottling", rebottling_doc)
    if rb.status not in ("Rebottling Completed", "Repackaging Completed"):
        frappe.throw("Nothing to reset.")

    for row in rb.rebottling_lines:
        frappe.db.set_value("Wine Batch Rebottling Line", row.name, {
            "actual_bottles": 0, "qc_bottles": 0, "sample_bottles": 1,
            "net_bottles": 0, "volume_litres": 0, "remaining_volume_litres": 0,
            "bottled_wine_item": None,
            "bottle_source_warehouse": None,
            "sealing_item": None, "sealing_source_warehouse": None,
        })

    _clear_repackaging_actuals(rb)

    frappe.db.set_value("Wine Batch Rebottling", rebottling_doc, {
        "status": "Pending",
        "process_loss_bottles": 0,
        "process_loss_litres": 0,
        "yield_pct": 0,
        "packaging_process_loss": 0,
        "packaging_yield_pct": 0,
    })
    frappe.msgprint("Rebottling actuals cleared. Document reset to Planning.", alert=True)


@frappe.whitelist()
def close_rebottling(rebottling_doc):
    """
    Create one Manufacture SE per repackaging line.

    Inputs per SE:
    - Proportional source cartons consumed from their original warehouse/batch
    - New empty bottles + sealings
    - New materials (reusable: returned at same rate; unreusable: expensed into output)

    Output per SE:
    - One new carton item with basic_rate = wine_cost_per_ml * new_size + new_materials

    The difference_account (Rebottling Expenses Account) absorbs the gap between
    the old packaging value consumed and the new packaging value produced.
    """
    rb = frappe.get_doc("Wine Batch Rebottling", rebottling_doc)

    if rb.status == "Completed":
        frappe.throw("This rebottling has already been closed.")
    if rb.status != "Repackaging Completed":
        frappe.throw("Please complete repackaging before closing.")

    settings = frappe.get_single("Winery Settings")
    if not settings.sample_warehouse:
        frappe.throw("Please configure a Sample Warehouse in Winery Settings.")
    sample_warehouse = settings.sample_warehouse
    unpackaged_warehouse = settings.unpackaged_bottle_warehouse
    rebottling_expense_account = settings.rebottling_expense_account or None

    # ---- Source cost & volume totals ----------------------------------------
    total_source_volume_ml = sum(
        flt(sl.planned_quantity) * cint(sl.bottles_per_unit) * cint(sl.bottle_size_ml)
        for sl in rb.source_lines
    )
    total_source_cost = sum(
        flt(sl.planned_quantity) * _get_bin_rate(sl.source_item, sl.source_warehouse)
        for sl in rb.source_lines
    )
    wine_cost_per_ml = total_source_cost / total_source_volume_ml if total_source_volume_ml else 0.0

    # ---- New output totals ---------------------------------------------------
    total_new_bottles = sum(cint(r.actual_bottles) for r in rb.rebottling_lines)
    total_new_volume_ml = sum(
        cint(r.actual_bottles) * cint(r.bottle_size_ml)
        for r in rb.rebottling_lines
    )

    # ---- Size → rebottling line lookup ---------------------------------------
    size_to_bl_rows = {}
    for row in rb.rebottling_lines:
        sz = cint(row.bottle_size_ml)
        size_to_bl_rows.setdefault(sz, []).append(row)

    total_bottles_by_size = {
        sz: sum(cint(r.actual_bottles) for r in rows)
        for sz, rows in size_to_bl_rows.items()
    }

    # ---- Create ERPNext Batch per unique output_item -------------------------
    seen_output_items = {}
    for row in rb.repackaging_lines:
        if row.output_item and row.output_item not in seen_output_items:
            batch_name = make_autoname("BTCH-.YYYY.-.#####")
            batch = frappe.new_doc("Batch")
            batch.batch_id = batch_name
            batch.item = row.output_item
            batch.insert(ignore_permissions=True)
            seen_output_items[row.output_item] = batch_name
            frappe.db.set_value("Wine Batch Repackaging Line", row.name, "output_batch_no", batch_name)

    rb.reload()

    # ---- Packaged bottles per size (for remainder calc) ----------------------
    packaged_by_size = {}
    for row in rb.repackaging_lines:
        sz = cint(row.bottle_size_ml)
        packaged_by_size[sz] = packaged_by_size.get(sz, 0) + cint(row.actual_total_bottles)

    # ---- Active repackaging lines --------------------------------------------
    active_lines = [r for r in rb.repackaging_lines if r.output_item and cint(r.actual_cartons)]

    mat_consumed = {}   # keyed by prefixed name to track across loop
    size_first_se = set()
    se_names = []

    for pl_idx, row in enumerate(active_lines):
        is_last = (pl_idx == len(active_lines) - 1)
        sz = cint(row.bottle_size_ml)
        pl_volume_ml = cint(row.actual_total_bottles) * sz
        vol_fraction = pl_volume_ml / total_new_volume_ml if total_new_volume_ml else 0.0
        btl_fraction = cint(row.actual_total_bottles) / total_new_bottles if total_new_bottles else 0.0

        se = frappe.new_doc("Stock Entry")
        se.stock_entry_type = "Manufacture"
        se.posting_date = rb.rebottling_date or today()
        if rebottling_expense_account:
            se.difference_account = rebottling_expense_account

        # ---- Source cartons consumed (proportional; last SE takes remainder) ----
        for sl in rb.source_lines:
            key = f"__src_{sl.name}"
            prev = mat_consumed.get(key, 0.0)
            qty = (round(flt(sl.planned_quantity) - prev, 6) if is_last
                   else round(flt(sl.planned_quantity) * vol_fraction, 6))
            mat_consumed[key] = prev + qty
            if qty > 0:
                se.append("items", {
                    "item_code": sl.source_item,
                    "qty": qty,
                    "s_warehouse": sl.source_warehouse,
                    "batch_no": sl.source_batch_no or None,
                    "use_serial_batch_fields": 1 if sl.source_batch_no else 0,
                    "is_finished_item": 0,
                })

        # ---- New empty bottles + sealings ------------------------------------
        size_total = total_bottles_by_size.get(sz, 0)
        for bl in size_to_bl_rows.get(sz, []):
            if not size_total:
                continue
            share = cint(bl.actual_bottles) / size_total
            btl_qty = round(cint(row.actual_total_bottles) * share)
            if btl_qty and bl.bottle_item and bl.bottle_source_warehouse:
                se.append("items", {
                    "item_code": bl.bottle_item,
                    "qty": btl_qty,
                    "s_warehouse": bl.bottle_source_warehouse,
                    "is_finished_item": 0,
                })
            if btl_qty and bl.sealing_item and bl.sealing_source_warehouse:
                se.append("items", {
                    "item_code": bl.sealing_item,
                    "qty": btl_qty,
                    "s_warehouse": bl.sealing_source_warehouse,
                    "is_finished_item": 0,
                })

        # ---- Materials (reusable: net-zero; unreusable: consumed into cost) ---
        unreusable_cost = 0.0
        for mat in rb.material_lines:
            if not mat.item or not flt(mat.quantity):
                continue
            key = f"__mat_{mat.name}"
            prev = mat_consumed.get(key, 0.0)
            qty = (round(flt(mat.quantity) - prev, 6) if is_last
                   else round(flt(mat.quantity) * btl_fraction, 6))
            mat_consumed[key] = prev + qty
            if qty <= 0:
                continue
            rate = _get_bin_rate(mat.item, mat.source_warehouse)
            se.append("items", {
                "item_code": mat.item,
                "qty": qty,
                "uom": mat.uom or None,
                "s_warehouse": mat.source_warehouse,
                "is_finished_item": 0,
            })
            if mat.is_reusable:
                se.append("items", {
                    "item_code": mat.item,
                    "qty": qty,
                    "uom": mat.uom or None,
                    "t_warehouse": mat.return_warehouse,
                    "is_finished_item": 0,
                    "basic_rate": rate,
                })
            else:
                unreusable_cost += qty * rate

        # ---- New carton basic_rate -------------------------------------------
        bl_list = size_to_bl_rows.get(sz, [])
        pl_btls = cint(row.actual_total_bottles)
        wine_cost_per_new_bottle = wine_cost_per_ml * sz
        new_bottle_rate = 0.0
        new_sealing_rate = 0.0
        if bl_list:
            bl = bl_list[0]
            new_bottle_rate = _get_bin_rate(bl.bottle_item, bl.bottle_source_warehouse) if bl.bottle_item else 0.0
            new_sealing_rate = _get_bin_rate(bl.sealing_item, bl.sealing_source_warehouse) if bl.sealing_item else 0.0
        unreusable_per_bottle = unreusable_cost / pl_btls if pl_btls else 0.0
        cost_per_new_bottle = wine_cost_per_new_bottle + new_bottle_rate + new_sealing_rate + unreusable_per_bottle
        basic_rate = round(cost_per_new_bottle * cint(row.bottles_per_carton), 4)

        # ---- Finished item (ONE per SE) --------------------------------------
        se.append("items", {
            "item_code": row.output_item,
            "qty": cint(row.actual_cartons),
            "t_warehouse": row.output_warehouse,
            "batch_no": row.output_batch_no or None,
            "use_serial_batch_fields": 1 if row.output_batch_no else 0,
            "is_finished_item": 1,
            "basic_rate": basic_rate,
        })

        # ---- Samples + remainder (first SE per bottle size only) -------------
        if sz not in size_first_se:
            size_first_se.add(sz)
            for bl in size_to_bl_rows.get(sz, []):
                sample_qty = max(cint(bl.sample_bottles), 1)
                bl_cost = cost_per_new_bottle
                if bl.bottled_wine_item:
                    se.append("items", {
                        "item_code": bl.bottled_wine_item,
                        "qty": sample_qty,
                        "t_warehouse": sample_warehouse,
                        "is_finished_item": 0,
                        "basic_rate": round(bl_cost, 4),
                    })
                elif bl.bottle_item:
                    se.append("items", {
                        "item_code": bl.bottle_item,
                        "qty": sample_qty,
                        "t_warehouse": sample_warehouse,
                        "is_finished_item": 0,
                    })
                if unpackaged_warehouse and bl.bottled_wine_item:
                    remainder = cint(bl.net_bottles) - packaged_by_size.get(sz, 0)
                    if remainder > 0:
                        se.append("items", {
                            "item_code": bl.bottled_wine_item,
                            "qty": remainder,
                            "t_warehouse": unpackaged_warehouse,
                            "is_finished_item": 0,
                            "basic_rate": round(bl_cost, 4),
                        })

        se.insert(ignore_permissions=True)
        se.submit()
        se_names.append(se.name)

    frappe.db.set_value("Wine Batch Rebottling", rebottling_doc, {
        "status": "Completed",
        "rebottling_stock_entries": "\n".join(se_names),
    })

    return {"stock_entries": se_names}


@frappe.whitelist()
def cancel_rebottling(rebottling_doc):
    """Cancel all SEs created by close_rebottling and revert to Pending."""
    rb = frappe.get_doc("Wine Batch Rebottling", rebottling_doc)
    if rb.status != "Completed":
        frappe.throw("Only a completed rebottling can be cancelled.")

    for se_name in (rb.rebottling_stock_entries or "").splitlines():
        se_name = se_name.strip()
        if not se_name:
            continue
        try:
            se = frappe.get_doc("Stock Entry", se_name)
            if se.docstatus == 1:
                se.cancel()
        except frappe.DoesNotExistError:
            pass

    for row in rb.rebottling_lines:
        frappe.db.set_value("Wine Batch Rebottling Line", row.name, {
            "actual_bottles": 0, "qc_bottles": 0, "sample_bottles": 1,
            "net_bottles": 0, "volume_litres": 0, "remaining_volume_litres": 0,
            "bottled_wine_item": None,
            "bottle_source_warehouse": None,
            "sealing_item": None, "sealing_source_warehouse": None,
        })

    _clear_repackaging_actuals(rb)

    frappe.db.set_value("Wine Batch Rebottling", rebottling_doc, {
        "status": "Pending",
        "rebottling_stock_entries": None,
        "process_loss_bottles": 0,
        "process_loss_litres": 0,
        "yield_pct": 0,
        "packaging_process_loss": 0,
        "packaging_yield_pct": 0,
    })


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _clear_repackaging_actuals(rb):
    for row in rb.repackaging_lines:
        frappe.db.set_value("Wine Batch Repackaging Line", row.name, {
            "actual_cartons": 0,
            "actual_total_bottles": 0,
            "remaining_bottles": 0,
            "output_batch_no": None,
        })
