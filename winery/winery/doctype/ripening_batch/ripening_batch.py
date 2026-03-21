# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.model.document import Document
from frappe.utils import add_days, date_diff


class RipeningBatch(Document):

	def validate(self):
		self._populate_batch_details()
		self._compute_totals()
		self._compute_material_costs()
		self._validate_fingers()
		self._compute_expected_end_date()

	def _populate_batch_details(self):
		for row in self.banana_grading_batches:
			if row.batch_no and row.banana_grading:
				data = frappe.db.get_value(
					"Banana Grading Batch",
					{"batch_id": row.batch_no, "parent": row.banana_grading},
					["fingers", "quality_grade"],
					as_dict=True,
				)
				if data:
					row.available_fingers = data.fingers
					row.quality_grade = data.quality_grade

	def _compute_totals(self):
		self.total_fingers_ripening = sum(
			row.fingers_for_ripening or 0 for row in self.banana_grading_batches
		)

	def _compute_material_costs(self):
		"""Estimate material cost using current stock valuation rates."""
		total = 0
		for row in self.ripening_materials:
			if row.additive and row.warehouse:
				rate = _get_valuation_rate(row.additive, row.warehouse)
				total += (row.quantity or 0) * rate
		self.total_materials_cost = total

	def _validate_fingers(self):
		for row in self.banana_grading_batches:
			available = row.available_fingers or 0
			going = row.fingers_for_ripening or 0
			if not going:
				frappe.throw(f"Batch <b>{row.batch_no}</b>: Fingers for Ripening cannot be zero.")
			if available and going > available:
				frappe.throw(
					f"Batch <b>{row.batch_no}</b>: fingers for ripening ({going}) "
					f"exceed available fingers ({available})."
				)

	def _compute_expected_end_date(self):
		if self.start_date and self.ripening_days:
			self.expected_end_date = add_days(self.start_date, self.ripening_days)

	# ------------------------------------------------------------------ #
	#  Submit / Cancel                                                     #
	# ------------------------------------------------------------------ #

	def on_submit(self):
		self._validate_rack_warehouse()
		self._create_banana_transfer()
		# Freeze the original total so material apportioning stays correct across partial transfers
		self.db_set("total_original_fingers", self.total_fingers_ripening)
		frappe.db.set_value("Ripening Rack", self.rack, "status", "In Use")
		self._stamp_batches_ripening_start()

	def _stamp_batches_ripening_start(self):
		"""Set ripening tracking fields on each ERPNext Batch when ripening starts."""
		for row in self.banana_grading_batches:
			if row.batch_no:
				frappe.db.set_value("Batch", row.batch_no, {
					"ripening_status": "In Ripening",
					"ripening_start_date": self.start_date,
					"ripening_batch_ref": self.name,
				})

	def on_cancel(self):
		self._cancel_entry("stock_entry")
		frappe.db.set_value("Ripening Rack", self.rack, "status", "Available")

	def _cancel_entry(self, field):
		name = self.get(field)
		if not name:
			return
		se = frappe.get_doc("Stock Entry", name)
		if se.docstatus == 1:
			se.cancel()
		self.db_set(field, None)

	def _validate_rack_warehouse(self):
		rack_warehouse = frappe.db.get_value("Ripening Rack", self.rack, "warehouse")
		if not rack_warehouse:
			frappe.throw(
				f"Ripening Rack <b>{self.rack}</b> does not have a Warehouse configured. "
				"Please set it on the Ripening Rack before submitting."
			)

	def _create_banana_transfer(self):
		"""SE 1 — Transfer raw bananas from source warehouse into the rack warehouse."""
		rack_warehouse = frappe.db.get_value("Ripening Rack", self.rack, "warehouse")

		se = frappe.new_doc("Stock Entry")
		se.purpose = "Material Transfer"
		se.stock_entry_type = "Material Transfer"
		se.posting_date = self.start_date
		se.use_serial_batch_fields = 1

		for row in self.banana_grading_batches:
			fingers = row.fingers_for_ripening or 0
			if fingers:
				se.append("items", {
					"item_code": self.banana_item,
					"qty": fingers,
					"uom": "Nos",
					"s_warehouse": self.source_warehouse,
					"t_warehouse": rack_warehouse,
					"batch_no": row.batch_no,
				})

		se.insert(ignore_permissions=True)
		# se.submit()
		self.db_set("stock_entry", se.name)
		frappe.msgprint(f"Stock Entry <b>{se.name}</b> — bananas transferred to rack.", alert=True)


# --------------------------------------------------------------------------- #
#  Whitelisted helpers                                                         #
# --------------------------------------------------------------------------- #

@frappe.whitelist()
def get_grading_batch_details(banana_grading, batch_no):
	"""Fetch child-table row details without triggering client-side permission check."""
	return frappe.db.get_value(
		"Banana Grading Batch",
		{"batch_id": batch_no, "parent": banana_grading},
		["fingers", "quality_grade"],
		as_dict=True,
	)


