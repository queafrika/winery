# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class BananaGrading(Document):
	def validate(self):
		self._assign_batch_ids()
		self._compute_totals()

	def _assign_batch_ids(self):
		for idx, row in enumerate(self.batches, start=1):
			if not row.batch_id:
				row.batch_id = f"{self.name}-{idx:03d}"

	def _compute_totals(self):
		# Get invoice grand total as the base for proportional distribution
		invoice_total = 0.0
		if self.purchase_invoice:
			invoice_total = float(
				frappe.db.get_value("Purchase Invoice", self.purchase_invoice, "grand_total") or 0
			)

		# First pass: sum all fingers
		total_fingers = sum(row.fingers or 0 for row in self.batches)

		# Second pass: auto-calculate each batch's proportional amount and accumulate totals
		total_good_fingers = 0
		total_damaged_fingers = 0
		total_amount = 0.0
		total_damaged_amount = 0.0

		for row in self.batches:
			fingers = row.fingers or 0
			# Proportional share of invoice total based on finger count
			row.amount = round((fingers / total_fingers) * invoice_total, 2) if total_fingers else 0

			if row.damaged:
				total_damaged_fingers += fingers
				total_damaged_amount += row.amount
			else:
				total_good_fingers += fingers
			total_amount += row.amount

		net_usable_cost = total_amount - total_damaged_amount

		# Valuation: percentage of total invoice value carried forward for production
		valuation_pct = float(self.valuation_percentage or 100)
		valuation_amount = invoice_total * valuation_pct / 100

		self.total_fingers = total_fingers
		self.total_good_fingers = total_good_fingers
		self.total_damaged_fingers = total_damaged_fingers
		self.total_amount = total_amount
		self.total_damaged_amount = total_damaged_amount
		self.net_usable_cost = net_usable_cost
		self.valuation_amount = valuation_amount
		# Cost per finger: valuation amount spread across ALL fingers
		self.cost_per_finger_carried_forward = (
			valuation_amount / total_fingers if total_fingers else 0
		)

	def on_submit(self):
		self._create_erpnext_batches()
		self._create_purchase_receipt()

	def on_cancel(self):
		if self.purchase_receipt:
			pr = frappe.get_doc("Purchase Receipt", self.purchase_receipt)
			if pr.docstatus == 1:
				pr.cancel()
			self.db_set("purchase_receipt", None)

	def _create_erpnext_batches(self):
		for row in self.batches:
			if not frappe.db.exists("Batch", row.batch_id):
				batch = frappe.new_doc("Batch")
				batch.item = self.banana_item
				batch.batch_id = row.batch_id
				batch.insert(ignore_permissions=True)
			# Stamp grading info onto the ERPNext batch
			frappe.db.set_value("Batch", row.batch_id, {
				"is_damaged": 1 if row.damaged else 0,
				"banana_grade": row.quality_grade or "",
			})

	def _create_purchase_receipt(self):
		supplier = None
		if self.purchase_invoice:
			supplier = frappe.db.get_value("Purchase Invoice", self.purchase_invoice, "supplier")
		if not supplier and self.farmer:
			supplier = frappe.db.get_value("Farmer", self.farmer, "supplier")
		if not supplier:
			frappe.throw(
				"Cannot create Purchase Receipt: no Supplier found. "
				"Link a Purchase Invoice or ensure the Farmer has a linked Supplier."
			)

		rejected_warehouse = self.damaged_warehouse or self.warehouse

		pr = frappe.new_doc("Purchase Receipt")
		pr.supplier = supplier
		pr.posting_date = self.procurement_date
		# Link to existing Purchase Invoice so ERPNext knows it is already billed
		if self.purchase_invoice:
			pr.bill_no = self.purchase_invoice
			pr.bill_date = self.procurement_date

		for row in self.batches:
			fingers = row.fingers or 0
			rate = (row.amount / fingers) if fingers else 0

			if row.damaged:
				pr.append("items", {
					"item_code": self.banana_item,
					"qty": 0,
					"rejected_qty": fingers,
					"rate": rate,
					"uom": "Nos",
					"rejected_uom": "Nos",
					"warehouse": self.warehouse,
					"rejected_warehouse": rejected_warehouse,
					"batch_no": row.batch_id,
					"description": f"Damaged — {row.batch_id}",
				})
			else:
				pr.append("items", {
					"item_code": self.banana_item,
					"qty": fingers,
					"rate": rate,
					"uom": "Nos",
					"warehouse": self.warehouse,
					"batch_no": row.batch_id,
					"description": f"Good — {row.batch_id}",
				})

		pr.insert(ignore_permissions=True)
		pr.submit()

		# Mark PR as fully billed — invoice was already created before receipt
		for item in pr.items:
			frappe.db.set_value(
				"Purchase Receipt Item", item.name, "billed_amt", item.amount
			)
		frappe.db.set_value("Purchase Receipt", pr.name, "per_billed", 100)

		self.db_set("purchase_receipt", pr.name)
		frappe.msgprint(f"Purchase Receipt {pr.name} created.", alert=True)


@frappe.whitelist()
def get_invoice_prefill(purchase_invoice):
	"""Return pre-fill data for a new Banana Grading from a Purchase Invoice."""
	# Check if one already exists
	existing = frappe.db.get_value("Banana Grading", {"purchase_invoice": purchase_invoice})
	if existing:
		return {"existing": existing}

	pi = frappe.get_doc("Purchase Invoice", purchase_invoice)
	farmer = frappe.db.get_value("Farmer", {"supplier": pi.supplier}, "name")

	return {
		"purchase_invoice": purchase_invoice,
		"procurement_date": str(pi.posting_date),
		"farmer": farmer or "",
	}
