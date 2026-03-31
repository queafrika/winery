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
			if not row.batch_no:
				continue
			# PI-mode: try Banana Grading Batch child table
			if row.banana_grading:
				data = frappe.db.get_value(
					"Banana Grading Batch",
					{"batch_id": row.batch_no, "parent": row.banana_grading},
					["fingers", "quality_grade"],
					as_dict=True,
				)
				if data:
					row.quality_grade = data.quality_grade
					# Use actual warehouse stock, not the picked-from-field count on the grading batch
					if self.source_warehouse and self.banana_item:
						wh_qty = int(
							_get_batch_qty_in_warehouse(self.banana_item, self.source_warehouse, row.batch_no)
						)
						row.available_fingers = wh_qty if wh_qty >= 0 else data.fingers
					else:
						row.available_fingers = data.fingers
					continue
			# ADR-mode fallback: read from Batch doc + stock ledger
			batch_info = frappe.db.get_value(
				"Batch", row.batch_no, ["banana_grade", "farm", "item"], as_dict=True
			) or {}
			row.quality_grade = batch_info.get("banana_grade") or row.quality_grade
			if not row.farm:
				row.farm = batch_info.get("farm") or ""
			# Use parent banana_item if set, else fall back to item stored on the Batch doc
			resolved_item = self.banana_item or batch_info.get("item") or ""
			if self.source_warehouse and resolved_item:
				row.available_fingers = int(
					_get_batch_qty_in_warehouse(resolved_item, self.source_warehouse, row.batch_no)
				)
			# Populate variety from item variant attribute
			if not row.variety:
				item_code = batch_info.get("item")
				if item_code:
					row.variety = (
						frappe.db.get_value(
							"Item Variant Attribute", {"parent": item_code}, "attribute_value"
						) or ""
					)

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

	def _revert_batches_ripening_start(self):
		"""Clear ripening tracking fields on source batches when ripening is cancelled."""
		for row in self.banana_grading_batches:
			if row.batch_no:
				frappe.db.set_value("Batch", row.batch_no, {
					"ripening_status": "",
					"ripening_start_date": None,
					"ripening_batch_ref": "",
				})

	def on_cancel(self):
		self._cancel_entry("stock_entry")
		self._revert_batches_ripening_start()
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
		"""SE 1 — Transfer raw bananas + ripening materials into the rack warehouse."""
		rack_warehouse = frappe.db.get_value("Ripening Rack", self.rack, "warehouse")

		se = frappe.new_doc("Stock Entry")
		se.purpose = "Material Transfer"
		se.stock_entry_type = "Material Transfer"
		se.posting_date = self.start_date
		se.company = frappe.db.get_value("Warehouse", self.source_warehouse, "company")
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
					"use_serial_batch_fields": 1,
				})

		for mat in self.ripening_materials:
			if (mat.quantity or 0) > 0 and mat.additive and mat.warehouse:
				se.append("items", {
					"item_code": mat.additive,
					"qty": mat.quantity,
					"uom": mat.uom,
					"s_warehouse": mat.warehouse,
					"t_warehouse": rack_warehouse,
				})

		se.insert(ignore_permissions=True)
		frappe.get_doc("Stock Entry", se.name).submit()
		self.db_set("stock_entry", se.name)
		frappe.msgprint(f"Stock Entry <b>{se.name}</b> — bananas and ripening materials transferred to rack.", alert=True)


