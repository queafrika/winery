# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.model.document import Document
from frappe.utils import flt, now_datetime, time_diff_in_hours


class CellarOperation(Document):

	def validate(self):
		self._compute_duration()

	def _compute_duration(self):
		if self.start_time and self.end_time:
			if self.end_time < self.start_time:
				frappe.throw("End Time cannot be before Start Time.")
			self.duration = time_diff_in_hours(self.end_time, self.start_time)

	def on_submit(self):
		if self.vessel:
			frappe.db.set_value("Vessel", self.vessel, "status", "In Use")

	def on_cancel(self):
		for field in ("stock_entry", "transfer_entry"):
			name = self.get(field)
			if name:
				se = frappe.get_doc("Stock Entry", name)
				if se.docstatus == 1:
					se.cancel()
				self.db_set(field, None)
		if self.vessel:
			frappe.db.set_value("Vessel", self.vessel, "status", "Empty")
		self.db_set("status", "Cancelled")

	# ------------------------------------------------------------------ #
	#  Whitelisted actions (called from buttons in JS)                     #
	# ------------------------------------------------------------------ #

	@frappe.whitelist()
	def start_operation(self, employee=None):
		"""Mark operation as In Progress, record start time and operator."""
		if self.status == "In Progress":
			frappe.throw("Operation has already been started.")
		if self.status == "Completed":
			frappe.throw("Operation is already completed.")

		now = now_datetime()
		self.db_set("start_time", now)
		self.db_set("status", "In Progress")

		if employee:
			self.db_set("started_by", employee)

		frappe.msgprint(f"Operation started at {frappe.utils.format_datetime(now)}.", alert=True)
		return {"start_time": str(now)}

	@frappe.whitelist()
	def complete_operation(self):
		"""Complete the operation — blocks if any mandatory lab analyses are incomplete."""
		if self.status != "In Progress":
			frappe.throw("Operation must be In Progress before it can be completed.")

		self.reload()

		# Check mandatory lab analyses from the recipe for this operation type
		if self.wine_batch and self.operation_type:
			recipe = frappe.db.get_value("Wine Batch", self.wine_batch, "recipe")
			if recipe:
				mandatory = frappe.get_all(
					"Recipe Lab Analysis",
					filters={"parent": recipe, "operation_type": self.operation_type, "is_mandatory": 1},
					fields=["test_type"],
				)
				if mandatory:
					done = {
						r.test_type
						for r in frappe.get_all(
							"Lab Analysis",
							filters={"cellar_operation": self.name, "docstatus": 1},
							fields=["test_type"],
						)
					}
					missing = [r.test_type for r in mandatory if r.test_type not in done]
					if missing:
						frappe.throw(
							"Cannot complete operation — the following mandatory lab analyses are not yet submitted:<br>"
							+ "<br>".join(f"• {t}" for t in missing)
						)

		now = now_datetime()
		self.db_set("end_time", now)
		self.db_set("status", "Completed")
		if self.start_time:
			self.db_set(
				"duration",
				time_diff_in_hours(str(now), str(self.start_time)),
			)

		if self.output_item and self.output_quantity and self.output_warehouse:
			self._create_manufacture_entry()

		# Update Wine Batch progress
		if self.wine_batch:
			wine_batch = frappe.get_doc("Wine Batch", self.wine_batch)
			wine_batch.update_progress(self)

		frappe.msgprint("Operation completed.", alert=True)

	@frappe.whitelist()
	def transfer_materials(self, wip_warehouse, items):
		"""Create a WIP Transfer SE. Called from the Transfer Stock dialog."""
		if isinstance(items, str):
			items = json.loads(items)

		if self.transfer_entry:
			frappe.throw("Materials have already been transferred for this operation.")

		se = frappe.new_doc("Stock Entry")
		se.purpose = "Material Transfer"
		se.stock_entry_type = "Material Transfer"
		se.remarks = f"WIP transfer for {self.operation_name}"

		for row in items:
			if not row.get("item_code") or not row.get("qty") or not row.get("s_warehouse"):
				continue
			item_row = {
				"item_code": row["item_code"],
				"qty": row["qty"],
				"s_warehouse": row["s_warehouse"],
				"t_warehouse": wip_warehouse,
			}
			if row.get("uom"):
				item_row["uom"] = row["uom"]
			if row.get("batch_no"):
				item_row["batch_no"] = row["batch_no"]
			if row.get("serial_no"):
				item_row["serial_no"] = row["serial_no"]
			if row.get("conversion_factor") and flt(row["conversion_factor"]) not in (0, 1):
				item_row["conversion_factor"] = flt(row["conversion_factor"])
			se.append("items", item_row)

		if not se.items:
			frappe.throw("No valid items to transfer. Please provide source warehouses.")

		se.insert(ignore_permissions=True)
		# se.submit()
		self.db_set("transfer_entry", se.name)
		self.db_set("wip_warehouse", wip_warehouse)
		frappe.msgprint(f"WIP Transfer Entry <b>{se.name}</b> created.", alert=True)
		return se.name

	def _create_manufacture_entry(self):
		"""Consume materials from WIP warehouse → produce output item."""
		se = frappe.new_doc("Stock Entry")
		se.purpose = "Manufacture"
		se.stock_entry_type = "Manufacture"
		se.remarks = f"Manufacture for {self.operation_name}"

		# Consume materials from WIP warehouse
		for row in self.details:
			if row.item and row.quantity:
				se.append("items", {
					"item_code": row.item,
					"qty": row.quantity,
					"uom": row.uom,
					"s_warehouse": self.wip_warehouse,
				})

		# Produce the output item
		se.append("items", {
			"item_code": self.output_item,
			"qty": self.output_quantity,
			"t_warehouse": self.output_warehouse,
			"is_finished_item": 1,
		})

		se.insert(ignore_permissions=True)
		se.submit()
		self.db_set("stock_entry", se.name)
		frappe.msgprint(f"Manufacture Entry <b>{se.name}</b> created.", alert=True)

	@frappe.whitelist()
	def mark_task_complete(self, task_name, lab_analysis=None):
		"""Mark a specific task as completed. Called automatically when Lab Analysis is submitted."""
		for row in self.tasks:
			if row.task_name == task_name and not row.completed:
				row.db_set("completed", 1)
				row.db_set("completed_at", now_datetime())
				row.db_set("completed_by", frappe.session.user)
				if lab_analysis:
					row.db_set("lab_analysis", lab_analysis)
				return True
		return False

