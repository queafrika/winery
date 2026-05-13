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
		{"label": "Grading", "fieldname": "name", "fieldtype": "Link", "options": "Banana Grading", "width": 160},
		{"label": "Date", "fieldname": "procurement_date", "fieldtype": "Date", "width": 100},
		{"label": "Farmer", "fieldname": "farmer", "fieldtype": "Link", "options": "Farmer", "width": 140},
		{"label": "Agent", "fieldname": "agent", "fieldtype": "Link", "options": "Agent", "width": 140},
		{"label": "Total Fingers", "fieldname": "total_fingers", "fieldtype": "Int", "width": 110},
		{"label": "Good Fingers", "fieldname": "total_good_fingers", "fieldtype": "Int", "width": 110},
		{"label": "Damaged Fingers", "fieldname": "total_damaged_fingers", "fieldtype": "Int", "width": 120},
		{"label": "Total Amount", "fieldname": "total_amount", "fieldtype": "Currency", "width": 120},
		{"label": "Damaged Amount", "fieldname": "total_damaged_amount", "fieldtype": "Currency", "width": 130},
		{"label": "Net Usable Cost", "fieldname": "net_usable_cost", "fieldtype": "Currency", "width": 130},
		{"label": "Valuation %", "fieldname": "valuation_percentage", "fieldtype": "Percent", "width": 100},
		{"label": "Valuation Amount", "fieldname": "valuation_amount", "fieldtype": "Currency", "width": 130},
		{"label": "Cost / Finger", "fieldname": "cost_per_finger_carried_forward", "fieldtype": "Currency", "width": 110},
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

	where = "WHERE " + " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT
			bg.name,
			bg.procurement_date,
			bg.farmer,
			bg.agent,
			bg.total_fingers,
			bg.total_good_fingers,
			bg.total_damaged_fingers,
			bg.total_amount,
			bg.total_damaged_amount,
			bg.net_usable_cost,
			bg.valuation_percentage,
			bg.valuation_amount,
			bg.cost_per_finger_carried_forward,
			bg.purchase_invoice
		FROM `tabBanana Grading` bg
		{where}
		ORDER BY bg.procurement_date DESC
		""",
		values,
		as_dict=True,
	)


def get_filters():
	return [
		{"fieldname": "from_date", "label": "From Date", "fieldtype": "Date"},
		{"fieldname": "to_date", "label": "To Date", "fieldtype": "Date"},
		{"fieldname": "farmer", "label": "Farmer", "fieldtype": "Link", "options": "Farmer"},
		{"fieldname": "agent", "label": "Agent", "fieldtype": "Link", "options": "Agent"},
	]
