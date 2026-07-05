import frappe

from winery.winery.pos import setup


def execute():
	"""Bootstrap shared Sales Agent POS artifacts.

	Idempotent: creates the Winery Sales Agent role, the non-KRA walk-in Customer
	Group, the Cash/M-Pesa/Bank Modes of Payment with company account mappings, the
	Sales Agents parent warehouse, and the default field-sales POS Profile — only if
	they are missing. Skipped on sites without a Company (e.g. fresh installs before
	company setup); it will run on the next migrate once a Company exists.
	"""
	if not (frappe.defaults.get_global_default("company") or frappe.db.exists("Company", {})):
		return
	setup.run_full_setup()
