# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ComplianceType(Document):
	def validate(self):
		for task in self.tasks:
			if task.task_type == "Payment":
				if not task.amount_source:
					frappe.throw(
						f"Task '{task.task_name}': Amount Source is required for Payment tasks."
					)
				if task.amount_source == "Fixed" and not task.fixed_amount:
					frappe.throw(
						f"Task '{task.task_name}': Fixed Amount is required when Amount Source is Fixed."
					)
				if task.amount_source == "SQL Query" and not task.amount_sql:
					frappe.throw(
						f"Task '{task.task_name}': SQL Query is required when Amount Source is SQL Query."
					)
			if task.is_recurring:
				if not task.frequency:
					frappe.throw(
						f"Task '{task.task_name}': Frequency is required for recurring tasks."
					)
				if not task.day_of_month:
					frappe.throw(
						f"Task '{task.task_name}': Day of Month is required for recurring tasks."
					)
				if not (1 <= task.day_of_month <= 28):
					frappe.throw(
						f"Task '{task.task_name}': Day of Month must be between 1 and 28."
					)