@frappe.whitelist()
def get_batch_quantities_in_rack(ripening_batch):
	"""Return current stock per batch for this item in the rack warehouse."""
	rb = frappe.get_doc("Ripening Batch", ripening_batch)
	rack_warehouse = frappe.db.get_value("Ripening Rack", rb.rack, "warehouse")
	if not rack_warehouse:
		frappe.throw(f"Rack <b>{rb.rack}</b> does not have a warehouse configured.")

	rows = frappe.db.sql(
		"""
		SELECT
			COALESCE(batch_no, '') AS batch_no,
			SUM(actual_qty)        AS qty
		FROM `tabStock Ledger Entry`
		WHERE item_code    = %s
		  AND warehouse    = %s
		  AND is_cancelled = 0
		GROUP BY batch_no
		HAVING SUM(actual_qty) > 0
		""",
		(rb.banana_item, rack_warehouse),
		as_dict=True,
	)

	if not rows:
		se_name = rb.stock_entry or "none"
		frappe.throw(
			f"No stock of <b>{rb.banana_item}</b> found in rack warehouse "
			f"<b>{rack_warehouse}</b>.<br><br>"
			f"Banana Transfer Entry: <b>{se_name}</b>.<br>"
			"Please verify the stock entry is submitted and the item has stock in the rack."
		)

	grade_map = {row.batch_no: row.quality_grade for row in rb.banana_grading_batches}

	return {
		"rack_warehouse": rack_warehouse,
		"batches": [
			{
				"batch_no": r.batch_no,
				"fingers_in_rack": int(r.qty),
				"quality_grade": grade_map.get(r.batch_no, ""),
			}
			for r in rows
		],
	}


@frappe.whitelist()
def end_ripening(ripening_batch, ripe_item, destination_warehouse, end_date, transfers):
	"""
	ONE Repack Stock Entry per End Ripening call.

	Sources:
	  - Each banana batch being transferred (full current qty consumed from rack)
	  - Ripening materials apportioned by: fingers_transferred / total_original_fingers
	    → their cost flows directly into the ripe banana valuation rate in ERPNext

	Targets:
	  - Ripe bananas → destination warehouse (new RIPE batch per source batch)
	  - Remaining raw bananas → back to rack under new STAY batch (splits only)
	"""
	if isinstance(transfers, str):
		transfers = json.loads(transfers)

	rb = frappe.get_doc("Ripening Batch", ripening_batch)
	rack_warehouse = frappe.db.get_value("Ripening Rack", rb.rack, "warehouse")
	ripening_days = date_diff(end_date, rb.start_date)

	# Material apportioning ratio based on frozen original total
	total_original = rb.total_original_fingers or rb.total_fingers_ripening or 1
	total_transferring = sum(int(t.get("fingers_to_transfer") or 0) for t in transfers)
	material_ratio = min(total_transferring / total_original, 1.0)

	# ONE Repack SE for this entire call
	se = frappe.new_doc("Stock Entry")
	se.purpose = "Repack"
	se.stock_entry_type = "Repack"
	se.posting_date = end_date
	se.remarks = f"End ripening for {ripening_batch}"
	se.use_serial_batch_fields = 1

	batch_updates = []   # (old_batch_no, remain_batch_id, fingers_to_keep)
	ripe_batch_map = {}  # batch_no → ripe_batch_id  (fix: avoid double _unique_batch_id call)

	for t in transfers:
		batch_no = t.get("batch_no")
		fingers_to_transfer = int(t.get("fingers_to_transfer") or 0)
		fingers_in_rack = int(t.get("fingers_in_rack") or 0)

		if fingers_to_transfer <= 0:
			continue

		fingers_to_keep = fingers_in_rack - fingers_to_transfer
		is_split = fingers_to_keep > 0

		# Fetch source batch info to copy to ripe batch
		source_batch_info = frappe.db.get_value(
			"Batch", batch_no, ["banana_grade", "is_damaged"], as_dict=True
		) or {}

		# Create ripe ERPNext batch — meaningful ID: {source}-RIPE (e.g. BG-2026-001-RIPE)
		ripe_batch_id = _unique_batch_id(batch_no, "RIPE")
		ripe_batch_map[batch_no] = ripe_batch_id   # store for stamping later

		ripe_batch = frappe.new_doc("Batch")
		ripe_batch.item = ripe_item
		ripe_batch.batch_id = ripe_batch_id
		ripe_batch.description = (
			f"Ripened from {batch_no} | {ripening_days} days | "
			f"{rb.start_date} → {end_date}"
		)
		# Copy grading info from source batch
		ripe_batch.banana_grade = source_batch_info.get("banana_grade") or ""
		ripe_batch.is_damaged = 0  # ripe bananas are never damaged
		ripe_batch.insert(ignore_permissions=True)

		# Create STAY batch for the remaining portion (split only)
		remain_batch_id = None
		if is_split:
			remain_batch_id = _unique_batch_id(batch_no, "STAY")
			remain_batch = frappe.new_doc("Batch")
			remain_batch.item = rb.banana_item
			remain_batch.batch_id = remain_batch_id
			remain_batch.description = (
				f"Remaining from {batch_no} — partial transfer on {end_date} "
				f"({ripening_days} days ripened so far)"
			)
			remain_batch.banana_grade = source_batch_info.get("banana_grade") or ""
			remain_batch.is_damaged = source_batch_info.get("is_damaged") or 0
			remain_batch.insert(ignore_permissions=True)
			batch_updates.append((batch_no, remain_batch_id, fingers_to_keep))

		# SOURCE: consume the full current batch qty from rack
		se.append("items", {
			"item_code": rb.banana_item,
			"qty": fingers_in_rack,
			"uom": "Nos",
			"s_warehouse": rack_warehouse,
			"batch_no": batch_no,
		})

		# TARGET: ripe bananas → destination
		se.append("items", {
			"item_code": ripe_item,
			"qty": fingers_to_transfer,
			"uom": "Nos",
			"t_warehouse": destination_warehouse,
			"batch_no": ripe_batch_id,
		})

		# TARGET: remaining raw bananas → back to rack under new STAY batch
		if is_split:
			se.append("items", {
				"item_code": rb.banana_item,
				"qty": fingers_to_keep,
				"uom": "Nos",
				"t_warehouse": rack_warehouse,
				"batch_no": remain_batch_id,
			})

	# SOURCE: apportioned ripening materials — cost flows into ripe banana valuation
	for mat in rb.ripening_materials:
		apportioned_qty = round((mat.quantity or 0) * material_ratio, 6)
		if apportioned_qty > 0 and mat.additive and mat.warehouse:
			se.append("items", {
				"item_code": mat.additive,
				"qty": apportioned_qty,
				"uom": mat.uom,
				"s_warehouse": mat.warehouse,
			})

	if not any(i.t_warehouse for i in se.items):
		frappe.throw("No fingers to transfer — please enter at least one transfer quantity.")

	se.insert(ignore_permissions=True)
	se.submit()

	# Update child table batch_no for split batches
	for old_batch_no, remain_batch_id, fingers_to_keep in batch_updates:
		for row in rb.banana_grading_batches:
			if row.batch_no == old_batch_no:
				row.db_set("batch_no", remain_batch_id)
				row.db_set("fingers_for_ripening", fingers_to_keep)
				break

	rb.db_set("actual_end_date", end_date)
	rb.db_set("ripening_days", ripening_days)

	# Stamp source and ripe batches with tracking info — use ripe_batch_map (no double call bug)
	for t in transfers:
		batch_no = t.get("batch_no")
		fingers_to_transfer = int(t.get("fingers_to_transfer") or 0)
		if not fingers_to_transfer or not batch_no:
			continue

		# Mark source batch as ripening complete
		frappe.db.set_value("Batch", batch_no, {
			"ripening_status": "Ripening Complete",
			"ripening_end_date": end_date,
			"ripening_days_actual": ripening_days,
		})

		# Stamp the ripe batch — use the stored ID, NOT a second _unique_batch_id call
		ripe_id = ripe_batch_map.get(batch_no)
		if ripe_id and frappe.db.exists("Batch", ripe_id):
			frappe.db.set_value("Batch", ripe_id, {
				"ripening_status": "Ripening Complete",
				"ripening_start_date": rb.start_date,
				"ripening_end_date": end_date,
				"ripening_days_actual": ripening_days,
				"ripening_batch_ref": ripening_batch,
			})

	frappe.msgprint(f"Transfer complete — Repack Stock Entry: <b>{se.name}</b>", alert=True)
	return {"stock_entries": [se.name]}


