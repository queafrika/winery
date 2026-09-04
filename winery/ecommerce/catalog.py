"""Read-side of the storefront: which Items are published, and at what price.

Nothing here writes. Everything is driven off two custom fields on Item —
`publish_on_website` and `web_slug` — plus the Item Group, so the shop is
controlled entirely from the ERP without a parallel "Website Item" table.
"""

import frappe
from frappe.utils import cint, cstr, flt

from winery.ecommerce.constants import (
	money,
	COFFEE_GROUP,
	DEPARTMENTS,
	SELLING_PRICE_LIST,
	WINE_GROUP,
)

PRODUCT_FIELDS = (
	"name as item_code",
	"item_name",
	"item_group",
	"stock_uom",
	"image",
	"description",
	"brand",
	"web_slug",
	"web_tagline",
	"web_description",
	"web_meta_title",
	"web_meta_description",
	"web_rank",
)

SORT_OPTIONS = {
	"featured": "web_rank asc, item_name asc",
	"name": "item_name asc",
	"price-asc": "item_name asc",  # re-sorted in Python once prices are resolved
	"price-desc": "item_name asc",
}


def get_departments():
	"""Departments with their live published counts, for filter chips.

	Counted one group at a time rather than with a GROUP BY: Frappe v16 rejects
	SQL functions passed as strings in `fields`, and there are only two groups.
	"""
	out = []
	for dept in DEPARTMENTS:
		row = dict(dept)
		filters = _base_filters()
		filters["item_group"] = dept["group"]
		row["count"] = cint(frappe.db.count("Item", filters))
		out.append(row)
	return out


def get_products(group=None, search=None, sort="featured", limit=None):
	"""Published products, optionally narrowed to one department or a search term.

	`group` accepts either the Item Group name ("Wine") or its slug ("wine").
	"""
	filters = _base_filters()

	group_name = resolve_group(group)
	if group_name:
		filters["item_group"] = group_name

	or_filters = None
	if search:
		term = f"%{cstr(search).strip()}%"
		or_filters = {
			"item_name": ("like", term),
			"description": ("like", term),
			"web_tagline": ("like", term),
			"brand": ("like", term),
		}

	items = frappe.get_all(
		"Item",
		filters=filters,
		or_filters=or_filters,
		fields=PRODUCT_FIELDS,
		order_by=SORT_OPTIONS.get(sort, SORT_OPTIONS["featured"]),
		limit_page_length=cint(limit) or 0,
	)

	prices = get_price_map([i.item_code for i in items])
	for item in items:
		_decorate(item, prices)

	if sort == "price-asc":
		items.sort(key=lambda i: i["price"] or 0)
	elif sort == "price-desc":
		items.sort(key=lambda i: i["price"] or 0, reverse=True)

	return items


def get_product(slug):
	"""One published product by its web slug, or None."""
	name = frappe.db.get_value("Item", {"web_slug": slug, **_base_filters()}, "name")
	if not name:
		return None

	item = frappe.db.get_value("Item", name, [f.split(" as ")[0] for f in PRODUCT_FIELDS], as_dict=True)
	item["item_code"] = name
	_decorate(item, get_price_map([name]))
	return item


def get_related(item, limit=4):
	"""Other products from the same department, excluding this one."""
	siblings = get_products(group=item.get("item_group"), limit=limit + 1)
	return [s for s in siblings if s["item_code"] != item["item_code"]][:limit]


def get_price_map(item_codes):
	"""item_code -> selling rate from the Standard Selling price list."""
	if not item_codes:
		return {}

	rows = frappe.get_all(
		"Item Price",
		filters={
			"item_code": ("in", item_codes),
			"price_list": SELLING_PRICE_LIST,
			"selling": 1,
		},
		fields=["item_code", "price_list_rate"],
		order_by="valid_from desc",
	)
	prices = {}
	for row in rows:
		prices.setdefault(row.item_code, flt(row.price_list_rate))
	return prices


def resolve_group(group):
	"""Accept a slug or an Item Group name; return a real Item Group name or None."""
	if not group:
		return None
	group = cstr(group).strip()
	for dept in DEPARTMENTS:
		if group.lower() in (dept["slug"], dept["group"].lower()):
			return dept["group"]
	return None


def _base_filters():
	return {
		"publish_on_website": 1,
		"disabled": 0,
		"is_sales_item": 1,
		"item_group": ("in", [WINE_GROUP, COFFEE_GROUP]),
	}


def _decorate(item, prices):
	"""Attach price, formatted price, department metadata and image fallbacks."""
	item["price"] = prices.get(item["item_code"])
	item["price_formatted"] = (
		money(item["price"]) if item["price"] else None
	)
	item["in_stock"] = item["price"] is not None
	item["route"] = f"/shop/{item.get('web_slug')}"
	item["image"] = item.get("image") or _placeholder(item.get("item_group"))
	item["department"] = "coffee" if item.get("item_group") == COFFEE_GROUP else "wine"
	item["short_description"] = (
		item.get("web_tagline") or frappe.utils.strip_html(cstr(item.get("description")))[:160]
	)
	return item


def _placeholder(item_group):
	return (
		"/assets/winery/images/placeholder-coffee.svg"
		if item_group == COFFEE_GROUP
		else "/assets/winery/images/placeholder-wine.svg"
	)
