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
		{"label": "Good Fingers", "fieldname": "total_good_fingers", "fieldtype": "Int", "width": 110},
		{"label": "Damaged Fingers", "fieldname": "total_damaged_fingers", "fieldtype": "Int", "width": 120},
		{"label": "Damaged %", "fieldname": "damaged_pct", "fieldtype": "Float", "width": 100},
		{"label": "Grade A", "fieldname": "grade_a_qty", "fieldtype": "Float", "width": 85},
		{"label": "Grade B", "fieldname": "grade_b_qty", "fieldtype": "Float", "width": 85},
		{"label": "Grade C", "fieldname": "grade_c_qty", "fieldtype": "Float", "width": 85},
		{"label": "Total Amount", "fieldname": "total_amount", "fieldtype": "Currency", "width": 120},
		{"label": "Damaged Amount", "fieldname": "total_damaged_amount", "fieldtype": "Currency", "width": 130},
		{"label": "Net Usable Cost", "fieldname": "net_usable_cost", "fieldtype": "Currency", "width": 130},
		{"label": "Write-off %", "fieldname": "write_off_pct", "fieldtype": "Float", "width": 100},
		{"label": "Cost / Finger", "fieldname": "cost_per_finger_carried_forward", "fieldtype": "Currency", "width": 120},
		{"label": "Purchase Invoice", "fieldname": "purchase_invoice", "fieldtype": "Link", "options": "Purchase Invoice", "width": 160},
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
			bg.total_good_fingers,
			bg.total_damaged_fingers,
			bg.total_amount,
			bg.total_damaged_amount,
			bg.net_usable_cost,
			bg.cost_per_finger_carried_forward,
			bg.purchase_invoice,
			SUM(bgi.grade_a_qty) AS grade_a_qty,
			SUM(bgi.grade_b_qty) AS grade_b_qty,
			SUM(bgi.grade_c_qty) AS grade_c_qty
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
		damaged = flt(row.total_damaged_fingers)
		total_amount = flt(row.total_amount)
		damaged_amount = flt(row.total_damaged_amount)

		row["damaged_pct"] = round(damaged / total * 100, 2) if total else 0.0
		row["write_off_pct"] = round(damaged_amount / total_amount * 100, 2) if total_amount else 0.0

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
