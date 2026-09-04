import frappe
from frappe.model.document import Document
from frappe.utils import flt, now_datetime


class RopenWebOrder(Document):
	def before_insert(self):
		if not self.order_token:
			self.order_token = frappe.generate_hash(length=24)
		if not self.order_date:
			self.order_date = now_datetime()

	def validate(self):
		for row in self.items:
			row.amount = flt(flt(row.rate) * flt(row.qty), 2)
		self.total = flt(sum(flt(r.amount) for r in self.items), 2)
