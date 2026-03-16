import frappe
from frappe.model.document import Document

BOTTLES_PER_CARTON = {
	"6-Pack": 6,
	"8-Pack": 8,
	"12-Pack": 12,
	"24-Pack": 24,
}


class Packaging(Document):
	def validate(self):
		self._update_line_totals()
		self._calculate_summary()

	def _update_line_totals(self):
		for row in self.packaging_lines:
			bpc = BOTTLES_PER_CARTON.get(row.pack_size, 0)
			row.bottles_per_carton = bpc
			row.total_bottles = (row.cartons or 0) * bpc

	def _calculate_summary(self):
		self.total_bottles_packed = sum(row.total_bottles or 0 for row in self.packaging_lines)
		available = self.available_bottles or 0
		self.remaining_bottles = max(available - self.total_bottles_packed, 0)

	def on_submit(self):
		self._validate_stock()
		self._create_stock_entry()

	def _validate_stock(self):
		if self.total_bottles_packed > (self.available_bottles or 0):
			frappe.throw(
				f"Total bottles packed ({self.total_bottles_packed}) exceeds available bottles ({self.available_bottles})."
			)

	def _create_stock_entry(self):
		company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
			"Global Defaults", "default_company"
		)
		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Manufacture"
		se.posting_date = frappe.utils.today()
		se.company = company

		total_packed = self.total_bottles_packed

		# Consume bottled wine from source warehouse
		if total_packed:
			se.append(
				"items",
				{
					"item_code": self.input_item,
					"qty": total_packed,
					"s_warehouse": self.input_warehouse,
					"is_finished_item": 0,
				},
			)

		# Produce packed cartons per line
		for row in self.packaging_lines:
			if not row.output_item or not row.cartons:
				continue
			se.append(
				"items",
				{
					"item_code": row.output_item,
					"qty": row.cartons,
					"t_warehouse": row.output_warehouse or self.input_warehouse,
					"is_finished_item": 1,
				},
			)

		se.insert(ignore_permissions=True)
		se.submit()
		self.db_set("stock_entry", se.name)
