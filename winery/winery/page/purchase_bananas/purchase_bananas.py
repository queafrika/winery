import json

import frappe
from frappe import _
from frappe.utils import flt, today


@frappe.whitelist()
def get_agent_for_user():
	"""Return the Agent linked to the currently logged-in user, or None."""
	return frappe.db.get_value("Agent", {"user": frappe.session.user}, "name")


@frappe.whitelist()
def get_agent_transit_warehouse(agent):
	"""Return the transit warehouse configured on this agent."""
	return frappe.db.get_value("Agent", agent, "transit_warehouse")


@frappe.whitelist()
def get_farmers_for_agent(agent):
	"""Return all farmers associated with this agent."""
	return frappe.db.get_all(
		"Farmer",
		filters={"agent": agent},
		fields=["name", "supplier"],
		order_by="name",
	)


@frappe.whitelist()
def get_farms_for_farmer(farmer):
	"""Return all farms belonging to this farmer."""
	return frappe.db.get_all(
		"Farm",
		filters={"farmer": farmer},
		fields=["name as farm"],
		order_by="name",
	)


@frappe.whitelist()
def get_banana_bunch_variants():
	"""Return all enabled variants of the Banana Bunch template item."""
	template = (
		frappe.db.get_single_value("Winery Settings", "banana_bunch_template")
		or "Banana Bunch"
	)
	return frappe.db.get_all(
		"Item",
		filters={"variant_of": template, "disabled": 0},
		fields=["name", "item_name"],
		order_by="item_name",
	)


@frappe.whitelist()
def create_purchase_invoice(agent, farm, farmer, supplier, warehouse, items):
	"""Create and immediately submit a Purchase Invoice that updates stock."""
	if isinstance(items, str):
		items = json.loads(items)

	if not items:
		frappe.throw(_("Please add at least one banana variety."))

	if not supplier:
		frappe.throw(
			_(
				"Farmer {0} has no linked Supplier. Please update the Farmer record before purchasing."
			).format(farmer)
		)

	pi = frappe.new_doc("Purchase Invoice")
	pi.supplier = supplier
	pi.update_stock = 1
	pi.posting_date = today()
	pi.agent = agent
	pi.farmer = farmer
	pi.custom_farm = farm

	for row in items:
		pi.append(
			"items",
			{
				"item_code": row["item_code"],
				"qty": flt(row["qty"]),
				"rate": flt(row["rate"]),
				"warehouse": warehouse,
			},
		)

	pi.flags.ignore_permissions = True
	pi.insert()
	pi.submit()

	return pi.name
