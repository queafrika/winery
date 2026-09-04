"""SEO context builder.

Every storefront page calls `page_seo()` from its `get_context`, which fills in
canonical URL, title, description, Open Graph / Twitter cards, and a JSON-LD
graph. Keeping it in one place means a page can never silently ship without
metadata.
"""

import json
import os

import frappe
from frappe.utils import cstr, get_url, strip_html

_ASSET_FILES = ("css/ropen-web.css", "js/ropen-web.js")

SITE_NAME = "Ropen Coffee & Fine Foods"
LEGAL_NAME = "Ropen Coffee & Fine Foods Limited"
DEFAULT_OG_IMAGE = "/assets/winery/images/og-default.jpg"
LOGO = "/assets/winery/images/ropen-logo.png"

TITLE_SUFFIX = f" | {SITE_NAME}"
MAX_TITLE = 60
MAX_DESCRIPTION = 158


def asset_version():
	"""Cache-buster for ropen-web.css / .js, derived from their own mtimes.

	Browsers were still serving a stylesheet fixed hours earlier because the CSS
	link had no version string and a 12-hour Cache-Control — the fix was on disk
	but never reached anyone. Appending `?v=` means every deploy invalidates the
	cache automatically, with nothing to remember to bump by hand.
	"""
	try:
		app_path = frappe.get_app_path("winery")
		stamp = int(
			sum(os.path.getmtime(os.path.join(app_path, "public", f)) for f in _ASSET_FILES)
		)
		return stamp
	except OSError:
		return "0"


def business():
	"""Contact/brand facts, overridable from Website Settings without a deploy."""
	settings = frappe.get_cached_doc("Website Settings")
	return {
		"name": SITE_NAME,
		"legal_name": LEGAL_NAME,
		"phone": settings.get("custom_ropen_phone") or "+254 700 000 000",
		"email": settings.get("custom_ropen_email") or "hello@ropen.co.ke",
		"street": settings.get("custom_ropen_street") or "Ruiru",
		"town": settings.get("custom_ropen_town") or "Ruiru",
		"county": settings.get("custom_ropen_county") or "Kiambu County",
		"country": "Kenya",
		"whatsapp": settings.get("custom_ropen_whatsapp") or "",
		"facebook": settings.get("custom_ropen_facebook") or "",
		"instagram": settings.get("custom_ropen_instagram") or "",
		"linkedin": settings.get("custom_ropen_linkedin") or "",
		"hours": "Mon–Fri 08:00–17:00, Sat 09:00–14:00",
	}


def page_seo(
	context,
	title,
	description,
	route="",
	image=None,
	page_type="website",
	breadcrumbs=None,
	extra_jsonld=None,
	noindex=False,
):
	"""Populate `context` with everything the <head> block needs."""
	canonical = get_url(f"/{route.lstrip('/')}" if route else "/")
	description = _clamp(strip_html(cstr(description)), MAX_DESCRIPTION)

	context.seo = frappe._dict(
		{
			"title": _clamp(title, MAX_TITLE),
			"full_title": _full_title(title),
			"description": description,
			"canonical": canonical,
			"image": get_url(image or DEFAULT_OG_IMAGE),
			"type": page_type,
			"noindex": noindex,
			"site_name": SITE_NAME,
		}
	)
	context.business = business()
	context.breadcrumbs = breadcrumbs or []
	context.asset_version = asset_version()
	# The navbar highlights the active link from this rather than poking at the
	# request object, which is not reliably reachable from the Jinja sandbox.
	context.current_route = "/" + route.lstrip("/").split("?")[0]

	graph = [_organisation(), _website()]
	if breadcrumbs:
		graph.append(_breadcrumb_list(breadcrumbs))
	if extra_jsonld:
		graph.extend(extra_jsonld if isinstance(extra_jsonld, list) else [extra_jsonld])

	context.jsonld = json.dumps(
		{"@context": "https://schema.org", "@graph": graph}, indent=None, separators=(",", ":")
	)
	# Frappe's own <head> helpers — keeps the desk-side metadata consistent too.
	context.title = context.seo.title
	context.metatags = {
		"title": context.seo.full_title,
		"description": description,
		"image": context.seo.image,
	}
	return context


