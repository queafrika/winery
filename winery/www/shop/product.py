import frappe
from frappe import _

from winery.ecommerce import catalog
from winery.ecommerce.constants import DEPARTMENT_BY_GROUP
from winery.ecommerce.seo import page_seo, product_jsonld

# Reached through the /shop/<slug> route rule; it has no static route of its own,
# so it is listed in the sitemap by winery/www/sitemap.py instead.
sitemap = 0
no_cache = 1


def get_context(context):
	slug = frappe.form_dict.get("slug") or ""
	product = catalog.get_product(slug)

	if not product:
		frappe.local.flags.redirect_location = "/shop"
		raise frappe.Redirect

	dept = DEPARTMENT_BY_GROUP.get(product["item_group"])

	page_seo(
		context,
		title=product.get("web_meta_title") or product["item_name"],
		description=(
			product.get("web_meta_description")
			or product.get("web_tagline")
			or product.get("short_description")
			or f"Buy {product['item_name']} online from Ropen Coffee and Fine Foods. Pay with M-Pesa."
		),
		route=f"shop/{slug}",
		image=product["image"],
		page_type="product",
		breadcrumbs=[
			{"label": "Home", "route": "/"},
			{"label": "Shop", "route": "/shop"},
			{"label": dept["label"], "route": f"/shop?group={dept['slug']}"} if dept else
			{"label": "Products", "route": "/shop"},
			{"label": product["item_name"], "route": f"/shop/{slug}"},
		],
		extra_jsonld=[product_jsonld(product)],
	)

	context.product = product
	context.department = dept
	context.related = catalog.get_related(product)
	return context
