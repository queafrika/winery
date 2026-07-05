"""Whitelisted HTTP API for the Winery Sales Agent mobile app.

Every endpoint (except ``login`` and the guest ``mpesa_callback``) authenticates via
the agent's API key/secret and resolves the Sales Agent from ``frappe.session.user``.
The client never chooses a warehouse, price list, or agent.

Functions are addressed as ``winery.winery.pos.api.<function>``.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, nowdate, getdate

from winery.winery.doctype.sales_agent.sales_agent import get_agent_for_user
from winery.winery.pos import mpesa as mpesa_mod
from winery.winery.pos import sale as sale_mod


# --------------------------------------------------------------------------- #
# auth
# --------------------------------------------------------------------------- #
@frappe.whitelist(allow_guest=True)
def login(usr, pwd):
	"""Exchange Frappe credentials for API key/secret + the agent profile."""
	login_manager = frappe.auth.LoginManager()
	login_manager.authenticate(user=usr, pwd=pwd)
	user = login_manager.user

	agent = get_agent_for_user(user=user, throw=False)
	if not agent:
		frappe.local.response["error_code"] = "AGENT_INACTIVE"
		frappe.throw(_("No Sales Agent is linked to this account."), frappe.AuthenticationError)
	if agent.status != "Active":
		frappe.local.response["error_code"] = "AGENT_INACTIVE"
		frappe.throw(_("This sales agent account is not active."), frappe.AuthenticationError)

	api_key, api_secret = _ensure_api_keys(user)
	company = frappe.defaults.get_global_default("company")
	return {
		"api_key": api_key,
		"api_secret": api_secret,
		"agent": _agent_profile(agent, company),
		"server_time": str(frappe.utils.now_datetime()),
	}


def _ensure_api_keys(user):
	user_doc = frappe.get_doc("User", user)
	if not user_doc.api_key:
		user_doc.api_key = frappe.generate_hash(length=15)
	api_secret = frappe.generate_hash(length=15)
	user_doc.api_secret = api_secret
	user_doc.flags.ignore_permissions = True
	user_doc.save()
	frappe.db.commit()
	return user_doc.api_key, api_secret


def _agent_profile(agent, company):
	return {
		"name": agent.name,
		"sales_agent_name": agent.sales_agent_name,
		"agent_warehouse": agent.agent_warehouse,
		"selling_price_list": agent.selling_price_list,
		"default_customer": agent.default_customer,
		"max_discount_pct": flt(agent.max_discount_pct),
		"pos_profile": agent.pos_profile,
		"currency": frappe.db.get_value("Company", company, "default_currency") if company else None,
		"company": company,
	}


# --------------------------------------------------------------------------- #
# sync
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def bootstrap(modified_after=None):
	"""Full (or delta) offline dataset: items, prices, stock, customers, settings."""
	agent = get_agent_for_user()
	return {
		"sync_timestamp": str(frappe.utils.now_datetime()),
		"items": _catalogue(agent, modified_after),
		"customers": _customers(modified_after),
		"modes_of_payment": _modes_of_payment(agent),
		"settings": {
			"max_discount_pct": flt(agent.max_discount_pct),
			"currency": frappe.db.get_value(
				"Price List", agent.selling_price_list, "currency"
			),
		},
	}


def _catalogue(agent, modified_after=None):
	from erpnext.stock.utils import get_latest_stock_qty

	filters = {"is_sales_item": 1, "disabled": 0}
	if modified_after:
		filters["modified"] = [">", modified_after]
	items = frappe.get_all(
		"Item",
		filters=filters,
		fields=[
			"name as item_code", "item_name", "item_group", "stock_uom as uom",
			"image", "has_batch_no",
		],
	)
	prices = _price_map(agent.selling_price_list)
	out = []
	for it in items:
		out.append(
			{
				**it,
				"rate": flt(prices.get(it.item_code)),
				"stock_qty": flt(get_latest_stock_qty(it.item_code, agent.agent_warehouse)),
			}
		)
	return out


def _price_map(price_list):
	rows = frappe.get_all(
		"Item Price",
		filters={"price_list": price_list, "selling": 1},
		fields=["item_code", "price_list_rate"],
	)
	return {r.item_code: r.price_list_rate for r in rows}


def _customers(modified_after=None):
	filters = {"disabled": 0}
	if modified_after:
		filters["modified"] = [">", modified_after]
	return frappe.get_all(
		"Customer",
		filters=filters,
		fields=["name", "customer_name", "mobile_no"],
		limit_page_length=0,
	)


def _modes_of_payment(agent):
	if agent.pos_profile:
		rows = frappe.get_all(
			"POS Payment Method",
			filters={"parent": agent.pos_profile},
			fields=["mode_of_payment"],
			order_by="idx",
		)
		if rows:
			return [r.mode_of_payment for r in rows]
	return ["Cash", "M-Pesa", "Bank"]


@frappe.whitelist()
def stock():
	"""Lightweight item_code -> qty map for the agent's warehouse."""
	from erpnext.stock.utils import get_latest_stock_qty

	agent = get_agent_for_user()
	items = frappe.get_all(
		"Item", filters={"is_sales_item": 1, "disabled": 0}, fields=["name"]
	)
	return {
		it.name: flt(get_latest_stock_qty(it.name, agent.agent_warehouse))
		for it in items
	}


