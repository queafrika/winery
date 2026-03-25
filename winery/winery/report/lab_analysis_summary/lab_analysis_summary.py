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
		{"label": "Test Type", "fieldname": "test_type", "fieldtype": "Data", "width": 160},
		{"label": "Operation Type", "fieldname": "operation_type", "fieldtype": "Link", "options": "Cellar Operation Type", "width": 140},
		{"label": "Cellar Operation", "fieldname": "cellar_operation", "fieldtype": "Link", "options": "Cellar Operation", "width": 140},
		{"label": "Analysis Date", "fieldname": "analysis_date", "fieldtype": "Date", "width": 110},
		{"label": "Result Value", "fieldname": "result_value", "fieldtype": "Float", "width": 100},
		{"label": "Result Unit", "fieldname": "result_unit", "fieldtype": "Data", "width": 90},
		{"label": "Classification", "fieldname": "wine_classification", "fieldtype": "Data", "width": 160},
		{"label": "Analyst", "fieldname": "analyst", "fieldtype": "Link", "options": "User", "width": 140},
	]


def get_data(filters):
	conditions = []
	values = {}

	# Only submitted and draft — exclude cancelled
	conditions.append("la.docstatus != 2")

	if filters.get("wine_batch"):
		conditions.append("la.wine_batch = %(wine_batch)s")
		values["wine_batch"] = filters["wine_batch"]

	if filters.get("test_type"):
		conditions.append("la.test_type = %(test_type)s")
		values["test_type"] = filters["test_type"]

	if filters.get("from_date"):
		conditions.append("la.analysis_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]

	if filters.get("to_date"):
		conditions.append("la.analysis_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	if filters.get("operation_type"):
		conditions.append("la.operation_type = %(operation_type)s")
		values["operation_type"] = filters["operation_type"]

	where = "WHERE " + " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT
			la.name,
			la.wine_batch,
			la.test_type,
			la.operation_type,
			la.cellar_operation,
			la.analysis_date,
			la.result_value,
			la.result_unit,
			la.wine_classification,
			la.analyst
		FROM `tabLab Analysis` la
		{where}
		ORDER BY la.analysis_date DESC, la.creation DESC
		""",
		values,
		as_dict=True,
	)


def get_filters():
	return [
		{
			"fieldname": "wine_batch",
			"label": "Wine Batch",
			"fieldtype": "Link",
			"options": "Wine Batch",
		},
		{
			"fieldname": "test_type",
			"label": "Test Type",
			"fieldtype": "Select",
			"options": "\nResidual Sugar Test\nBrix Test\nABV Test\nTemperature Test\npH Test\nSensory Evaluation\nDissolution Test\nGravity Test\nMicrobial Stability Test",
		},
		{
			"fieldname": "operation_type",
			"label": "Operation Type",
			"fieldtype": "Link",
			"options": "Cellar Operation Type",
		},
		{
			"fieldname": "from_date",
			"label": "From Date",
			"fieldtype": "Date",
		},
		{
			"fieldname": "to_date",
			"label": "To Date",
			"fieldtype": "Date",
		},
	]
