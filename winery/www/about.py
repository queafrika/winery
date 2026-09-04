import frappe

from winery.ecommerce.seo import page_seo

sitemap = 1


def get_context(context):
	page_seo(
		context,
		title="About Us",
		description=(
			"Ropen Coffee & Fine Foods Limited is a family-owned Kenyan establishment "
			"specialising in the farming and processing of fine alcoholic and non-alcoholic "
			"beverages, across four divisions in Kiambu County and the USA."
		),
		route="about",
		image="/assets/winery/images/about-farmers.webp",
		breadcrumbs=[
			{"label": "Home", "route": "/"},
			{"label": "About", "route": "/about"},
		],
	)
	context.no_cache = 1
	return context
