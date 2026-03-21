# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import today


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
					"task_name": la.task_name,
					"scheduled_hours_from_start": la.scheduled_hours_from_start,
					"is_mandatory": la.is_mandatory,
					"expected_sample_size": la.expected_sample_size,
					"expected_sample_uom": la.expected_sample_uom,
					"notes": la.notes,
					"status": "Pending",
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
		stages = sorted(recipe.stages, key=lambda s: s.idx)

		next_idx = (self.current_stage_number or 0) + 1
		if next_idx > len(stages):
			frappe.throw("All stages in the recipe have been completed.")

		stage = stages[next_idx - 1]

		# ---- Create Cellar Operation for this stage --------------------------
		co = frappe.new_doc("Cellar Operation")
		co.operation_type = stage.operation_type
		co.operation_name = f"{self.name} — Stage {next_idx}: {stage.operation_type}"
		co.wine_batch = self.name
		co.recipe_stage_idx = stage.idx
		co.status = "Planned"
		co.vessel = self.current_vessel

		# Pre-fill tasks from Cellar Operation Type
		op_type = frappe.get_doc("Cellar Operation Type", stage.operation_type)
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

		# Add Lab Test tasks defined in the recipe for this operation type
		for la in recipe.lab_analyses:
			if la.operation_type == stage.operation_type:
				co.append("tasks", {
					"task_name": la.task_name,
					"task_type": "Lab Test",
					"scheduled_hours_from_start": la.scheduled_hours_from_start,
					"expected_sample_size": la.expected_sample_size,
					"expected_sample_uom": la.expected_sample_uom,
					"completed": 0,
				})

		# Pre-fill materials from recipe raw materials for this operation type
		for rm in recipe.raw_materials:
			if rm.stage_name == stage.operation_type:
				# Scale quantity by batch size ratio
				recipe_yield = recipe.base_batch_size or 1
				scale = (self.target_batch_size or recipe_yield) / recipe_yield
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
				sample_info = f"{lt.task_name}"
				if lt.expected_sample_size:
					sample_info += f" — {lt.expected_sample_size} {lt.expected_sample_uom or ''}"
				if lt.scheduled_hours_from_start:
					sample_info += f" (at {lt.scheduled_hours_from_start} min)"
				sample_msg += f"<li>{sample_info}</li>"
			sample_msg += "</ul>"
			frappe.msgprint(sample_msg, title="Lab Test Requirements", indicator="blue")

		# Update Wine Batch progress
		self.db_set("current_stage_number", next_idx)
		self.db_set("current_stage_name", stage.operation_type)

		return co.name

	def update_progress(self, co):
		"""Called by Cellar Operation when an operation is completed."""
		self.db_set("current_stage_number", co.recipe_stage_idx)
		self.db_set("current_stage_name", co.operation_type)
		if co.vessel:
			self.db_set("current_vessel", co.vessel)

		recipe = frappe.get_doc("Recipe", self.recipe)
		if co.recipe_stage_idx >= len(recipe.stages):
			self.db_set("status", "Completed")
			self.db_set("end_date", today())
