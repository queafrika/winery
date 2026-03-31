# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ComplianceType(Document):
	def validate(self):
		if self.amount_source == "Fixed" and not self.default_amount:
			frappe.throw("Default Amount is required when Amount Source is Fixed.")
		if self.amount_source == "Query":
			if not self.query_doctype:
				frappe.throw("Query DocType is required when Amount Source is Query.")
			if not self.query_date_field:
				frappe.throw("Date Field is required when Amount Source is Query.")
			if not self.query_amount_field:
				frappe.throw("Amount Field is required when Amount Source is Query.")
