import frappe

from winery.ecommerce.seo import page_seo

# The basket is per-shopper and worthless to a crawler.
sitemap = 0
no_cache = 1


def get_context(context):
	page_seo(
		context,
		title="Your Basket",
		description="Review the wine and coffee in your Ropen basket before checking out with M-Pesa.",
		route="cart",
		breadcrumbs=[
			{"label": "Home", "route": "/"},
			{"label": "Shop", "route": "/shop"},
			{"label": "Basket", "route": "/cart"},
		],
		noindex=True,
	)
	return context
