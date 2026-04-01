# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt, cint, today
from frappe.model.naming import make_autoname


def _ordered_ops(recipe):
	"""Return ordered list of distinct operation_type values from Recipe Stage (canonical order)."""
	seen = []
	for s in sorted(recipe.stages, key=lambda x: x.idx):
		if s.operation_type and s.operation_type not in seen:
			seen.append(s.operation_type)
	return seen


class WineBatch(Document):
	def before_insert(self):
		if not self.recipe:
			return
		recipe = frappe.get_doc("Recipe", self.recipe)
		recipe_yield = recipe.base_batch_size or 1
		scale = (self.target_batch_size or recipe_yield) / recipe_yield

		# JS already populates required_materials when the user sets recipe/target_batch_size.
		# Only populate here if the table is empty (e.g. programmatic creation without JS).
		if not self.required_materials:
			for rm in recipe.raw_materials:
				self.append("required_materials", {
					"item": rm.item,
					"quantity": round(rm.quantity * scale, 3),
					"uom": rm.uom,
					"stage_name": rm.stage_name,
					"notes": rm.notes,
					"status": "Pending",
				})

		if not self.lab_analyses:
			for la in recipe.lab_analyses:
				self.append("lab_analyses", {
					"operation_type": la.operation_type,
					"hours_after_start": la.hours_after_start,
					"test_type": la.test_type,
					"is_mandatory": la.is_mandatory,
					"target_value": la.target_value,
					"sample_size_ml": la.sample_size_ml,
					"is_recurring": la.is_recurring,
					"recurrence_interval_hrs": la.recurrence_interval_hrs,
					"notes": la.notes,
				})

	def on_submit(self):
		if not self.start_date:
			self.db_set("start_date", today())
		self.db_set("status", "Active")

	def on_cancel(self):
		self.db_set("status", "Cancelled")

	@frappe.whitelist()
	def start_next_stage(self):
		recipe = frappe.get_doc("Recipe", self.recipe)
		ordered_ops = _ordered_ops(recipe)

		if not ordered_ops:
			frappe.throw("No operations defined in the Recipe Lab Analyses.")

		next_idx = (self.current_stage_number or 0) + 1
		if next_idx > len(ordered_ops):
			frappe.throw("All stages in the recipe have been completed.")

		op_type_name = ordered_ops[next_idx - 1]

		# ---- Create Cellar Operation for this stage --------------------------
		co = frappe.new_doc("Cellar Operation")
		co.operation_type = op_type_name
		co.operation_name = f"{self.name} — Stage {next_idx}: {op_type_name}"
		co.wine_batch = self.name
		co.recipe_stage_idx = next_idx
		co.status = "Planned"

		# Pre-fill tasks from Cellar Operation Type
		op_type = frappe.get_doc("Cellar Operation Type", op_type_name)
		for t in op_type.tasks:
			co.append("tasks", {
				"task_name": t.task_name,
				"task_type": t.task_type,
				"scheduled_hours_from_start": t.scheduled_hours_from_start,
				"expected_sample_size": t.expected_sample_size,
				"expected_sample_uom": t.expected_sample_uom,
				"description": t.description,
				"completed": 0,
			})

		# Get the expected duration for this stage (drives recurring task count)
		stage_duration = next(
			(s.expected_duration for s in recipe.stages if s.operation_type == op_type_name), 0
		) or 0

		# Add Lab Test tasks defined in the recipe for this operation type
		for la in recipe.lab_analyses:
			if la.operation_type != op_type_name:
				continue

			first_at = la.hours_after_start or 0

			if la.is_recurring and la.recurrence_interval_hrs:
				interval = la.recurrence_interval_hrs
				# First occurrence at first_at, then every interval hours up to stage_duration
				num_occurrences = (
					int((stage_duration - first_at) / interval) + 1
					if stage_duration > first_at and interval > 0
					else 1
				)
				for i in range(num_occurrences):
					scheduled_at = first_at + (i * interval)
					co.append("tasks", {
						"task_name": f"{la.test_type} @ {scheduled_at}h",
						"task_type": "Lab Test",
						"test_type": la.test_type,
						"scheduled_hours_from_start": scheduled_at,
						"expected_sample_size": la.sample_size_ml,
						"completed": 0,
					})
			else:
				co.append("tasks", {
					"task_name": f"{la.test_type} @ {first_at}h",
					"task_type": "Lab Test",
					"test_type": la.test_type,
					"scheduled_hours_from_start": first_at,
					"expected_sample_size": la.sample_size_ml,
					"completed": 0,
				})

		# Pre-fill materials from recipe raw materials for this operation type
		recipe_yield = recipe.base_batch_size or 1
		scale = (self.target_batch_size or recipe_yield) / recipe_yield

		for rm in recipe.raw_materials:
			if rm.stage_name == op_type_name:
				co.append("details", {
					"item": rm.item,
					"quantity": round(rm.quantity * scale, 3),
					"uom": rm.uom,
					"description": rm.notes or "",
				})

		co.insert(ignore_permissions=True)
		try:
			co.submit()
		except Exception:
			frappe.delete_doc("Cellar Operation", co.name, ignore_permissions=True, force=True)
			raise

		# Notify about lab test sample requirements
		lab_tasks = [t for t in co.tasks if t.task_type == "Lab Test"]
		if lab_tasks:
			sample_msg = "<b>Lab samples required for this operation:</b><ul>"
			for lt in lab_tasks:
				sample_info = lt.task_name
				if lt.expected_sample_size:
					sample_info += f" — {lt.expected_sample_size} ml"
				sample_msg += f"<li>{sample_info}</li>"
			sample_msg += "</ul>"
			frappe.msgprint(sample_msg, title="Lab Test Requirements", indicator="blue")

		# Update Wine Batch progress
		self.db_set("current_stage_number", next_idx)
		self.db_set("current_stage_name", op_type_name)

		return co.name

	def update_progress(self, co):
		"""Called by Cellar Operation when an operation is completed."""
		self.db_set("current_stage_number", co.recipe_stage_idx)
		self.db_set("current_stage_name", co.operation_type)

		pass