# --------------------------------------------------------------------------- #
#  Whitelisted helpers                                                         #
# --------------------------------------------------------------------------- #

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_batches_with_stock(doctype, txt, searchfield, start, page_len, filters):
	"""Link-field search query: return only Batch records that have positive stock
	in the given warehouse for the given item.  Falls back to all batches for the
	item when no warehouse is supplied (e.g. field cleared or not yet selected).
	"""
	item = (filters or {}).get("item") or ""
	warehouse = (filters or {}).get("warehouse") or ""
	txt_like = f"%{txt}%"

	if warehouse and item:
		# SBB approach (ERPNext v15+)
		bundle_batches = frappe.db.sql("""
			SELECT sbi.batch_no
			FROM `tabSerial and Batch Entry` sbi
			JOIN `tabSerial and Batch Bundle` sbb ON sbi.parent = sbb.name
			JOIN `tabStock Ledger Entry` sle ON sle.serial_and_batch_bundle = sbb.name
			WHERE sle.item_code = %(item)s
			  AND sle.warehouse  = %(warehouse)s
			  AND sle.is_cancelled = 0
			GROUP BY sbi.batch_no
			HAVING SUM(sbi.qty) > 0
		""", {"item": item, "warehouse": warehouse}, as_dict=True)

		# Legacy approach (batch_no on SLE directly)
		legacy_batches = frappe.db.sql("""
			SELECT batch_no
			FROM `tabStock Ledger Entry`
			WHERE item_code = %(item)s
			  AND warehouse  = %(warehouse)s
			  AND is_cancelled = 0
			  AND serial_and_batch_bundle IS NULL
			  AND batch_no IS NOT NULL AND batch_no != ''
			GROUP BY batch_no
			HAVING SUM(actual_qty) > 0
		""", {"item": item, "warehouse": warehouse}, as_dict=True)

		valid = {r.batch_no for r in bundle_batches} | {r.batch_no for r in legacy_batches}
		if not valid:
			return []

		return frappe.db.sql("""
			SELECT name, batch_id
			FROM `tabBatch`
			WHERE name IN %(valid)s
			  AND (name LIKE %(txt)s OR batch_id LIKE %(txt)s)
			ORDER BY name
			LIMIT %(start)s, %(page_len)s
		""", {"valid": list(valid), "txt": txt_like, "start": start, "page_len": page_len})

	# No warehouse yet — show all batches for the item (standard behaviour)
	item_filter = "AND item = %(item)s" if item else ""
	return frappe.db.sql(f"""
		SELECT name, batch_id
		FROM `tabBatch`
		WHERE (name LIKE %(txt)s OR batch_id LIKE %(txt)s)
		  {item_filter}
		ORDER BY name
		LIMIT %(start)s, %(page_len)s
	""", {"txt": txt_like, "item": item, "start": start, "page_len": page_len})


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
def get_batch_details_for_ripening(batch_no, source_warehouse=None, banana_item=None):
	"""Return farm, variety, grade and available stock for a given batch — works for both ADR and PI batches."""
	batch_info = frappe.db.get_value(
		"Batch", batch_no, ["banana_grade", "farm", "item"], as_dict=True
	) or {}

	variety = ""
	item_code = batch_info.get("item")
	if item_code:
		variety = (
			frappe.db.get_value(
				"Item Variant Attribute", {"parent": item_code}, "attribute_value"
			) or ""
		)

	# Resolve item: prefer caller-supplied banana_item, fall back to item on the Batch doc
	resolved_item = banana_item or batch_info.get("item") or ""
	available = 0
	if resolved_item:
		if source_warehouse:
			available = int(
				_get_batch_qty_in_warehouse(resolved_item, source_warehouse, batch_no)
			)
		else:
			# No warehouse specified yet — return total across all warehouses
			bundle_qty = frappe.db.sql(
				"""
				SELECT COALESCE(SUM(sbi.qty), 0)
				FROM `tabSerial and Batch Entry` sbi
				JOIN `tabSerial and Batch Bundle` sbb ON sbi.parent = sbb.name
				JOIN `tabStock Ledger Entry` sle ON sle.serial_and_batch_bundle = sbb.name
				WHERE sbi.batch_no = %s AND sle.item_code = %s AND sle.is_cancelled = 0
				""",
				(batch_no, resolved_item),
			)
			legacy_qty = frappe.db.sql(
				"""
				SELECT COALESCE(SUM(actual_qty), 0)
				FROM `tabStock Ledger Entry`
				WHERE item_code = %s AND batch_no = %s AND is_cancelled = 0
				""",
				(resolved_item, batch_no),
			)
			available = int(
				((bundle_qty[0][0] or 0) if bundle_qty else 0)
				+ ((legacy_qty[0][0] or 0) if legacy_qty else 0)
			)

	return {
		"quality_grade": batch_info.get("banana_grade") or "",
		"farm":          batch_info.get("farm") or "",
		"variety":       variety,
		"available_fingers": available,
	}


