"""Shared constants for the Ropen public storefront."""

# Item Groups that back the two storefront departments. The shop filter chips,
# the Winery/Coffee page CTAs and the sitemap all key off these names.
WINE_GROUP = "Wine"
COFFEE_GROUP = "Coffee"

DEPARTMENTS = (
	{
		"group": WINE_GROUP,
		"slug": "wine",
		"label": "Wine",
		"blurb": "Banana wines pressed, fermented and bottled at our Kiambu winery.",
	},
	{
		"group": COFFEE_GROUP,
		"slug": "coffee",
		"label": "Coffee",
		"blurb": "Single-origin Kenyan arabica, roasted to order.",
	},
)

DEPARTMENT_BY_SLUG = {d["slug"]: d for d in DEPARTMENTS}
DEPARTMENT_BY_GROUP = {d["group"]: d for d in DEPARTMENTS}

SELLING_PRICE_LIST = "Standard Selling"

# Guests can never move more than this in one order without talking to sales.
MAX_QTY_PER_LINE = 60
MAX_LINES_PER_ORDER = 30

# The storefront only ever creates orders for this customer group / territory.
WEB_CUSTOMER_GROUP = "Individual"
WEB_TERRITORY = "Kenya"

CART_COOKIE = "ropen_cart"


def money(amount):
	"""Format a KES amount for the storefront.

	Frappe renders the KES symbol as "Sh"; Kenyan shoppers expect "KSh". Formatted
	here rather than by changing the Currency record, so POS receipts, invoices and
	every other ERP document keep the accounting team's existing formatting.
	"""
	from frappe.utils import flt

	return f"KSh {flt(amount):,.2f}"