# --------------------------------------------------------------------------- #
#  Module-level whitelisted helpers                                            #
# --------------------------------------------------------------------------- #

@frappe.whitelist()
def start_next_stage(name):
	"""Module-level wrapper so Frappe v15 can resolve this as a module function."""
	doc = frappe.get_doc("Wine Batch", name)
	return doc.start_next_stage()


@frappe.whitelist()
def get_abv_tax_band(abv_percentage):
	"""Return the matching ABV Tax Band and excise duty rate for a given ABV %."""
	abv = flt(abv_percentage)
	band = frappe.db.sql(
		"""
		SELECT name, excise_duty_per_litre
		FROM `tabABV Tax Band`
		WHERE min_abv <= %s AND max_abv > %s
		ORDER BY min_abv DESC LIMIT 1
		""",
		(abv, abv),
		as_dict=True,
	)
	return band[0] if band else {}



@frappe.whitelist()
def check_materials_availability(items):
	"""Return availability info for a list of {item, quantity, uom} rows.

	Uses Bin.actual_qty for all-warehouse total stock. Handles template items
	(aggregates variants) and applies a hardcoded 1 Kg = 100 Nos conversion for
	ripe banana fingers (the only cross-UOM pairing currently in use).

	Returns a dict keyed by item_code:
	  {"available": bool, "available_qty": float, "required_qty": float, "stock_uom": str}
	"""
	import json as _json

	if isinstance(items, str):
		items = _json.loads(items)

	KG_TO_NOS = 100  # 1 Kg = 100 Nos (ripe banana fingers)

	ripe_tpl = frappe.db.get_single_value("Winery Settings", "ripe_banana_finger_template")

	result = {}

	for row in items:
		item_code = row.get("item")
		required_qty = flt(row.get("quantity", 0))
		uom = row.get("uom")
		if not item_code:
			continue

		stock_uom = frappe.db.get_value("Item", item_code, "stock_uom") or uom

		# Resolve which item codes to sum Bin stock for
		items_to_check = []
		has_variants = frappe.db.get_value("Item", item_code, "has_variants")
		if has_variants:
			items_to_check = frappe.db.get_all(
				"Item", filters={"variant_of": item_code, "disabled": 0}, pluck="name"
			)
			if ripe_tpl and item_code == ripe_tpl:
				stock_uom = frappe.db.get_value("Item", ripe_tpl, "stock_uom") or stock_uom
		else:
			variant_of = frappe.db.get_value("Item", item_code, "variant_of")
			if ripe_tpl and item_code != ripe_tpl and variant_of != ripe_tpl:
				# Legacy item — check template variants if they exist
				variants = frappe.db.get_all(
					"Item", filters={"variant_of": ripe_tpl, "disabled": 0}, pluck="name"
				)
				if variants:
					items_to_check = variants
					stock_uom = frappe.db.get_value("Item", ripe_tpl, "stock_uom") or stock_uom
				else:
					items_to_check = [item_code]
			else:
				items_to_check = [item_code]

		# Sum actual_qty across all bins
		total_available = 0.0
		if items_to_check:
			rows = frappe.db.sql(
				"SELECT SUM(actual_qty) FROM `tabBin` WHERE item_code IN %s",
				(items_to_check,),
			)
			total_available = flt(rows[0][0]) if rows and rows[0][0] else 0.0

		# Convert required_qty to stock_uom
		required_in_stock_uom = required_qty
		if uom and stock_uom and uom != stock_uom:
			if uom == "Kg" and stock_uom == "Nos":
				required_in_stock_uom = required_qty * KG_TO_NOS
			elif uom == "Nos" and stock_uom == "Kg":
				required_in_stock_uom = required_qty / KG_TO_NOS
			else:
				cf = frappe.db.get_value(
					"UOM Conversion Factor", {"from_uom": uom, "to_uom": stock_uom}, "value"
				)
				if cf:
					required_in_stock_uom = required_qty * flt(cf)

		result[item_code] = {
			"available": total_available >= required_in_stock_uom,
			"available_qty": total_available,
			"required_qty": required_in_stock_uom,
			"stock_uom": stock_uom,
		}

	return result


