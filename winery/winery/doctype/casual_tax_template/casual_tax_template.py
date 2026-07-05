# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CasualTaxTemplate(Document):
	def validate(self):
		if self.is_default:
			# Ensure only one default template per company
			others = frappe.get_all(
				"Casual Tax Template",
				filters={
					"is_default": 1,
					"name": ("!=", self.name),
					"company": self.company or "",
				},
			)
			for row in others:
				frappe.db.set_value("Casual Tax Template", row.name, "is_default", 0)
