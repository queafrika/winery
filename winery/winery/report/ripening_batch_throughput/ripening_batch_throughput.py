# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import date_diff, flt, today


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"label": "Ripening Batch", "fieldname": "name", "fieldtype": "Link", "options": "Ripening Batch", "width": 160},
		{"label": "Rack", "fieldname": "rack", "fieldtype": "Link", "options": "Ripening Rack", "width": 140},
		{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 120},
		{"label": "Start Date", "fieldname": "start_date", "fieldtype": "Date", "width": 100},
		{"label": "Expected End", "fieldname": "expected_end_date", "fieldtype": "Date", "width": 110},
		{"label": "Actual End", "fieldname": "actual_end_date", "fieldtype": "Date", "width": 100},
		{"label": "Days Planned", "fieldname": "days_planned", "fieldtype": "Int", "width": 100},
		{"label": "Days Actual", "fieldname": "days_actual", "fieldtype": "Int", "width": 100},
		{"label": "Variance (days)", "fieldname": "days_variance", "fieldtype": "Int", "width": 120},
		{"label": "Fingers In", "fieldname": "total_fingers_ripening", "fieldtype": "Int", "width": 100},
		{"label": "Material Cost", "fieldname": "total_materials_cost", "fieldtype": "Currency", "width": 120},
		{"label": "Cost / Finger", "fieldname": "cost_per_finger", "fieldtype": "Currency", "width": 110},
	]


def get_data(filters):
	conditions = []
	values = {}

	if filters.get("status"):
		conditions.append("rb.status = %(status)s")
		values["status"] = filters["status"]

	if filters.get("rack"):
		conditions.append("rb.rack = %(rack)s")
		values["rack"] = filters["rack"]

	if filters.get("from_date"):
		conditions.append("rb.start_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]

	if filters.get("to_date"):
		conditions.append("rb.start_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

	rows = frappe.db.sql(
		f"""
		SELECT
			rb.name,
			rb.rack,
			rb.status,
			rb.start_date,
			rb.expected_end_date,
			rb.actual_end_date,
			rb.total_fingers_ripening,
			rb.total_materials_cost
		FROM `tabRipening Batch` rb
		{where}
		ORDER BY rb.start_date DESC
		""",
		values,
		as_dict=True,
	)

	for row in rows:
		end_ref = row.actual_end_date or (today() if row.status == "In Progress" else None)

		planned = (
			date_diff(row.expected_end_date, row.start_date)
			if row.expected_end_date and row.start_date else None
		)
		actual = (
			date_diff(end_ref, row.start_date)
			if end_ref and row.start_date else None
		)
		variance = (actual - planned) if (actual is not None and planned is not None) else None

		row["days_planned"] = planned
		row["days_actual"] = actual
		row["days_variance"] = variance

		fingers = flt(row.total_fingers_ripening)
		cost = flt(row.total_materials_cost)
		row["cost_per_finger"] = round(cost / fingers, 4) if fingers else 0.0

		if variance is not None and variance > 2:
			row["days_variance"] = frappe.bold(f"{variance}  ⚠")

	return rows


def get_filters():
	return [
		{
			"fieldname": "status",
			"label": "Status",
			"fieldtype": "Select",
			"options": "\nIn Progress\nReady for Sale\nReady for Wine\nCompleted\nCancelled",
		},
		{"fieldname": "rack", "label": "Ripening Rack", "fieldtype": "Link", "options": "Ripening Rack"},
		{"fieldname": "from_date", "label": "From Date", "fieldtype": "Date"},
		{"fieldname": "to_date", "label": "To Date", "fieldtype": "Date"},
	]