def _get_bin_rate(item_code, warehouse):
	"""Return the current valuation rate for an item in a warehouse (0 if not found)."""
	if not item_code or not warehouse:
		return 0.0
	rate = frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "valuation_rate")
	return flt(rate)


@frappe.whitelist()
def submit_bottling_actuals(wine_batch, bottling_date, abv_percentage, lines):
	"""Save bottling actuals from the Complete Bottling modal."""
	import json as _json
	if isinstance(lines, str):
		lines = _json.loads(lines)

	wb = frappe.get_doc("Wine Batch", wine_batch)

	if wb.bottling_status not in ("Pending", "Bottling Completed"):
		frappe.throw("Cannot update bottling actuals at this stage.")

	abv = flt(abv_percentage)
	if not abv:
		frappe.throw("ABV (%) is required.")

	# Match ABV tax band
	band = frappe.db.sql(
		"""
		SELECT name, excise_duty_per_litre FROM `tabABV Tax Band`
		WHERE min_abv <= %s AND max_abv > %s ORDER BY min_abv DESC LIMIT 1
		""",
		(abv, abv), as_dict=True,
	)
	abv_tax_band = band[0].name if band else None
	excise_rate = flt(band[0].excise_duty_per_litre) if band else 0.0

	# Save per-line actuals
	for ld in lines:
		bl_name = ld.get("name")
		row = next((r for r in wb.bottling_lines if r.name == bl_name), None)
		if not row:
			continue
		actual = cint(ld.get("actual_bottles", 0))
		qc     = cint(ld.get("qc_bottles", 0))
		sample = max(cint(ld.get("sample_bottles", 1)), 1)
		net    = max(actual - qc - sample, 0)
		vol    = round(actual * cint(row.bottle_size_ml) / 1000, 4)
		planned_vol = round(cint(row.planned_bottles) * cint(row.bottle_size_ml) / 1000, 4)
		frappe.db.set_value("Wine Batch Bottling Line", bl_name, {
			"actual_bottles": actual,
			"qc_bottles": qc,
			"sample_bottles": sample,
			"net_bottles": net,
			"volume_litres": vol,
			"remaining_volume_litres": round(max(planned_vol - vol, 0), 4),
			"bottled_wine_item": ld.get("bottled_wine_item") or None,
			"bottle_source_warehouse": ld.get("bottle_source_warehouse"),
			"sealing_item": ld.get("sealing_item") or None,
			"sealing_source_warehouse": ld.get("sealing_source_warehouse") or None,
		})

	wb.reload()

	total_volume_bottled = round(sum(flt(r.volume_litres) for r in wb.bottling_lines), 4)
	input_vol = flt(wb.target_batch_size)
	process_loss = round(max(input_vol - total_volume_bottled, 0), 4)
	yield_pct = round((total_volume_bottled / input_vol) * 100, 2) if input_vol else 0.0

	# If packaging was already done, roll it back — bottling data changed
	if wb.bottling_status == "Packaging Completed":
		for row in wb.packaging_lines:
			frappe.db.set_value("Wine Batch Packaging Line", row.name, {
				"actual_cartons": 0,
				"actual_total_bottles": 0,
				"remaining_bottles": 0,
				"output_item": None,
				"output_warehouse": None,
			})
		frappe.db.set_value("Wine Batch", wine_batch, {
			"packaging_process_loss": 0,
			"packaging_yield_pct": 0,
		})

	frappe.db.set_value("Wine Batch", wine_batch, {
		"bottling_date": bottling_date,
		"abv_percentage": abv,
		"abv_tax_band": abv_tax_band,
		"excise_duty_per_litre": excise_rate,
		"excise_duty_amount": round(total_volume_bottled * excise_rate, 4),
		"total_volume_bottled": total_volume_bottled,
		"process_loss": process_loss,
		"yield_efficiency_pct": yield_pct,
		"bottling_status": "Bottling Completed",
	})

	return {
		"total_volume_bottled": total_volume_bottled,
		"process_loss": process_loss,
		"yield_efficiency_pct": yield_pct,
	}