@frappe.whitelist()
def get_batch_quantities_in_rack(ripening_batch):
	"""Return current stock per batch for this item in the rack warehouse."""
	rb = frappe.get_doc("Ripening Batch", ripening_batch)
	rack_warehouse = frappe.db.get_value("Ripening Rack", rb.rack, "warehouse")
	if not rack_warehouse:
		frappe.throw(f"Rack <b>{rb.rack}</b> does not have a warehouse configured.")

	# Restrict to batches that belong to this ripening batch.
	batch_nos = [row.batch_no for row in rb.banana_grading_batches if row.batch_no]
	if not batch_nos:
		frappe.throw("No batches found in this Ripening Batch grading table.")

	batch_placeholders = ", ".join(["%s"] * len(batch_nos))

	# ERPNext v15 stores batch qty in Serial and Batch Bundle (sbi.qty is signed).
	# Legacy entries store batch_no directly on the SLE.  Query both and merge.
	rows = frappe.db.sql(
		f"""
		SELECT sbi.batch_no AS batch_no, SUM(sbi.qty) AS qty
		FROM `tabSerial and Batch Entry` sbi
		JOIN `tabSerial and Batch Bundle` sbb ON sbi.parent = sbb.name
		JOIN `tabStock Ledger Entry` sle ON sle.serial_and_batch_bundle = sbb.name
		WHERE sle.item_code    = %s
		  AND sle.warehouse    = %s
		  AND sle.is_cancelled = 0
		  AND sbi.batch_no IN ({batch_placeholders})
		GROUP BY sbi.batch_no
		HAVING SUM(sbi.qty) > 0

		UNION ALL

		SELECT batch_no, SUM(actual_qty) AS qty
		FROM `tabStock Ledger Entry`
		WHERE item_code    = %s
		  AND warehouse    = %s
		  AND is_cancelled = 0
		  AND serial_and_batch_bundle IS NULL
		  AND batch_no IN ({batch_placeholders})
		GROUP BY batch_no
		HAVING SUM(actual_qty) > 0
		""",
		[rb.banana_item, rack_warehouse] + batch_nos + [rb.banana_item, rack_warehouse] + batch_nos,
		as_dict=True,
	)

	# Merge rows with the same batch_no (shouldn't happen but be safe)
	merged = {}
	for r in rows:
		merged[r.batch_no] = merged.get(r.batch_no, 0) + (r.qty or 0)
	rows = [frappe._dict(batch_no=b, qty=q) for b, q in merged.items() if q > 0]

	if not rows:
		se_name = rb.stock_entry or "none"
		frappe.throw(
			f"No stock of <b>{rb.banana_item}</b> found in rack warehouse "
			f"<b>{rack_warehouse}</b>.<br><br>"
			f"Banana Transfer Entry: <b>{se_name}</b>.<br>"
			"Please verify the stock entry is submitted and the item has stock in the rack."
		)

	grade_map   = {row.batch_no: row.quality_grade for row in rb.banana_grading_batches}
	farm_map    = {row.batch_no: row.farm          for row in rb.banana_grading_batches}
	variety_map = {row.batch_no: row.variety       for row in rb.banana_grading_batches}

	return {
		"rack_warehouse": rack_warehouse,
		"batches": [
			{
				"batch_no":       r.batch_no,
				"fingers_in_rack": int(r.qty),
				"quality_grade":  grade_map.get(r.batch_no, ""),
				"farm":           farm_map.get(r.batch_no, ""),
				"variety":        variety_map.get(r.batch_no, ""),
			}
			for r in rows
		],
	}


