"""Guest-facing endpoints for the Ropen storefront.

Everything here is reachable by anonymous shoppers, so each entry point is
rate-limited and treats its input as hostile. Prices, totals and item
availability are always recomputed server-side.
"""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint

from winery.ecommerce import catalog, payments
from winery.ecommerce.cart import price_cart
from winery.ecommerce.order import create_web_order, get_public_order


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=120, seconds=60)
def get_cart(items=None):
	"""Re-price a browser cart. Returns lines, totals and any adjustment notes."""
	return price_cart(items)


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=120, seconds=60)
def search_products(group=None, search=None, sort="featured", limit=48):
	"""Live product search / filtering for the shop page."""
	products = catalog.get_products(
		group=group, search=search, sort=sort, limit=min(cint(limit) or 48, 96)
	)
	return {
		"products": [
			{
				"item_code": p["item_code"],
				"item_name": p["item_name"],
				"item_group": p["item_group"],
				"department": p["department"],
				"image": p["image"],
				"route": p["route"],
				"price": p["price"],
				"price_formatted": p["price_formatted"],
				"in_stock": p["in_stock"],
				"short_description": p["short_description"],
			}
			for p in products
		],
		"count": len(products),
	}


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=10, seconds=60)
def start_checkout(contact, items):
	"""Create the web order and trigger the M-Pesa STK prompt.

	Returns the order token the checkout page polls on. If the STK push fails we
	mark the order failed rather than leaving a ghost 'Pending Payment' row.
	"""
	if not payments.is_configured():
		frappe.throw(
			_("Online payment is not available right now. Please call us to place your order."),
			title=_("M-Pesa unavailable"),
		)

	order = create_web_order(contact, items)

	try:
		payments.request_payment(order)
	except Exception:
		frappe.db.rollback()
		frappe.db.set_value(
			"Ropen Web Order", order.name, {"status": "Failed", "failure_reason": "STK push failed"}
		)
		frappe.db.commit()
		raise

	return {
		"order_token": order.order_token,
		"order_id": order.name,
		"total": order.total,
		"phone": order.phone,
	}


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=240, seconds=60)
def payment_status(order_token):
	"""Poll for the outcome of the STK prompt."""
	return payments.poll(order_token)


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=30, seconds=60)
def submit_enquiry(name, email, message, phone=None, subject=None):
	"""Contact form -> a Lead the sales team already watches in the ERP."""
	from winery.ecommerce.order import EMAIL_RE

	name = (name or "").strip()
	email = (email or "").strip()
	message = (message or "").strip()

	if len(name) < 2:
		frappe.throw(_("Please tell us your name."))
	if not EMAIL_RE.match(email):
		frappe.throw(_("Please enter a valid email address."))
	if len(message) < 10:
		frappe.throw(_("Please give us a little more detail so we can help."))

	lead = frappe.new_doc("Lead")
	lead.lead_name = name[:140]
	lead.email_id = email[:140]
	lead.mobile_no = (phone or "").strip()[:20]
	lead.request_type = "Product Enquiry"
	lead.status = "Lead"
	# utm_source is a Link; only set it if setup created the record.
	if frappe.db.exists("UTM Source", "Website"):
		lead.utm_source = "Website"
	lead.flags.ignore_permissions = True
	lead.flags.ignore_mandatory = True
	lead.insert()

	# A received Communication (not a Comment — v16 rejects that type here) so the
	# enquiry lands in the Lead's activity timeline and can be replied to in place.
	comm = frappe.new_doc("Communication")
	comm.communication_type = "Communication"
	comm.communication_medium = "Email"
	comm.sent_or_received = "Received"
	comm.reference_doctype = "Lead"
	comm.reference_name = lead.name
	comm.sender = email
	comm.sender_full_name = name
	comm.subject = (subject or "Website enquiry")[:140]
	comm.content = frappe.utils.escape_html(message)[:5000]
	comm.status = "Open"
	comm.flags.ignore_permissions = True
	comm.flags.ignore_mandatory = True
	comm.insert()

	frappe.db.commit()
	return {"ok": True}


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=60, seconds=60)
def order_summary(order_token):
	"""Read-only order view for the confirmation page."""
	order = get_public_order(order_token)
	if not order:
		frappe.throw(_("Order not found."), frappe.DoesNotExistError)
	return order