@frappe.whitelist()
def submit_packaging_actuals(wine_batch, lines):
	"""Save packaging actuals (actual cartons, output item/warehouse) from the Complete Packaging modal."""
	import json as _json
	if isinstance(lines, str):
		lines = _json.loads(lines)

	wb = frappe.get_doc("Wine Batch", wine_batch)

	if wb.bottling_status not in ("Bottling Completed", "Packaging Completed"):
		frappe.throw("Please complete bottling before packaging.")

	for ld in lines:
		pl_name = ld.get("name")
		row = next((r for r in wb.packaging_lines if r.name == pl_name), None)
		if not row:
			continue
		actual_cartons = cint(ld.get("actual_cartons", 0))
		output_item = ld.get("output_item")
		output_warehouse = ld.get("output_warehouse")
		if not output_item or not output_warehouse:
			frappe.throw("Output Item and Output Warehouse are required for all packaging lines.")
		frappe.db.set_value("Wine Batch Packaging Line", pl_name, {
			"actual_cartons": actual_cartons,
			"actual_total_bottles": actual_cartons * cint(row.bottles_per_carton),
			"output_item": output_item,
			"output_warehouse": output_warehouse,
		})

	wb.reload()

	net_by_size = {}
	for row in wb.bottling_lines:
		sz = cint(row.bottle_size_ml)
		net_by_size[sz] = net_by_size.get(sz, 0) + cint(row.net_bottles)

	packaged_by_size = {}
	for row in wb.packaging_lines:
		sz = cint(row.bottle_size_ml)
		packaged_by_size[sz] = packaged_by_size.get(sz, 0) + cint(row.actual_total_bottles)

	for row in wb.packaging_lines:
		sz = cint(row.bottle_size_ml)
		frappe.db.set_value(
			"Wine Batch Packaging Line", row.name, "remaining_bottles",
			max(net_by_size.get(sz, 0) - packaged_by_size.get(sz, 0), 0),
		)

	total_net    = sum(cint(r.net_bottles) for r in wb.bottling_lines)
	total_packed = sum(cint(r.actual_total_bottles) for r in wb.packaging_lines)
	pkg_loss  = max(total_net - total_packed, 0)
	pkg_yield = round((total_packed / total_net) * 100, 2) if total_net else 0.0

	frappe.db.set_value("Wine Batch", wine_batch, {
		"packaging_process_loss": pkg_loss,
		"packaging_yield_pct": pkg_yield,
		"bottling_status": "Packaging Completed",
	})

	return {"packaging_process_loss": pkg_loss, "packaging_yield_pct": pkg_yield}


@frappe.whitelist()
def reset_bottling_actuals(wine_batch):
	"""Clear all bottling/packaging actuals and reset Wine Batch to Planning (Pending)."""
	wb = frappe.get_doc("Wine Batch", wine_batch)
	if wb.bottling_status not in ("Bottling Completed", "Packaging Completed"):
		frappe.throw("Nothing to reset.")
	for row in wb.bottling_lines:
		frappe.db.set_value("Wine Batch Bottling Line", row.name, {
			"actual_bottles": 0,
			"qc_bottles": 0,
			"sample_bottles": 1,
			"net_bottles": 0,
			"volume_litres": 0,
			"remaining_volume_litres": 0,
			"bottled_wine_item": None,
			"bottle_source_warehouse": None,
			"sealing_item": None,
			"sealing_source_warehouse": None,
		})
	for row in wb.packaging_lines:
		frappe.db.set_value("Wine Batch Packaging Line", row.name, {
			"actual_cartons": 0,
			"actual_total_bottles": 0,
			"remaining_bottles": 0,
			"output_item": None,
			"output_warehouse": None,
		})
	frappe.db.set_value("Wine Batch", wine_batch, {
		"bottling_status": "Pending",
		"bottling_date": None,
		"abv_percentage": 0,
		"abv_tax_band": None,
		"excise_duty_per_litre": 0,
		"total_volume_bottled": 0,
		"process_loss": 0,
		"yield_efficiency_pct": 0,
		"packaging_process_loss": 0,
		"packaging_yield_pct": 0,
		"excise_duty_amount": 0,
	})
	frappe.msgprint("Bottling actuals cleared. Wine Batch reset to Planning.", alert=True)