# --------------------------------------------------------------------------- #
#  Internal helpers                                                            #
# --------------------------------------------------------------------------- #

def _get_batch_qty_in_warehouse(item_code, warehouse, batch_no):
	result = frappe.db.sql(
		"""
		SELECT SUM(actual_qty)
		FROM `tabStock Ledger Entry`
		WHERE item_code = %s AND warehouse = %s AND batch_no = %s AND is_cancelled = 0
		""",
		(item_code, warehouse, batch_no),
	)
	return (result[0][0] or 0) if result else 0


def _get_valuation_rate(item_code, warehouse):
	"""Get the most recent valuation rate for an item in a warehouse from the SLE."""
	result = frappe.db.sql(
		"""
		SELECT valuation_rate
		FROM `tabStock Ledger Entry`
		WHERE item_code    = %s
		  AND warehouse    = %s
		  AND is_cancelled = 0
		ORDER BY posting_date DESC, posting_time DESC, creation DESC
		LIMIT 1
		""",
		(item_code, warehouse),
	)
	return (result[0][0] or 0) if result else 0


def _unique_batch_id(source_batch, suffix):
	"""
	Return a unique batch ID: {source}-{suffix}, then {source}-{suffix}-2, -3, …
	Example: BG-2026-00001-001-RIPE, BG-2026-00001-001-STAY
	"""
	candidate = f"{source_batch}-{suffix}"
	if not frappe.db.exists("Batch", candidate):
		return candidate
	counter = 2
	while frappe.db.exists("Batch", f"{candidate}-{counter}"):
		counter += 1
	return f"{candidate}-{counter}"
