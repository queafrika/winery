# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class LabAnalysis(Document):
	def validate(self):
		if self.analysis_source == "Purchased Item" and not self.item_batch:
			frappe.throw("Item Batch is required for a Purchased Item analysis.")
		if self.analysis_source != "Purchased Item" and not self.wine_batch:
			frappe.throw("Wine Batch is required for a Wine Batch analysis.")
		self._calc_residual_sugar()
		self._calc_brix()
		self._calc_abv()
		self._calc_temperature()
		self._calc_ph()

	def _calc_residual_sugar(self):
		if self.test_type != "Residual Sugar Test":
			return
		readings = [v for v in [self.rs_reading_1, self.rs_reading_2, self.rs_reading_3] if v]
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
		readings = [v for v in [self.brix_reading_1, self.brix_reading_2, self.brix_reading_3] if v]
		if not readings:
			return
		avg = round(sum(readings) / len(readings), 2)
		self.brix_average = avg

	def _calc_abv(self):
		if self.test_type != "ABV Test":
			return
		readings = [v for v in [self.abv_reading_1, self.abv_reading_2, self.abv_reading_3] if v]
		if not readings:
			return
		avg = round(sum(readings) / len(readings), 2)
		self.abv_average_abv = avg
		correction = self.abv_correction_factor or 0
		self.abv_corrected_abv = round(avg + correction, 2)

	def _calc_temperature(self):
		if self.test_type != "Temperature Test":
			return
		readings = [v for v in [self.temp_reading_1, self.temp_reading_2, self.temp_reading_3] if v]
		if not readings:
			return
		avg = round(sum(readings) / len(readings), 1)
		self.temp_average = avg
		temp_min = self.temp_target_min
		temp_max = self.temp_target_max
		out = (temp_min is not None and any(t < temp_min for t in readings)) or \
		      (temp_max is not None and any(t > temp_max for t in readings))
		self.temp_out_of_range = 1 if out else 0

	def _calc_ph(self):
		if self.test_type != "pH Test":
			return

		# Average of readings
		readings = [v for v in [self.ph_reading_1, self.ph_reading_2, self.ph_reading_3] if v is not None and v != 0]
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
		else:
			self._mark_cellar_task_complete()

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


