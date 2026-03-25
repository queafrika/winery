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
def load_bottling_template(wine_batch, template):  # wine_batch is required by the Frappe RPC call signature
	"""Return template bottling and packaging lines as dicts for JS pre-fill."""
	tpl = frappe.get_doc("Bottling Packaging Template", template)
	return {
		"bottling_lines": [
			{
				"bottle_item": r.bottle_item,
				"bottle_size_ml": r.bottle_size_ml,
				"bottled_wine_item": r.bottled_wine_item,
				"bottle_source_warehouse": r.bottle_source_warehouse,
				"sealing_item": r.sealing_item,
				"sealing_source_warehouse": r.sealing_source_warehouse,
				"planned_bottles": r.planned_bottles,
				"sample_bottles": r.sample_bottles or 1,
			}
			for r in tpl.bottling_lines
		],
		"packaging_lines": [
			{
				"pack_size": r.pack_size,
				"bottle_size_ml": r.bottle_size_ml,
				"bottles_per_carton": r.bottles_per_carton,
				"output_item": r.output_item,
				"output_warehouse": r.output_warehouse,
			}
			for r in tpl.packaging_lines
		],
		"material_lines": [
			{
				"item": r.item,
				"description": r.description,
				"quantity": r.quantity,
				"uom": r.uom,
				"source_warehouse": r.source_warehouse,
			}
			for r in tpl.material_lines
		],
	}


def _get_bin_rate(item_code, warehouse):
	"""Return the current valuation rate for an item in a warehouse (0 if not found)."""
	if not item_code or not warehouse:
		return 0.0
	rate = frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "valuation_rate")
	return flt(rate)


