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
		{"label": "Wine Batch", "fieldname": "wine_batch", "fieldtype": "Link", "options": "Wine Batch", "width": 160},
		{"label": "Recipe", "fieldname": "recipe", "fieldtype": "Link", "options": "Recipe", "width": 150},
		{"label": "Start Date", "fieldname": "start_date", "fieldtype": "Date", "width": 100},
		{"label": "ABV %", "fieldname": "abv_percentage", "fieldtype": "Float", "width": 70},
		{"label": "Tax Band", "fieldname": "abv_tax_band", "fieldtype": "Link", "options": "ABV Tax Band", "width": 150},
		{"label": "Duty / Litre", "fieldname": "excise_duty_per_litre", "fieldtype": "Currency", "width": 110},
		# Bottle line detail
		{"label": "Bottle Item", "fieldname": "bottle_item", "fieldtype": "Link", "options": "Item", "width": 160},
		{"label": "Size (ml)", "fieldname": "bottle_size_ml", "fieldtype": "Int", "width": 80},
		{"label": "Planned Bottles", "fieldname": "planned_bottles", "fieldtype": "Int", "width": 120},
		{"label": "Actual Bottles", "fieldname": "actual_bottles", "fieldtype": "Int", "width": 110},
		{"label": "Net Bottles", "fieldname": "net_bottles", "fieldtype": "Int", "width": 100},
		{"label": "Vol This Line (L)", "fieldname": "volume_litres", "fieldtype": "Float", "width": 130},
		# Packaging for this bottle size
		{"label": "Pack Size", "fieldname": "pack_size", "fieldtype": "Data", "width": 100},
		{"label": "Btls / Carton", "fieldname": "bottles_per_carton", "fieldtype": "Int", "width": 100},
		{"label": "Planned Cartons", "fieldname": "planned_cartons", "fieldtype": "Int", "width": 120},
		{"label": "Actual Cartons", "fieldname": "actual_cartons", "fieldtype": "Int", "width": 110},
		# Valuation
		{"label": "Excise / Bottle", "fieldname": "excise_per_bottle", "fieldtype": "Currency", "width": 120},
		{"label": "Excise / Carton", "fieldname": "excise_per_carton", "fieldtype": "Currency", "width": 120},
		{"label": "Total Line Excise", "fieldname": "total_line_excise", "fieldtype": "Currency", "width": 130},
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

	if filters.get("wine_batch"):
		conditions.append("wb.name = %(wine_batch)s")
		values["wine_batch"] = filters["wine_batch"]

	if filters.get("recipe"):
		conditions.append("wb.recipe = %(recipe)s")
		values["recipe"] = filters["recipe"]

	if filters.get("abv_tax_band"):
		conditions.append("wb.abv_tax_band = %(abv_tax_band)s")
		values["abv_tax_band"] = filters["abv_tax_band"]

	where = "WHERE " + " AND ".join(conditions)

	# Fetch wine batch headers
	batches = frappe.db.sql(
		f"""
		SELECT
			wb.name,
			wb.recipe,
			wb.start_date,
			wb.abv_percentage,
			wb.abv_tax_band,
			wb.excise_duty_per_litre,
			wb.total_volume_bottled
		FROM `tabWine Batch` wb
		{where}
		ORDER BY wb.start_date DESC
		""",
		values,
		as_dict=True,
	)

	if not batches:
		return []

	batch_names = [b.name for b in batches]
	placeholders = ", ".join(["%s"] * len(batch_names))

	# Fetch bottling lines
	bottle_lines = frappe.db.sql(
		f"""
		SELECT
			parent AS wine_batch,
			bottle_item,
			bottle_size_ml,
			planned_bottles,
			actual_bottles,
			net_bottles,
			volume_litres
		FROM `tabWine Batch Bottling Line`
		WHERE parent IN ({placeholders})
		ORDER BY parent, bottle_size_ml
		""",
		batch_names,
		as_dict=True,
	)

	# Fetch packaging lines
	pack_lines = frappe.db.sql(
		f"""
		SELECT
			parent AS wine_batch,
			pack_size,
			bottle_size_ml,
			bottles_per_carton,
			cartons AS planned_cartons,
			actual_cartons
		FROM `tabWine Batch Packaging Line`
		WHERE parent IN ({placeholders})
		ORDER BY parent, bottle_size_ml
		""",
		batch_names,
		as_dict=True,
	)

	# Build packaging lookup: (wine_batch, bottle_size_ml) -> pack line
	pack_map = {}
	for pl in pack_lines:
		key = (pl.wine_batch, flt(pl.bottle_size_ml))
		pack_map.setdefault(key, []).append(pl)

	# Build batch header lookup
	batch_map = {b.name: b for b in batches}

	result = []
	for bl in bottle_lines:
		wb = batch_map[bl.wine_batch]
		duty_per_litre = flt(wb.excise_duty_per_litre)
		size_ml = flt(bl.bottle_size_ml)
		size_l = size_ml / 1000.0

		excise_per_bottle = round(duty_per_litre * size_l, 4)
		net_bottles = flt(bl.net_bottles)
		vol_litres = flt(bl.volume_litres)
		total_line_excise = round(duty_per_litre * vol_litres, 4)

		# Get matching packaging lines for this bottle size
		pack_entries = pack_map.get((bl.wine_batch, size_ml), [{}])

		for pack in pack_entries:
			btls_per_carton = flt(pack.get("bottles_per_carton", 0))
			excise_per_carton = round(excise_per_bottle * btls_per_carton, 4) if btls_per_carton else 0.0

			result.append({
				"wine_batch": bl.wine_batch,
				"recipe": wb.recipe,
				"start_date": wb.start_date,
				"abv_percentage": wb.abv_percentage,
				"abv_tax_band": wb.abv_tax_band,
				"excise_duty_per_litre": duty_per_litre,
				"bottle_item": bl.bottle_item,
				"bottle_size_ml": int(size_ml),
				"planned_bottles": flt(bl.planned_bottles),
				"actual_bottles": flt(bl.actual_bottles),
				"net_bottles": net_bottles,
				"volume_litres": vol_litres,
				"pack_size": pack.get("pack_size", "—"),
				"bottles_per_carton": int(btls_per_carton),
				"planned_cartons": flt(pack.get("planned_cartons", 0)),
				"actual_cartons": flt(pack.get("actual_cartons", 0)),
				"excise_per_bottle": excise_per_bottle,
				"excise_per_carton": excise_per_carton,
				"total_line_excise": total_line_excise,
			})

	return result


def get_filters():
	return [
		{"fieldname": "from_date", "label": "From Date", "fieldtype": "Date"},
		{"fieldname": "to_date", "label": "To Date", "fieldtype": "Date"},
		{"fieldname": "wine_batch", "label": "Wine Batch", "fieldtype": "Link", "options": "Wine Batch"},
		{"fieldname": "recipe", "label": "Recipe", "fieldtype": "Link", "options": "Recipe"},
		{"fieldname": "abv_tax_band", "label": "Tax Band", "fieldtype": "Link", "options": "ABV Tax Band"},
	]
