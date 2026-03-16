# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import time_diff_in_hours


class BatchProcessLog(Document):
	def validate(self):
		self._compute_duration()
		self._compute_material_loss()

	def _compute_duration(self):
		if self.start_time and self.end_time:
			if self.end_time < self.start_time:
				frappe.throw("End Time cannot be before Start Time.")
			self.duration = time_diff_in_hours(self.end_time, self.start_time)

	def _compute_material_loss(self):
		total_input = sum(row.quantity or 0 for row in self.input_batches)
		if total_input and self.output_quantity is not None:
			self.material_loss = max(0, total_input - self.output_quantity)
			self.material_loss_pct = (self.material_loss / total_input) * 100 if total_input else 0

	def on_submit(self):
		self._validate_inputs()
		self._create_wip_transfer()
		self._create_manufacture_stock_entry()
		self._update_wine_batch()

	def on_cancel(self):
		# Cancel Manufacture SE first, then Transfer SE
		for field in ("stock_entry", "transfer_entry"):
			name = self.get(field)
			if name:
				se = frappe.get_doc("Stock Entry", name)
				if se.docstatus == 1:
					se.cancel()
				self.db_set(field, None)
		self._revert_wine_batch()

	def _validate_inputs(self):
		if not self.input_batches:
			frappe.throw("Please add at least one Input Batch before submitting.")
		if not self.wip_warehouse:
			frappe.throw("Please set the WIP Warehouse before submitting.")
		if not self.output_item or not self.output_quantity or not self.output_warehouse:
			frappe.throw("Output Item, Quantity and Warehouse are required before submitting.")

	def _create_wip_transfer(self):
		"""Move input batches from their source warehouses → WIP warehouse."""
		se = frappe.new_doc("Stock Entry")
		se.purpose = "Material Transfer"
		se.stock_entry_type = "Material Transfer"
		se.remarks = f"WIP transfer for {self.stage_name} — {self.wine_batch}"

		for row in self.input_batches:
			if not row.quantity or not row.source_warehouse:
				continue
			se.append("items", {
				"item_code": row.item_code,
				"qty": row.quantity,
				"uom": "Nos",
				"s_warehouse": row.source_warehouse,
				"t_warehouse": self.wip_warehouse,
				"batch_no": row.batch_no,
			})

		se.insert(ignore_permissions=True)
		se.submit()
		self.db_set("transfer_entry", se.name)
		frappe.msgprint(f"WIP Transfer Entry <b>{se.name}</b> created.", alert=True)

	def _create_manufacture_stock_entry(self):
		"""Consume from WIP warehouse + additives → produce output item."""
		se = frappe.new_doc("Stock Entry")
		se.purpose = "Manufacture"
		se.stock_entry_type = "Manufacture"
		se.remarks = f"Manufacture for {self.stage_name} — {self.wine_batch}"

		# Consume all input batches from WIP warehouse
		for row in self.input_batches:
			if not row.quantity:
				continue
			se.append("items", {
				"item_code": row.item_code,
				"qty": row.quantity,
				"uom": "Nos",
				"s_warehouse": self.wip_warehouse,
				"batch_no": row.batch_no,
			})

		# Consume additives from their source warehouses
		for row in self.additive_used:
			if row.additive and row.quantity:
				se.append("items", {
					"item_code": row.additive,
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

	def _update_wine_batch(self):
		if not self.wine_batch:
			return
		wine_batch = frappe.get_doc("Wine Batch", self.wine_batch)
		wine_batch.update_progress(self)

		if self.vessel:
			frappe.db.set_value("Vessel", self.vessel, "status", "In Use")
			frappe.db.set_value("Vessel", self.vessel, "current_volume", self.output_quantity)

	def _revert_wine_batch(self):
		if not self.wine_batch:
			return
		prev_stage = (self.stage_number or 1) - 1
		frappe.db.set_value("Wine Batch", self.wine_batch, {
			"current_stage_number": prev_stage,
			"current_stage_name": "",
			"status": "Active",
		})
