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
		{"label": "Log", "fieldname": "name", "fieldtype": "Link", "options": "Banana Disinfection Log", "width": 160},
		{"label": "Date", "fieldname": "date", "fieldtype": "Date", "width": 100},
		{"label": "Time", "fieldname": "time", "fieldtype": "Time", "width": 90},
		{"label": "Banana Grading", "fieldname": "banana_grading", "fieldtype": "Link", "options": "Banana Grading", "width": 160},
		{"label": "Performed By", "fieldname": "performed_by", "fieldtype": "Link", "options": "Employee", "width": 160},
		{"label": "Disinfectant Item", "fieldname": "disinfectant_item", "fieldtype": "Link", "options": "Item", "width": 180},
		{"label": "Quantity", "fieldname": "quantity", "fieldtype": "Float", "width": 90},
		{"label": "UOM", "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 80},
		{"label": "Stock Entry", "fieldname": "stock_entry", "fieldtype": "Link", "options": "Stock Entry", "width": 160},
	]


def get_data(filters):
	conditions = ["dl.docstatus != 2"]
	values = {}

	if filters.get("from_date"):
		conditions.append("dl.date >= %(from_date)s")
		values["from_date"] = filters["from_date"]

	if filters.get("to_date"):
		conditions.append("dl.date <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	if filters.get("performed_by"):
		conditions.append("dl.performed_by = %(performed_by)s")
		values["performed_by"] = filters["performed_by"]

	if filters.get("disinfectant_item"):
		conditions.append("dl.disinfectant_item = %(disinfectant_item)s")
		values["disinfectant_item"] = filters["disinfectant_item"]

	where = "WHERE " + " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT
			dl.name,
			dl.date,
			dl.time,
			dl.banana_grading,
			dl.performed_by,
			dl.disinfectant_item,
			dl.quantity,
			dl.uom,
			dl.stock_entry
		FROM `tabBanana Disinfection Log` dl
		{where}
		ORDER BY dl.date DESC, dl.time DESC
		""",
		values,
		as_dict=True,
	)


def get_filters():
	return [
		{"fieldname": "from_date", "label": "From Date", "fieldtype": "Date"},
		{"fieldname": "to_date", "label": "To Date", "fieldtype": "Date"},
		{"fieldname": "performed_by", "label": "Performed By", "fieldtype": "Link", "options": "Employee"},
		{"fieldname": "disinfectant_item", "label": "Disinfectant Item", "fieldtype": "Link", "options": "Item"},
	]