# --------------------------------------------------------------------------- #
#  UOM conversion helper (called from Transfer Stock dialog)                   #
# --------------------------------------------------------------------------- #

@frappe.whitelist()
def get_uom_conversion(item_code, from_uom):
	"""
	Return the stock_uom and conversion_factor for item_code when measuring in from_uom.
	conversion_factor: 1 from_uom = conversion_factor stock_uom units.
	e.g. stock_uom=Kg, from_uom=Fingers → factor=0.08 (1 Finger = 0.08 Kg)
	"""
	stock_uom = frappe.db.get_value("Item", item_code, "stock_uom") or from_uom

	if from_uom == stock_uom:
		return {"stock_uom": stock_uom, "conversion_factor": 1.0}

	# 1. Item-specific UOM conversion table
	cf = frappe.db.get_value(
		"UOM Conversion Detail",
		{"parent": item_code, "uom": from_uom},
		"conversion_factor",
	)

	# 2. Global UOM Conversion Factor table
	if not cf:
		cf = frappe.db.get_value(
			"UOM Conversion Factor",
			{"from_uom": from_uom, "to_uom": stock_uom},
			"value",
		)

	# 3. Try reverse direction and invert
	if not cf:
		reverse = frappe.db.get_value(
			"UOM Conversion Factor",
			{"from_uom": stock_uom, "to_uom": from_uom},
			"value",
		)
		if reverse:
			cf = 1.0 / flt(reverse)

	return {"stock_uom": stock_uom, "conversion_factor": flt(cf) or 1.0}
