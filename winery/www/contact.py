import frappe
from frappe.utils import get_url

from winery.ecommerce.seo import business, page_seo

sitemap = 1


def get_context(context):
	biz = business()

	page_seo(
		context,
		title="Contact Us",
		description=(
			f"Get in touch with Ropen Coffee & Fine Foods in {biz['town']}, Kiambu , retail "
			"orders, wholesale terms, and TerraNova green coffee samples for the USA."
		),
		route="contact",
		image="/assets/winery/images/about-farmers.webp",
		breadcrumbs=[
			{"label": "Home", "route": "/"},
			{"label": "Contact", "route": "/contact"},
		],
		extra_jsonld=[
			{
				"@type": "ContactPage",
				"@id": get_url("/contact") + "#contactpage",
				"name": "Contact Ropen Coffee and Fine Foods",
				"mainEntity": {"@id": get_url("/") + "#organization"},
			}
		],
	)
	context.no_cache = 1
	return context
