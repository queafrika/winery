# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import date_diff, flt


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"label": "Ripening Batch", "fieldname": "name", "fieldtype": "Link", "options": "Ripening Batch", "width": 160},
		{"label": "Ripening Rack", "fieldname": "ripening_rack", "fieldtype": "Link", "options": "Ripening Rack", "width": 140},
		{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 120},
		{"label": "Start Date", "fieldname": "start_date", "fieldtype": "Date", "width": 100},
		{"label": "Expected End", "fieldname": "expected_end_date", "fieldtype": "Date", "width": 110},
		{"label": "Actual End", "fieldname": "actual_end_date", "fieldtype": "Date", "width": 100},
		{"label": "Days Planned", "fieldname": "days_planned", "fieldtype": "Int", "width": 100},
		{"label": "Days Actual", "fieldname": "days_actual", "fieldtype": "Int", "width": 100},
		{"label": "Variance (days)", "fieldname": "days_variance", "fieldtype": "Int", "width": 120},
		{"label": "Total Fingers In", "fieldname": "total_fingers", "fieldtype": "Float", "width": 120},
		{"label": "Total Cost", "fieldname": "total_material_cost", "fieldtype": "Currency", "width": 120},
		{"label": "Cost per Finger", "fieldname": "cost_per_finger", "fieldtype": "Currency", "width": 120},
	]


def get_data(filters):
	conditions = []
	values = {}

	if filters.get("status"):
		conditions.append("rb.status = %(status)s")
		values["status"] = filters["status"]

	if filters.get("ripening_rack"):
		conditions.append("rb.ripening_rack = %(ripening_rack)s")
		values["ripening_rack"] = filters["ripening_rack"]

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
			rb.ripening_rack,
			rb.status,
			rb.start_date,
			rb.expected_end_date,
			rb.actual_end_date,
			rb.total_fingers,
			rb.total_material_cost
		FROM `tabRipening Batch` rb
		{where}
		ORDER BY rb.start_date DESC
		""",
		values,
		as_dict=True,
	)

	for row in rows:
		planned_days = (
			date_diff(row.expected_end_date, row.start_date)
			if row.expected_end_date and row.start_date else None
		)
		actual_days = (
			date_diff(row.actual_end_date, row.start_date)
			if row.actual_end_date and row.start_date else None
		)
		row["days_planned"] = planned_days
		row["days_actual"] = actual_days
		row["days_variance"] = (
			(actual_days - planned_days) if (actual_days is not None and planned_days is not None) else None
		)
		fingers = flt(row.total_fingers)
		cost = flt(row.total_material_cost)
		row["cost_per_finger"] = round(cost / fingers, 4) if fingers else 0.0

	return rows


def get_filters():
	return [
		{
			"fieldname": "status",
			"label": "Status",
			"fieldtype": "Select",
			"options": "\nDraft\nIn Progress\nRipening Complete\nCancelled",
		},
		{
			"fieldname": "ripening_rack",
			"label": "Ripening Rack",
			"fieldtype": "Link",
			"options": "Ripening Rack",
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
