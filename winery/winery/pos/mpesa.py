"""Daraja (Safaricom) STK Push client for the Winery Sales Agent POS.

Self-contained — reads credentials from the Winery Mpesa Settings single doctype and
posts to the Lipa Na M-Pesa Online (STK Push) endpoints. No dependency on POS Awesome
(whose M-Pesa support is C2B-only).

Flow:
  stk_push()      -> Daraja processrequest, create a Pending payment request
  mpesa_callback()-> Safaricom posts the result, we mark Success/Failed
  payment_status()-> the app polls this until Success/Failed/Timeout
  stk_query()     -> scheduled reconciliation for lost callbacks
"""

import base64
import json
from datetime import datetime

import frappe
import requests
from frappe import _
from frappe.utils import flt, now_datetime, get_datetime

from winery.winery.pos.constants import ErrorCode


DARAJA_TIMEOUT = 30  # seconds


def _settings():
	s = frappe.get_single("Winery Mpesa Settings")
	if not s.enabled:
		frappe.throw(_("M-Pesa is not enabled in Winery Mpesa Settings."))
	return s


def _get_token(settings):
	url = f"{settings.base_url()}/oauth/v1/generate?grant_type=client_credentials"
	try:
		resp = requests.get(
			url,
			auth=(
				settings.get_password("consumer_key"),
				settings.get_password("consumer_secret"),
			),
			timeout=DARAJA_TIMEOUT,
		)
		resp.raise_for_status()
		return resp.json()["access_token"]
	except Exception as e:  # noqa: BLE001
		frappe.log_error(frappe.get_traceback(), "Winery M-Pesa token error")
		_raise(ErrorCode.DARAJA_UNREACHABLE, _("Could not reach M-Pesa: {0}").format(e))


def normalise_phone(phone):
	"""Convert 07XXXXXXXX / +2547XXXXXXXX / 2547XXXXXXXX to 2547XXXXXXXX."""
	digits = "".join(ch for ch in str(phone) if ch.isdigit())
	if digits.startswith("0") and len(digits) == 10:
		digits = "254" + digits[1:]
	elif digits.startswith("7") and len(digits) == 9:
		digits = "254" + digits
	elif digits.startswith("254") and len(digits) == 12:
		pass
	else:
		_raise(ErrorCode.INVALID_PHONE, _("Invalid Safaricom phone number: {0}").format(phone))
	return digits


def stk_push(phone, amount, pos_client_uuid):
	"""Initiate an STK Push and record a Pending Winery Mpesa Payment Request."""
	settings = _settings()
	msisdn = normalise_phone(phone)
	amount = int(flt(amount))
	if amount <= 0:
		_raise(ErrorCode.PAYMENT_MISMATCH, _("M-Pesa amount must be positive."))

	timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
	password = base64.b64encode(
		f"{settings.shortcode}{settings.get_password('passkey')}{timestamp}".encode()
	).decode()
	txn_type = (
		"CustomerBuyGoodsOnline"
		if settings.till_type == "Buy Goods"
		else "CustomerPayBillOnline"
	)

	payload = {
		"BusinessShortCode": settings.shortcode,
		"Password": password,
		"Timestamp": timestamp,
		"TransactionType": txn_type,
		"Amount": amount,
		"PartyA": msisdn,
		"PartyB": settings.shortcode,
		"PhoneNumber": msisdn,
		"CallBackURL": settings.callback_url,
		"AccountReference": pos_client_uuid[:12],
		"TransactionDesc": "Winery POS sale",
	}

	token = _get_token(settings)
	try:
		resp = requests.post(
			f"{settings.base_url()}/mpesa/stkpush/v1/processrequest",
			json=payload,
			headers={"Authorization": f"Bearer {token}"},
			timeout=DARAJA_TIMEOUT,
		)
		data = resp.json()
	except Exception as e:  # noqa: BLE001
		frappe.log_error(frappe.get_traceback(), "Winery M-Pesa STK push error")
		_raise(ErrorCode.DARAJA_UNREACHABLE, _("M-Pesa request failed: {0}").format(e))

	if str(data.get("ResponseCode")) != "0":
		_raise(
			ErrorCode.DARAJA_UNREACHABLE,
			data.get("errorMessage") or data.get("ResponseDescription") or _("STK push rejected."),
		)

	req = frappe.new_doc("Winery Mpesa Payment Request")
	req.status = "Pending"
	req.phone_number = msisdn
	req.amount = amount
	req.pos_client_uuid = pos_client_uuid
	req.checkout_request_id = data.get("CheckoutRequestID")
	req.merchant_request_id = data.get("MerchantRequestID")
	req.flags.ignore_permissions = True
	req.insert()
	frappe.db.commit()

	return {"checkout_request_id": req.checkout_request_id, "status": "Pending"}


