import frappe
from frappe.model.document import Document
from frappe.utils import flt


class BananaDisinfectionLog(Document):

	def on_submit(self):
		self._create_material_issue()

	def on_cancel(self):
		self._cancel_material_issue()

	# ------------------------------------------------------------------

	def _create_material_issue(self):
		company = frappe.db.get_value("Warehouse", self.warehouse, "company")
		if not company:
			frappe.throw(
				f"Could not determine company from warehouse <b>{self.warehouse}</b>."
			)

		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Material Issue"
		se.posting_date = self.date
		se.posting_time = self.time
		se.company = company
		se.remarks = (
			f"Banana disinfection for Banana Grading {self.banana_grading}"
		)
		se.append("items", {
			"item_code":   self.disinfectant_item,
			"qty":         flt(self.quantity),
			"uom":         self.uom,
			"s_warehouse": self.warehouse,
		})
		se.insert()
		se.submit()
		self.db_set("stock_entry", se.name)

	def _cancel_material_issue(self):
		if not self.stock_entry:
			return
		se_doc = frappe.get_doc("Stock Entry", self.stock_entry)
		if se_doc.docstatus == 1:
			se_doc.cancel()
		self.db_set("stock_entry", None)
