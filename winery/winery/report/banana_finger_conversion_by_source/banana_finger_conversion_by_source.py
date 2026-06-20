# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"label": "Date",              "fieldname": "posting_date",    "fieldtype": "Date",     "width": 100},
		{"label": "Cellar Operation",  "fieldname": "cellar_operation","fieldtype": "Link",     "options": "Cellar Operation", "width": 160},
		{"label": "Wine Batch",        "fieldname": "wine_batch",      "fieldtype": "Link",     "options": "Wine Batch",       "width": 140},
		{"label": "Ripe Batch",        "fieldname": "batch_no",        "fieldtype": "Link",     "options": "Batch",            "width": 170},
		{"label": "Farm",              "fieldname": "farm",            "fieldtype": "Link",     "options": "Farm",             "width": 130},
		{"label": "Farmer",            "fieldname": "farmer",          "fieldtype": "Link",     "options": "Farmer",           "width": 130},
		{"label": "Agent",             "fieldname": "agent",           "fieldtype": "Link",     "options": "Agent",            "width": 130},
		{"label": "Fingers (Nos)",     "fieldname": "fingers_used",    "fieldtype": "Int",      "width": 110},
		{"label": "Weight (Kg)",       "fieldname": "actual_weight_kg","fieldtype": "Float",    "width": 110},
		{"label": "Actual Nos/Kg",     "fieldname": "nos_per_kg",      "fieldtype": "Float",    "width": 110},
		{"label": "Deviation from 100 Nos/Kg (%)", "fieldname": "deviation_pct", "fieldtype": "Float", "width": 180},
	]


def get_data(filters):
	conditions = ["se.docstatus = 1", "sei.actual_weight_kg > 0", "sei.batch_no IS NOT NULL"]
	values = {}

	if filters.get("from_date"):
		conditions.append("se.posting_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]

	if filters.get("to_date"):
		conditions.append("se.posting_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	if filters.get("wine_batch"):
		conditions.append("co.wine_batch = %(wine_batch)s")
		values["wine_batch"] = filters["wine_batch"]

	where = "WHERE " + " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT
			se.posting_date,
			sei.parent AS stock_entry,
			sei.batch_no,
			sei.qty AS fingers_used,
			sei.actual_weight_kg,
			sei.nos_per_kg,
			co.name AS cellar_operation,
			co.wine_batch
		FROM `tabStock Entry Detail` sei
		JOIN `tabStock Entry` se ON se.name = sei.parent
		JOIN `tabCellar Operation` co ON co.transfer_entry = se.name
		{where}
		ORDER BY se.posting_date DESC, co.name
		""",
		values,
		as_dict=True,
	)

	if not rows:
		return rows

	_enrich_with_source(rows)

	# Apply post-filters that depend on enriched fields
	if filters.get("farm"):
		rows = [r for r in rows if r.get("farm") == filters["farm"]]
	if filters.get("farmer"):
		rows = [r for r in rows if r.get("farmer") == filters["farmer"]]
	if filters.get("agent"):
		rows = [r for r in rows if r.get("agent") == filters["agent"]]

	for r in rows:
		nos_kg = flt(r.get("nos_per_kg"))
		r["deviation_pct"] = round((nos_kg - 100.0) / 100.0 * 100.0, 2) if nos_kg else None

	return rows


def _enrich_with_source(rows):
	"""Bulk-enrich each row with farm, farmer, agent traced back through ripening to grading."""
	batch_nos = list({r["batch_no"] for r in rows if r.get("batch_no")})
	if not batch_nos:
		return

	# 1. Fetch source_batch and farm for all ripe batches in one query
	batch_data = {
		d.name: d
		for d in frappe.db.get_all(
			"Batch",
			filters={"name": ["in", batch_nos]},
			fields=["name", "farm", "source_batch"],
		)
	}

	# 2. Map each ripe batch to its raw/source lookup batch
	lookup_map = {}
	for b in batch_nos:
		bd = batch_data.get(b) or {}
		lookup_map[b] = bd.get("source_batch") or b

	all_lookup = list(set(lookup_map.values()))

	# 3. Fetch farm on raw batches (fallback when ripe batch has no farm set)
	raw_farm = {
		d.name: d.farm
		for d in frappe.db.get_all(
			"Batch",
			filters={"name": ["in", all_lookup]},
			fields=["name", "farm"],
		)
	}

	# 4. Find Banana Grading via Banana Grading Batch child table (PI mode)
	grading_map = {}
	for row in frappe.db.get_all(
		"Banana Grading Batch",
		filters={"batch_id": ["in", all_lookup]},
		fields=["batch_id", "parent"],
	):
		grading_map[row.batch_id] = row.parent

	# 5. For batches not found above, search Banana Grading Item grade fields (ADR mode)
	missing = [b for b in all_lookup if b not in grading_map]
	if missing:
		for grade_field in ("grade_a_batch", "grade_b_batch", "grade_c_batch", "damaged_batch"):
			for row in frappe.db.get_all(
				"Banana Grading Item",
				filters={grade_field: ["in", missing]},
				fields=[grade_field, "parent"],
			):
				b = row.get(grade_field)
				if b and b not in grading_map:
					grading_map[b] = row.parent

	# 6. Bulk fetch agent, farmer, farm from all matched Banana Grading docs
	grading_names = list(set(grading_map.values()))
	grading_details = {}
	if grading_names:
		for g in frappe.db.get_all(
			"Banana Grading",
			filters={"name": ["in", grading_names]},
			fields=["name", "agent", "farmer", "farm"],
		):
			grading_details[g.name] = g

	# 7. Write enriched fields back onto each row
	for r in rows:
		batch_no = r.get("batch_no")
		if not batch_no:
			continue
		bd      = batch_data.get(batch_no) or {}
		lookup  = lookup_map.get(batch_no, batch_no)
		grading = grading_details.get(grading_map.get(lookup))

		r["farm"]   = bd.get("farm") or raw_farm.get(lookup) or (grading.farm   if grading else None)
		r["farmer"] = grading.farmer if grading else None
		r["agent"]  = grading.agent  if grading else None


def get_filters():
	return [
		{
			"fieldname": "from_date",
			"label": "From Date",
			"fieldtype": "Date",
			"reqd": 1,
			"default": frappe.utils.add_months(frappe.utils.today(), -3),
		},
		{
			"fieldname": "to_date",
			"label": "To Date",
			"fieldtype": "Date",
			"reqd": 1,
			"default": frappe.utils.today(),
		},
		{"fieldname": "farm",       "label": "Farm",       "fieldtype": "Link", "options": "Farm"},
		{"fieldname": "farmer",     "label": "Farmer",     "fieldtype": "Link", "options": "Farmer"},
		{"fieldname": "agent",      "label": "Agent",      "fieldtype": "Link", "options": "Agent"},
		{"fieldname": "wine_batch", "label": "Wine Batch", "fieldtype": "Link", "options": "Wine Batch"},
	]
