# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class BananaGrading(Document):

	def validate(self):
		if self.agent_delivery_receipt:
			self._resolve_raw_finger_items()
			self._assign_grading_batch_ids()
			self._compute_grading_item_totals()
			self._compute_adr_totals()
		else:
			# PI-mode: enforce fields that are no longer reqd in the JSON
			if not self.banana_item:
				frappe.throw("Grading Item is required.")
			if not self.warehouse:
				frappe.throw("Accepted Warehouse is required.")
			self._assign_batch_ids()
			self._compute_totals()

	def on_submit(self):
		if self.agent_delivery_receipt:
			self._create_grading_batches_for_adr()
			self._create_repack_stock_entry()
			frappe.db.set_value(
				"Agent Delivery Receipt", self.agent_delivery_receipt, "status", "Graded"
			)
		else:
			self._create_erpnext_batches()
			self._create_purchase_receipt()

	def on_cancel(self):
		if self.agent_delivery_receipt:
			self._cancel_repack_stock_entry()
			frappe.db.set_value(
				"Agent Delivery Receipt", self.agent_delivery_receipt, "status", "Received"
			)
		else:
			if self.purchase_receipt:
				pr = frappe.get_doc("Purchase Receipt", self.purchase_receipt)
				if pr.docstatus == 1:
					pr.cancel()
				self.db_set("purchase_receipt", None)

	# ------------------------------------------------------------------
	# ADR-mode helpers
	# ------------------------------------------------------------------

	def _resolve_raw_finger_items(self):
		raw_tpl = frappe.db.get_single_value("Winery Settings", "raw_banana_finger_template")
		if not raw_tpl:
			frappe.throw(
				"Please set <b>Raw Banana Finger Template Item</b> in Winery Settings "
				"before grading."
			)
		for row in self.grading_items:
			if not row.raw_finger_item and row.banana_item:
				row.raw_finger_item = _find_matching_raw_finger_variant(row.banana_item, raw_tpl)
				if not row.raw_finger_item:
					frappe.throw(
						f"Row {row.idx}: Cannot find a Raw Banana Finger variant matching "
						f"<b>{row.banana_item}</b>. Ensure matching variants exist under "
						f"the Raw Banana Finger template in Winery Settings."
					)

	def _assign_grading_batch_ids(self):
		date_str = str(self.procurement_date).replace("-", "")
		for row in self.grading_items:
			farm = (row.farm or "").replace(" ", "-")
			variety = (
				frappe.db.get_value(
					"Item Variant Attribute",
					{"parent": row.raw_finger_item},
					"attribute_value",
				)
				if row.raw_finger_item
				else str(row.idx)
			)
			base = f"{date_str}-{farm}-{variety}" if farm else f"{date_str}-{variety}"
			for attr, suffix in [
				("grade_a_batch", "A"),
				("grade_b_batch", "B"),
				("grade_c_batch", "C"),
				("damaged_batch", "Damaged"),
			]:
				if not getattr(row, attr):
					candidate = f"{base}-{suffix}"
					if frappe.db.exists("Batch", candidate):
						counter = 2
						while frappe.db.exists("Batch", f"{base}-{suffix}-{counter}"):
							counter += 1
						candidate = f"{base}-{suffix}-{counter}"
					setattr(row, attr, candidate)

	def _compute_grading_item_totals(self):
		for row in self.grading_items:
			row.total_fingers = (
				flt(row.grade_a_qty)
				+ flt(row.grade_b_qty)
				+ flt(row.grade_c_qty)
				+ flt(row.damaged_qty)
			)

	def _compute_adr_totals(self):
		adr = frappe.get_doc("Agent Delivery Receipt", self.agent_delivery_receipt)
		total_received = flt(adr.total_received) or 1  # avoid div/0
		adr_total_amount = flt(adr.total_amount)

		for row in self.grading_items:
			row.valuation_amount = (
				flt(row.bunches_received) / total_received
			) * adr_total_amount
			row.cost_per_finger = (
				row.valuation_amount / flt(row.total_fingers)
				if row.total_fingers else 0
			)

		self.total_fingers = int(sum(flt(r.total_fingers) for r in self.grading_items))
		self.total_good_fingers = int(
			sum(flt(r.grade_a_qty) + flt(r.grade_b_qty) + flt(r.grade_c_qty)
				for r in self.grading_items)
		)
		self.total_damaged_fingers = int(
			sum(flt(r.damaged_qty) for r in self.grading_items)
		)
		self.total_amount = adr_total_amount
		self.cost_per_finger_carried_forward = (
			adr_total_amount / self.total_fingers if self.total_fingers else 0
		)

	def _create_grading_batches_for_adr(self):
		# Look up the most recent submitted disinfection log for this grading
		disinfection_log = frappe.db.get_value(
			"Banana Disinfection Log",
			{"banana_grading": self.name, "docstatus": 1},
			["name", "date", "time"],
			as_dict=True,
			order_by="creation desc",
		)

		for row in self.grading_items:
			if not row.raw_finger_item:
				frappe.throw(
					f"Row {row.idx}: Raw Finger Item is not set. "
					"Save the document first so the system can resolve it."
				)
			for batch_id, qty, grade_name, is_damaged in [
				(row.grade_a_batch, row.grade_a_qty, "Grade A", 0),
				(row.grade_b_batch, row.grade_b_qty, "Grade B", 0),
				(row.grade_c_batch, row.grade_c_qty, "Grade C", 0),
				(row.damaged_batch,  row.damaged_qty, None,      1),
			]:
				if flt(qty) > 0 and not frappe.db.exists("Batch", batch_id):
					batch = frappe.new_doc("Batch")
					batch.item = row.raw_finger_item
					batch.batch_id = batch_id
					batch.banana_grade = grade_name
					batch.is_damaged = is_damaged
					batch.farm = row.farm or ""
					if disinfection_log:
						batch.disinfection_log  = disinfection_log.name
						batch.disinfection_date = disinfection_log.date
						batch.disinfection_time = disinfection_log.time
					batch.insert(ignore_permissions=True)

	def _create_repack_stock_entry(self):
		if not self.source_warehouse:
			frappe.throw(
				"<b>Source Warehouse</b> is required to create the Repack Stock Entry."
			)
		if not self.target_warehouse:
			frappe.throw(
				"<b>Accepted Warehouse</b> is required to create the Repack Stock Entry."
			)

		company = frappe.db.get_value("Warehouse", self.source_warehouse, "company")
		damaged_wh = self.damaged_warehouse or self.target_warehouse

		se = frappe.new_doc("Stock Entry")
		se.purpose = "Repack"
		se.stock_entry_type = "Repack"
		se.posting_date = self.procurement_date
		se.company = company
		se.remarks = (
			f"Grading repack for {self.name} / ADR {self.agent_delivery_receipt}"
		)

		for row in self.grading_items:
			# Source: banana bunches consumed
			if flt(row.bunches_received) > 0:
				se.append("items", {
					"item_code":   row.banana_item,
					"qty":         flt(row.bunches_received),
					"s_warehouse": self.source_warehouse,
				})
			# Targets: graded raw fingers produced.
			# basic_rate is set per variety (cost_per_finger) and flagged manual
			# so ERPNext does not blend rates across multiple finished-good items.
			cost_per_finger = flt(row.cost_per_finger)
			for batch_id, qty, wh in [
				(row.grade_a_batch, row.grade_a_qty, self.target_warehouse),
				(row.grade_b_batch, row.grade_b_qty, self.target_warehouse),
				(row.grade_c_batch, row.grade_c_qty, self.target_warehouse),
				(row.damaged_batch, row.damaged_qty, damaged_wh),
			]:
				if flt(qty) > 0:
					se.append("items", {
						"item_code":               row.raw_finger_item,
						"qty":                     flt(qty),
						"t_warehouse":             wh,
						"batch_no":                batch_id,
						"basic_rate":              cost_per_finger,
						"set_basic_rate_manually": 1,
					})

		has_output = any(i.get("t_warehouse") for i in se.items)
		if not has_output:
			frappe.throw(
				"No graded quantities found. "
				"Enter at least one grade quantity before submitting."
			)

		se.insert()
		se.submit()
		self.db_set("stock_entry", se.name)

	def _cancel_repack_stock_entry(self):
		if not self.stock_entry:
			return
		se = frappe.get_doc("Stock Entry", self.stock_entry)
		if se.docstatus == 1:
			se.cancel()
		self.db_set("stock_entry", None)

	# ------------------------------------------------------------------
	# PI-mode helpers (unchanged)
	# ------------------------------------------------------------------

	def _assign_batch_ids(self):
		for idx, row in enumerate(self.batches, start=1):
			if not row.batch_id:
				row.batch_id = f"{self.name}-{idx:03d}"

	def _compute_totals(self):
		invoice_total = 0.0
		if self.purchase_invoice:
			invoice_total = float(
				frappe.db.get_value("Purchase Invoice", self.purchase_invoice, "grand_total") or 0
			)

		total_fingers = sum(row.fingers or 0 for row in self.batches)

		total_good_fingers = 0
		total_damaged_fingers = 0
		total_amount = 0.0
		total_damaged_amount = 0.0

		for row in self.batches:
			fingers = row.fingers or 0
			row.amount = round((fingers / total_fingers) * invoice_total, 2) if total_fingers else 0

			if row.damaged:
				total_damaged_fingers += fingers
				total_damaged_amount += row.amount
			else:
				total_good_fingers += fingers
			total_amount += row.amount

		net_usable_cost = total_amount - total_damaged_amount
		valuation_pct = float(self.valuation_percentage or 100)
		valuation_amount = invoice_total * valuation_pct / 100

		self.total_fingers = total_fingers
		self.total_good_fingers = total_good_fingers
		self.total_damaged_fingers = total_damaged_fingers
		self.total_amount = total_amount
		self.total_damaged_amount = total_damaged_amount
		self.net_usable_cost = net_usable_cost
		self.valuation_amount = valuation_amount
		self.cost_per_finger_carried_forward = (
			valuation_amount / total_fingers if total_fingers else 0
		)

	def _create_erpnext_batches(self):
		for row in self.batches:
			if not frappe.db.exists("Batch", row.batch_id):
				batch = frappe.new_doc("Batch")
				batch.item = self.banana_item
				batch.batch_id = row.batch_id
				batch.insert(ignore_permissions=True)
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
		if self.purchase_invoice:
			pr.bill_no = self.purchase_invoice
			pr.bill_date = self.procurement_date

		for row in self.batches:
			fingers = row.fingers or 0
			rate = (row.amount / fingers) if fingers else 0

			if row.damaged:
				pr.append("items", {
					"item_code":          self.banana_item,
					"qty":                0,
					"rejected_qty":       fingers,
					"rate":               rate,
					"uom":                "Nos",
					"rejected_uom":       "Nos",
					"warehouse":          self.warehouse,
					"rejected_warehouse": rejected_warehouse,
					"batch_no":           row.batch_id,
					"description":        f"Damaged — {row.batch_id}",
				})
			else:
				pr.append("items", {
					"item_code":  self.banana_item,
					"qty":        fingers,
					"rate":       rate,
					"uom":        "Nos",
					"warehouse":  self.warehouse,
					"batch_no":   row.batch_id,
					"description": f"Good — {row.batch_id}",
				})

		pr.insert(ignore_permissions=True)
		pr.submit()

		for item in pr.items:
			frappe.db.set_value("Purchase Receipt Item", item.name, "billed_amt", item.amount)
		frappe.db.set_value("Purchase Receipt", pr.name, "per_billed", 100)

		self.db_set("purchase_receipt", pr.name)
		frappe.msgprint(f"Purchase Receipt {pr.name} created.", alert=True)


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _find_matching_raw_finger_variant(banana_item, raw_template):
	"""Return the Raw Banana Finger variant whose variant attributes match banana_item."""
	bunch_attrs = {
		a.attribute: a.attribute_value
		for a in frappe.db.get_all(
			"Item Variant Attribute",
			filters={"parent": banana_item},
			fields=["attribute", "attribute_value"],
		)
	}
	if not bunch_attrs:
		return None

	candidates = frappe.db.get_all(
		"Item",
		filters={"variant_of": raw_template, "disabled": 0},
		fields=["name"],
	)
	for c in candidates:
		cand_attrs = {
			a.attribute: a.attribute_value
			for a in frappe.db.get_all(
				"Item Variant Attribute",
				filters={"parent": c.name},
				fields=["attribute", "attribute_value"],
			)
		}
		if all(cand_attrs.get(k) == v for k, v in bunch_attrs.items()):
			return c.name
	return None


