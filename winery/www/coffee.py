import frappe

from winery.ecommerce import catalog
from winery.ecommerce.constants import COFFEE_GROUP
from winery.ecommerce.seo import faq_jsonld, item_list_jsonld, page_seo

sitemap = 1

FAQS = [
	(
		"Where is Njagũ Farm?",
		"In Njagũ village, near the boundary of the Lari and Githunguri sub-counties of "
		"Kiambu. The farm sits on a hilly slope between 1,550 and 1,725 metres above sea "
		"level and borders a permanent stream at its lower end.",
	),
	(
		"What are the growing conditions?",
		"The area receives around 1,380mm of rainfall a year, with temperatures between "
		"15 °C and 23 °C. The soils are reddish to brown, deep, well-drained fertile humic "
		"nitisols derived from volcanic rock.",
	),
	(
		"Which varieties do you grow?",
		"Mostly SL28 and SL34 , many of the trees planted in the colonial era are still "
		"yielding today. Ruiru 11, a more disease-resistant variety from the Kenya "
		"Agricultural Research Laboratories, has been taking root since the early 1990s, "
		"and we use it when replacing gaps.",
	),
	(
		"How is the coffee processed?",
		"Wet-processed, or washed: the skin and pulp are removed from the cherry before the "
		"bean is set out to sun-dry for up to 14 days, until the moisture content falls "
		"below 11%. Some of our coffee goes to the local cooperative society factory, where "
		"it undergoes the same washing, pulping and sun-drying.",
	),
	(
		"What do you mean by good agricultural practices?",
		"Soil conservation, minimal tillage, minimal spraying with approved organics, "
		"application of organic manure, replacing crop gaps with disease-resistant "
		"varieties, shade regulation and selective harvesting.",
	),
	(
		"Why do proceeds go to aged women's welfare?",
		"Because the coffee farms of this area were established largely on the forced and "
		"low-wage labour of women and children between 1912 and 1954. Part of our coffee "
		"proceeds goes to support aged women welfare programmes in the local communities, "
		"in honour of those who did that work.",
	),
	(
		"Can I buy your coffee outside Kenya?",
		"Yes. Our USA-registered affiliate, TerraNova Coffee LLC, holds stateside stock of "
		"single-origin Kenyan specialty green coffee. See the contact page for their "
		"sample and order desk.",
	),
]


def get_context(context):
	products = catalog.get_products(group=COFFEE_GROUP, limit=4)

	page_seo(
		context,
		title="Njagũ Farm Specialty Coffee",
		description=(
			"Single-origin Kenyan specialty coffee from Njagũ Farm, Kiambu , SL28, SL34 and "
			"Ruiru 11 grown at 1,550–1,725m, fully washed and sun-dried. Traceable to the tree."
		),
		route="coffee",
		image="/assets/winery/images/hero-coffee.webp",
		breadcrumbs=[
			{"label": "Home", "route": "/"},
			{"label": "Coffee", "route": "/coffee"},
		],
		extra_jsonld=[faq_jsonld(FAQS)]
		+ ([item_list_jsonld(products, "Ropen coffees")] if products else []),
	)

	context.products = products
	context.faqs = FAQS
	context.no_cache = 1
	return context
