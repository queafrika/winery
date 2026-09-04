import frappe

from winery.ecommerce import catalog
from winery.ecommerce.constants import WINE_GROUP
from winery.ecommerce.seo import faq_jsonld, item_list_jsonld, page_seo

sitemap = 1

FAQS = [
	(
		"What is Banny's Dry Banana Wine?",
		"A dry wine fermented from ripe Kenyan bananas at our Ruiru winery. It is bottled "
		"at 8.5% ABV in 750ml glass, and made from ripe bananas, sugar, pectinase and "
		"amylase enzymes, with food-grade potassium sorbate and potassium metabisulphate "
		"as preservatives. It contains sulphur.",
	),
	(
		"Why bananas rather than grapes?",
		"Because the fruit was already here and going to waste. Bananas crop year-round in "
		"Kiambu and carry high post-harvest losses , a glut drives prices to nothing and "
		"the fruit rots in the compound. Wine turns that surplus into something with a "
		"shelf life and a market.",
	),
	(
		"What does it taste like, and how should I serve it?",
		"Dry rather than sweet, with the fruit still clearly present. Serve it well chilled "
		"at 8–10 °C. Once opened, keep it refrigerated and finish it within a few days.",
	),
	(
		"What makes it an eco-friendly drink?",
		"It is made from overripe bananas that would otherwise be wasted, brewed with low "
		"power drawn from our own solar, and packed in recyclable glass, biodegradable "
		"paper packs, corks and labels, and banana-fibre carriers made at Bansoko Centre.",
	),
	(
		"Who is the woman on the label?",
		"She represents the traditional Kikuyu woman. The banana plant's key uses , food "
		"and brew preparation, thatching, weaving , were led by women, and the label "
		"honours that. Part of what we do supports welfare programmes for aged women in "
		"our local communities.",
	),
	(
		"Do you supply bars, restaurants and events?",
		"Yes. We sell singles and cases through this shop, and we supply trade customers "
		"on standing terms. Use the contact form and our sales team will come back to you "
		"with wholesale pricing.",
	),
]


def get_context(context):
	products = catalog.get_products(group=WINE_GROUP, limit=4)

	page_seo(
		context,
		title="Banny's Banana Wine",
		description=(
			"Banny's Dry Banana Wine , culturally inspired, deeply rooted. Fermented from "
			"ripe Kenyan bananas at our Ruiru winery in Kiambu County. 8.5% ABV, 750ml."
		),
		route="winery",
		image="/assets/winery/images/hero-winery.webp",
		breadcrumbs=[
			{"label": "Home", "route": "/"},
			{"label": "Winery", "route": "/winery"},
		],
		extra_jsonld=[faq_jsonld(FAQS)]
		+ ([item_list_jsonld(products, "Banny's banana wines")] if products else []),
	)

	context.products = products
	context.faqs = FAQS
	context.no_cache = 1
	return context
