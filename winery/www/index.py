import frappe

from winery.ecommerce import catalog
from winery.ecommerce.seo import item_list_jsonld, page_seo

sitemap = 1


def get_context(context):
	featured = catalog.get_products(limit=8)

	page_seo(
		context,
		title="Ropen Coffee & Fine Foods",
		description=(
			"Banny's Dry Banana Wine and single-origin Njagũ Farm coffee, farmed and processed "
			"in Kiambu County, Kenya. Order online and pay with M-Pesa."
		),
		route="",
		image="/assets/winery/images/og-default.jpg",
		extra_jsonld=[item_list_jsonld(featured, "Featured products")] if featured else None,
	)

	context.featured = featured
	context.departments = catalog.get_departments()
	context.no_cache = 1
	return context
