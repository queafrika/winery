"""Web order lifecycle: cart -> Ropen Web Order -> M-Pesa -> Sales Order.

A Ropen Web Order is created up front and holds the shopper's details and the
server-priced cart. Only once M-Pesa confirms payment do we touch ERPNext
selling documents, so the Sales Order list stays free of abandoned carts.
"""

import re

import frappe
from frappe import _
from frappe.utils import add_days, cstr, flt, nowdate

from winery.ecommerce.cart import price_cart
from winery.ecommerce.constants import money, WEB_CUSTOMER_GROUP, WEB_TERRITORY
from winery.winery.pos.constants import KENYA_TAX_TEMPLATE_TITLE
from winery.winery.pos.mpesa import normalise_phone

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")


def create_web_order(contact, lines):
	"""Validate the shopper's details, re-price the cart and persist the order.

	Returns the inserted Ropen Web Order document.
	"""
	contact = _validate_contact(contact)
	priced = price_cart(lines)

	if not priced["lines"]:
		frappe.throw(_("Your basket is empty."), title=_("Nothing to pay for"))
	if priced["total"] <= 0:
		frappe.throw(_("This order has no payable amount."))

	order = frappe.new_doc("Ropen Web Order")
	order.status = "Pending Payment"
	order.customer_name = contact["customer_name"]
	order.phone = contact["phone"]
	order.email = contact["email"]
	order.delivery_address = contact["delivery_address"]
	order.town = contact["town"]
	order.delivery_notes = contact["delivery_notes"]
	order.currency = "KES"

	for line in priced["lines"]:
		order.append(
			"items",
			{
				"item_code": line["item_code"],
				"item_name": line["item_name"],
				"item_group": line["item_group"],
				"qty": line["qty"],
				"uom": line["uom"],
				"rate": line["rate"],
			},
		)

	order.flags.ignore_permissions = True
	order.insert()
	return order


def finalise_paid_order(order_name, receipt=None, mpesa_request=None):
	"""Mark an order paid and post the ERPNext Customer + Sales Order.

	Idempotent: an order that already has a Sales Order is left alone, so a
	replayed Safaricom callback or the reconciliation cron cannot double-post.
	"""
	order = frappe.get_doc("Ropen Web Order", order_name)
	if order.sales_order:
		return order.sales_order

	customer = _resolve_customer(order)
	so = _create_sales_order(order, customer)

	order.db_set(
		{
			"status": "Paid",
			"customer": customer,
			"sales_order": so,
			"mpesa_receipt_number": receipt or order.mpesa_receipt_number,
			"mpesa_request": mpesa_request or order.mpesa_request,
		},
		update_modified=True,
	)
	frappe.db.commit()

	_notify(order.name)
	return so


def mark_order_failed(order_name, reason=None):
	order = frappe.get_doc("Ropen Web Order", order_name)
	if order.status in ("Paid", "Failed"):
		return
	order.db_set({"status": "Failed", "failure_reason": cstr(reason)[:500]}, update_modified=True)
	frappe.db.commit()


def get_public_order(order_token):
	"""Order summary for the confirmation page, keyed by the unguessable token."""
	name = frappe.db.get_value("Ropen Web Order", {"order_token": order_token}, "name")
	if not name:
		return None

	order = frappe.get_doc("Ropen Web Order", name)
	return {
		"order_id": order.name,
		"status": order.status,
		"customer_name": order.customer_name,
		"phone": order.phone,
		"email": order.email,
		"delivery_address": order.delivery_address,
		"town": order.town,
		"order_date": order.order_date,
		"total": flt(order.total),
		"total_formatted": money(order.total),
		"mpesa_receipt_number": order.mpesa_receipt_number,
		"failure_reason": order.failure_reason,
		"items": [
			{
				"item_name": r.item_name,
				"qty": r.qty,
				"uom": r.uom,
				"rate_formatted": money(r.rate),
				"amount_formatted": money(r.amount),
			}
			for r in order.items
		],
	}


# --------------------------------------------------------------------------- #
# internals
# --------------------------------------------------------------------------- #
def _validate_contact(contact):
	if isinstance(contact, str):
		contact = frappe.parse_json(contact)
	contact = contact or {}

	name = cstr(contact.get("customer_name")).strip()
	if len(name) < 2:
		frappe.throw(_("Please enter your full name."))

	phone = normalise_phone(contact.get("phone"))

	email = cstr(contact.get("email")).strip()
	if email and not EMAIL_RE.match(email):
		frappe.throw(_("Please enter a valid email address."))

	address = cstr(contact.get("delivery_address")).strip()
	if len(address) < 5:
		frappe.throw(_("Please enter a delivery address so we know where to send your order."))

	return {
		"customer_name": name[:140],
		"phone": phone,
		"email": email[:140],
		"delivery_address": address[:500],
		"town": cstr(contact.get("town")).strip()[:140],
		"delivery_notes": cstr(contact.get("delivery_notes")).strip()[:500],
	}


