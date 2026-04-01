# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, today


_STATUS_COLORS = {
	"Open": "#3498db",
	"In Progress": "#e67e22",
	"Completed": "#27ae60",
	"Overdue": "#e74c3c",
	"Cancelled": "#bdc3c7",
}


class ComplianceTask(Document):
	def validate(self):
		self._auto_overdue()
		self._reset_reminder_on_due_date_change()
		self.calendar_color = _STATUS_COLORS.get(self.status, "#3498db")

	def _auto_overdue(self):
		if self.due_date and self.status in ("Open", "In Progress"):
			if getdate(self.due_date) < getdate(today()):
				self.status = "Overdue"

	def _reset_reminder_on_due_date_change(self):
		prev = self.get_doc_before_save()
		if prev and str(prev.due_date) != str(self.due_date):
			self.reminder_sent = 0

	@frappe.whitelist()
	def calculate_amount(self):
		"""Execute the stored SQL query and populate the amount field."""
		if not self.amount_sql:
			frappe.throw("No SQL query is configured on this task.")

		sql = self.amount_sql.strip()
		if not sql.lower().startswith("select"):
			frappe.throw(
				"Only SELECT statements are allowed in the SQL Query field for security reasons."
			)

		try:
			result = frappe.db.sql(sql)
		except Exception as e:
			frappe.throw(f"SQL query failed: {e}")

		if not result or result[0][0] is None:
			amount = 0.0
		else:
			try:
				amount = float(result[0][0])
			except (TypeError, ValueError):
				frappe.throw(
					"The SQL query did not return a numeric value. Ensure it returns a single number."
				)

		self.amount = amount
		self.save()
		return {"amount": amount}
