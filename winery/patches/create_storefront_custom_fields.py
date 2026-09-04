import frappe

from winery.ecommerce import setup


def execute():
	"""Create the Item / Customer / Website Settings storefront custom fields.

	These were previously only created by `bench execute winery.ecommerce.setup.run`,
	so sites that never ran it 500 on /shop and /winery with
	"Unknown column 'web_slug'". Idempotent — create_custom_fields updates in place.
	"""
	setup.ensure_custom_fields()
	frappe.clear_cache()