@frappe.whitelist()
def close_wine_batch(wine_batch):
	"""
	Create and submit the Manufacture Stock Entry to close the Wine Batch.
	Requires bottling and packaging actuals to have been submitted first.
	"""
	wb = frappe.get_doc("Wine Batch", wine_batch)

	# ---- Guard ---------------------------------------------------------------
	if wb.bottling_status == "Completed":
		frappe.throw("Wine batch has already been closed.")
	if wb.bottling_status != "Packaging Completed":
		frappe.throw("Please complete packaging before closing the wine batch.")

	# ---- Validate ------------------------------------------------------------
	if not wb.bottling_lines or not any(cint(r.actual_bottles) > 0 for r in wb.bottling_lines):
		frappe.throw("Please complete bottling before closing the wine batch.")
	if not wb.packaging_lines:
		frappe.throw("Please add at least one Packaging Line.")
	if not all(r.output_item and r.output_warehouse for r in wb.packaging_lines):
		frappe.throw("All Packaging Lines must have an Output Item and Output Warehouse.")
	if not any(cint(r.actual_cartons) > 0 for r in wb.packaging_lines):
		frappe.throw("Please enter Actual Cartons on at least one Packaging Line.")
	if not wb.abv_tax_band:
		frappe.throw(
			f"No ABV Tax Band matched for ABV {wb.abv_percentage}%. "
			"Please configure ABV Tax Bands in Setup."
		)

	settings = frappe.get_single("Winery Settings")
	if not settings.sample_warehouse:
		frappe.throw(
			"Please configure a Sample Warehouse in Winery Settings before closing the wine batch."
		)
	sample_warehouse = settings.sample_warehouse
	unpackaged_warehouse = settings.unpackaged_bottle_warehouse

	# ---- Use already-stored totals -------------------------------------------
	total_volume_bottled   = flt(wb.total_volume_bottled)
	excise_rate            = flt(wb.excise_duty_per_litre)
	excise_duty_amount     = flt(wb.excise_duty_amount)
	process_loss           = flt(wb.process_loss)
	yield_efficiency_pct   = flt(wb.yield_efficiency_pct)
	packaging_process_loss = cint(wb.packaging_process_loss)
	packaging_yield_pct    = flt(wb.packaging_yield_pct)

	# ---- Build packaged_by_size (for remainder lines) ------------------------
	packaged_by_size = {}
	for row in wb.packaging_lines:
		sz = cint(row.bottle_size_ml)
		packaged_by_size[sz] = packaged_by_size.get(sz, 0) + cint(row.actual_total_bottles)

	# ---- Valuation calculations ----------------------------------------------
	# Step 1: WIP wine cost per ml — fetch all COs and flatten into wip_item_list
	cellar_ops = frappe.get_all(
		"Cellar Operation",
		filters={"wine_batch": wb.name, "docstatus": 1},
		fields=["name", "transfer_entry", "stock_entry", "wip_warehouse"],
	)
	wip_item_list = []  # {item_code, wip_warehouse, uom, batch_no, total_qty, consumed}
	wip_total_cost = 0.0
	for co in cellar_ops:
		if not co.transfer_entry or co.stock_entry:
			continue
		transfer_items = frappe.get_all(
			"Stock Entry Detail",
			filters={"parent": co.transfer_entry},
			fields=["item_code", "qty", "t_warehouse", "uom", "batch_no"],
		)
		for item in transfer_items:
			if item.t_warehouse != co.wip_warehouse:
				continue
			wip_item_list.append({
				"item_code": item.item_code,
				"wip_warehouse": co.wip_warehouse,
				"uom": item.uom,
				"batch_no": item.batch_no,
				"total_qty": flt(item.qty),
				"consumed": 0.0,
			})
			wip_total_cost += flt(item.qty) * _get_bin_rate(item.item_code, co.wip_warehouse)

	total_volume_ml = sum(
		cint(r.actual_bottles) * cint(r.bottle_size_ml) for r in wb.bottling_lines
	)
	wine_cost_per_ml = wip_total_cost / total_volume_ml if total_volume_ml else 0.0

	# Step 2: Per-bottle material cost (bottle + sealing) indexed by bottling line name
	mat_cost_per_bottling_line = {}
	for row in wb.bottling_lines:
		bottle_rate = _get_bin_rate(row.bottle_item, row.bottle_source_warehouse)
		sealing_rate = (
			_get_bin_rate(row.sealing_item, row.sealing_source_warehouse)
			if row.sealing_item and row.sealing_source_warehouse
			else 0.0
		)
		mat_cost_per_bottling_line[row.name] = bottle_rate + sealing_rate

	# Step 3: Additional materials cost spread per bottle
	total_additional_cost = sum(
		flt(row.quantity) * _get_bin_rate(row.item, row.source_warehouse)
		for row in wb.material_lines
		if row.item and flt(row.quantity)
	)
	total_actual_bottles = sum(cint(r.actual_bottles) for r in wb.bottling_lines)
	additional_cost_per_bottle = (
		total_additional_cost / total_actual_bottles if total_actual_bottles else 0.0
	)

	# Step 4: Lab Analysis consumables already transferred to WIP — collect for SE inputs
	lab_analysis_names = frappe.get_all(
		"Lab Analysis",
		filters={"wine_batch": wb.name, "docstatus": 1},
		pluck="name",
	)
	lab_consumable_list = []  # {item_code, total_qty, uom, consumed}
	lab_consumable_cost = 0.0
	for la_name in lab_analysis_names:
		la_consumables = frappe.get_all(
			"Lab Analysis Consumable",
			filters={"parent": la_name},
			fields=["item", "quantity", "uom"],
		)
		for row in la_consumables:
			if not row.item or not flt(row.quantity):
				continue
			lab_consumable_list.append({
				"item_code": row.item,
				"total_qty": flt(row.quantity),
				"uom": row.uom,
				"consumed": 0.0,
			})
			lab_consumable_cost += flt(row.quantity) * _get_bin_rate(row.item, wb.wip_warehouse)
	lab_consumable_cost_per_bottle = (
		lab_consumable_cost / total_actual_bottles if total_actual_bottles else 0.0
	)

	# ---- Per-size bottling line lookup (handles multiple BLs per size) -------
	size_to_bl_rows = {}
	for row in wb.bottling_lines:
		sz = cint(row.bottle_size_ml)
		size_to_bl_rows.setdefault(sz, []).append(row)

	total_bottles_by_size = {
		sz: sum(cint(r.actual_bottles) for r in rows)
		for sz, rows in size_to_bl_rows.items()
	}

	# ---- Create ERPNext Batch per unique output_item in packaging lines ------
	series = settings.batch_number_series or "BATCH-.YYYY.-.#####"
	item_to_batch = {}
	for row in wb.packaging_lines:
		if not row.output_item:
			continue
		if row.output_item not in item_to_batch:
			batch_id = make_autoname(series)
			existing_batch = frappe.db.get_value("Batch", {"batch_id": batch_id}, "name")
			if existing_batch:
				item_to_batch[row.output_item] = existing_batch
			else:
				batch = frappe.new_doc("Batch")
				batch.item = row.output_item
				batch.batch_id = batch_id
				batch.description = f"Wine Batch {wb.name}"
				batch.insert(ignore_permissions=True)
				item_to_batch[row.output_item] = batch.name
		frappe.db.set_value(
			"Wine Batch Packaging Line", row.name, "output_batch_no",
			item_to_batch[row.output_item],
		)

	wb.reload()

	# ---- One Manufacture SE per packaging line --------------------------------
	active_lines  = [r for r in wb.packaging_lines if r.output_item and cint(r.actual_cartons)]
	mat_consumed  = {}       # mat.name → qty consumed so far (last SE takes remainder)
	size_first_se = set()    # sizes whose samples/remainder have been produced
	se_names      = []

	for pl_idx, row in enumerate(active_lines):
		is_last      = (pl_idx == len(active_lines) - 1)
		sz           = cint(row.bottle_size_ml)
		pl_volume_ml = cint(row.actual_total_bottles) * sz
		vol_fraction = pl_volume_ml / total_volume_ml if total_volume_ml else 0.0
		btl_fraction = cint(row.actual_total_bottles) / total_actual_bottles if total_actual_bottles else 0.0

		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Manufacture"
		se.posting_date = wb.bottling_date or today()

		# WIP consumption — proportional by volume; last SE takes the exact remainder
		for wip in wip_item_list:
			if is_last:
				qty = round(wip["total_qty"] - wip["consumed"], 6)
			else:
				qty = round(wip["total_qty"] * vol_fraction, 6)
				wip["consumed"] += qty
			if qty <= 0:
				continue
			se.append("items", {
				"item_code": wip["item_code"],
				"qty": qty,
				"uom": wip["uom"],
				"s_warehouse": wip["wip_warehouse"],
				"batch_no": wip["batch_no"] or None,
				"use_serial_batch_fields": 1 if wip["batch_no"] else 0,
				"is_finished_item": 0,
			})

		# Bottle + sealing — exact qty for this packaging line's size,
		# distributed across matching bottling lines proportionally
		size_total = total_bottles_by_size.get(sz, 0)
		for bl in size_to_bl_rows.get(sz, []):
			if not size_total:
				continue
			share   = cint(bl.actual_bottles) / size_total
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

		# Additional materials — proportional by bottle count; last SE takes remainder
		for mat in wb.material_lines:
			if not mat.item or not flt(mat.quantity):
				continue
			if is_last:
				qty = round(flt(mat.quantity) - mat_consumed.get(mat.name, 0.0), 6)
			else:
				qty = round(flt(mat.quantity) * btl_fraction, 6)
			mat_consumed[mat.name] = mat_consumed.get(mat.name, 0.0) + qty
			if qty > 0:
				se.append("items", {
					"item_code": mat.item,
					"qty": qty,
					"uom": mat.uom or None,
					"s_warehouse": mat.source_warehouse,
					"is_finished_item": 0,
				})

		# Lab Analysis consumables — from WIP warehouse (already transferred there on LA submit)
		for lc in lab_consumable_list:
			if is_last:
				qty = round(lc["total_qty"] - lc["consumed"], 6)
			else:
				qty = round(lc["total_qty"] * btl_fraction, 6)
			lc["consumed"] += qty
			if qty > 0 and wb.wip_warehouse:
				se.append("items", {
					"item_code": lc["item_code"],
					"qty": qty,
					"uom": lc["uom"] or None,
					"s_warehouse": wb.wip_warehouse,
					"is_finished_item": 0,
				})

		# Finished item — exactly one per SE (the carton output for this packaging line)
		bl_list  = size_to_bl_rows.get(sz, [])
		mat_cost = mat_cost_per_bottling_line.get(bl_list[0].name, 0.0) if bl_list else 0.0
		cost_per_bottle = wine_cost_per_ml * sz + mat_cost + additional_cost_per_bottle + lab_consumable_cost_per_bottle
		basic_rate      = cost_per_bottle * cint(row.bottles_per_carton)
		se.append("items", {
			"item_code": row.output_item,
			"qty": cint(row.actual_cartons),
			"t_warehouse": row.output_warehouse,
			"batch_no": row.output_batch_no or None,
			"use_serial_batch_fields": 1 if row.output_batch_no else 0,
			"is_finished_item": 1,
			"basic_rate": round(basic_rate, 4),
		})

		# Samples + remainder — only in the FIRST SE created for each bottle size
		if sz not in size_first_se:
			size_first_se.add(sz)
			for bl in size_to_bl_rows.get(sz, []):
				sample_qty = max(cint(bl.sample_bottles), 1)
				cost = (
					wine_cost_per_ml * sz
					+ mat_cost_per_bottling_line.get(bl.name, 0.0)
					+ additional_cost_per_bottle
				+ lab_consumable_cost_per_bottle
				)
				if bl.bottled_wine_item:
					se.append("items", {
						"item_code": bl.bottled_wine_item,
						"qty": sample_qty,
						"t_warehouse": sample_warehouse,
						"is_finished_item": 0,
						"basic_rate": round(cost, 4),
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
							"basic_rate": round(cost, 4),
						})

		se.insert(ignore_permissions=True)
		frappe.get_doc("Stock Entry", se.name).submit()
		se_names.append(se.name)

	stock_entries_str = "\n".join(se_names)
	frappe.msgprint(
		f"Created {len(se_names)} Stock {'Entry' if len(se_names) == 1 else 'Entries'}: "
		f"<b>{', '.join(se_names)}</b> — wine batch closed.",
		alert=True,
	)

	# ---- Update Wine Batch ---------------------------------------------------
	frappe.db.set_value("Wine Batch", wb.name, {
		"bottling_status": "Completed",
		"bottling_stock_entry": stock_entries_str,
		"total_volume_bottled": total_volume_bottled,
		"process_loss": process_loss,
		"yield_efficiency_pct": yield_efficiency_pct,
		"packaging_process_loss": packaging_process_loss,
		"packaging_yield_pct": packaging_yield_pct,
		"excise_duty_per_litre": excise_rate,
		"excise_duty_amount": excise_duty_amount,
		"status": "Completed",
		"end_date": today(),
	})

	return {"stock_entries": se_names}


