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
		{"label": "Farmer", "fieldname": "farmer", "fieldtype": "Link", "options": "Farmer", "width": 150},
		{"label": "Farmer Name", "fieldname": "farmer_name", "fieldtype": "Data", "width": 160},
		{"label": "Phone", "fieldname": "phone", "fieldtype": "Data", "width": 120},
		{"label": "Total Gradings", "fieldname": "total_gradings", "fieldtype": "Int", "width": 120},
		{"label": "Total Fingers", "fieldname": "total_fingers", "fieldtype": "Int", "width": 110},
		{"label": "Good Fingers", "fieldname": "total_good_fingers", "fieldtype": "Int", "width": 110},
		{"label": "Damaged Fingers", "fieldname": "total_damaged_fingers", "fieldtype": "Int", "width": 120},
		{"label": "Avg Damaged %", "fieldname": "avg_damaged_pct", "fieldtype": "Float", "width": 120},
		{"label": "Total Amount", "fieldname": "total_amount", "fieldtype": "Currency", "width": 130},
		{"label": "Invoices", "fieldname": "total_invoices", "fieldtype": "Int", "width": 90},
	]


def get_data(filters):
	conditions = ["bg.docstatus = 1"]
	values = {}

	if filters.get("from_date"):
		conditions.append("bg.procurement_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]

	if filters.get("to_date"):
		conditions.append("bg.procurement_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	if filters.get("agent"):
		conditions.append("bg.agent = %(agent)s")
		values["agent"] = filters["agent"]

	where = "WHERE " + " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT
			bg.farmer,
			f.farmer_name,
			f.phone,
			COUNT(bg.name) AS total_gradings,
			SUM(bg.total_fingers) AS total_fingers,
			SUM(bg.total_good_fingers) AS total_good_fingers,
			SUM(bg.total_damaged_fingers) AS total_damaged_fingers,
			SUM(bg.total_amount) AS total_amount,
			COUNT(DISTINCT bg.purchase_invoice) AS total_invoices
		FROM `tabBanana Grading` bg
		LEFT JOIN `tabFarmer` f ON f.name = bg.farmer
		{where}
		GROUP BY bg.farmer
		ORDER BY SUM(bg.total_fingers) DESC
		""",
		values,
		as_dict=True,
	)

	for row in rows:
		total = flt(row.total_fingers)
		damaged = flt(row.total_damaged_fingers)
		row["avg_damaged_pct"] = round(damaged / total * 100, 2) if total else 0.0

	return rows


def get_filters():
	return [
		{"fieldname": "from_date", "label": "From Date", "fieldtype": "Date"},
		{"fieldname": "to_date", "label": "To Date", "fieldtype": "Date"},
		{"fieldname": "agent", "label": "Agent", "fieldtype": "Link", "options": "Agent"},
	]
