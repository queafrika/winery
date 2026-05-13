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
		{"label": "Analysis Date", "fieldname": "analysis_date", "fieldtype": "Date", "width": 110},
		{"label": "Wine Batch", "fieldname": "wine_batch", "fieldtype": "Link", "options": "Wine Batch", "width": 140},
		{"label": "Test Type", "fieldname": "test_type", "fieldtype": "Link", "options": "Lab Analysis Test Type", "width": 160},
		{"label": "Item", "fieldname": "item", "fieldtype": "Link", "options": "Item", "width": 180},
		{"label": "Description", "fieldname": "description", "fieldtype": "Data", "width": 180},
		{"label": "Quantity", "fieldname": "quantity", "fieldtype": "Float", "width": 90},
		{"label": "UOM", "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 80},
		{"label": "Source Warehouse", "fieldname": "source_warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 180},
		{"label": "Stock Entry", "fieldname": "consumable_stock_entry", "fieldtype": "Data", "width": 160},
	]


def get_data(filters):
	conditions = ["la.docstatus != 2"]
	values = {}

	if filters.get("from_date"):
		conditions.append("DATE(la.analysis_date) >= %(from_date)s")
		values["from_date"] = filters["from_date"]

	if filters.get("to_date"):
		conditions.append("DATE(la.analysis_date) <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	if filters.get("test_type"):
		conditions.append("la.test_type = %(test_type)s")
		values["test_type"] = filters["test_type"]

	if filters.get("item"):
		conditions.append("lac.item = %(item)s")
		values["item"] = filters["item"]

	where = "WHERE " + " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT
			la.name,
			DATE(la.analysis_date) AS analysis_date,
			la.wine_batch,
			la.test_type,
			lac.item,
			lac.description,
			lac.quantity,
			lac.uom,
			lac.source_warehouse,
			la.consumable_stock_entry
		FROM `tabLab Analysis` la
		INNER JOIN `tabLab Analysis Consumable` lac ON lac.parent = la.name
		{where}
		ORDER BY la.analysis_date DESC, la.name
		""",
		values,
		as_dict=True,
	)


def get_filters():
	return [
		{"fieldname": "from_date", "label": "From Date", "fieldtype": "Date"},
		{"fieldname": "to_date", "label": "To Date", "fieldtype": "Date"},
		{"fieldname": "test_type", "label": "Test Type", "fieldtype": "Link", "options": "Lab Analysis Test Type"},
		{"fieldname": "item", "label": "Item", "fieldtype": "Link", "options": "Item"},
	]