def handle_callback(body):
	"""Process Safaricom's stkCallback body. Returns the Daraja ack dict."""
	try:
		stk = (body.get("Body") or {}).get("stkCallback") or {}
		checkout_id = stk.get("CheckoutRequestID")
		if not checkout_id:
			return {"ResultCode": 0, "ResultDesc": "Accepted"}

		name = frappe.db.get_value(
			"Winery Mpesa Payment Request", {"checkout_request_id": checkout_id}, "name"
		)
		if not name:
			# Unknown request — acknowledge without side effects (no info leak).
			return {"ResultCode": 0, "ResultDesc": "Accepted"}

		req = frappe.get_doc("Winery Mpesa Payment Request", name)
		req.result_code = str(stk.get("ResultCode"))
		req.result_desc = stk.get("ResultDesc")
		req.callback_payload = json.dumps(body, indent=2)

		if str(stk.get("ResultCode")) == "0":
			req.status = "Success"
			for item in (stk.get("CallbackMetadata") or {}).get("Item", []):
				if item.get("Name") == "MpesaReceiptNumber":
					req.mpesa_receipt_number = item.get("Value")
		else:
			req.status = "Failed"

		req.flags.ignore_permissions = True
		req.save()
		frappe.db.commit()
	except Exception:  # noqa: BLE001 - never fail the webhook
		frappe.log_error(frappe.get_traceback(), "Winery M-Pesa callback error")

	return {"ResultCode": 0, "ResultDesc": "Accepted"}


def get_status(checkout_request_id):
	row = frappe.db.get_value(
		"Winery Mpesa Payment Request",
		{"checkout_request_id": checkout_request_id},
		["status", "mpesa_receipt_number", "result_desc"],
		as_dict=True,
	)
	if not row:
		frappe.throw(_("Unknown checkout request."))
	return {
		"status": row.status,
		"mpesa_receipt_number": row.mpesa_receipt_number,
		"result_desc": row.result_desc,
	}


def stk_query():
	"""Scheduled reconciliation for Pending requests with lost callbacks.

	Re-queries Daraja for requests pending >2 min; marks Timeout after 15 min.
	"""
	settings = frappe.get_single("Winery Mpesa Settings")
	if not settings.enabled:
		return

	pending = frappe.get_all(
		"Winery Mpesa Payment Request",
		filters={"status": "Pending"},
		fields=["name", "checkout_request_id", "creation"],
	)
	if not pending:
		return

	token = None
	timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
	password = base64.b64encode(
		f"{settings.shortcode}{settings.get_password('passkey')}{timestamp}".encode()
	).decode()

	for req in pending:
		age = (now_datetime() - get_datetime(req.creation)).total_seconds()
		if age < 120:
			continue
		if age > 900:
			frappe.db.set_value(
				"Winery Mpesa Payment Request", req.name, "status", "Timeout"
			)
			continue
		if token is None:
			token = _get_token(settings)
		try:
			resp = requests.post(
				f"{settings.base_url()}/mpesa/stkpushquery/v1/query",
				json={
					"BusinessShortCode": settings.shortcode,
					"Password": password,
					"Timestamp": timestamp,
					"CheckoutRequestID": req.checkout_request_id,
				},
				headers={"Authorization": f"Bearer {token}"},
				timeout=DARAJA_TIMEOUT,
			)
			data = resp.json()
		except Exception:  # noqa: BLE001
			continue
		result_code = str(data.get("ResultCode"))
		if result_code == "0":
			frappe.db.set_value(
				"Winery Mpesa Payment Request",
				req.name,
				{"status": "Success", "result_desc": data.get("ResultDesc")},
			)
		elif result_code and result_code not in ("1032",):  # 1032 = still pending/cancelled
			frappe.db.set_value(
				"Winery Mpesa Payment Request",
				req.name,
				{"status": "Failed", "result_code": result_code,
				 "result_desc": data.get("ResultDesc")},
			)
	frappe.db.commit()


def _raise(code, message):
	frappe.local.response["error_code"] = code
	frappe.throw(message)
