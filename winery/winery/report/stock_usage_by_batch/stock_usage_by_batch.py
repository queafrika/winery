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
		{"label": "Batch No", "fieldname": "batch_no", "fieldtype": "Link", "options": "Batch", "width": 160},
		{"label": "Item Code", "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 160},
		{"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data", "width": 200},
		{"label": "Warehouse", "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 180},
		{"label": "UOM", "fieldname": "stock_uom", "fieldtype": "Link", "options": "UOM", "width": 70},
		{"label": "Qty Used", "fieldname": "qty_used", "fieldtype": "Float", "width": 100},
		{"label": "Qty Received", "fieldname": "qty_received", "fieldtype": "Float", "width": 110},
		{"label": "Net Qty Movement", "fieldname": "net_qty", "fieldtype": "Float", "width": 130},
		{"label": "Value Used", "fieldname": "value_used", "fieldtype": "Currency", "width": 120},
		{"label": "Value Received", "fieldname": "value_received", "fieldtype": "Currency", "width": 130},
		{"label": "Net Value", "fieldname": "net_value", "fieldtype": "Currency", "width": 110},
		{"label": "Avg Valuation Rate", "fieldname": "avg_valuation_rate", "fieldtype": "Currency", "width": 140},
	]


def get_data(filters):
	conditions = ["sle.is_cancelled = 0", "sle.batch_no IS NOT NULL", "sle.batch_no != ''"]
	values = {}

	if filters.get("from_date"):
		conditions.append("sle.posting_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]

	if filters.get("to_date"):
		conditions.append("sle.posting_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	if filters.get("batch_no"):
		conditions.append("sle.batch_no = %(batch_no)s")
		values["batch_no"] = filters["batch_no"]

	if filters.get("warehouse"):
		conditions.append("sle.warehouse = %(warehouse)s")
		values["warehouse"] = filters["warehouse"]

	if filters.get("item_code"):
		conditions.append("sle.item_code = %(item_code)s")
		values["item_code"] = filters["item_code"]

	where = "WHERE " + " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT
			sle.batch_no,
			sle.item_code,
			i.item_name,
			sle.warehouse,
			sle.stock_uom,
			SUM(CASE WHEN sle.actual_qty < 0 THEN ABS(sle.actual_qty) ELSE 0 END) AS qty_used,
			SUM(CASE WHEN sle.actual_qty > 0 THEN sle.actual_qty ELSE 0 END) AS qty_received,
			SUM(sle.actual_qty) AS net_qty,
			SUM(CASE WHEN sle.stock_value_difference < 0 THEN ABS(sle.stock_value_difference) ELSE 0 END) AS value_used,
			SUM(CASE WHEN sle.stock_value_difference > 0 THEN sle.stock_value_difference ELSE 0 END) AS value_received,
			SUM(sle.stock_value_difference) AS net_value,
			AVG(sle.valuation_rate) AS avg_valuation_rate
		FROM `tabStock Ledger Entry` sle
		LEFT JOIN `tabItem` i ON i.name = sle.item_code
		{where}
		GROUP BY sle.batch_no, sle.item_code, sle.warehouse
		ORDER BY sle.batch_no, sle.item_code
		""",
		values,
		as_dict=True,
	)

	for row in rows:
		row["qty_used"] = flt(row.qty_used, 3)
		row["qty_received"] = flt(row.qty_received, 3)
		row["net_qty"] = flt(row.net_qty, 3)
		row["avg_valuation_rate"] = flt(row.avg_valuation_rate, 4)

	return rows


def get_filters():
	return [
		{"fieldname": "from_date", "label": "From Date", "fieldtype": "Date"},
		{"fieldname": "to_date", "label": "To Date", "fieldtype": "Date"},
		{"fieldname": "batch_no", "label": "Batch No", "fieldtype": "Link", "options": "Batch"},
		{"fieldname": "warehouse", "label": "Warehouse", "fieldtype": "Link", "options": "Warehouse"},
		{"fieldname": "item_code", "label": "Item", "fieldtype": "Link", "options": "Item"},
	]
