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
		{"label": "Tax Band", "fieldname": "abv_tax_band", "fieldtype": "Link", "options": "ABV Tax Band", "width": 180},
		{"label": "Band Name", "fieldname": "band_name", "fieldtype": "Data", "width": 160},
		{"label": "Min ABV %", "fieldname": "min_abv", "fieldtype": "Float", "width": 90},
		{"label": "Max ABV %", "fieldname": "max_abv", "fieldtype": "Float", "width": 90},
		{"label": "Duty / L Pure Alcohol", "fieldname": "excise_duty_per_dl", "fieldtype": "Currency", "width": 150},
		{"label": "Bottlings", "fieldname": "bottling_count", "fieldtype": "Int", "width": 90},
		{"label": "Total Volume (L)", "fieldname": "total_volume_bottled", "fieldtype": "Float", "width": 130},
		{"label": "Total Excise Duty", "fieldname": "total_excise_duty", "fieldtype": "Currency", "width": 150},
	]


def get_data(filters):
	conditions = ["b.docstatus = 1"]
	values = {}

	if filters.get("from_date"):
		conditions.append("b.bottling_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]

	if filters.get("to_date"):
		conditions.append("b.bottling_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	if filters.get("abv_tax_band"):
		conditions.append("b.abv_tax_band = %(abv_tax_band)s")
		values["abv_tax_band"] = filters["abv_tax_band"]

	where = "WHERE " + " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT
			b.abv_tax_band,
			atb.band_name,
			atb.min_abv,
			atb.max_abv,
			b.excise_duty_per_dl,
			COUNT(b.name) AS bottling_count,
			SUM(b.total_volume_bottled) AS total_volume_bottled,
			SUM(b.excise_duty_amount) AS total_excise_duty
		FROM `tabBottling` b
		LEFT JOIN `tabABV Tax Band` atb ON atb.name = b.abv_tax_band
		{where}
		GROUP BY b.abv_tax_band
		ORDER BY atb.min_abv
		""",
		values,
		as_dict=True,
	)


def get_filters():
	return [
		{"fieldname": "from_date", "label": "From Date", "fieldtype": "Date"},
		{"fieldname": "to_date", "label": "To Date", "fieldtype": "Date"},
		{"fieldname": "abv_tax_band", "label": "Tax Band", "fieldtype": "Link", "options": "ABV Tax Band"},
	]
