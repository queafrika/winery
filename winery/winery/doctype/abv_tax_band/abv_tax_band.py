# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ABVTaxBand(Document):
	def validate(self):
		if self.min_abv >= self.max_abv:
			frappe.throw("Min ABV must be less than Max ABV.")