@frappe.whitelist()
def cancel_bottling(wine_batch):
	"""Cancel the bottling stock entry and revert the Wine Batch to Active."""
	wb = frappe.get_doc("Wine Batch", wine_batch)

	if wb.bottling_status != "Completed":
		frappe.throw("Bottling has not been completed — nothing to cancel.")

	# Cancel all stock entries (newline-separated list)
	for se_name in (wb.bottling_stock_entry or "").splitlines():
		se_name = se_name.strip()
		if not se_name:
			continue
		try:
			se = frappe.get_doc("Stock Entry", se_name)
			if se.docstatus == 1:
				se.cancel()
		except frappe.DoesNotExistError:
			pass

	# Cancel all ERPNext Batches stamped on packaging lines
	batch_nos = {row.output_batch_no for row in wb.packaging_lines if row.output_batch_no}
	for bn in batch_nos:
		batch = frappe.get_doc("Batch", bn)
		if batch.docstatus == 1:
			batch.cancel()

	# Clear actuals on bottling lines
	for row in wb.bottling_lines:
		frappe.db.set_value("Wine Batch Bottling Line", row.name, {
			"actual_bottles": 0,
			"qc_bottles": 0,
			"sample_bottles": 1,
			"net_bottles": 0,
			"volume_litres": 0,
			"remaining_volume_litres": 0,
			"bottled_wine_item": None,
			"bottle_source_warehouse": None,
			"sealing_item": None,
			"sealing_source_warehouse": None,
		})

	# Clear actuals on packaging lines
	for row in wb.packaging_lines:
		frappe.db.set_value("Wine Batch Packaging Line", row.name, {
			"output_batch_no": None,
			"remaining_bottles": 0,
			"actual_cartons": 0,
			"actual_total_bottles": 0,
			"output_item": None,
			"output_warehouse": None,
		})

	# Revert Wine Batch
	frappe.db.set_value("Wine Batch", wb.name, {
		"bottling_status": "Pending",
		"bottling_stock_entry": None,
		"total_volume_bottled": 0,
		"process_loss": 0,
		"yield_efficiency_pct": 0,
		"packaging_process_loss": 0,
		"packaging_yield_pct": 0,
		"excise_duty_amount": 0,
		"status": "Active",
		"end_date": None,
	})

	frappe.msgprint("Bottling & Packaging cancelled. Wine Batch reverted to Active.", alert=True)


