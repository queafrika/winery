import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class WineryPOSDayClose(Document):
	def validate(self):
		self._compute_variance()

	def before_submit(self):
		# Guard against two closes for the same agent/day (excluding cancelled).
		existing = frappe.db.exists(
			"Winery POS Day Close",
			{
				"sales_agent": self.sales_agent,
				"close_date": self.close_date,
				"docstatus": 1,
				"name": ["!=", self.name],
			},
		)
		if existing:
			frappe.throw(
				_("A day close already exists for {0} on {1}.").format(
					self.sales_agent, self.close_date
				)
			)

	def _compute_variance(self):
		self.cash_variance = flt(self.declared_cash) - flt(self.system_cash)
