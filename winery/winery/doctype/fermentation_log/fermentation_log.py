import frappe
from frappe.model.document import Document
from frappe.utils import date_diff, today, getdate


STABILITY_TOLERANCE = 0.002  # industry standard: ±0.002 SG


class FermentationLog(Document):
	def validate(self):
		self._calc_days_in_fermentation()
		self._calc_temperature_rows()
		self._calc_weekly_sample_rows()
		self._check_stability()
		self._update_latest_readings()

	def _calc_days_in_fermentation(self):
		if self.fermentation_start_date:
			self.days_in_fermentation = date_diff(today(), self.fermentation_start_date)

	def _calc_temperature_rows(self):
		temp_min = self.target_temp_min or 0
		temp_max = self.target_temp_max or 999
		for row in self.temp_readings:
			readings = [v for v in [row.morning_temp, row.afternoon_temp, row.evening_temp] if v]
			if readings:
				row.average_temp = round(sum(readings) / len(readings), 1)
				row.out_of_range = 1 if any(t < temp_min or t > temp_max for t in readings) else 0

	def _calc_weekly_sample_rows(self):
		start = getdate(self.fermentation_start_date) if self.fermentation_start_date else None
		for row in self.weekly_samples:
			if start and row.sample_date:
				days = date_diff(row.sample_date, start)
				row.week_number = max(1, (days // 7) + 1)

	def _check_stability(self):
		samples = [r for r in self.weekly_samples if r.specific_gravity]
		if len(samples) < 3:
			self.fermentation_stable = 0
			for row in self.weekly_samples:
				row.gravity_stable = 0
			return

		# Check last 3 readings
		last3 = [r.specific_gravity for r in samples[-3:]]
		is_stable = (max(last3) - min(last3)) <= STABILITY_TOLERANCE

		self.fermentation_stable = 1 if is_stable else 0

		# Flag each row where the 3-reading window ending at that row is stable
		for i, row in enumerate(samples):
			if i >= 2:
				window = [samples[j].specific_gravity for j in range(i - 2, i + 1)]
				row.gravity_stable = 1 if (max(window) - min(window)) <= STABILITY_TOLERANCE else 0
			else:
				row.gravity_stable = 0

		if is_stable and self.fermentation_status == "Active":
			frappe.msgprint(
				"Fermentation appears stable — last 3 gravity readings are within ±0.002. "
				"Consider marking this fermentation as Complete.",
				indicator="green",
				title="Fermentation Stable",
			)

	def _update_latest_readings(self):
		sg_rows = [r for r in self.weekly_samples if r.specific_gravity]
		if sg_rows:
			latest = sg_rows[-1]
			self.latest_sg = latest.specific_gravity
			self.latest_ph = latest.ph or None