def product_jsonld(product):
	"""schema.org/Product with an Offer, so listings can win rich results."""
	offer = {
		"@type": "Offer",
		"url": get_url(product["route"]),
		"priceCurrency": "KES",
		"availability": "https://schema.org/InStock"
		if product.get("in_stock")
		else "https://schema.org/OutOfStock",
		"seller": {"@type": "Organization", "name": LEGAL_NAME},
	}
	if product.get("price"):
		offer["price"] = f"{product['price']:.2f}"

	return {
		"@type": "Product",
		"@id": get_url(product["route"]) + "#product",
		"name": product["item_name"],
		"sku": product["item_code"],
		"description": _clamp(
			strip_html(cstr(product.get("short_description") or product.get("description"))), 300
		),
		"image": [get_url(product["image"])],
		"brand": {"@type": "Brand", "name": product.get("brand") or SITE_NAME},
		"category": product.get("item_group"),
		"offers": offer,
	}


def item_list_jsonld(products, list_name):
	return {
		"@type": "ItemList",
		"name": list_name,
		"numberOfItems": len(products),
		"itemListElement": [
			{
				"@type": "ListItem",
				"position": i + 1,
				"url": get_url(p["route"]),
				"name": p["item_name"],
			}
			for i, p in enumerate(products)
		],
	}


def faq_jsonld(pairs):
	return {
		"@type": "FAQPage",
		"mainEntity": [
			{
				"@type": "Question",
				"name": q,
				"acceptedAnswer": {"@type": "Answer", "text": strip_html(a)},
			}
			for q, a in pairs
		],
	}


# --------------------------------------------------------------------------- #
# internals
# --------------------------------------------------------------------------- #
def _organisation():
	biz = business()
	socials = [biz[k] for k in ("facebook", "instagram", "linkedin") if biz.get(k)]

	return {
		"@type": ["Organization", "LocalBusiness"],
		"@id": get_url("/") + "#organization",
		"name": LEGAL_NAME,
		"alternateName": SITE_NAME,
		"url": get_url("/"),
		"logo": {"@type": "ImageObject", "url": get_url(LOGO)},
		"image": get_url(DEFAULT_OG_IMAGE),
		"description": (
			"Family-owned Kenyan producer of Banny's Dry Banana Wine and single-origin "
			"specialty coffee from Njagũ Farm in Kiambu County."
		),
		"telephone": biz["phone"],
		"email": biz["email"],
		"address": {
			"@type": "PostalAddress",
			"streetAddress": biz["street"],
			"addressLocality": biz["town"],
			"addressRegion": biz["county"],
			"addressCountry": "KE",
		},
		"openingHours": ["Mo-Fr 08:00-17:00", "Sa 09:00-14:00"],
		"currenciesAccepted": "KES",
		"paymentAccepted": "M-Pesa",
		"areaServed": {"@type": "Country", "name": "Kenya"},
		**({"sameAs": socials} if socials else {}),
	}


def _website():
	return {
		"@type": "WebSite",
		"@id": get_url("/") + "#website",
		"url": get_url("/"),
		"name": SITE_NAME,
		"publisher": {"@id": get_url("/") + "#organization"},
		"inLanguage": "en-KE",
		"potentialAction": {
			"@type": "SearchAction",
			"target": {
				"@type": "EntryPoint",
				"urlTemplate": get_url("/shop") + "?q={search_term_string}",
			},
			"query-input": "required name=search_term_string",
		},
	}


def _breadcrumb_list(breadcrumbs):
	return {
		"@type": "BreadcrumbList",
		"itemListElement": [
			{
				"@type": "ListItem",
				"position": i + 1,
				"name": crumb["label"],
				"item": get_url(crumb["route"]),
			}
			for i, crumb in enumerate(breadcrumbs)
		],
	}


def _full_title(title):
	title = cstr(title).strip()
	if title.lower().startswith(SITE_NAME.lower()):
		return title
	if len(title) + len(TITLE_SUFFIX) <= 65:
		return title + TITLE_SUFFIX
	return title


def _clamp(text, limit):
	text = " ".join(cstr(text).split())
	if len(text) <= limit:
		return text
	return text[: limit - 1].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
