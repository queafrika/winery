import frappe

from winery.ecommerce import catalog
from winery.ecommerce.constants import DEPARTMENT_BY_GROUP
from winery.ecommerce.seo import item_list_jsonld, page_seo

sitemap = 1

# Copy per filter state, so /shop?group=wine is a genuinely distinct, indexable page
# rather than duplicate content behind a query string.
VARIANTS = {
	"Wine": {
		"title": "Buy Banny's Banana Wine Online",
		"heading": "Banny’s Banana Wine",
		"description": (
			"Buy Banny's Dry Banana Wine online in Kenya , 8.5% ABV, 750ml, made from ripe "
			"Kenyan bananas at our Ruiru winery. Delivered nationwide, paid for with M-Pesa."
		),
		"lede": (
			"Culturally inspired, deeply rooted. Dry banana wine fermented and bottled at our "
			"winery in Ruiru, Kiambu. Singles and cases, delivered across Kenya."
		),
	},
	"Coffee": {
		"title": "Buy Njagũ Farm Coffee Online",
		"heading": "Njagũ Farm Coffee",
		"description": (
			"Buy single-origin Kenyan specialty coffee online , SL28, SL34 and Ruiru 11 from "
			"Njagũ Farm in Kiambu, fully washed and sun-dried. Delivered nationwide. Pay with M-Pesa."
		),
		"lede": (
			"Single-origin specialty coffee, traceable to Njagũ Farm in Kiambu and grown "
			"between 1,550 and 1,725 metres."
		),
	},
	None: {
		"title": "Shop Wine and Coffee",
		"heading": "The shop",
		"description": (
			"Shop Banny's Dry Banana Wine and single-origin Njagũ Farm coffee online. Filter "
			"by wine or coffee, order in minutes and pay with M-Pesa. Delivery across Kenya."
		),
		"lede": (
			"Everything we make, in one place. Filter by wine or coffee, add to your basket "
			"and pay with M-Pesa."
		),
	},
}


def get_context(context):
	args = frappe.form_dict
	group = catalog.resolve_group(args.get("group"))
	search = (args.get("q") or "").strip()[:80]
	sort = args.get("sort") if args.get("sort") in catalog.SORT_OPTIONS else "featured"

	products = catalog.get_products(group=group, search=search, sort=sort)
	variant = VARIANTS.get(group, VARIANTS[None])

	crumbs = [{"label": "Home", "route": "/"}, {"label": "Shop", "route": "/shop"}]
	route = "shop"
	if group:
		dept = DEPARTMENT_BY_GROUP[group]
		crumbs.append({"label": dept["label"], "route": f"/shop?group={dept['slug']}"})
		route = f"shop?group={dept['slug']}"

	page_seo(
		context,
		title=variant["title"],
		description=variant["description"],
		route=route,
		image="/assets/winery/images/hero-shop.webp",
		breadcrumbs=crumbs,
		# A search results page is thin, duplicated content , keep it out of the index.
		noindex=bool(search),
		extra_jsonld=[item_list_jsonld(products, variant["heading"])] if products else None,
	)

	context.products = products
	context.departments = catalog.get_departments()
	context.active_group = DEPARTMENT_BY_GROUP[group]["slug"] if group else ""
	context.search = search
	context.sort = sort
	context.heading = variant["heading"]
	context.lede = variant["lede"]
	context.total_count = len(products)
	context.no_cache = 1
	return context
