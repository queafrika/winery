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
		{"label": "Recipe", "fieldname": "recipe", "fieldtype": "Link", "options": "Recipe", "width": 150},
		{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 100},
		{"label": "Start Date", "fieldname": "start_date", "fieldtype": "Date", "width": 100},
		{"label": "End Date", "fieldname": "end_date", "fieldtype": "Date", "width": 100},
		# Volume
		{"label": "Target Vol (L)", "fieldname": "target_batch_size", "fieldtype": "Float", "width": 110},
		{"label": "Actual Vol (L)", "fieldname": "total_volume_bottled", "fieldtype": "Float", "width": 110},
		{"label": "Vol Loss (L)", "fieldname": "process_loss", "fieldtype": "Float", "width": 100},
		{"label": "Vol Yield %", "fieldname": "yield_efficiency_pct", "fieldtype": "Percent", "width": 90},
		# Bottles
		{"label": "Planned Bottles", "fieldname": "planned_bottles", "fieldtype": "Int", "width": 120},
		{"label": "Actual Bottles", "fieldname": "actual_bottles", "fieldtype": "Int", "width": 110},
		{"label": "Net Bottles", "fieldname": "net_bottles", "fieldtype": "Int", "width": 100},
		{"label": "Bottle Variance", "fieldname": "bottle_variance", "fieldtype": "Int", "width": 120},
		{"label": "Bottle Yield %", "fieldname": "bottle_yield_pct", "fieldtype": "Float", "width": 110},
		# Packaging
		{"label": "Planned Cartons", "fieldname": "planned_cartons", "fieldtype": "Int", "width": 120},
		{"label": "Actual Cartons", "fieldname": "actual_cartons", "fieldtype": "Int", "width": 110},
		{"label": "Carton Variance", "fieldname": "carton_variance", "fieldtype": "Int", "width": 120},
		{"label": "Remaining Bottles", "fieldname": "remaining_bottles", "fieldtype": "Int", "width": 130},
		# Excise
		{"label": "Excise Duty", "fieldname": "excise_duty_amount", "fieldtype": "Currency", "width": 120},
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

	if filters.get("status"):
		conditions.append("wb.status = %(status)s")
		values["status"] = filters["status"]

	if filters.get("recipe"):
		conditions.append("wb.recipe = %(recipe)s")
		values["recipe"] = filters["recipe"]

	where = "WHERE " + " AND ".join(conditions)

	batches = frappe.db.sql(
		f"""
		SELECT
			wb.name,
			wb.recipe,
			wb.status,
			wb.start_date,
			wb.end_date,
			wb.target_batch_size,
			wb.total_volume_bottled,
			wb.process_loss,
			wb.yield_efficiency_pct,
			wb.excise_duty_amount
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

	# Aggregate bottling lines from Wine Batch Bottling Line
	bottle_rows = frappe.db.sql(
		f"""
		SELECT
			parent AS wine_batch,
			SUM(planned_bottles) AS planned_bottles,
			SUM(actual_bottles) AS actual_bottles,
			SUM(net_bottles) AS net_bottles
		FROM `tabWine Batch Bottling Line`
		WHERE parent IN ({placeholders})
		GROUP BY parent
		""",
		batch_names,
		as_dict=True,
	)
	bottle_map = {r.wine_batch: r for r in bottle_rows}

	# Aggregate packaging lines from Wine Batch Packaging Line
	pack_rows = frappe.db.sql(
		f"""
		SELECT
			parent AS wine_batch,
			SUM(cartons) AS planned_cartons,
			SUM(actual_cartons) AS actual_cartons,
			SUM(remaining_bottles) AS remaining_bottles
		FROM `tabWine Batch Packaging Line`
		WHERE parent IN ({placeholders})
		GROUP BY parent
		""",
		batch_names,
		as_dict=True,
	)
	pack_map = {r.wine_batch: r for r in pack_rows}

	result = []
	for batch in batches:
		b = bottle_map.get(batch.name, {})
		p = pack_map.get(batch.name, {})

		planned = flt(b.get("planned_bottles"))
		actual = flt(b.get("actual_bottles"))
		net = flt(b.get("net_bottles"))
		bottle_variance = actual - planned
		bottle_yield_pct = round(actual / planned * 100, 2) if planned else 0.0

		planned_cartons = flt(p.get("planned_cartons"))
		actual_cartons = flt(p.get("actual_cartons"))
		carton_variance = actual_cartons - planned_cartons

		row = {
			**batch,
			"planned_bottles": int(planned),
			"actual_bottles": int(actual),
			"net_bottles": int(net),
			"bottle_variance": int(bottle_variance),
			"bottle_yield_pct": bottle_yield_pct,
			"planned_cartons": int(planned_cartons),
			"actual_cartons": int(actual_cartons),
			"carton_variance": int(carton_variance),
			"remaining_bottles": int(flt(p.get("remaining_bottles"))),
		}

		# Flag low bottle yield
		if bottle_yield_pct and bottle_yield_pct < 90:
			row["bottle_yield_pct"] = frappe.bold(f"{bottle_yield_pct}%  ⚠")

		result.append(row)

	return result


def get_filters():
	return [
		{"fieldname": "from_date", "label": "From Date", "fieldtype": "Date"},
		{"fieldname": "to_date", "label": "To Date", "fieldtype": "Date"},
		{
			"fieldname": "status",
			"label": "Status",
			"fieldtype": "Select",
			"options": "\nActive\nCompleted\nCancelled",
		},
		{"fieldname": "recipe", "label": "Recipe", "fieldtype": "Link", "options": "Recipe"},
	]
