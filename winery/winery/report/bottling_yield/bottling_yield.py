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
		{"label": "Bottling", "fieldname": "name", "fieldtype": "Link", "options": "Bottling", "width": 160},
		{"label": "Wine Batch", "fieldname": "wine_batch", "fieldtype": "Link", "options": "Wine Batch", "width": 140},
		{"label": "Bottling Date", "fieldname": "bottling_date", "fieldtype": "Date", "width": 110},
		{"label": "Input Vol (L)", "fieldname": "input_quantity", "fieldtype": "Float", "width": 110},
		{"label": "Bottled Vol (L)", "fieldname": "total_volume_bottled", "fieldtype": "Float", "width": 120},
		{"label": "Process Loss (L)", "fieldname": "process_loss", "fieldtype": "Float", "width": 120},
		{"label": "Yield %", "fieldname": "yield_efficiency_pct", "fieldtype": "Float", "width": 80},
		{"label": "ABV %", "fieldname": "abv_percentage", "fieldtype": "Float", "width": 70},
		{"label": "Tax Band", "fieldname": "abv_tax_band", "fieldtype": "Link", "options": "ABV Tax Band", "width": 180},
		{"label": "Duty/Litre", "fieldname": "excise_duty_per_litre", "fieldtype": "Currency", "width": 100},
		{"label": "Total Excise Duty", "fieldname": "excise_duty_amount", "fieldtype": "Currency", "width": 130},
		{"label": "Stock Entry", "fieldname": "stock_entry", "fieldtype": "Link", "options": "Stock Entry", "width": 140},
	]


def get_data(filters):
	conditions = []
	values = {}

	# Only submitted
	conditions.append("b.docstatus = 1")

	if filters.get("wine_batch"):
		conditions.append("b.wine_batch = %(wine_batch)s")
		values["wine_batch"] = filters["wine_batch"]

	if filters.get("abv_tax_band"):
		conditions.append("b.abv_tax_band = %(abv_tax_band)s")
		values["abv_tax_band"] = filters["abv_tax_band"]

	if filters.get("from_date"):
		conditions.append("b.bottling_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]

	if filters.get("to_date"):
		conditions.append("b.bottling_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	where = "WHERE " + " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT
			b.name,
			b.wine_batch,
			b.bottling_date,
			b.input_quantity,
			b.total_volume_bottled,
			b.process_loss,
			b.yield_efficiency_pct,
			b.abv_percentage,
			b.abv_tax_band,
			b.excise_duty_per_litre,
			b.excise_duty_amount,
			b.stock_entry
		FROM `tabBottling` b
		{where}
		ORDER BY b.bottling_date DESC
		""",
		values,
		as_dict=True,
	)

	# Flag low-yield rows for visibility
	for row in rows:
		if flt(row.yield_efficiency_pct) < 85:
			row["yield_efficiency_pct"] = frappe.bold(str(row.yield_efficiency_pct) + "%  ⚠")

	return rows


def get_filters():
	return [
		{
			"fieldname": "wine_batch",
			"label": "Wine Batch",
			"fieldtype": "Link",
			"options": "Wine Batch",
		},
		{
			"fieldname": "abv_tax_band",
			"label": "Tax Band",
			"fieldtype": "Link",
			"options": "ABV Tax Band",
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