@frappe.whitelist()
def complete_bottling(wine_batch):
	"""
	Validate, create ERPNext Batch, build and submit the Manufacture Stock Entry,
	then mark the Wine Batch as Completed.
	"""
	wb = frappe.get_doc("Wine Batch", wine_batch)

	# ---- Guard ---------------------------------------------------------------
	if wb.bottling_status == "Completed":
		frappe.throw("Bottling & Packaging has already been completed for this batch.")

	# ---- Validate ------------------------------------------------------------
	if not wb.bottling_lines or not any(cint(r.actual_bottles) > 0 for r in wb.bottling_lines):
		frappe.throw("Please add at least one Bottling Line with actual bottles filled.")
	if not wb.packaging_lines:
		frappe.throw("Please add at least one Packaging Line.")
	if not all(r.output_item and r.output_warehouse for r in wb.packaging_lines):
		frappe.throw("All Packaging Lines must have an Output Item and Output Warehouse.")
	if not wb.abv_percentage:
		frappe.throw("ABV (%) is required before completing bottling.")
	if not wb.abv_tax_band:
		frappe.throw(
			f"No ABV Tax Band matched for ABV {wb.abv_percentage}%. "
			"Please configure ABV Tax Bands in Setup."
		)

	settings = frappe.get_single("Winery Settings")
	if not settings.sample_warehouse:
		frappe.throw(
			"Please configure a Sample Warehouse in Winery Settings before completing bottling."
		)
	sample_warehouse = settings.sample_warehouse
	unpackaged_warehouse = settings.unpackaged_bottle_warehouse

	# ---- Compute line totals -------------------------------------------------
	for row in wb.bottling_lines:
		sample = max(cint(row.sample_bottles), 1)
		row.net_bottles = max(cint(row.actual_bottles) - cint(row.qc_bottles) - sample, 0)
		row.volume_litres = round(cint(row.actual_bottles) * cint(row.bottle_size_ml) / 1000, 4)
		frappe.db.set_value("Wine Batch Bottling Line", row.name, {
			"net_bottles": row.net_bottles,
			"volume_litres": row.volume_litres,
		})

	for row in wb.packaging_lines:
		row.total_bottles = cint(row.cartons) * cint(row.bottles_per_carton)
		frappe.db.set_value("Wine Batch Packaging Line", row.name, "total_bottles", row.total_bottles)

	total_volume_bottled = round(sum(flt(r.volume_litres) for r in wb.bottling_lines), 4)
	input_vol = flt(wb.target_batch_size)
	process_loss = round(max(input_vol - total_volume_bottled, 0), 4)
	yield_efficiency_pct = round((total_volume_bottled / input_vol) * 100, 2) if input_vol else 0.0

	# Excise duty
	excise_rate = flt(frappe.db.get_value("ABV Tax Band", wb.abv_tax_band, "excise_duty_per_litre"))
	excise_duty_amount = round(total_volume_bottled * excise_rate, 4)

	# ---- Valuation calculations ----------------------------------------------
	# Step 1: WIP wine cost per ml
	cellar_ops = frappe.get_all(
		"Cellar Operation",
		filters={"wine_batch": wb.name, "docstatus": 1},
		fields=["name", "transfer_entry", "stock_entry", "wip_warehouse"],
	)
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

	# Step 4: Weighted average cost per bottle (for samples and remainder)
	total_weighted_cost = sum(
		(wine_cost_per_ml * cint(r.bottle_size_ml)
		 + mat_cost_per_bottling_line.get(r.name, 0.0)
		 + additional_cost_per_bottle)
		* cint(r.actual_bottles)
		for r in wb.bottling_lines
	)
	avg_cost_per_bottle = (
		total_weighted_cost / total_actual_bottles if total_actual_bottles else 0.0
	)

	# Build a lookup: bottle_size_ml → first matching bottling line name
	size_to_bottling_line = {}
	for row in wb.bottling_lines:
		sz = cint(row.bottle_size_ml)
		if sz and sz not in size_to_bottling_line:
			size_to_bottling_line[sz] = row.name

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

	# ---- Build Manufacture Stock Entry ---------------------------------------
	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Manufacture"
	se.posting_date = wb.bottling_date or today()

	# Consume WIP materials (only COs with a transfer entry and no manufacture entry yet)
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
			se.append("items", {
				"item_code": item.item_code,
				"qty": item.qty,
				"uom": item.uom,
				"s_warehouse": co.wip_warehouse,
				"batch_no": item.batch_no or None,
				"is_finished_item": 0,
			})

	# Consume bottles and sealing items
	for row in wb.bottling_lines:
		if not cint(row.actual_bottles):
			continue
		se.append("items", {
			"item_code": row.bottle_item,
			"qty": cint(row.actual_bottles),
			"s_warehouse": row.bottle_source_warehouse,
			"is_finished_item": 0,
		})
		if row.sealing_item and row.sealing_source_warehouse:
			se.append("items", {
				"item_code": row.sealing_item,
				"qty": cint(row.actual_bottles),
				"s_warehouse": row.sealing_source_warehouse,
				"is_finished_item": 0,
			})

	# Consume additional materials (corks, labels, stickers, etc.)
	for row in wb.material_lines:
		if not row.item or not flt(row.quantity):
			continue
		se.append("items", {
			"item_code": row.item,
			"qty": flt(row.quantity),
			"uom": row.uom or None,
			"s_warehouse": row.source_warehouse,
			"is_finished_item": 0,
		})

	# Reload packaging lines to get the stamped batch_no, then produce packaged cartons
	wb.reload()
	for row in wb.packaging_lines:
		if not row.output_item or not cint(row.cartons):
			continue
		sz = cint(row.bottle_size_ml)
		bl_name = size_to_bottling_line.get(sz)
		mat_cost = mat_cost_per_bottling_line.get(bl_name, 0.0) if bl_name else 0.0
		cost_per_bottle = wine_cost_per_ml * sz + mat_cost + additional_cost_per_bottle
		basic_rate = cost_per_bottle * cint(row.bottles_per_carton)
		se.append("items", {
			"item_code": row.output_item,
			"qty": cint(row.cartons),
			"t_warehouse": row.output_warehouse,
			"batch_no": row.output_batch_no or None,
			"is_finished_item": 1,
			"basic_rate": round(basic_rate, 4),
		})

	# Produce sample bottles — one SE line per bottling line using row.bottled_wine_item
	for row in wb.bottling_lines:
		sample_qty = max(cint(row.sample_bottles), 1)
		if row.bottled_wine_item:
			cost = (
				wine_cost_per_ml * cint(row.bottle_size_ml)
				+ mat_cost_per_bottling_line.get(row.name, 0.0)
				+ additional_cost_per_bottle
			)
			se.append("items", {
				"item_code": row.bottled_wine_item,
				"qty": sample_qty,
				"t_warehouse": sample_warehouse,
				"is_finished_item": 0,
				"basic_rate": round(cost, 4),
			})
		elif row.bottle_item:
			# Fallback: use empty bottle item if bottled_wine_item not configured
			se.append("items", {
				"item_code": row.bottle_item,
				"qty": sample_qty,
				"t_warehouse": sample_warehouse,
				"is_finished_item": 0,
			})

	# Produce remainder filled bottles — one SE line per bottling line → unpackaged warehouse
	if unpackaged_warehouse:
		packaged_by_size = {}
		for row in wb.packaging_lines:
			sz = cint(row.bottle_size_ml)
			packaged_by_size[sz] = packaged_by_size.get(sz, 0) + cint(row.total_bottles)

		for row in wb.bottling_lines:
			if not row.bottled_wine_item:
				continue
			sz = cint(row.bottle_size_ml)
			remainder = cint(row.net_bottles) - packaged_by_size.get(sz, 0)
			if remainder > 0:
				cost = (
					wine_cost_per_ml * sz
					+ mat_cost_per_bottling_line.get(row.name, 0.0)
					+ additional_cost_per_bottle
				)
				se.append("items", {
					"item_code": row.bottled_wine_item,
					"qty": remainder,
					"t_warehouse": unpackaged_warehouse,
					"is_finished_item": 0,
					"basic_rate": round(cost, 4),
				})

	se.insert(ignore_permissions=True)
	se.submit()
	stock_entry_name = se.name

	frappe.msgprint(
		f"Stock Entry <b>{stock_entry_name}</b> created — bottling & packaging complete.",
		alert=True,
	)

	# ---- Update Wine Batch ---------------------------------------------------
	frappe.db.set_value("Wine Batch", wb.name, {
		"bottling_status": "Completed",
		"bottling_stock_entry": stock_entry_name,
		"total_volume_bottled": total_volume_bottled,
		"process_loss": process_loss,
		"yield_efficiency_pct": yield_efficiency_pct,
		"excise_duty_per_litre": excise_rate,
		"excise_duty_amount": excise_duty_amount,
		"status": "Completed",
		"end_date": today(),
	})

	return {"stock_entry": stock_entry_name}


