"""M-Pesa for the storefront.

Reuses the POS Daraja client (`winery.winery.pos.mpesa`) so there is exactly one
STK Push implementation, one callback endpoint and one reconciliation cron in
the system. This module only owns the web order <-> payment request handshake.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from winery.ecommerce.order import finalise_paid_order, mark_order_failed
from winery.winery.pos import mpesa

# How long a shopper's STK prompt stays actionable before we call it expired.
CHECKOUT_TIMEOUT_SECONDS = 180


def request_payment(order):
	"""Push the STK prompt for a Ropen Web Order and link the payment request."""
	result = mpesa.stk_push(
		phone=order.phone,
		amount=flt(order.total),
		pos_client_uuid=order.name,
		account_reference=order.name.replace("ROPEN-WEB-", "RW")[:12],
		description="Ropen online order",
	)

	checkout_id = result.get("checkout_request_id")
	request_name = frappe.db.get_value(
		"Winery Mpesa Payment Request", {"checkout_request_id": checkout_id}, "name"
	)

	order.db_set(
		{"checkout_request_id": checkout_id, "mpesa_request": request_name},
		update_modified=False,
	)
	frappe.db.commit()

	return {"checkout_request_id": checkout_id, "status": "Pending"}


def poll(order_token):
	"""Status for the checkout page's poller. Never leaks other shoppers' data."""
	order = frappe.db.get_value(
		"Ropen Web Order",
		{"order_token": order_token},
		["name", "status", "checkout_request_id", "mpesa_receipt_number", "failure_reason"],
		as_dict=True,
	)
	if not order:
		frappe.throw(_("Unknown order."), frappe.DoesNotExistError)

	if order.status == "Pending Payment" and order.checkout_request_id:
		_sync_from_payment_request(order)
		order = frappe.db.get_value(
			"Ropen Web Order",
			order.name,
			["name", "status", "mpesa_receipt_number", "failure_reason"],
			as_dict=True,
		)

	return {
		"status": order.status,
		"mpesa_receipt_number": order.mpesa_receipt_number,
		"message": order.failure_reason,
		"redirect": f"/order/{order_token}" if order.status != "Pending Payment" else None,
	}


def on_payment_request_update(doc, method=None):
	"""Doc event on Winery Mpesa Payment Request — settle the matching web order.

	Safaricom's callback lands in the shared POS handler; this hook is what turns
	that into a Sales Order for web sales. Wrapped so a failure here can never
	break the webhook or the POS flow.
	"""
	if doc.status not in ("Success", "Failed", "Timeout"):
		return

	order_name = frappe.db.get_value(
		"Ropen Web Order",
		{"checkout_request_id": doc.checkout_request_id, "status": "Pending Payment"},
		"name",
	)
	if not order_name:
		return

	try:
		if doc.status == "Success":
			frappe.db.set_value(
				"Ropen Web Order", order_name, "mpesa_receipt_number", doc.mpesa_receipt_number
			)
			finalise_paid_order(order_name, receipt=doc.mpesa_receipt_number, mpesa_request=doc.name)
		else:
			mark_order_failed(order_name, doc.result_desc or doc.status)
	except Exception:  # noqa: BLE001 - never fail the payment webhook
		frappe.log_error(frappe.get_traceback(), "Ropen web order settlement")


def expire_stale_orders():
	"""Scheduled sweep: orders whose STK prompt was never answered.

	Runs after the POS reconciliation cron has had a chance to resolve the
	underlying payment request, so a slow-but-successful payment still wins.
	"""
	stale = frappe.get_all(
		"Ropen Web Order",
		filters={
			"status": "Pending Payment",
			"creation": ("<", frappe.utils.add_to_date(None, minutes=-20)),
		},
		fields=["name", "checkout_request_id"],
		limit=200,
	)
	for order in stale:
		status = (
			frappe.db.get_value(
				"Winery Mpesa Payment Request",
				{"checkout_request_id": order.checkout_request_id},
				["status", "mpesa_receipt_number", "name"],
				as_dict=True,
			)
			if order.checkout_request_id
			else None
		)

		if status and status.status == "Success":
			try:
				finalise_paid_order(
					order.name, receipt=status.mpesa_receipt_number, mpesa_request=status.name
				)
			except Exception:  # noqa: BLE001
				frappe.log_error(frappe.get_traceback(), "Ropen web order late settlement")
			continue

		frappe.db.set_value(
			"Ropen Web Order",
			order.name,
			{"status": "Expired", "failure_reason": "No M-Pesa confirmation received."},
		)
	frappe.db.commit()


def _sync_from_payment_request(order):
	"""Pull the latest payment request state in case the doc event was missed."""
	req = frappe.db.get_value(
		"Winery Mpesa Payment Request",
		{"checkout_request_id": order.checkout_request_id},
		["name", "status", "mpesa_receipt_number", "result_desc"],
		as_dict=True,
	)
	if not req or req.status == "Pending":
		return

	try:
		if req.status == "Success":
			frappe.db.set_value(
				"Ropen Web Order", order.name, "mpesa_receipt_number", req.mpesa_receipt_number
			)
			finalise_paid_order(order.name, receipt=req.mpesa_receipt_number, mpesa_request=req.name)
		else:
			mark_order_failed(order.name, req.result_desc or req.status)
	except Exception:  # noqa: BLE001
		frappe.log_error(frappe.get_traceback(), "Ropen web order poll settlement")


def is_configured():
	"""Whether M-Pesa credentials are live, so the UI can say so honestly."""
	settings = frappe.get_cached_doc("Winery Mpesa Settings")
	return bool(
		cint(settings.enabled)
		and settings.shortcode
		and settings.callback_url
		and settings.get_password("consumer_key", raise_exception=False)
	)
