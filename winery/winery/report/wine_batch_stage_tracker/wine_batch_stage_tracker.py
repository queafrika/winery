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
		{"label": "Wine Batch", "fieldname": "name", "fieldtype": "Link", "options": "Wine Batch", "width": 160},
		{"label": "Recipe", "fieldname": "recipe", "fieldtype": "Link", "options": "Recipe", "width": 160},
		{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 100},
		{"label": "Start Date", "fieldname": "start_date", "fieldtype": "Date", "width": 100},
		{"label": "End Date", "fieldname": "end_date", "fieldtype": "Date", "width": 100},
		{"label": "Current Stage", "fieldname": "current_stage_name", "fieldtype": "Data", "width": 150},
		{"label": "Stage No.", "fieldname": "current_stage_number", "fieldtype": "Int", "width": 80},
		{"label": "Days in Production", "fieldname": "days_in_production", "fieldtype": "Int", "width": 130},
		{"label": "Target Vol (L)", "fieldname": "target_batch_size", "fieldtype": "Float", "width": 110},
		{"label": "Bottling Status", "fieldname": "bottling_status", "fieldtype": "Data", "width": 140},
		{"label": "WIP Warehouse", "fieldname": "wip_warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 160},
		{"label": "ERPNext Batch", "fieldname": "erpnext_batch_no", "fieldtype": "Link", "options": "Batch", "width": 140},
	]


def get_data(filters):
	conditions = []
	values = {}

	if filters.get("status"):
		conditions.append("wb.status = %(status)s")
		values["status"] = filters["status"]

	if filters.get("recipe"):
		conditions.append("wb.recipe = %(recipe)s")
		values["recipe"] = filters["recipe"]

	if filters.get("from_date"):
		conditions.append("wb.start_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]

	if filters.get("to_date"):
		conditions.append("wb.start_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	if filters.get("bottling_status"):
		conditions.append("wb.bottling_status = %(bottling_status)s")
		values["bottling_status"] = filters["bottling_status"]

	where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

	rows = frappe.db.sql(
		f"""
		SELECT
			wb.name,
			wb.recipe,
			wb.status,
			wb.start_date,
			wb.end_date,
			wb.current_stage_name,
			wb.current_stage_number,
			wb.target_batch_size,
			wb.bottling_status,
			wb.wip_warehouse,
			wb.erpnext_batch_no
		FROM `tabWine Batch` wb
		{where}
		ORDER BY wb.start_date DESC
		""",
		values,
		as_dict=True,
	)

	today_date = today()
	for row in rows:
		if row.start_date and row.status != "Completed":
			row["days_in_production"] = date_diff(today_date, row.start_date)
		elif row.start_date and row.end_date:
			row["days_in_production"] = date_diff(row.end_date, row.start_date)
		else:
			row["days_in_production"] = None

	return rows


def get_filters():
	return [
		{
			"fieldname": "status",
			"label": "Status",
			"fieldtype": "Select",
			"options": "\nActive\nCompleted\nCancelled",
		},
		{"fieldname": "recipe", "label": "Recipe", "fieldtype": "Link", "options": "Recipe"},
		{"fieldname": "from_date", "label": "From Date", "fieldtype": "Date"},
		{"fieldname": "to_date", "label": "To Date", "fieldtype": "Date"},
		{
			"fieldname": "bottling_status",
			"label": "Bottling Status",
			"fieldtype": "Select",
			"options": "\nPending\nBottling Completed\nPackaging Completed\nCompleted",
		},
	]
