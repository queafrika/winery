"""Authoritative cart pricing.

The browser holds the cart (localStorage) so guest pages stay cacheable and no
server session is needed. Prices sent by the browser are never trusted: every
cart render and every checkout re-prices from Item Price here.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from winery.ecommerce.catalog import get_price_map
from winery.ecommerce.constants import (
	money,
	COFFEE_GROUP,
	MAX_LINES_PER_ORDER,
	MAX_QTY_PER_LINE,
	WINE_GROUP,
)


def price_cart(lines):
	"""Re-price a browser cart.

	`lines` is [{item_code, qty}, ...]. Returns resolved lines plus totals, and
	a list of human-readable notes about anything that had to be adjusted or
	dropped (unpublished item, price withdrawn, qty over the cap).
	"""
	lines = _normalise(lines)
	if not lines:
		return _empty()

	items = frappe.get_all(
		"Item",
		filters={
			"name": ("in", list(lines.keys())),
			"publish_on_website": 1,
			"disabled": 0,
			"is_sales_item": 1,
			"item_group": ("in", [WINE_GROUP, COFFEE_GROUP]),
		},
		fields=["name as item_code", "item_name", "item_group", "stock_uom", "image", "web_slug"],
	)
	prices = get_price_map([i.item_code for i in items])

	resolved, notes = [], []
	found = set()

	for item in items:
		found.add(item.item_code)
		rate = prices.get(item.item_code)
		if rate is None:
			notes.append(_("{0} is not currently available to buy online.").format(item.item_name))
			continue

		qty = lines[item.item_code]
		if qty > MAX_QTY_PER_LINE:
			qty = MAX_QTY_PER_LINE
			notes.append(
				_("{0} is limited to {1} per online order — please contact sales for bulk quantities.").format(
					item.item_name, MAX_QTY_PER_LINE
				)
			)

		resolved.append(
			{
				"item_code": item.item_code,
				"item_name": item.item_name,
				"item_group": item.item_group,
				"uom": item.stock_uom,
				"image": item.image or "/assets/winery/images/placeholder-wine.svg",
				"route": f"/shop/{item.web_slug}" if item.web_slug else "/shop",
				"qty": qty,
				"rate": rate,
				"rate_formatted": money(rate),
				"amount": flt(rate * qty, 2),
				"amount_formatted": money(flt(rate * qty, 2)),
			}
		)

	for missing in set(lines) - found:
		notes.append(_("An item in your basket is no longer on sale and was removed."))
		break

	resolved.sort(key=lambda r: r["item_name"])
	total = flt(sum(r["amount"] for r in resolved), 2)

	return {
		"lines": resolved,
		"count": sum(r["qty"] for r in resolved),
		"total": total,
		"total_formatted": money(total),
		"currency": "KES",
		"notes": notes,
	}


def _normalise(lines):
	"""Coerce untrusted browser input into {item_code: qty}.

	Bounded only by an absurd upper limit here; the real per-line cap is applied
	in `price_cart` so it can tell the shopper their quantity was reduced rather
	than silently changing it.
	"""
	if isinstance(lines, str):
		lines = frappe.parse_json(lines)
	if not isinstance(lines, list):
		return {}

	out = {}
	for line in lines[:MAX_LINES_PER_ORDER]:
		if not isinstance(line, dict):
			continue
		code = (line.get("item_code") or "").strip()
		qty = cint(line.get("qty"))
		if not code or qty <= 0:
			continue
		out[code] = min(qty, 100_000)
	return out


def _empty():
	return {
		"lines": [],
		"count": 0,
		"total": 0.0,
		"total_formatted": money(0),
		"currency": "KES",
		"notes": [],
	}