@frappe.whitelist()
def get_adr_grading(adr_name):
	"""Return the Banana Grading name linked to this ADR, or None."""
	return (
		frappe.db.get_value("Banana Grading", {"agent_delivery_receipt": adr_name}, "name")
		or None
	)


@frappe.whitelist()
def get_adr_items_for_grading(adr_name):
	"""Return rows grouped by (farm, item_code) for full farm traceability.

	Farm is sourced from the custom_farm field on each Purchase Invoice so
	that bananas from different farms of the same variety produce separate
	grading rows and distinct output batches.
	"""
	adr = frappe.get_doc("Agent Delivery Receipt", adr_name)

	# Build PI → farm lookup (custom_farm field on Purchase Invoice)
	pi_names = list({row.purchase_invoice for row in adr.items if row.purchase_invoice})
	farm_map = {
		pi: frappe.db.get_value("Purchase Invoice", pi, "custom_farm") or ""
		for pi in pi_names
	}

	# Aggregate received_qty by (farm, item_code)
	key_map = {}
	for row in adr.items:
		farm = farm_map.get(row.purchase_invoice, "")
		key = (farm, row.item_code)
		if key not in key_map:
			key_map[key] = {
				"item_name": row.item_name,
				"bunches_received": 0.0,
				"farm": farm,
			}
		key_map[key]["bunches_received"] += flt(row.received_qty)

	return [
		{
			"banana_item": item_code,
			"item_name": v["item_name"],
			"bunches_received": v["bunches_received"],
			"farm": v["farm"],
		}
		for (farm, item_code), v in key_map.items()
	]


@frappe.whitelist()
def get_invoice_prefill(purchase_invoice):
	"""Return pre-fill data for a new Banana Grading from a Purchase Invoice."""
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
