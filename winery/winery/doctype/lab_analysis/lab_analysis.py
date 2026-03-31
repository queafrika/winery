# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


class LabAnalysis(Document):
	def validate(self):
		if self.analysis_source == "Purchased Item" and not self.item_batch:
			frappe.throw("Item Batch is required for a Purchased Item analysis.")
		if self.analysis_source != "Purchased Item" and not self.wine_batch:
			frappe.throw("Wine Batch is required for a Wine Batch analysis.")
		self._calc_residual_sugar()
		self._calc_brix()
		self._calc_gravity()
		self._calc_abv()
		self._calc_temperature()
		self._calc_ph()

	def _calc_residual_sugar(self):
		if self.test_type != "Residual Sugar Test":
			return
		readings = [v for v in [self.rs_reading_1, self.rs_reading_2, self.rs_reading_3] if v is not None]
		if not readings:
			return
		avg = sum(readings) / len(readings)
		self.rs_average_fg = round(avg, 3)
		correction = self.rs_temp_correction or 0
		corrected = round(avg + correction, 3)
		self.rs_corrected_fg = corrected
		rs = round((corrected - 1.0) * 1000, 2)
		self.rs_residual_sugar_gl = rs

		if corrected < 1.001:
			self.rs_wine_classification = "Bone Dry (<1 g/L)"
			self.rs_fg_below_1000 = 1
		elif rs < 2:
			self.rs_wine_classification = "Very Dry (1-2 g/L)"
		elif rs < 5:
			self.rs_wine_classification = "Dry (2-5 g/L)"
		elif rs < 10:
			self.rs_wine_classification = "Off-Dry (5-10 g/L)"
		elif rs < 15:
			self.rs_wine_classification = "Medium Sweet (10-15 g/L)"
		elif rs < 25:
			self.rs_wine_classification = "Sweet (15-25 g/L)"
		else:
			self.rs_wine_classification = "Very Sweet (>25 g/L)"

	def _calc_brix(self):
		if self.test_type != "Brix Test":
			return
		readings = [v for v in [self.brix_reading_1, self.brix_reading_2, self.brix_reading_3] if v is not None]
		if not readings:
			return
		avg = round(sum(readings) / len(readings), 2)
		self.brix_average = avg

	def _calc_gravity(self):
		if self.test_type != "Gravity Test":
			return
		readings = [v for v in [self.gravity_reading_1, self.gravity_reading_2, self.gravity_reading_3] if v is not None]
		if not readings:
			return
		self.average_gravity = round(sum(readings) / len(readings), 3)

	def _calc_abv(self):
		if self.test_type != "ABV Test":
			return
		readings = [v for v in [self.abv_reading_1, self.abv_reading_2, self.abv_reading_3] if v is not None]
		if not readings:
			return
		avg = round(sum(readings) / len(readings), 2)
		self.abv_average_abv = avg
		correction = self.abv_correction_factor or 0
		self.abv_corrected_abv = round(avg + correction, 2)

	def _calc_temperature(self):
		if self.test_type != "Temperature Test":
			return
		if self.temp_reading_1 is None:
			return
		reading = self.temp_reading_1
		self.temp_average = round(reading, 1)
		temp_min = self.temp_target_min
		temp_max = self.temp_target_max
		out = (temp_min is not None and reading < temp_min) or \
		      (temp_max is not None and reading > temp_max)
		self.temp_out_of_range = 1 if out else 0

	def _calc_ph(self):
		if self.test_type != "pH Test":
			return

		# Average of readings
		readings = [v for v in [self.ph_reading_1, self.ph_reading_2, self.ph_reading_3] if v is not None]
		if not readings:
			return
		avg = round(sum(readings) / len(readings), 2)
		self.ph_average = avg

		# Result vs target range
		target_min = self.ph_target_min
		target_max = self.ph_target_max
		if target_min is not None and target_max is not None:
			self.ph_result = "PASS" if target_min <= avg <= target_max else "FAIL"

	def on_submit(self):
		if self.analysis_source == "Purchased Item":
			self._release_batch_if_complete()
			self._expense_consumables()
		else:
			self._mark_cellar_task_complete()
			self._transfer_consumables_to_wip()

	def on_cancel(self):
		self._cancel_consumable_stock_entry()

	def _transfer_consumables_to_wip(self):
		"""On submit of a Wine Batch Lab Analysis, transfer consumables to the WIP warehouse."""
		if not self.consumables:
			return
		if not self.wine_batch:
			return
		wip_warehouse = frappe.db.get_value("Wine Batch", self.wine_batch, "wip_warehouse")
		if not wip_warehouse:
			frappe.throw(
				f"Please set a WIP Warehouse on Wine Batch <b>{self.wine_batch}</b> before submitting "
				f"a Lab Analysis with consumables."
			)
		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Material Transfer"
		se.posting_date = (
			self.analysis_date.date() if self.analysis_date else today()
		)
		for row in self.consumables:
			if not row.item or not flt(row.quantity):
				continue
			se.append("items", {
				"item_code": row.item,
				"qty": flt(row.quantity),
				"uom": row.uom or None,
				"s_warehouse": row.source_warehouse,
				"t_warehouse": wip_warehouse,
			})
		if not se.items:
			return
		se.insert(ignore_permissions=True)
		se.submit()
		self.db_set("consumable_stock_entry", se.name)

	def _expense_consumables(self):
		"""On submit of a Purchased Item Lab Analysis, expense consumables via Material Issue."""
		if not self.consumables:
			return
		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Material Issue"
		se.posting_date = (
			self.analysis_date.date() if self.analysis_date else today()
		)
		for row in self.consumables:
			if not row.item or not flt(row.quantity):
				continue
			se.append("items", {
				"item_code": row.item,
				"qty": flt(row.quantity),
				"uom": row.uom or None,
				"s_warehouse": row.source_warehouse,
			})
		if not se.items:
			return
		se.insert(ignore_permissions=True)
		se.submit()
		self.db_set("consumable_stock_entry", se.name)

	def _cancel_consumable_stock_entry(self):
		"""Cancel the consumable SE when the Lab Analysis is cancelled."""
		if not self.consumable_stock_entry:
			return
		try:
			se = frappe.get_doc("Stock Entry", self.consumable_stock_entry)
			if se.docstatus == 1:
				se.cancel()
		except frappe.DoesNotExistError:
			pass

	def _release_batch_if_complete(self):
		"""Release the batch QA hold once all mandatory tests have been submitted."""
		if not self.item_batch or not self.item:
			return
		mandatory = [
			r.test_type
			for r in frappe.get_all(
				"Item Lab Test Requirement",
				filters={"parent": self.item, "is_mandatory": 1},
				fields=["test_type"],
			)
		]
		if not mandatory:
			return
		done = {
			r.test_type
			for r in frappe.get_all(
				"Lab Analysis",
				filters={"item_batch": self.item_batch, "docstatus": 1},
				fields=["test_type"],
			)
		}
		if all(t in done for t in mandatory):
			frappe.db.set_value("Batch", self.item_batch, "qa_status", "Released")
			frappe.msgprint(
				f"Batch <b>{self.item_batch}</b> has passed all mandatory QA tests and is now released for use.",
				alert=True,
				indicator="green",
			)

	def _mark_cellar_task_complete(self):
		"""Auto-check the linked Cellar Operation task when this lab analysis is submitted."""
		if not self.cellar_operation or not self.cellar_operation_task:
			return
		co = frappe.get_doc("Cellar Operation", self.cellar_operation)
		co.mark_task_complete(
			task_name=self.cellar_operation_task,
			lab_analysis=self.name,
		)