@frappe.whitelist()
def end_ripening(ripening_batch, destination_warehouse, end_date, transfers, ripe_item=None):
	"""
	ONE Repack Stock Entry PER SOURCE BATCH — ensures each ripe batch is valued as:
	  (raw batch cost) + (ripening materials apportioned by fingers_transferred / total_original)

	A single SE pooling multiple batches would blend all costs into one rate, losing
	per-batch traceability of ripening material costs.

	Targets per SE:
	  - Ripe bananas → destination warehouse  (new RIPE batch)
	  - Remaining raw bananas → back to rack   (new STAY batch, splits only)
	"""
	if isinstance(transfers, str):
		transfers = json.loads(transfers)

	rb = frappe.get_doc("Ripening Batch", ripening_batch)
	rack_warehouse = frappe.db.get_value("Ripening Rack", rb.rack, "warehouse")
	ripening_days = date_diff(end_date, rb.start_date)
	company = frappe.db.get_value("Warehouse", rack_warehouse, "company")

	# Load ripe banana finger template for auto-resolving variety-matched ripe items
	ripe_tpl = frappe.db.get_single_value("Winery Settings", "ripe_banana_finger_template")

	# Denominator for material apportioning — frozen at ripening start
	total_original = rb.total_original_fingers or rb.total_fingers_ripening or 1

	batch_updates = []   # (old_batch_no, remain_batch_id, fingers_to_keep)
	ripe_batch_map = {}  # batch_no → ripe_batch_id
	submitted_ses = []   # names of all submitted SEs

	for t in transfers:
		batch_no = t.get("batch_no")
		fingers_to_transfer = int(t.get("fingers_to_transfer") or 0)
		fingers_in_rack = int(t.get("fingers_in_rack") or 0)

		if fingers_to_transfer <= 0:
			continue

		fingers_to_keep = fingers_in_rack - fingers_to_transfer
		is_split = fingers_to_keep > 0

		# Fetch source batch metadata to carry forward to ripe batch
		source_batch_info = frappe.db.get_value(
			"Batch", batch_no,
			["banana_grade", "is_damaged", "farm", "disinfection_log",
			 "disinfection_date", "disinfection_time"],
			as_dict=True,
		) or {}

		# Auto-resolve ripe item by matching variety from the source batch's item
		batch_item = frappe.db.get_value("Batch", batch_no, "item")
		resolved_ripe_item = ripe_item  # fallback to caller-supplied value
		if ripe_tpl and batch_item:
			matched = _find_ripe_finger_variant(batch_item, ripe_tpl)
			if matched:
				resolved_ripe_item = matched
		if not resolved_ripe_item:
			frappe.throw(
				f"Cannot determine ripe banana item for batch <b>{batch_no}</b>. "
				"Set <b>Ripe Banana Finger Template</b> in Winery Settings."
			)

		# RIPE batch ID: {source}-R
		ripe_batch_id = _unique_batch_id(batch_no, "R")
		ripe_batch_map[batch_no] = ripe_batch_id

		ripe_batch = frappe.new_doc("Batch")
		ripe_batch.item = resolved_ripe_item
		ripe_batch.batch_id = ripe_batch_id
		ripe_batch.description = (
			f"Ripened from {batch_no} | {ripening_days} days | "
			f"{rb.start_date} → {end_date}"
		)
		ripe_batch.source_batch      = batch_no
		ripe_batch.banana_grade      = source_batch_info.get("banana_grade") or ""
		ripe_batch.farm              = source_batch_info.get("farm") or ""
		ripe_batch.disinfection_log  = source_batch_info.get("disinfection_log") or ""
		ripe_batch.disinfection_date = source_batch_info.get("disinfection_date") or None
		ripe_batch.disinfection_time = source_batch_info.get("disinfection_time") or None
		ripe_batch.is_damaged = 0
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
			remain_batch.source_batch    = batch_no
			remain_batch.banana_grade    = source_batch_info.get("banana_grade") or ""
			remain_batch.farm            = source_batch_info.get("farm") or ""
			remain_batch.disinfection_log  = source_batch_info.get("disinfection_log") or ""
			remain_batch.disinfection_date = source_batch_info.get("disinfection_date") or None
			remain_batch.disinfection_time = source_batch_info.get("disinfection_time") or None
			remain_batch.is_damaged = source_batch_info.get("is_damaged") or 0
			remain_batch.insert(ignore_permissions=True)
			batch_updates.append((batch_no, remain_batch_id, fingers_to_keep))

		# ONE Repack SE for this batch — keeps raw cost + material cost separate per batch
		se = frappe.new_doc("Stock Entry")
		se.purpose = "Repack"
		se.stock_entry_type = "Repack"
		se.posting_date = end_date
		se.remarks = f"End ripening for {ripening_batch}"
		se.use_serial_batch_fields = 1
		se.company = company

		# SOURCE: consume full current qty of this batch from rack
		se.append("items", {
			"item_code": rb.banana_item,
			"qty": fingers_in_rack,
			"uom": "Nos",
			"s_warehouse": rack_warehouse,
			"batch_no": batch_no,
			"use_serial_batch_fields": 1,
		})

		# TARGET: ripe bananas → destination warehouse
		se.append("items", {
			"item_code": resolved_ripe_item,
			"qty": fingers_to_transfer,
			"uom": "Nos",
			"t_warehouse": destination_warehouse,
			"batch_no": ripe_batch_id,
			"use_serial_batch_fields": 1,
		})

		# TARGET: remaining raw bananas → back to rack under STAY batch (split only)
		if is_split:
			se.append("items", {
				"item_code": rb.banana_item,
				"qty": fingers_to_keep,
				"uom": "Nos",
				"t_warehouse": rack_warehouse,
				"batch_no": remain_batch_id,
				"use_serial_batch_fields": 1,
			})

		# SOURCE: ripening materials apportioned to this batch
		# Formula: mat.quantity × (fingers_to_transfer / total_original)
		# Ensures ripe valuation = raw cost + this batch's share of material cost
		for mat in rb.ripening_materials:
			batch_mat_qty = round((mat.quantity or 0) * fingers_to_transfer / total_original, 6)
			if batch_mat_qty > 0 and mat.additive:
				se.append("items", {
					"item_code": mat.additive,
					"qty": batch_mat_qty,
					"uom": mat.uom,
					"s_warehouse": rack_warehouse,
				})

		se.insert(ignore_permissions=True)
		frappe.get_doc("Stock Entry", se.name).submit()
		submitted_ses.append(se.name)

	if not submitted_ses:
		frappe.throw("No fingers to transfer — please enter at least one transfer quantity.")

	# Update child table batch_no for split batches
	for old_batch_no, remain_batch_id, fingers_to_keep in batch_updates:
		for row in rb.banana_grading_batches:
			if row.batch_no == old_batch_no:
				row.db_set("batch_no", remain_batch_id)
				row.db_set("fingers_for_ripening", fingers_to_keep)
				break

	rb.db_set("actual_end_date", end_date)
	rb.db_set("ripening_days", ripening_days)

	# Stamp source and ripe batches with tracking info
	for t in transfers:
		batch_no = t.get("batch_no")
		fingers_to_transfer = int(t.get("fingers_to_transfer") or 0)
		if not fingers_to_transfer or not batch_no:
			continue

		frappe.db.set_value("Batch", batch_no, {
			"ripening_status": "Ripening Complete",
			"ripening_end_date": end_date,
			"ripening_days_actual": ripening_days,
		})

		ripe_id = ripe_batch_map.get(batch_no)
		if ripe_id and frappe.db.exists("Batch", ripe_id):
			frappe.db.set_value("Batch", ripe_id, {
				"ripening_status": "Ripening Complete",
				"ripening_start_date": rb.start_date,
				"ripening_end_date": end_date,
				"ripening_days_actual": ripening_days,
				"ripening_batch_ref": ripening_batch,
			})

	se_links = ", ".join(f"<b>{n}</b>" for n in submitted_ses)
	frappe.msgprint(f"Transfer complete — Repack Stock Entries: {se_links}", alert=True)
	return {"stock_entries": submitted_ses}


