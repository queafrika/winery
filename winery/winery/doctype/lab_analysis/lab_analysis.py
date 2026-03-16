# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class LabAnalysis(Document):
	def validate(self):
		self._auto_fill_vessel()
		self._calc_residual_sugar()
		self._calc_brix()
		self._calc_abv()
		self._calc_sensory_average()
		self._calc_temperature()
		self._calc_ph()

	def _auto_fill_vessel(self):
		if self.batch_process_log and not self.vessel:
			vessel = frappe.db.get_value("Batch Process Log", self.batch_process_log, "vessel")
			if vessel:
				self.vessel = vessel

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
		self.brix_potential_abv = round(avg * 0.59, 2)

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

	def _calc_sensory_average(self):
		if self.test_type != "Sensory Evaluation":
			return
		scores = [row.score for row in (self.sens_taster_scores or []) if row.score is not None]
		if not scores:
			return
		avg = round(sum(scores) / len(scores), 1)
		self.sens_average_score = avg

		if avg >= 9:
			self.sens_quality_classification = "Excellent (9-10)"
		elif avg >= 7:
			self.sens_quality_classification = "Very Good (7-8)"
		elif avg >= 5:
			self.sens_quality_classification = "Acceptable (5-6)"
		elif avg >= 3:
			self.sens_quality_classification = "Below Standard (3-4)"
		else:
			self.sens_quality_classification = "Unacceptable (0-2)"

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

		# Set target range from stage
		if self.ph_stage == "Pre-Production":
			self.ph_target_min = 6.5
			self.ph_target_max = 7.5
		elif self.ph_stage == "Post-Production":
			self.ph_target_min = 3.2
			self.ph_target_max = 4.0

		# Calibration pass (all 3 buffers must pass)
		all_pass = bool(self.ph_cal_buffer_4_pass and self.ph_cal_buffer_7_pass and self.ph_cal_buffer_10_pass)
		self.ph_calibration_pass = "PASS" if all_pass else "FAIL"

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
		self._evaluate_readings()
		self._mark_cellar_task_complete()

	def _mark_cellar_task_complete(self):
		"""Auto-check the linked Cellar Operation task when this lab analysis is submitted."""
		if not self.cellar_operation or not self.cellar_operation_task:
			return
		co = frappe.get_doc("Cellar Operation", self.cellar_operation)
		co.mark_task_complete(
			task_name=self.cellar_operation_task,
			lab_analysis=self.name,
		)

	def _evaluate_readings(self):
		has_failure = False
		for row in self.measurement:
			if not row.parameter:
				continue
			param = frappe.get_doc("Lab Test Parameter", row.parameter)
			within = True
			if param.min_value is not None and row.value is not None and row.value < param.min_value:
				within = False
			if param.max_value is not None and row.value is not None and row.value > param.max_value:
				within = False
			frappe.db.set_value(
				"Lab Analysis Reading",
				row.name,
				"within_range",
				1 if within else 0,
			)
			if not within:
				has_failure = True

		if self.measurement:
			new_status = "Failed" if has_failure else "Passed"
			self.db_set("status", new_status)
			if has_failure:
				frappe.msgprint(
					"One or more readings are outside the acceptable range. Status set to Failed.",
					indicator="orange",
				)
