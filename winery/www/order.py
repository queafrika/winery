import frappe

from winery.ecommerce.order import get_public_order
from winery.ecommerce.seo import page_seo

sitemap = 0
no_cache = 1


def get_context(context):
	# Reached via /order/<token>; the token is a 24-char random hash, so knowing an
	# order number is not enough to read someone else's order.
	token = frappe.form_dict.get("token") or ""
	order = get_public_order(token)

	if not order:
		frappe.local.flags.redirect_location = "/shop"
		raise frappe.Redirect

	page_seo(
		context,
		title="Your Order",
		description="Your Ropen order confirmation.",
		route=f"order/{token}",
		breadcrumbs=[{"label": "Home", "route": "/"}],
		noindex=True,
	)

	context.order = order
	context.order_token = token
	return context