@frappe.whitelist()
def create_rebottling_from_batch(wine_batch_name):
	"""
	Create a draft Wine Batch Rebottling pre-populated with source lines
	derived from the Wine Batch's completed packaging lines.
	Returns the name of the new rebottling document.
	"""
	wb = frappe.get_doc("Wine Batch", wine_batch_name)
	if wb.bottling_status != "Completed":
		frappe.throw(
			"Wine Batch must be fully closed (status: Completed) before creating a rebottling."
		)

	active_lines = [
		pl for pl in wb.packaging_lines
		if pl.output_item and cint(pl.actual_cartons)
	]
	if not active_lines:
		frappe.throw(
			"No completed packaging lines found on this Wine Batch. "
			"Please close the wine batch first."
		)

	rb = frappe.new_doc("Wine Batch Rebottling")
	rb.wine_batch = wine_batch_name
	rb.is_auto_created = 1

	for pl in active_lines:
		rb.append("source_lines", {
			"source_item":        pl.output_item,
			"source_warehouse":   pl.output_warehouse,
			"source_batch_no":    pl.output_batch_no or None,
			"bottle_size_ml":     cint(pl.bottle_size_ml),
			"bottles_per_unit":   cint(pl.bottles_per_carton),
			"pack_size":          pl.pack_size or "",
			"available_quantity": cint(pl.actual_cartons),
			"planned_quantity":   0,
		})

	rb.insert(ignore_permissions=True)
	return rb.name
