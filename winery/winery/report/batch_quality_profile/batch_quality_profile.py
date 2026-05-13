# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

import frappe


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
		{"label": "pH Avg", "fieldname": "ph_average", "fieldtype": "Float", "width": 80},
		{"label": "pH Result", "fieldname": "ph_result", "fieldtype": "Data", "width": 90},
		{"label": "Brix Avg", "fieldname": "brix_average", "fieldtype": "Float", "width": 80},
		{"label": "ABV %", "fieldname": "abv_corrected_abv", "fieldtype": "Float", "width": 75},
		{"label": "Gravity Avg", "fieldname": "average_gravity", "fieldtype": "Float", "width": 100},
		{"label": "Residual Sugar (g/L)", "fieldname": "rs_residual_sugar_gl", "fieldtype": "Float", "width": 150},
		{"label": "Wine Classification", "fieldname": "rs_wine_classification", "fieldtype": "Data", "width": 150},
		{"label": "Stability Decision", "fieldname": "stability_decision", "fieldtype": "Data", "width": 140},
		{"label": "Analyst", "fieldname": "analyzed_by", "fieldtype": "Link", "options": "User", "width": 140},
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

	if filters.get("analyzed_by"):
		conditions.append("la.analyzed_by = %(analyzed_by)s")
		values["analyzed_by"] = filters["analyzed_by"]

	where = "WHERE " + " AND ".join(conditions)

	return frappe.db.sql(
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
			la.abv_corrected_abv,
			la.average_gravity,
			la.rs_residual_sugar_gl,
			la.rs_wine_classification,
			la.stability_decision,
			la.analyzed_by
		FROM `tabLab Analysis` la
		{where}
		ORDER BY la.analysis_date DESC, la.creation DESC
		""",
		values,
		as_dict=True,
	)


def get_filters():
	return [
		{"fieldname": "wine_batch", "label": "Wine Batch", "fieldtype": "Link", "options": "Wine Batch"},
		{"fieldname": "test_type", "label": "Test Type", "fieldtype": "Link", "options": "Lab Analysis Test Type"},
		{"fieldname": "from_date", "label": "From Date", "fieldtype": "Date"},
		{"fieldname": "to_date", "label": "To Date", "fieldtype": "Date"},
		{"fieldname": "analyzed_by", "label": "Analyst", "fieldtype": "Link", "options": "User"},
	]