# --------------------------------------------------------------------------- #
#  Internal helpers                                                            #
# --------------------------------------------------------------------------- #

def _get_batch_qty_in_warehouse(item_code, warehouse, batch_no):
	"""Return net qty for a batch in a warehouse.

	Handles both storage approaches used by ERPNext:
	  - New (v15+): batch info in Serial and Batch Bundle / Serial and Batch Entry
	  - Legacy: batch_no stored directly on the Stock Ledger Entry
	"""
	# Bundle approach: sbi.qty is already signed (negative for Outward) — plain SUM is correct
	bundle_qty = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(sbi.qty), 0)
		FROM `tabSerial and Batch Entry` sbi
		JOIN `tabSerial and Batch Bundle` sbb ON sbi.parent = sbb.name
		JOIN `tabStock Ledger Entry` sle ON sle.serial_and_batch_bundle = sbb.name
		WHERE sbi.batch_no = %s
		  AND sle.item_code = %s
		  AND sle.warehouse = %s
		  AND sle.is_cancelled = 0
		""",
		(batch_no, item_code, warehouse),
	)
	bundle_qty = (bundle_qty[0][0] or 0) if bundle_qty else 0

	# Legacy approach: batch_no directly on SLE
	legacy_qty = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(actual_qty), 0)
		FROM `tabStock Ledger Entry`
		WHERE item_code = %s AND warehouse = %s AND batch_no = %s AND is_cancelled = 0
		""",
		(item_code, warehouse, batch_no),
	)
	legacy_qty = (legacy_qty[0][0] or 0) if legacy_qty else 0

	return bundle_qty + legacy_qty


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


def _find_ripe_finger_variant(raw_item, ripe_template):
	"""Return the Ripe Banana Finger variant whose attributes match the given raw item."""
	raw_attrs = {
		a.attribute: a.attribute_value
		for a in frappe.db.get_all(
			"Item Variant Attribute",
			filters={"parent": raw_item},
			fields=["attribute", "attribute_value"],
		)
	}
	if not raw_attrs:
		return None
	for candidate in frappe.db.get_all(
		"Item",
		filters={"variant_of": ripe_template, "disabled": 0},
		fields=["name"],
	):
		cand_attrs = {
			a.attribute: a.attribute_value
			for a in frappe.db.get_all(
				"Item Variant Attribute",
				filters={"parent": candidate.name},
				fields=["attribute", "attribute_value"],
			)
		}
		if all(cand_attrs.get(k) == v for k, v in raw_attrs.items()):
			return candidate.name
	return None


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