def _resolve_customer(order):
	"""Find an existing web customer by phone, else create one."""
	existing = frappe.db.get_value("Customer", {"custom_web_phone": order.phone}, "name")
	if existing:
		return existing

	customer = frappe.new_doc("Customer")
	customer.customer_name = order.customer_name
	customer.customer_type = "Individual"
	customer.customer_group = _group()
	customer.territory = _territory()
	customer.custom_web_phone = order.phone
	if order.email:
		customer.email_id = order.email
	customer.mobile_no = order.phone
	customer.flags.ignore_permissions = True
	customer.flags.ignore_mandatory = True
	customer.insert()
	return customer.name


def _create_sales_order(order, customer):
	company = _company()

	so = frappe.new_doc("Sales Order")
	so.customer = customer
	so.company = company
	so.order_type = "Sales"
	so.transaction_date = nowdate()
	so.delivery_date = add_days(nowdate(), 3)
	so.currency = "KES"
	so.selling_price_list = "Standard Selling"
	so.territory = _territory()
	so.customer_group = _group()
	so.set_warehouse = _warehouse(company)
	so.po_no = order.name  # traceability back to the web order

	for row in order.items:
		so.append(
			"items",
			{
				"item_code": row.item_code,
				"item_name": row.item_name,
				"qty": row.qty,
				"uom": row.uom,
				"rate": row.rate,
				"delivery_date": so.delivery_date,
				"warehouse": so.set_warehouse,
			},
		)

	_apply_shipping_address(so, order)
	so.run_method("set_missing_values")
	_apply_sales_taxes(so, company)
	so.run_method("calculate_taxes_and_totals")

	so.flags.ignore_permissions = True
	_prev_mute = frappe.flags.mute_messages
	frappe.flags.mute_messages = True
	try:
		so.insert()
		so.submit()
	finally:
		frappe.flags.mute_messages = _prev_mute

	return so.name


def _apply_shipping_address(so, order):
	"""Best-effort: attach the typed delivery address as a real Address record.

	Never blocks the order — if Address creation fails we still keep the raw text
	on the Ropen Web Order for the fulfilment team.
	"""
	try:
		address = frappe.new_doc("Address")
		address.address_title = f"{order.customer_name} ({order.name})"
		address.address_type = "Shipping"
		address.address_line1 = (order.delivery_address or "").splitlines()[0][:240]
		rest = "\n".join((order.delivery_address or "").splitlines()[1:]).strip()
		if rest:
			address.address_line2 = rest[:240]
		address.city = order.town or "Nairobi"
		address.country = "Kenya"
		address.phone = order.phone
		if order.email:
			address.email_id = order.email
		address.append("links", {"link_doctype": "Customer", "link_name": so.customer})
		address.flags.ignore_permissions = True
		address.flags.ignore_mandatory = True
		address.insert()
		so.shipping_address_name = address.name
		so.customer_address = address.name
	except Exception:  # noqa: BLE001 - address is a convenience, not a gate
		frappe.log_error(frappe.get_traceback(), "Ropen web order address")


def _apply_sales_taxes(so, company):
	"""Attach Kenya VAT as INCLUSIVE, matching the POS engine.

	The shopper paid exactly the cart total via M-Pesa, so VAT must be
	back-calculated out of the rate rather than added on top.
	"""
	if so.get("taxes"):
		return

	template = frappe.db.get_value(
		"Sales Taxes and Charges Template",
		{"company": company, "name": ["like", f"{KENYA_TAX_TEMPLATE_TITLE}%"], "disabled": 0},
		"name",
	)
	if not template:
		return

	from erpnext.controllers.accounts_controller import get_taxes_and_charges

	so.taxes_and_charges = template
	for row in get_taxes_and_charges("Sales Taxes and Charges Template", template):
		row["included_in_print_rate"] = 1
		so.append("taxes", row)


def _notify(order_name):
	"""Fire the 'new web order' notification without ever failing the payment."""
	try:
		frappe.publish_realtime("ropen_web_order_paid", {"order": order_name})
	except Exception:  # noqa: BLE001
		pass


def _company():
	return (
		frappe.db.get_single_value("Global Defaults", "default_company")
		or frappe.db.get_value("Company", {}, "name")
	)


def _group():
	return (
		WEB_CUSTOMER_GROUP
		if frappe.db.exists("Customer Group", WEB_CUSTOMER_GROUP)
		else frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
	)


def _territory():
	return (
		WEB_TERRITORY
		if frappe.db.exists("Territory", WEB_TERRITORY)
		else frappe.db.get_value("Territory", {"is_group": 0}, "name")
	)


def _warehouse(company):
	for candidate in ("Finished Goods", "Stores"):
		name = frappe.db.get_value(
			"Warehouse", {"company": company, "warehouse_name": candidate, "is_group": 0}, "name"
		)
		if name:
			return name
	return frappe.db.get_value("Warehouse", {"company": company, "is_group": 0}, "name")
