# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.model.document import Document
from frappe.utils import add_months, get_first_day, get_last_day, getdate, today


_STATUS_COLORS = {
	"Active": "#27ae60",
	"Pending Renewal": "#e67e22",
	"Expired": "#e74c3c",
	"Suspended": "#f39c12",
	"Cancelled": "#bdc3c7",
}


class ComplianceLicense(Document):
	def validate(self):
		self._auto_expire()
		self._reset_reminders_on_expiry_change()
		self.calendar_color = _STATUS_COLORS.get(self.status, "#3498db")

	def _auto_expire(self):
		if self.expiry_date and self.status in ("Active", "Pending Renewal"):
			if getdate(self.expiry_date) < getdate(today()):
				self.status = "Expired"

	def _reset_reminders_on_expiry_change(self):
		"""Reset reminder_sent flags when expiry_date is changed."""
		prev = self.get_doc_before_save()
		if prev and str(prev.expiry_date) != str(self.expiry_date):
			for rule in self.reminder_rules:
				rule.reminder_sent = 0

	@frappe.whitelist()
	def calculate_amount(self):
		"""Calculate amount by querying the configured doctype over the auto-derived period."""
		if not self.compliance_type:
			frappe.throw("Please set a Compliance Type before calculating the amount.")

		ct = frappe.get_doc("Compliance Type", self.compliance_type)

		if ct.amount_source != "Query":
			frappe.throw("Amount Source on the Compliance Type is not set to 'Query'.")
		if not self.expiry_date:
			frappe.throw("Expiry / Due Date is required to calculate the period.")
		if not self.payment_frequency:
			frappe.throw("Payment Frequency is required to calculate the period.")

		period_start, period_end = _get_period_dates(self.expiry_date, self.payment_frequency)

		# Build filters list
		filters = [[ct.query_date_field, "between", [str(period_start), str(period_end)]]]
		if ct.query_submitted_only:
			filters.append(["docstatus", "=", 1])
		if ct.query_extra_filters:
			try:
				extra = json.loads(ct.query_extra_filters)
				filters.extend(extra)
			except Exception:
				frappe.throw("Extra Filters JSON in Compliance Type is not valid JSON.")

		# Build WHERE clause
		conditions = []
		values = []
		for f in filters:
			field, op, val = f[0], f[1], f[2]
			if op.lower() == "between":
				conditions.append(f"`{field}` BETWEEN %s AND %s")
				values.extend(val)
			elif op == "=":
				conditions.append(f"`{field}` = %s")
				values.append(val)
			elif op == "!=":
				conditions.append(f"`{field}` != %s")
				values.append(val)
			elif op.lower() == "in":
				placeholders = ", ".join(["%s"] * len(val))
				conditions.append(f"`{field}` IN ({placeholders})")
				values.extend(val)

		where_clause = " AND ".join(conditions)
		table = f"`tab{ct.query_doctype}`"
		sql = f"SELECT COALESCE(SUM(`{ct.query_amount_field}`), 0) FROM {table} WHERE {where_clause}"

		result = frappe.db.sql(sql, values)
		calculated = result[0][0] if result else 0

		self.amount = calculated
		self.calculated_period = (
			f"{frappe.utils.formatdate(str(period_start))} – {frappe.utils.formatdate(str(period_end))}"
		)
		self.save()
		return {"amount": calculated, "period": self.calculated_period}


def _get_period_dates(expiry_date, frequency):
	"""Return (period_start, period_end) derived from expiry_date and payment frequency."""
	expiry = getdate(expiry_date)

	if frequency == "Monthly":
		period_start = get_first_day(expiry)
		period_end = expiry

	elif frequency == "Quarterly":
		# First month of the quarter containing expiry_date
		quarter_start_month = ((expiry.month - 1) // 3) * 3 + 1
		period_start = expiry.replace(month=quarter_start_month, day=1)
		period_end = expiry

	elif frequency == "Semi-Annual":
		# First month of the half-year
		half_start_month = 1 if expiry.month <= 6 else 7
		period_start = expiry.replace(month=half_start_month, day=1)
		period_end = expiry

	elif frequency == "Annual":
		period_start = expiry.replace(month=1, day=1)
		period_end = expiry

	else:
		# One-time or unrecognised — use full year
		period_start = expiry.replace(month=1, day=1)
		period_end = expiry

	return period_start, period_end
