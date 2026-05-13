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
		{"label": "Invoice", "fieldname": "name", "fieldtype": "Link", "options": "Purchase Invoice", "width": 160},
		{"label": "Posting Date", "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 160},
		{"label": "Bill No", "fieldname": "bill_no", "fieldtype": "Data", "width": 120},
		{"label": "Bill Date", "fieldname": "bill_date", "fieldtype": "Date", "width": 100},
		{"label": "Due Date", "fieldname": "due_date", "fieldtype": "Date", "width": 100},
		{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 100},
		{"label": "Item Code", "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 160},
		{"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data", "width": 180},
		{"label": "Item Group", "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 130},
		{"label": "Qty", "fieldname": "qty", "fieldtype": "Float", "width": 80},
		{"label": "UOM", "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 70},
		{"label": "Rate", "fieldname": "rate", "fieldtype": "Currency", "width": 100},
		{"label": "Amount", "fieldname": "amount", "fieldtype": "Currency", "width": 110},
		{"label": "Net Amount", "fieldname": "net_amount", "fieldtype": "Currency", "width": 110},
		{"label": "Warehouse", "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 150},
		{"label": "Batch No", "fieldname": "batch_no", "fieldtype": "Link", "options": "Batch", "width": 130},
		{"label": "Expense Account", "fieldname": "expense_account", "fieldtype": "Link", "options": "Account", "width": 180},
		{"label": "Invoice Total", "fieldname": "grand_total", "fieldtype": "Currency", "width": 120},
		{"label": "Outstanding", "fieldname": "outstanding_amount", "fieldtype": "Currency", "width": 120},
	]


def get_data(filters):
	conditions = ["pi.docstatus = 1"]
	values = {}

	if filters.get("from_date"):
		conditions.append("pi.posting_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]

	if filters.get("to_date"):
		conditions.append("pi.posting_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	if filters.get("supplier"):
		conditions.append("pi.supplier = %(supplier)s")
		values["supplier"] = filters["supplier"]

	if filters.get("item_code"):
		conditions.append("pii.item_code = %(item_code)s")
		values["item_code"] = filters["item_code"]

	if filters.get("item_group"):
		conditions.append("pii.item_group = %(item_group)s")
		values["item_group"] = filters["item_group"]

	if filters.get("warehouse"):
		conditions.append("pii.warehouse = %(warehouse)s")
		values["warehouse"] = filters["warehouse"]

	where = "WHERE " + " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT
			pi.name,
			pi.posting_date,
			pi.supplier,
			pi.bill_no,
			pi.bill_date,
			pi.due_date,
			pi.status,
			pii.item_code,
			pii.item_name,
			pii.item_group,
			pii.qty,
			pii.uom,
			pii.rate,
			pii.amount,
			pii.net_amount,
			pii.warehouse,
			pii.batch_no,
			pii.expense_account,
			pi.grand_total,
			pi.outstanding_amount
		FROM `tabPurchase Invoice` pi
		INNER JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
		{where}
		ORDER BY pi.posting_date DESC, pi.name, pii.idx
		""",
		values,
		as_dict=True,
	)


def get_filters():
	return [
		{"fieldname": "from_date", "label": "From Date", "fieldtype": "Date"},
		{"fieldname": "to_date", "label": "To Date", "fieldtype": "Date"},
		{"fieldname": "supplier", "label": "Supplier", "fieldtype": "Link", "options": "Supplier"},
		{"fieldname": "item_code", "label": "Item", "fieldtype": "Link", "options": "Item"},
		{"fieldname": "item_group", "label": "Item Group", "fieldtype": "Link", "options": "Item Group"},
		{"fieldname": "warehouse", "label": "Warehouse", "fieldtype": "Link", "options": "Warehouse"},
	]
