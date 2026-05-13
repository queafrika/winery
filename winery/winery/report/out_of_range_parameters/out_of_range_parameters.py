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
		{"label": "Lab Analysis", "fieldname": "name", "fieldtype": "Link", "options": "Lab Analysis", "width": 160},
		{"label": "Wine Batch", "fieldname": "wine_batch", "fieldtype": "Link", "options": "Wine Batch", "width": 140},
		{"label": "Analysis Date", "fieldname": "analysis_date", "fieldtype": "Date", "width": 110},
		{"label": "Test Type", "fieldname": "test_type", "fieldtype": "Link", "options": "Lab Analysis Test Type", "width": 160},
		{"label": "Cellar Operation", "fieldname": "cellar_operation", "fieldtype": "Link", "options": "Cellar Operation", "width": 150},
		{"label": "Failed Parameter", "fieldname": "failed_parameter", "fieldtype": "Data", "width": 150},
		{"label": "Reading", "fieldname": "reading", "fieldtype": "Float", "width": 90},
		{"label": "Analyst", "fieldname": "analyzed_by", "fieldtype": "Link", "options": "User", "width": 140},
		{"label": "Notes", "fieldname": "notes", "fieldtype": "Data", "width": 200},
	]


def get_data(filters):
	conditions = ["la.docstatus != 2"]
	values = {}

	if filters.get("wine_batch"):
		conditions.append("la.wine_batch = %(wine_batch)s")
		values["wine_batch"] = filters["wine_batch"]

	if filters.get("test_type"):
		conditions.append("la.test_type = %(test_type)s")
		values["test_type"] = filters["test_type"]

	if filters.get("from_date"):
		conditions.append("DATE(la.analysis_date) >= %(from_date)s")
		values["from_date"] = filters["from_date"]

	if filters.get("to_date"):
		conditions.append("DATE(la.analysis_date) <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	where = "WHERE " + " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT
			la.name,
			la.wine_batch,
			DATE(la.analysis_date) AS analysis_date,
			la.test_type,
			la.cellar_operation,
			la.ph_average,
			la.ph_result,
			la.brix_average,
			la.target_brix,
			la.abv_corrected_abv,
			la.temp_average,
			la.temp_out_of_range,
			la.analyzed_by,
			la.notes
		FROM `tabLab Analysis` la
		{where}
		ORDER BY la.analysis_date DESC, la.creation DESC
		""",
		values,
		as_dict=True,
	)

	failures = []
	for row in rows:
		failure_rows = _extract_failures(row)
		failures.extend(failure_rows)

	return failures


def _extract_failures(row):
	"""Return one row per failed parameter found in the lab analysis."""
	base = {
		"name": row.name,
		"wine_batch": row.wine_batch,
		"analysis_date": row.analysis_date,
		"test_type": row.test_type,
		"cellar_operation": row.cellar_operation,
		"analyzed_by": row.analyzed_by,
		"notes": row.notes,
	}

	results = []

	# pH failure
	if row.get("ph_result") == "Fail":
		results.append({**base, "failed_parameter": "pH", "reading": flt(row.ph_average)})

	# Temperature out of range
	if row.get("temp_out_of_range"):
		results.append({**base, "failed_parameter": "Temperature", "reading": flt(row.temp_average)})

	# Brix deviation > 5% of target
	brix_avg = flt(row.get("brix_average"))
	target_brix = flt(row.get("target_brix"))
	if target_brix and brix_avg:
		deviation_pct = abs(brix_avg - target_brix) / target_brix * 100
		if deviation_pct > 5:
			results.append({**base, "failed_parameter": f"Brix (target {target_brix})", "reading": brix_avg})

	# ABV missing or zero on a submitted record with ABV test type
	if row.get("test_type") and "abv" in str(row.get("test_type", "")).lower():
		abv = flt(row.get("abv_corrected_abv"))
		if not abv:
			results.append({**base, "failed_parameter": "ABV (no reading)", "reading": abv})

	return results


def get_filters():
	return [
		{"fieldname": "wine_batch", "label": "Wine Batch", "fieldtype": "Link", "options": "Wine Batch"},
		{"fieldname": "test_type", "label": "Test Type", "fieldtype": "Link", "options": "Lab Analysis Test Type"},
		{"fieldname": "from_date", "label": "From Date", "fieldtype": "Date"},
		{"fieldname": "to_date", "label": "To Date", "fieldtype": "Date"},
	]
