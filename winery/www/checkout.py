import frappe

from winery.ecommerce import payments
from winery.ecommerce.seo import page_seo

sitemap = 0
no_cache = 1


def get_context(context):
	page_seo(
		context,
		title="Checkout",
		description="Complete your Ropen order and pay securely with M-Pesa.",
		route="checkout",
		breadcrumbs=[
			{"label": "Home", "route": "/"},
			{"label": "Shop", "route": "/shop"},
			{"label": "Basket", "route": "/cart"},
			{"label": "Checkout", "route": "/checkout"},
		],
		noindex=True,
	)

	# Tell the shopper up front if M-Pesa credentials are not live, rather than
	# letting them fill in the whole form and fail at the last step.
	context.mpesa_ready = payments.is_configured()
	return context