@frappe.whitelist()
def cancel_bottling(wine_batch):
	"""Cancel the bottling stock entry and revert the Wine Batch to Active."""
	wb = frappe.get_doc("Wine Batch", wine_batch)

	if wb.bottling_status != "Completed":
		frappe.throw("Bottling has not been completed — nothing to cancel.")

	# Cancel the stock entry
	if wb.bottling_stock_entry:
		se = frappe.get_doc("Stock Entry", wb.bottling_stock_entry)
		if se.docstatus == 1:
			se.cancel()

	# Cancel all ERPNext Batches stamped on packaging lines
	batch_nos = {row.output_batch_no for row in wb.packaging_lines if row.output_batch_no}
	for bn in batch_nos:
		batch = frappe.get_doc("Batch", bn)
		if batch.docstatus == 1:
			batch.cancel()

	# Clear output_batch_no on packaging lines
	for row in wb.packaging_lines:
		frappe.db.set_value("Wine Batch Packaging Line", row.name, "output_batch_no", None)

	# Revert Wine Batch
	frappe.db.set_value("Wine Batch", wb.name, {
		"bottling_status": "Pending",
		"bottling_stock_entry": None,
		"total_volume_bottled": 0,
		"process_loss": 0,
		"yield_efficiency_pct": 0,
		"excise_duty_amount": 0,
		"status": "Active",
		"end_date": None,
	})

	frappe.msgprint("Bottling & Packaging cancelled. Wine Batch reverted to Active.", alert=True)
