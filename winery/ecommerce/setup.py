"""Idempotent storefront setup.

Run with:  bench --site <site> execute winery.ecommerce.setup.run

Creates the Wine / Coffee Item Groups, the Item website custom fields, moves the
retail wines into the Wine group, seeds placeholder coffee products, and fills in
the Website Settings the templates read (contact details, robots.txt).

Safe to re-run: everything checks before it writes and nothing is deleted.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import flt

from winery.ecommerce.constants import COFFEE_GROUP, SELLING_PRICE_LIST, WINE_GROUP

# --------------------------------------------------------------------------- #
# 1. Item custom fields — the storefront's entire control surface on Item.
# --------------------------------------------------------------------------- #
ITEM_FIELDS = {
	"Item": [
		{
			"fieldname": "web_section",
			"label": "Website",
			"fieldtype": "Section Break",
			"insert_after": "description",
			"collapsible": 1,
			"module": "Winery",
		},
		{
			"fieldname": "publish_on_website",
			"label": "Publish on Website",
			"fieldtype": "Check",
			"insert_after": "web_section",
			"description": "Show this item in the public shop at /shop.",
			"module": "Winery",
		},
		{
			"fieldname": "web_slug",
			"label": "Web Slug",
			"fieldtype": "Data",
			"insert_after": "publish_on_website",
			"unique": 1,
			"depends_on": "publish_on_website",
			"description": "URL segment, e.g. 'banana-wine-750ml-dry' -> /shop/banana-wine-750ml-dry",
			"module": "Winery",
		},
		{
			"fieldname": "web_tagline",
			"label": "Web Tagline",
			"fieldtype": "Data",
			"insert_after": "web_slug",
			"depends_on": "publish_on_website",
			"length": 200,
			"description": "One-line summary shown on product cards.",
			"module": "Winery",
		},
		{
			"fieldname": "web_rank",
			"label": "Web Sort Order",
			"fieldtype": "Int",
			"insert_after": "web_tagline",
			"depends_on": "publish_on_website",
			"default": "100",
			"description": "Lower numbers appear first in the shop.",
			"module": "Winery",
		},
		{
			"fieldname": "web_col_break",
			"fieldtype": "Column Break",
			"insert_after": "web_rank",
			"module": "Winery",
		},
		{
			"fieldname": "web_meta_title",
			"label": "SEO Title",
			"fieldtype": "Data",
			"insert_after": "web_col_break",
			"depends_on": "publish_on_website",
			"length": 70,
			"description": "Overrides the browser/search-result title. Aim for under 60 characters.",
			"module": "Winery",
		},
		{
			"fieldname": "web_meta_description",
			"label": "SEO Description",
			"fieldtype": "Small Text",
			"insert_after": "web_meta_title",
			"depends_on": "publish_on_website",
			"description": "Search-result snippet. Aim for 150-158 characters.",
			"module": "Winery",
		},
		{
			"fieldname": "web_description",
			"label": "Web Description",
			"fieldtype": "Text Editor",
			"insert_after": "web_meta_description",
			"depends_on": "publish_on_website",
			"description": "Full product story shown on the product page.",
			"module": "Winery",
		},
	],
	"Customer": [
		{
			"fieldname": "custom_web_phone",
			"label": "Web Order Phone",
			"fieldtype": "Data",
			"insert_after": "mobile_no",
			"read_only": 1,
			"description": "M-Pesa number used to match returning online shoppers.",
			"module": "Winery",
		}
	],
	"Website Settings": [
		{
			"fieldname": "custom_ropen_section",
			"label": "Ropen Storefront",
			"fieldtype": "Section Break",
			"insert_after": "footer_logo",
			"collapsible": 1,
			"module": "Winery",
		},
		{"fieldname": "custom_ropen_phone", "label": "Public Phone", "fieldtype": "Data",
		 "insert_after": "custom_ropen_section", "module": "Winery"},
		{"fieldname": "custom_ropen_email", "label": "Public Email", "fieldtype": "Data",
		 "insert_after": "custom_ropen_phone", "module": "Winery"},
		{"fieldname": "custom_ropen_whatsapp", "label": "WhatsApp Number", "fieldtype": "Data",
		 "insert_after": "custom_ropen_email", "module": "Winery"},
		{"fieldname": "custom_ropen_col", "fieldtype": "Column Break",
		 "insert_after": "custom_ropen_whatsapp", "module": "Winery"},
		{"fieldname": "custom_ropen_street", "label": "Street Address", "fieldtype": "Data",
		 "insert_after": "custom_ropen_col", "module": "Winery"},
		{"fieldname": "custom_ropen_town", "label": "Town / City", "fieldtype": "Data",
		 "insert_after": "custom_ropen_street", "module": "Winery"},
		{"fieldname": "custom_ropen_county", "label": "County / Region", "fieldtype": "Data",
		 "insert_after": "custom_ropen_town", "module": "Winery"},
		{"fieldname": "custom_ropen_social", "fieldtype": "Section Break", "label": "Social Links",
		 "insert_after": "custom_ropen_county", "collapsible": 1, "module": "Winery"},
		{"fieldname": "custom_ropen_facebook", "label": "Facebook URL", "fieldtype": "Data",
		 "insert_after": "custom_ropen_social", "module": "Winery"},
		{"fieldname": "custom_ropen_instagram", "label": "Instagram URL", "fieldtype": "Data",
		 "insert_after": "custom_ropen_facebook", "module": "Winery"},
		{"fieldname": "custom_ropen_linkedin", "label": "LinkedIn URL", "fieldtype": "Data",
		 "insert_after": "custom_ropen_instagram", "module": "Winery"},
	],
}

# --------------------------------------------------------------------------- #
# 2. Existing wines to publish. (item_code, slug, rank, tagline, image, price)
#    A price of None means "keep whatever Item Price already exists".
# --------------------------------------------------------------------------- #
_WINE_SPEC = (
	"<h3>Specification</h3>"
	"<ul>"
	"<li><strong>Style</strong> — dry banana wine</li>"
	"<li><strong>Strength</strong> — 8.5% ABV</li>"
	"<li><strong>Ingredients</strong> — ripe bananas, sugar, pectinase &amp; amylase enzymes, "
	"food-grade potassium sorbate &amp; potassium metabisulphate</li>"
	"<li><strong>Allergens</strong> — contains sulphur</li>"
	"<li><strong>Serve</strong> — well chilled at 8–10&nbsp;°C; refrigerate once opened</li>"
	"<li><strong>Made in</strong> — Ruiru, Kiambu, Kenya</li>"
	"</ul>"
	"<p><em>Excessive consumption is harmful to your health. Not for sale to persons under "
	"the age of 18 years.</em></p>"
)

WINE_ITEMS = [
	(
		"Banana Wine - 750ML Dry",
		"Banny’s Dry Banana Wine — 750ml",
		"bannys-dry-banana-wine-750ml",
		10,
		"Banny’s Dry Banana Wine — culturally inspired, deeply rooted. 8.5% ABV, 750ml.",
		"/assets/winery/images/products/wine-750-dry.webp",
		None,
		"<p>Banny’s is fermented from ripe Kenyan bananas at our Ruiru winery — fruit that "
		"would otherwise have been lost to a glut. It is fermented out <strong>dry</strong> "
		"rather than left sweet, so the fruit reads as fruit and not as syrup.</p>"
		"<p>The woman on the label represents the traditional Kikuyu woman. The banana plant’s "
		"key uses — food and brew preparation, thatching, weaving — were led by women, and the "
		"label honours that.</p>" + _WINE_SPEC,
	),
	(
		"1l Dry Wine",
		"Banny’s Dry Banana Wine — 1 Litre",
		"bannys-dry-banana-wine-1l",
		20,
		"Banny’s Dry Banana Wine in a one-litre bottle, for the table.",
		"/assets/winery/images/products/wine-1l-dry.webp",
		1950,
		"<p>The same dry banana wine in a one-litre format, made for the table rather than the "
		"cellar. Same fruit, same ferment — simply more of it.</p>" + _WINE_SPEC,
	),
	(
		"12 *750ML Package",
		"Banny’s Dry Banana Wine — Case of 12 × 750ml",
		"bannys-750ml-case-of-12",
		30,
		"A full case of twelve 750ml bottles of Banny’s, at a case price.",
		"/assets/winery/images/products/wine-case-750.webp",
		None,
		"<p>Twelve 750ml bottles of Banny’s Dry Banana Wine, bulk packed in a carton box. The "
		"sensible way to buy for a wedding, a function or a bar.</p>"
		"<p>Case orders are delivered directly from our Ruiru winery. For standing wholesale "
		"terms, talk to our sales team.</p>" + _WINE_SPEC,
	),
	(
		"12 * 1L Dry Wine",
		"Banny’s Dry Banana Wine — Case of 12 × 1 Litre",
		"bannys-1l-case-of-12",
		40,
		"Twelve one-litre bottles of Banny’s, case-priced.",
		"/assets/winery/images/products/wine-case-1l.webp",
		None,
		"<p>Twelve one-litre bottles of Banny’s Dry Banana Wine in a single carton — our best "
		"value per litre, and the format most of our trade customers reorder.</p>"
		+ _WINE_SPEC,
	),
]

# --------------------------------------------------------------------------- #
# 3. Placeholder coffee catalogue. Replace with real SKUs once roasting starts.
# --------------------------------------------------------------------------- #
_COFFEE_ORIGIN = (
	"<h3>Origin</h3>"
	"<ul>"
	"<li><strong>Farm</strong> — Njagũ Farm, Njagũ village, Lari / Githunguri, Kiambu</li>"
	"<li><strong>Altitude</strong> — 1,550–1,725 m above sea level</li>"
	"<li><strong>Varieties</strong> — SL28 &amp; SL34, with Ruiru 11 in replanted gaps</li>"
	"<li><strong>Soils</strong> — deep, well-drained humic nitisols of volcanic origin</li>"
	"<li><strong>Process</strong> — fully washed, sun-dried up to 14 days to below 11% moisture</li>"
	"</ul>"
	"<p>Part of the proceeds from our coffee supports aged women welfare programmes in the "
	"local communities.</p>"
)

COFFEE_ITEMS = [
	(
		"ROPEN-COF-AA-250G",
		"Njagũ Farm AA — Ground, 250g",
		"njagu-farm-aa-ground-250g",
		10,
		"Single-origin Njagũ Farm AA, washed and sun-dried, ground for filter and pour-over.",
		"/assets/winery/images/products/coffee-ground.webp",
		850,
		"<p>Grade AA cherry, selectively picked at Njagũ Farm, pulped and fermented at our "
		"station, then dried on raised beds until the moisture falls below 11%.</p>"
		"<p>Ground for filter, pour-over and French press. Packed in a valve bag with the "
		"roast date on the label.</p>" + _COFFEE_ORIGIN,
	),
	(
		"ROPEN-COF-AA-500G",
		"Njagũ Farm AA — Whole Beans, 500g",
		"njagu-farm-aa-beans-500g",
		20,
		"The same AA lot left whole, for grinding fresh at home.",
		"/assets/winery/images/products/coffee-beans.webp",
		1550,
		"<p>Our flagship AA lot left whole so you can grind it fresh. Whole beans keep their "
		"aromatics far longer than pre-ground coffee.</p>"
		"<p>Rest for three days after roasting, then use within six weeks for the clearest "
		"cup.</p>" + _COFFEE_ORIGIN,
	),
	(
		"ROPEN-COF-ESP-250G",
		"Njagũ Farm Espresso Roast — 250g",
		"njagu-farm-espresso-roast-250g",
		30,
		"A darker roast of the same single-origin lot, built for espresso.",
		"/assets/winery/images/products/coffee-espresso.webp",
		900,
		"<p>Taken further into second crack for the body and sweetness espresso needs, while "
		"keeping the origin character of the farm.</p>"
		"<p>Dial in around 18g in, 36g out, 27–30 seconds. Equally good in a moka pot.</p>"
		+ _COFFEE_ORIGIN,
	),
	(
		"ROPEN-COF-FIL-500G",
		"Njagũ Farm Filter Roast — 500g",
		"njagu-farm-filter-roast-500g",
		40,
		"A lighter roast for batch brew and pour-over, in a 500g bag.",
		"/assets/winery/images/products/coffee-filter.webp",
		1650,
		"<p>Roasted lighter to keep the acidity and floral character the altitude gives this "
		"cherry.</p>"
		"<p>Best as pour-over or batch brew at a 1:16 ratio.</p>" + _COFFEE_ORIGIN,
	),
]


def run():
	"""Entry point. Prints a short report of what changed."""
	log = []

	log += _create_custom_fields()
	log += _create_item_groups()
	log += _create_lead_source()
	log += _publish_wines()
	log += _create_coffee_items()
	log += _configure_website_settings()

	frappe.db.commit()
	frappe.clear_cache()

	print("\n".join(log) or "Nothing to do — already set up.")
	print(f"\n{len(log)} change(s) applied.")
	return log


# --------------------------------------------------------------------------- #
def _create_custom_fields():
	create_custom_fields(ITEM_FIELDS, ignore_validate=True, update=True)
	return ["✓ Item / Customer / Website Settings custom fields created or updated"]


def _create_item_groups():
	log = []
	parent = "All Item Groups"

	for group, description in (
		(WINE_GROUP, "Bottled banana wine sold to the public."),
		(COFFEE_GROUP, "Roasted arabica coffee sold to the public."),
	):
		if frappe.db.exists("Item Group", group):
			continue
		doc = frappe.new_doc("Item Group")
		doc.item_group_name = group
		doc.parent_item_group = parent
		doc.is_group = 0
		doc.description = description
		doc.flags.ignore_permissions = True
		doc.flags.ignore_mandatory = True
		doc.insert()
		log.append(f"✓ Item Group '{group}' created")

	return log


def set_canonical_host(url):
	"""Pin the host used in canonical URLs, og:url, sitemap.xml and robots.txt.

	Without this, those URLs are derived from whatever Host header the request
	arrived with — which is fine behind a single production vhost, but emits
	`http://…:8000` when the dev server is hit directly. Set it once the site is
	live behind its real hostname and TLS:

	    bench --site <site> execute winery.ecommerce.setup.set_canonical_host \\
	        --kwargs '{"url": "https://winery.finesoftafrika.com"}'
	"""
	url = url.rstrip("/")
	if not url.startswith(("http://", "https://")):
		frappe.throw("Pass a full URL including the scheme, e.g. https://example.com")

	frappe.db.set_single_value("Website Settings", "robots_txt", _robots_txt(url))
	conf = frappe.get_site_config()
	conf["host_name"] = url
	# site_config.json is the only place host_name is read from.
	import json
	import os

	path = os.path.join(frappe.get_site_path(), "site_config.json")
	with open(path) as f:
		data = json.load(f)
	data["host_name"] = url
	with open(path, "w") as f:
		json.dump(data, f, indent=1)

	frappe.db.commit()
	frappe.clear_cache()
	print(f"✓ Canonical host set to {url}. Restart bench for it to take effect.")


def _robots_txt(base_url):
	return (
		"User-agent: *\n"
		"Allow: /\n"
		"Disallow: /app\n"
		"Disallow: /api\n"
		"Disallow: /private\n"
		"Disallow: /cart\n"
		"Disallow: /checkout\n"
		"Disallow: /order\n"
		"Disallow: /login\n"
		"\n"
		f"Sitemap: {base_url}/sitemap.xml\n"
	)


def _create_lead_source():
	"""So contact-form Leads are attributable to the website in CRM reports."""
	if frappe.db.exists("UTM Source", "Website"):
		return []

	# UTM Source is autoname="prompt" — the name is the source itself.
	doc = frappe.new_doc("UTM Source")
	doc.name = "Website"
	doc.description = "Enquiries submitted through the Ropen website contact form."
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert()
	return ["✓ UTM Source 'Website' created"]


def _publish_wines():
	log = []
	for code, name, slug, rank, tagline, image, price, body in WINE_ITEMS:
		if not frappe.db.exists("Item", code):
			log.append(f"⚠ Item '{code}' not found — skipped")
			continue

		item = frappe.get_doc("Item", code)
		# The stock codes ("12 *750ML Package") are warehouse shorthand, not
		# shelf names — give the storefront something a shopper can read.
		item.item_name = name
		item.item_group = WINE_GROUP
		item.publish_on_website = 1
		item.web_slug = slug
		item.web_rank = rank
		item.web_tagline = tagline
		item.web_description = body
		item.web_meta_title = f"{name} | Ropen Winery"
		item.web_meta_description = tagline
		if not item.image:
			item.image = image
		item.flags.ignore_permissions = True
		item.flags.ignore_mandatory = True
		item.save()

		if price:
			_set_price(code, price)
		log.append(f"✓ Published wine '{code}' -> /shop/{slug}")

	return log


def _create_coffee_items():
	log = []
	for code, name, slug, rank, tagline, image, price, body in COFFEE_ITEMS:
		if frappe.db.exists("Item", code):
			item = frappe.get_doc("Item", code)
			created = False
		else:
			item = frappe.new_doc("Item")
			item.item_code = code
			item.is_stock_item = 1
			item.stock_uom = "Nos"
			item.is_sales_item = 1
			item.is_purchase_item = 0
			created = True

		item.item_name = name
		item.item_group = COFFEE_GROUP
		item.description = tagline
		item.publish_on_website = 1
		item.web_slug = slug
		item.web_rank = rank
		item.web_tagline = tagline
		item.web_description = body
		item.web_meta_title = f"{name} | Njagũ Farm Coffee"
		item.web_meta_description = tagline
		if not item.image:
			item.image = image
		item.flags.ignore_permissions = True
		item.flags.ignore_mandatory = True
		item.save()

		_set_price(code, price)
		log.append(f"{'✓ Created' if created else '✓ Updated'} coffee '{code}' -> /shop/{slug}")

	return log


def _set_price(item_code, rate):
	"""Ensure a Standard Selling price exists at `rate`."""
	name = frappe.db.get_value(
		"Item Price", {"item_code": item_code, "price_list": SELLING_PRICE_LIST, "selling": 1}, "name"
	)
	if name:
		if flt(frappe.db.get_value("Item Price", name, "price_list_rate")) != flt(rate):
			frappe.db.set_value("Item Price", name, "price_list_rate", rate)
		return

	doc = frappe.new_doc("Item Price")
	doc.item_code = item_code
	doc.price_list = SELLING_PRICE_LIST
	doc.selling = 1
	doc.currency = "KES"
	doc.price_list_rate = rate
	doc.flags.ignore_permissions = True
	doc.insert()


def _configure_website_settings():
	"""Point the site root at our home page and fill in defaults the templates read."""
	ws = frappe.get_single("Website Settings")
	changed = []

	defaults = {
		"home_page": "index",
		"app_name": "Ropen Coffee and Fine Foods",
		"disable_signup": 1,
		"custom_ropen_phone": "+254 700 000 000",
		"custom_ropen_email": "hello@ropen.co.ke",
		"custom_ropen_street": "Ruiru",
		"custom_ropen_town": "Ruiru",
		"custom_ropen_county": "Kiambu County",
	}
	for field, value in defaults.items():
		if not ws.get(field):
			ws.set(field, value)
			changed.append(field)

	if not ws.get("robots_txt"):
		ws.robots_txt = _robots_txt(frappe.utils.get_url())
		changed.append("robots_txt")

	if changed:
		ws.flags.ignore_permissions = True
		ws.save()
		return [f"✓ Website Settings updated ({', '.join(changed)})"]
	return []
