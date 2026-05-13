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
		{"label": "County", "fieldname": "county", "fieldtype": "Data", "width": 130},
		{"label": "Sub-County", "fieldname": "sub_county", "fieldtype": "Data", "width": 130},
		{"label": "Farm", "fieldname": "farm", "fieldtype": "Link", "options": "Farm", "width": 140},
		{"label": "Farm Name", "fieldname": "farm_name", "fieldtype": "Data", "width": 150},
		{"label": "Farmer", "fieldname": "farmer", "fieldtype": "Link", "options": "Farmer", "width": 140},
		{"label": "Size (Acres)", "fieldname": "farm_size_acres", "fieldtype": "Float", "width": 100},
		{"label": "Deliveries", "fieldname": "total_deliveries", "fieldtype": "Int", "width": 100},
		{"label": "Total Fingers", "fieldname": "total_fingers", "fieldtype": "Int", "width": 110},
		{"label": "Avg Damaged %", "fieldname": "avg_damaged_pct", "fieldtype": "Float", "width": 120},
		{"label": "Total Amount", "fieldname": "total_amount", "fieldtype": "Currency", "width": 130},
		{"label": "Avg Cost / Finger", "fieldname": "avg_cost_per_finger", "fieldtype": "Currency", "width": 140},
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

	if filters.get("farmer"):
		conditions.append("fm.farmer = %(farmer)s")
		values["farmer"] = filters["farmer"]

	if filters.get("county"):
		conditions.append("fm.county = %(county)s")
		values["county"] = filters["county"]

	where = "WHERE " + " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT
			fm.county,
			fm.sub_county,
			bg.farm,
			fm.farm_name,
			fm.farmer,
			fm.farm_size_acres,
			COUNT(bg.name) AS total_deliveries,
			SUM(bg.total_fingers) AS total_fingers,
			SUM(bg.total_damaged_fingers) AS total_damaged_fingers,
			SUM(bg.total_amount) AS total_amount,
			AVG(bg.cost_per_finger_carried_forward) AS avg_cost_per_finger
		FROM `tabBanana Grading` bg
		LEFT JOIN `tabFarm` fm ON fm.name = bg.farm
		{where}
		GROUP BY bg.farm
		ORDER BY fm.county, fm.sub_county, fm.farm_name
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
		{"fieldname": "county", "label": "County", "fieldtype": "Data"},
		{"fieldname": "farmer", "label": "Farmer", "fieldtype": "Link", "options": "Farmer"},
	]
