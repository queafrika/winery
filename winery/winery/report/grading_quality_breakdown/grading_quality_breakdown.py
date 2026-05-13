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
		{"label": "Grading", "fieldname": "name", "fieldtype": "Link", "options": "Banana Grading", "width": 160},
		{"label": "Date", "fieldname": "procurement_date", "fieldtype": "Date", "width": 100},
		{"label": "Farmer", "fieldname": "farmer", "fieldtype": "Link", "options": "Farmer", "width": 140},
		{"label": "Agent", "fieldname": "agent", "fieldtype": "Link", "options": "Agent", "width": 140},
		{"label": "Farm", "fieldname": "farm", "fieldtype": "Link", "options": "Farm", "width": 140},
		{"label": "Total Fingers", "fieldname": "total_fingers", "fieldtype": "Int", "width": 110},
		{"label": "Grade A", "fieldname": "grade_a_qty", "fieldtype": "Float", "width": 90},
		{"label": "Grade B", "fieldname": "grade_b_qty", "fieldtype": "Float", "width": 90},
		{"label": "Grade C", "fieldname": "grade_c_qty", "fieldtype": "Float", "width": 90},
		{"label": "Damaged", "fieldname": "damaged_qty", "fieldtype": "Float", "width": 90},
		{"label": "Grade A %", "fieldname": "grade_a_pct", "fieldtype": "Float", "width": 90},
		{"label": "Damaged %", "fieldname": "damaged_pct", "fieldtype": "Float", "width": 90},
		{"label": "Cost / Finger", "fieldname": "cost_per_finger_carried_forward", "fieldtype": "Currency", "width": 120},
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
		conditions.append("bg.farmer = %(farmer)s")
		values["farmer"] = filters["farmer"]

	if filters.get("agent"):
		conditions.append("bg.agent = %(agent)s")
		values["agent"] = filters["agent"]

	if filters.get("farm"):
		conditions.append("bg.farm = %(farm)s")
		values["farm"] = filters["farm"]

	where = "WHERE " + " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT
			bg.name,
			bg.procurement_date,
			bg.farmer,
			bg.agent,
			bg.farm,
			bg.total_fingers,
			bg.cost_per_finger_carried_forward,
			SUM(bgi.grade_a_qty) AS grade_a_qty,
			SUM(bgi.grade_b_qty) AS grade_b_qty,
			SUM(bgi.grade_c_qty) AS grade_c_qty,
			SUM(bgi.damaged_qty) AS damaged_qty
		FROM `tabBanana Grading` bg
		LEFT JOIN `tabBanana Grading Item` bgi ON bgi.parent = bg.name
		{where}
		GROUP BY bg.name
		ORDER BY bg.procurement_date DESC
		""",
		values,
		as_dict=True,
	)

	for row in rows:
		total = flt(row.total_fingers)
		grade_a = flt(row.grade_a_qty)
		damaged = flt(row.damaged_qty)

		row["grade_a_pct"] = round(grade_a / total * 100, 2) if total else 0.0
		row["damaged_pct"] = round(damaged / total * 100, 2) if total else 0.0

		if row["damaged_pct"] > 10:
			row["damaged_pct"] = frappe.bold(f"{row['damaged_pct']}%  ⚠")

	return rows


def get_filters():
	return [
		{"fieldname": "from_date", "label": "From Date", "fieldtype": "Date"},
		{"fieldname": "to_date", "label": "To Date", "fieldtype": "Date"},
		{"fieldname": "farmer", "label": "Farmer", "fieldtype": "Link", "options": "Farmer"},
		{"fieldname": "agent", "label": "Agent", "fieldtype": "Link", "options": "Agent"},
		{"fieldname": "farm", "label": "Farm", "fieldtype": "Link", "options": "Farm"},
	]
