# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


class CasualPayment(Document):
	def validate(self):
		self._compute_totals()
		if flt(self.net_pay) < 0:
			frappe.throw("Net Pay cannot be negative. Deductions exceed total earnings.")

	def _compute_totals(self):
		self.total_earnings = sum(flt(r.amount) for r in self.earnings)
		self.total_deductions = sum(flt(r.amount) for r in self.deductions)
		self.net_pay = flt(self.total_earnings) - flt(self.total_deductions)

	# ------------------------------------------------------------------
	# Client-invoked actions (called via frm.call with doc=frm.doc)
	# ------------------------------------------------------------------
	@frappe.whitelist()
	def get_earnings(self):
		"""Load all submitted, unpaid earnings for the selected worker into the child table."""
		if not self.casual_worker:
			frappe.throw("Please select a Casual Worker first.")

		filters = {
			"casual_worker": self.casual_worker,
			"docstatus": 1,
			"payment_status": "Unpaid",
		}
		if self.from_date:
			filters["work_date"] = (">=", self.from_date)

		earnings = frappe.get_all(
			"Casual Worker Earning",
			filters=filters,
			fields=["name", "earning_type", "work_date", "description", "amount"],
			order_by="work_date asc",
		)
		# Apply the upper date bound separately (a single field can't hold two conditions above)
		if self.to_date:
			earnings = [e for e in earnings if str(e.work_date) <= str(self.to_date)]

		self.set("earnings", [])
		for e in earnings:
			self.append("earnings", {
				"casual_worker_earning": e.name,
				"earning_type": e.earning_type,
				"work_date": e.work_date,
				"description": e.description,
				"amount": e.amount,
			})

		self._compute_totals()
		if not earnings:
			frappe.msgprint("No unpaid earnings found for this worker in the selected range.")
		return len(earnings)

	@frappe.whitelist()
	def apply_tax_template(self):
		"""Compute deductions from the selected tax template and refresh the template rows."""
		if not self.tax_template:
			frappe.throw("Please select a Tax Template first.")

		self._compute_totals()
		gross_amount = flt(self.total_earnings)

		template = frappe.get_doc("Casual Tax Template", self.tax_template)

		# Keep manual deductions, drop previously generated template rows
		manual_rows = [r for r in self.deductions if not r.is_tax]
		self.set("deductions", [])

		running_deductions = 0.0
		for tax in template.taxes:
			value = self._evaluate_tax_row(tax, gross_amount, running_deductions)
			value = flt(value)
			if value <= 0:
				continue
			running_deductions += value
			self.append("deductions", {
				"deduction_name": tax.tax_name,
				"account": tax.account,
				"amount": value,
				"is_tax": 1,
				"description": tax.description,
			})

		# Re-append the user's manual rows after the template rows
		for r in manual_rows:
			self.append("deductions", {
				"deduction_name": r.deduction_name,
				"account": r.account,
				"amount": r.amount,
				"is_tax": 0,
				"description": r.description,
			})

		self._compute_totals()
		return self.total_deductions

	def _evaluate_tax_row(self, tax, gross_amount, total_deductions_so_far):
		calc = tax.calculation_type
		if calc == "Flat Amount":
			return flt(tax.amount)
		if calc == "On Gross Total":
			return flt(gross_amount) * flt(tax.rate) / 100.0
		if calc == "Formula":
			if not tax.formula:
				return 0.0
			context = {
				"gross_amount": flt(gross_amount),
				"total_deductions_so_far": flt(total_deductions_so_far),
				"flt": flt,
			}
			try:
				return flt(frappe.safe_eval(tax.formula, None, context))
			except Exception as e:
				frappe.throw(f"Error evaluating formula for '{tax.tax_name}': {e}")
		return 0.0

	# ------------------------------------------------------------------
	# Submission lifecycle
	# ------------------------------------------------------------------
	def on_submit(self):
		if not self.earnings:
			frappe.throw("Cannot submit a Casual Payment with no earnings.")
		self._mark_earnings_paid()
		self._create_payment_journal_entry()

	def on_cancel(self):
		self.ignore_linked_doctypes = ("GL Entry", "Journal Entry", "Payment Ledger Entry")
		self._cancel_journal_entry()
		self._mark_earnings_unpaid()

	def _mark_earnings_paid(self):
		for row in self.earnings:
			earning = frappe.get_doc("Casual Worker Earning", row.casual_worker_earning)
			if earning.payment_status == "Paid":
				frappe.throw(
					f"Earning {earning.name} has already been paid on {earning.casual_payment}."
				)
			earning.db_set("payment_status", "Paid")
			earning.db_set("casual_payment", self.name)

	def _mark_earnings_unpaid(self):
		for row in self.earnings:
			if not row.casual_worker_earning:
				continue
			if frappe.db.exists("Casual Worker Earning", row.casual_worker_earning):
				earning = frappe.get_doc("Casual Worker Earning", row.casual_worker_earning)
				earning.db_set("payment_status", "Unpaid")
				earning.db_set("casual_payment", None)

	def _create_payment_journal_entry(self):
		"""Post the payment as a single balanced Journal Entry.

		DR  Casual Labour Expense        total_earnings (gross)
		CR  <deduction account head(s)>  each deduction amount
		CR  Payment Account (Cash/Bank)  net_pay
		"""
		settings = frappe.get_cached_doc("Winery Settings")
		expense_account = settings.get("casual_labour_expense_account")
		default_tax_account = settings.get("casual_default_tax_payable_account")

		if not expense_account:
			frappe.throw(
				"Please set the Casual Labour Expense Account in Winery Settings before submitting."
			)

		je = frappe.new_doc("Journal Entry")
		je.voucher_type = "Journal Entry"
		je.posting_date = self.posting_date or today()
		je.company = self.company
		je.cheque_no = self.reference_number
		je.user_remark = f"Casual Payment {self.name} — {self.worker_name}"

		# DR gross labour expense
		je.append("accounts", {
			"account": expense_account,
			"debit_in_account_currency": flt(self.total_earnings),
		})

		# CR each deduction to its own account head
		for ded in self.deductions:
			account = ded.account or default_tax_account
			if not account:
				frappe.throw(
					f"Deduction '{ded.deduction_name}' has no account, and no default "
					"tax payable account is set in Winery Settings."
				)
			je.append("accounts", {
				"account": account,
				"credit_in_account_currency": flt(ded.amount),
			})

		# CR net pay to the cash/bank account it is disbursed from
		je.append("accounts", {
			"account": self.payment_account,
			"credit_in_account_currency": flt(self.net_pay),
		})

		je.insert(ignore_permissions=True)
		je.submit()
		self.db_set("journal_entry", je.name)

	def _cancel_journal_entry(self):
		if not self.journal_entry:
			return
		if not frappe.db.exists("Journal Entry", self.journal_entry):
			return
		je = frappe.get_doc("Journal Entry", self.journal_entry)
		if je.docstatus == 1:
			je.cancel()
		self.db_set("journal_entry", None)
