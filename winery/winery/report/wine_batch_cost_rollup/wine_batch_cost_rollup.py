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
		{"label": "Wine Batch", "fieldname": "name", "fieldtype": "Link", "options": "Wine Batch", "width": 160},
		{"label": "Recipe", "fieldname": "recipe", "fieldtype": "Link", "options": "Recipe", "width": 160},
		{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 100},
		{"label": "Start Date", "fieldname": "start_date", "fieldtype": "Date", "width": 100},
		{"label": "Target Vol (L)", "fieldname": "target_batch_size", "fieldtype": "Float", "width": 110},
		{"label": "Bottled Vol (L)", "fieldname": "total_volume_bottled", "fieldtype": "Float", "width": 110},
		{"label": "Process Loss (L)", "fieldname": "process_loss", "fieldtype": "Float", "width": 120},
		{"label": "Yield %", "fieldname": "yield_efficiency_pct", "fieldtype": "Percent", "width": 80},
		{"label": "ABV %", "fieldname": "abv_percentage", "fieldtype": "Float", "width": 70},
		{"label": "Tax Band", "fieldname": "abv_tax_band", "fieldtype": "Link", "options": "ABV Tax Band", "width": 160},
		{"label": "Excise Duty", "fieldname": "excise_duty_amount", "fieldtype": "Currency", "width": 120},
		{"label": "Excise / Litre", "fieldname": "excise_per_litre", "fieldtype": "Currency", "width": 120},
	]


def get_data(filters):
	conditions = ["wb.docstatus != 2"]
	values = {}

	if filters.get("from_date"):
		conditions.append("wb.start_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]

	if filters.get("to_date"):
		conditions.append("wb.start_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	if filters.get("recipe"):
		conditions.append("wb.recipe = %(recipe)s")
		values["recipe"] = filters["recipe"]

	if filters.get("status"):
		conditions.append("wb.status = %(status)s")
		values["status"] = filters["status"]

	if filters.get("abv_tax_band"):
		conditions.append("wb.abv_tax_band = %(abv_tax_band)s")
		values["abv_tax_band"] = filters["abv_tax_band"]

	where = "WHERE " + " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT
			wb.name,
			wb.recipe,
			wb.status,
			wb.start_date,
			wb.target_batch_size,
			wb.total_volume_bottled,
			wb.process_loss,
			wb.yield_efficiency_pct,
			wb.abv_percentage,
			wb.abv_tax_band,
			wb.excise_duty_amount
		FROM `tabWine Batch` wb
		{where}
		ORDER BY wb.start_date DESC
		""",
		values,
		as_dict=True,
	)

	for row in rows:
		vol = flt(row.total_volume_bottled)
		duty = flt(row.excise_duty_amount)
		row["excise_per_litre"] = round(duty / vol, 4) if vol else 0.0

	return rows


def get_filters():
	return [
		{"fieldname": "from_date", "label": "From Date", "fieldtype": "Date"},
		{"fieldname": "to_date", "label": "To Date", "fieldtype": "Date"},
		{"fieldname": "recipe", "label": "Recipe", "fieldtype": "Link", "options": "Recipe"},
		{
			"fieldname": "status",
			"label": "Status",
			"fieldtype": "Select",
			"options": "\nActive\nCompleted\nCancelled",
		},
		{"fieldname": "abv_tax_band", "label": "Tax Band", "fieldtype": "Link", "options": "ABV Tax Band"},
	]
