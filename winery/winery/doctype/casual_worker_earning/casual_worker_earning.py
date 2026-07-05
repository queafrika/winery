# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class CasualWorkerEarning(Document):
	def validate(self):
		if flt(self.amount) <= 0:
			frappe.throw("Amount must be greater than zero.")

	def on_trash(self):
		if self.payment_status == "Paid":
			frappe.throw("Cannot delete an earning that has already been paid.")