# --------------------------------------------------------------------------- #
# sales
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def create_sale(**kwargs):
	payload = kwargs.get("payload") or kwargs
	if isinstance(payload, str):
		payload = json.loads(payload)
	result = sale_mod.create_sale(payload)
	frappe.local.response["http_status_code"] = 200 if result.get("duplicate") else 201
	return result


@frappe.whitelist()
def sync_batch(sales):
	return sale_mod.sync_batch(sales)


@frappe.whitelist()
def history(from_date=None, to_date=None, limit=50, start=0):
	agent = get_agent_for_user()
	filters = {"pos_sales_agent": agent.name, "docstatus": 1}
	if from_date and to_date:
		filters["posting_date"] = ["between", [from_date, to_date]]
	invoices = frappe.get_all(
		"Sales Invoice",
		filters=filters,
		fields=["name", "posting_date", "customer", "grand_total", "pos_client_uuid"],
		order_by="posting_date desc, creation desc",
		limit_page_length=int(limit),
		limit_start=int(start),
	)
	for inv in invoices:
		inv["payments"] = frappe.get_all(
			"Sales Invoice Payment",
			filters={"parent": inv.name},
			fields=[
				"mode_of_payment", "amount", "winery_mpesa_receipt_no",
				"winery_bank_reference", "winery_verification_status",
			],
		)
	return invoices


# --------------------------------------------------------------------------- #
# payments (M-Pesa)
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def stk_push(phone, amount, pos_client_uuid):
	# Ensure the caller is a valid agent before initiating a charge.
	get_agent_for_user()
	return mpesa_mod.stk_push(phone, amount, pos_client_uuid)


@frappe.whitelist()
def payment_status(checkout_request_id):
	get_agent_for_user()
	return mpesa_mod.get_status(checkout_request_id)


@frappe.whitelist(allow_guest=True)
def mpesa_callback(**kwargs):
	"""Safaricom STK callback. Guest, but hardened by IP allowlist + request match."""
	_enforce_callback_ip()
	body = frappe.local.form_dict
	# Frappe puts the raw JSON body into form_dict; fall back to request data.
	if not body.get("Body") and frappe.request and frappe.request.data:
		try:
			body = json.loads(frappe.request.data)
		except Exception:  # noqa: BLE001
			body = {}
	return mpesa_mod.handle_callback(dict(body))


