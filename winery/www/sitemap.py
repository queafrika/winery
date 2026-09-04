"""Sitemap for the Ropen storefront.

Overrides Frappe's default (the winery app is resolved ahead of frappe) so the
dynamically-routed product pages at /shop/<slug> get listed. Those have no static
route and no web-view doctype, so the stock sitemap cannot see them.
"""

from urllib.parse import quote

import frappe
from frappe.utils import get_url, nowdate
from frappe.website.router import get_pages

no_cache = 1
base_template_path = "www/sitemap.xml"

# Priority / change frequency by route. Anything unlisted gets the defaults.
WEIGHTS = {
	"": ("1.0", "weekly"),
	"shop": ("0.9", "daily"),
	"winery": ("0.8", "monthly"),
	"coffee": ("0.8", "monthly"),
	"about": ("0.6", "yearly"),
	"contact": ("0.6", "yearly"),
}
DEFAULT_WEIGHT = ("0.5", "monthly")

# Never advertise the shopper's own pages to a crawler.
EXCLUDE = {"cart", "checkout", "order", "sitemap", "robots"}


def get_context(context):
	links = []
	seen = set()

	for route, page in get_pages().items():
		if not page.sitemap:
			continue
		route = (route or "").strip("/")
		if route in EXCLUDE or route.startswith(tuple(e + "/" for e in EXCLUDE)):
			continue
		if route in seen:
			continue
		seen.add(route)

		priority, changefreq = WEIGHTS.get(route, DEFAULT_WEIGHT)
		links.append(
			{
				"loc": get_url(quote(route.encode("utf-8"))),
				"lastmod": nowdate(),
				"priority": priority,
				"changefreq": changefreq,
			}
		)

	links.extend(_department_links())
	links.extend(_product_links())

	return {"links": links}


def _department_links():
	"""The two filtered shop views are real landing pages with their own copy."""
	from winery.ecommerce.constants import DEPARTMENTS

	return [
		{
			"loc": get_url(f"/shop?group={dept['slug']}"),
			"lastmod": nowdate(),
			"priority": "0.8",
			"changefreq": "weekly",
		}
		for dept in DEPARTMENTS
	]


def _product_links():
	from winery.ecommerce.constants import COFFEE_GROUP, WINE_GROUP

	rows = frappe.get_all(
		"Item",
		filters={
			"publish_on_website": 1,
			"disabled": 0,
			"is_sales_item": 1,
			"item_group": ("in", [WINE_GROUP, COFFEE_GROUP]),
			"web_slug": ("is", "set"),
		},
		fields=["web_slug", "modified"],
	)
	return [
		{
			"loc": get_url("/shop/" + quote(row.web_slug.encode("utf-8"))),
			"lastmod": f"{row.modified:%Y-%m-%d}",
			"priority": "0.7",
			"changefreq": "weekly",
		}
		for row in rows
	]
