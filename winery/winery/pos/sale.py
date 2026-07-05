"""POS sale posting engine.

`create_sale` turns a mobile-app cart payload into a submitted POS Sales Invoice
under the consignment model: stock lives in the agent's own warehouse and revenue is
booked at the moment of the field sale. The same function backs both the online
endpoint and the offline batch-sync endpoint, so it is fully idempotent on
`pos_client_uuid`.

Everything that matters for money or stock — price, discount cap, warehouse, batch —
is resolved server-side from the Sales Agent record. Client-supplied values for those
are ignored.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, cint, nowdate, get_datetime

from winery.winery.doctype.sales_agent.sales_agent import get_agent_for_user
from winery.winery.pos.constants import POS_CUSTOMER_GROUP, ErrorCode


class POSError(frappe.ValidationError):
	"""Business error carrying a machine-readable code for the mobile client."""

	def __init__(self, code, message, detail=None):
		self.error_code = code
		self.detail = detail or {}
		super().__init__(message)


def _fail(code, message, detail=None):
	frappe.local.response["error_code"] = code
	if detail is not None:
		frappe.local.response["error_detail"] = detail
	raise POSError(code, message, detail)


def create_sale(payload, agent=None):
	"""Create and submit one POS Sales Invoice from a cart payload.

	Returns a dict describing the invoice. Idempotent: re-posting the same
	`pos_client_uuid` returns the original invoice with ``duplicate: True``.
	"""
	if isinstance(payload, str):
		payload = json.loads(payload)

	agent = agent or get_agent_for_user()

	uuid = payload.get("pos_client_uuid")
	if not uuid:
		_fail(ErrorCode.PAYMENT_MISMATCH, _("pos_client_uuid is required."))

	# 1. Idempotency — never post the same client sale twice.
	existing = frappe.db.get_value(
		"Sales Invoice", {"pos_client_uuid": uuid}, ["name", "grand_total"], as_dict=True
	)
	if existing:
		return _invoice_result(existing.name, duplicate=True)

	# 2. Resolve customer (explicit > quick-create > agent default walk-in).
	customer = _resolve_customer(payload, agent)

	# 3. Build the POS invoice shell.
	si = frappe.new_doc("Sales Invoice")
	si.customer = customer
	si.is_pos = 1
	si.update_stock = 1
	si.pos_profile = agent.pos_profile
	si.selling_price_list = agent.selling_price_list
	si.set_warehouse = agent.agent_warehouse
	si.pos_sales_agent = agent.name
	si.pos_client_uuid = uuid
	if agent.territory:
		si.territory = agent.territory
	posting = payload.get("posting_datetime")
	if posting:
		dt = get_datetime(posting)
		si.set_posting_time = 1
		si.posting_date = dt.date()
		si.posting_time = dt.time()
	else:
		si.posting_date = nowdate()

	# 4. Lines — price and discount are validated against the agent's price list.
	_append_items(si, payload.get("items") or [], agent)

	# Let ERPNext compute rates/taxes/totals from the price list.
	si.run_method("set_missing_values")
	si.run_method("calculate_taxes_and_totals")

	# 5. Stock availability in the agent warehouse (before we try to submit).
	_validate_stock(si, agent)

	# 6. Payments split (Cash / M-Pesa / Bank) must equal the computed grand total.
	mpesa_requests = _append_payments(si, payload.get("payments") or [], uuid)

	si.flags.ignore_permissions = True
	_prev_mute = frappe.flags.mute_messages
	frappe.flags.mute_messages = True
	try:
		si.insert()
		si.submit()
	finally:
		frappe.flags.mute_messages = _prev_mute

	# 7. Link any M-Pesa STK requests to the posted invoice.
	for req in mpesa_requests:
		frappe.db.set_value(
			"Winery Mpesa Payment Request", req, "sales_invoice", si.name
		)

	return _invoice_result(si.name, duplicate=False)


# --------------------------------------------------------------------------- #
# customer
# --------------------------------------------------------------------------- #
def _resolve_customer(payload, agent):
	if payload.get("customer"):
		return payload["customer"]

	quick = payload.get("quick_customer")
	if quick and quick.get("customer_name"):
		return _get_or_create_quick_customer(quick, agent)

	if not agent.default_customer:
		_fail(ErrorCode.PAYMENT_MISMATCH, _("No customer and no default walk-in customer."))
	return agent.default_customer


def _get_or_create_quick_customer(quick, agent):
	name = quick["customer_name"].strip()
	mobile = (quick.get("mobile_no") or "").strip()
	# Reuse an existing quick customer with the same name + phone if present.
	filters = {"customer_name": name}
	if mobile:
		filters["mobile_no"] = mobile
	existing = frappe.db.get_value("Customer", filters, "name")
	if existing:
		return existing
	cust = frappe.new_doc("Customer")
	cust.customer_name = name
	cust.customer_group = POS_CUSTOMER_GROUP
	cust.customer_type = "Individual"
	if mobile:
		cust.mobile_no = mobile
	if agent.territory:
		cust.territory = agent.territory
	cust.flags.ignore_permissions = True
	cust.insert()
	return cust.name


# --------------------------------------------------------------------------- #
# items / pricing / discount
# --------------------------------------------------------------------------- #
def _append_items(si, items, agent):
	if not items:
		_fail(ErrorCode.PAYMENT_MISMATCH, _("A sale must have at least one item."))
	max_disc = flt(agent.max_discount_pct)
	for row in items:
		discount = flt(row.get("discount_pct"))
		if discount < 0 or (max_disc and discount > max_disc):
			_fail(
				ErrorCode.DISCOUNT_EXCEEDED,
				_("Discount {0}% on {1} exceeds the {2}% cap.").format(
					discount, row.get("item_code"), max_disc
				),
				detail={"item_code": row.get("item_code"), "max_discount_pct": max_disc},
			)
		si.append(
			"items",
			{
				"item_code": row["item_code"],
				"qty": flt(row["qty"]),
				"warehouse": agent.agent_warehouse,
				"discount_percentage": discount,
			},
		)


# --------------------------------------------------------------------------- #
# stock
# --------------------------------------------------------------------------- #
def _validate_stock(si, agent):
	"""Check on-hand qty in the agent warehouse and reject shortages up front.

	Batch selection itself is left to ERPNext's auto-batch (FEFO) at submit time;
	this guard gives the app a clean STOCK_SHORT with available quantities rather
	than a raw batch/negative-stock traceback during submit.
	"""
	from erpnext.stock.utils import get_latest_stock_qty

	shortages = []
	# Aggregate requested qty per item (a cart can list an item twice).
	requested = {}
	for item in si.items:
		requested[item.item_code] = requested.get(item.item_code, 0) + flt(item.qty)

	for item_code, qty in requested.items():
		available = flt(get_latest_stock_qty(item_code, agent.agent_warehouse))
		if qty > available:
			shortages.append(
				{"item_code": item_code, "requested": qty, "available": available}
			)

	if shortages:
		_fail(
			ErrorCode.STOCK_SHORT,
			_("Insufficient stock in the agent warehouse for one or more items."),
			detail={"shortages": shortages},
		)


# --------------------------------------------------------------------------- #
# payments
# --------------------------------------------------------------------------- #
def _append_payments(si, payments, uuid):
	"""Append payment rows and validate the split equals the grand total.

	Returns the list of Winery Mpesa Payment Request names referenced by M-Pesa
	rows so the caller can back-link them once the invoice is posted.
	"""
	grand_total = flt(si.grand_total, si.precision("grand_total"))
	total_paid = 0.0
	mpesa_requests = []

	for pay in payments:
		amount = flt(pay.get("amount"))
		if amount <= 0:
			continue
		mode = pay.get("mode_of_payment")
		row = {"mode_of_payment": mode, "amount": amount}

		mode_type = frappe.db.get_value("Mode of Payment", mode, "type")
		if mode_type == "Phone":  # M-Pesa
			_resolve_mpesa_payment(pay, amount, uuid, row, mpesa_requests)
		elif mode_type == "Bank":
			ref = (pay.get("bank_reference") or "").strip()
			if not ref:
				_fail(
					ErrorCode.PAYMENT_MISMATCH,
					_("Bank payments require a reference number."),
				)
			row["winery_bank_reference"] = ref
			row["reference_no"] = ref
			row["winery_verification_status"] = "Pending"

		si.append("payments", row)
		total_paid += amount

	if flt(total_paid, si.precision("grand_total")) != grand_total:
		_fail(
			ErrorCode.PAYMENT_MISMATCH,
			_("Payments ({0}) do not equal the invoice total ({1}).").format(
				total_paid, grand_total
			),
			detail={"grand_total": grand_total, "total_paid": total_paid},
		)

	si.run_method("calculate_taxes_and_totals")
	return mpesa_requests


def _resolve_mpesa_payment(pay, amount, uuid, row, mpesa_requests):
	"""Validate an M-Pesa payment row: either a confirmed STK request or a manual code."""
	checkout_id = pay.get("checkout_request_id")
	if checkout_id:
		req = frappe.db.get_value(
			"Winery Mpesa Payment Request",
			{"checkout_request_id": checkout_id},
			["name", "status", "amount", "mpesa_receipt_number"],
			as_dict=True,
		)
		if not req or req.status != "Success":
			_fail(
				ErrorCode.MPESA_NOT_CONFIRMED,
				_("The M-Pesa payment has not been confirmed yet."),
				detail={"checkout_request_id": checkout_id},
			)
		if flt(req.amount) != amount:
			_fail(
				ErrorCode.PAYMENT_MISMATCH,
				_("M-Pesa amount does not match the confirmed payment."),
			)
		row["winery_mpesa_receipt_no"] = req.mpesa_receipt_number
		row["reference_no"] = req.mpesa_receipt_number
		row["winery_verification_status"] = "Auto-verified"
		mpesa_requests.append(req.name)
		return

	# Manual code fallback (offline / lost callback). Flagged for back-office review.
	code = (pay.get("mpesa_receipt_no") or "").strip().upper()
	if not code:
		_fail(
			ErrorCode.MPESA_NOT_CONFIRMED,
			_("Provide an M-Pesa confirmation code or a confirmed STK request."),
		)
	dupe = frappe.db.exists(
		"Sales Invoice Payment", {"winery_mpesa_receipt_no": code, "docstatus": 1}
	)
	if dupe:
		_fail(
			ErrorCode.DUPLICATE_MPESA_CODE,
			_("M-Pesa code {0} has already been used on another sale.").format(code),
		)
	row["winery_mpesa_receipt_no"] = code
	row["reference_no"] = code
	row["winery_verification_status"] = "Pending"


# --------------------------------------------------------------------------- #
# result serialisation
# --------------------------------------------------------------------------- #
def _invoice_result(invoice_name, duplicate=False):
	si = frappe.get_doc("Sales Invoice", invoice_name)
	return {
		"sales_invoice": si.name,
		"grand_total": flt(si.grand_total),
		"duplicate": duplicate,
		"customer": si.customer,
		"posting_date": str(si.posting_date),
		"payments": [
			{
				"mode_of_payment": p.mode_of_payment,
				"amount": flt(p.amount),
				"mpesa_receipt_no": p.get("winery_mpesa_receipt_no"),
				"bank_reference": p.get("winery_bank_reference"),
				"verification_status": p.get("winery_verification_status"),
			}
			for p in si.payments
		],
		"items": [
			{
				"item_code": i.item_code,
				"item_name": i.item_name,
				"qty": flt(i.qty),
				"rate": flt(i.rate),
				"amount": flt(i.amount),
			}
			for i in si.items
		],
	}


def sync_batch(sales):
	"""Post a FIFO batch of offline sales. Partial success is expected.

	Each sale is committed in its own savepoint so one bad sale (e.g. STOCK_SHORT)
	does not roll back the others. Returns a per-sale result list.
	"""
	if isinstance(sales, str):
		sales = json.loads(sales)
	agent = get_agent_for_user()
	results = []
	for payload in sales[:25]:
		uuid = payload.get("pos_client_uuid")
		savepoint = f"sale_{frappe.generate_hash(length=8)}"
		frappe.db.savepoint(savepoint)
		try:
			results.append(create_sale(payload, agent=agent))
		except POSError as e:
			frappe.db.rollback(save_point=savepoint)
			results.append(
				{"pos_client_uuid": uuid, "error_code": e.error_code, "detail": e.detail,
				 "message": str(e)}
			)
		except Exception as e:  # noqa: BLE001 - surface any unexpected error per-sale
			frappe.db.rollback(save_point=savepoint)
			frappe.log_error(frappe.get_traceback(), f"POS sync_batch: {uuid}")
			results.append(
				{"pos_client_uuid": uuid, "error_code": "SERVER_ERROR", "message": str(e)}
			)
	return results