def _enforce_callback_ip():
	settings = frappe.get_single("Winery Mpesa Settings")
	allow = (settings.callback_allowlist_ips or "").strip()
	if not allow:
		return
	import ipaddress

	remote = frappe.local.request_ip
	try:
		ip = ipaddress.ip_address(remote)
	except ValueError:
		frappe.throw(_("Forbidden"), frappe.PermissionError)
	for line in allow.splitlines():
		line = line.strip()
		if not line:
			continue
		try:
			if ip in ipaddress.ip_network(line, strict=False):
				return
		except ValueError:
			if line == remote:
				return
	frappe.throw(_("Forbidden"), frappe.PermissionError)


# --------------------------------------------------------------------------- #
# reports
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def day_summary(date=None):
	agent = get_agent_for_user()
	date = getdate(date or nowdate())
	return _build_day_summary(agent, date)


def _build_day_summary(agent, date):
	from erpnext.stock.utils import get_latest_stock_qty

	invoices = frappe.get_all(
		"Sales Invoice",
		filters={"pos_sales_agent": agent.name, "docstatus": 1, "posting_date": date},
		fields=["name", "grand_total"],
	)
	invoice_names = [i.name for i in invoices]
	by_mode = {}
	pending_verification = 0
	if invoice_names:
		rows = frappe.get_all(
			"Sales Invoice Payment",
			filters={"parent": ["in", invoice_names]},
			fields=["mode_of_payment", "amount", "winery_verification_status"],
		)
		for r in rows:
			by_mode[r.mode_of_payment] = by_mode.get(r.mode_of_payment, 0) + flt(r.amount)
			if r.winery_verification_status == "Pending":
				pending_verification += 1

	sold = _sold_by_item(agent, date)
	stock_rows = []
	for item_code, qty in sold.items():
		stock_rows.append(
			{
				"item_code": item_code,
				"sold": qty,
				"balance": flt(get_latest_stock_qty(item_code, agent.agent_warehouse)),
			}
		)

	return {
		"date": str(date),
		"invoice_count": len(invoices),
		"grand_total": sum(flt(i.grand_total) for i in invoices),
		"by_mode": by_mode,
		"pending_verification": pending_verification,
		"stock": stock_rows,
	}


def _sold_by_item(agent, date):
	rows = frappe.db.sql(
		"""
		SELECT sii.item_code, SUM(sii.qty) AS qty
		FROM `tabSales Invoice Item` sii
		JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.pos_sales_agent = %s AND si.docstatus = 1 AND si.posting_date = %s
		GROUP BY sii.item_code
		""",
		(agent.name, date),
		as_dict=True,
	)
	return {r.item_code: flt(r.qty) for r in rows}


@frappe.whitelist()
def day_close(date=None, declared_cash=0, notes=None):
	agent = get_agent_for_user()
	date = getdate(date or nowdate())

	if frappe.db.exists(
		"Winery POS Day Close",
		{"sales_agent": agent.name, "close_date": date, "docstatus": 1},
	):
		frappe.local.response["error_code"] = "ALREADY_CLOSED"
		frappe.throw(_("A day close already exists for {0}.").format(date))

	summary = _build_day_summary(agent, date)
	by_mode = summary["by_mode"]

	doc = frappe.new_doc("Winery POS Day Close")
	doc.sales_agent = agent.name
	doc.close_date = date
	doc.invoice_count = summary["invoice_count"]
	doc.system_cash = flt(by_mode.get("Cash"))
	doc.declared_cash = flt(declared_cash)
	doc.mpesa_total = flt(by_mode.get("M-Pesa"))
	doc.bank_total = flt(by_mode.get("Bank"))
	doc.grand_total = flt(summary["grand_total"])
	doc.notes = notes
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()

	return {
		"day_close": doc.name,
		"system_cash": flt(doc.system_cash),
		"declared_cash": flt(doc.declared_cash),
		"cash_variance": flt(doc.cash_variance),
		"grand_total": flt(doc.grand_total),
	}
