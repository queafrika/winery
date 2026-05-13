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
		{"label": "Item Code", "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 160},
		{"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data", "width": 200},
		{"label": "Item Group", "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 130},
		{"label": "Warehouse", "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 180},
		{"label": "UOM", "fieldname": "stock_uom", "fieldtype": "Link", "options": "UOM", "width": 70},
		{"label": "Actual Qty", "fieldname": "actual_qty", "fieldtype": "Float", "width": 100},
		{"label": "Reserved Qty", "fieldname": "reserved_qty", "fieldtype": "Float", "width": 110},
		{"label": "Ordered Qty", "fieldname": "ordered_qty", "fieldtype": "Float", "width": 100},
		{"label": "Projected Qty", "fieldname": "projected_qty", "fieldtype": "Float", "width": 110},
		{"label": "Valuation Rate", "fieldname": "valuation_rate", "fieldtype": "Currency", "width": 120},
		{"label": "Stock Value", "fieldname": "stock_value", "fieldtype": "Currency", "width": 120},
		{"label": "Reorder Level", "fieldname": "reorder_level", "fieldtype": "Float", "width": 110},
		{"label": "Reorder Qty", "fieldname": "reorder_qty", "fieldtype": "Float", "width": 100},
		{"label": "MR Type", "fieldname": "material_request_type", "fieldtype": "Data", "width": 110},
		{"label": "Status", "fieldname": "reorder_status", "fieldtype": "Data", "width": 130},
	]


def get_data(filters):
	bin_conditions = ["b.actual_qty >= 0"]
	values = {}

	if filters.get("item_code"):
		bin_conditions.append("b.item_code = %(item_code)s")
		values["item_code"] = filters["item_code"]

	if filters.get("item_group"):
		bin_conditions.append("i.item_group = %(item_group)s")
		values["item_group"] = filters["item_group"]

	if filters.get("warehouse"):
		bin_conditions.append("b.warehouse = %(warehouse)s")
		values["warehouse"] = filters["warehouse"]

	where = "WHERE " + " AND ".join(bin_conditions)

	rows = frappe.db.sql(
		f"""
		SELECT
			b.item_code,
			i.item_name,
			i.item_group,
			b.warehouse,
			i.stock_uom,
			b.actual_qty,
			b.reserved_qty,
			b.ordered_qty,
			b.projected_qty,
			b.valuation_rate,
			b.stock_value,
			ir.warehouse_reorder_level AS reorder_level,
			ir.warehouse_reorder_qty AS reorder_qty,
			ir.material_request_type
		FROM `tabBin` b
		LEFT JOIN `tabItem` i ON i.name = b.item_code
		LEFT JOIN `tabItem Reorder` ir ON ir.parent = b.item_code AND ir.warehouse = b.warehouse
		{where}
		ORDER BY i.item_group, b.item_code, b.warehouse
		""",
		values,
		as_dict=True,
	)

	show_below_only = filters.get("show_below_reorder_only")
	result = []

	for row in rows:
		actual = flt(row.actual_qty)
		level = flt(row.reorder_level)

		if level > 0:
			if actual <= level:
				row["reorder_status"] = frappe.bold("Below Reorder Level  ⚠")
			else:
				row["reorder_status"] = "OK"
		else:
			row["reorder_status"] = "No Reorder Set"
			if show_below_only:
				continue

		if show_below_only and row.get("reorder_status") == "OK":
			continue

		result.append(row)

	return result


def get_filters():
	return [
		{"fieldname": "item_code", "label": "Item", "fieldtype": "Link", "options": "Item"},
		{"fieldname": "item_group", "label": "Item Group", "fieldtype": "Link", "options": "Item Group"},
		{"fieldname": "warehouse", "label": "Warehouse", "fieldtype": "Link", "options": "Warehouse"},
		{
			"fieldname": "show_below_reorder_only",
			"label": "Show Below Reorder Only",
			"fieldtype": "Check",
			"default": 0,
		},
	]
