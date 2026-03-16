# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Vessel(Document):
	def validate(self):
		if self.capacity and self.current_volume:
			if self.current_volume > self.capacity:
				frappe.throw(
					f"Current Volume ({self.current_volume} L) cannot exceed Capacity ({self.capacity} L)."
				)
