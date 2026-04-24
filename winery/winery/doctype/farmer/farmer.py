import frappe
from frappe.model.document import Document
from winery.winery.doctype.farmer.kenya_location_data import KENYA_LOCATIONS


class Farmer(Document):
	def after_insert(self):
		self.create_supplier()

	def create_supplier(self):
		supplier = frappe.get_doc({
			"doctype": "Supplier",
			"supplier_name": self.farmer_name,
			"supplier_group": "All Supplier Groups",
			"supplier_type": "Individual",
		})
		supplier.insert(ignore_permissions=True)
		self.db_set("supplier", supplier.name, notify=True)


@frappe.whitelist()
def get_kenya_counties():
	return sorted(KENYA_LOCATIONS.keys())


@frappe.whitelist()
def get_kenya_sub_counties(county):
	data = KENYA_LOCATIONS.get(county, {})
	return sorted(data.keys())


@frappe.whitelist()
def get_kenya_wards(sub_county):
	for county_data in KENYA_LOCATIONS.values():
		if sub_county in county_data:
			return sorted(county_data[sub_county])
	return []


@frappe.whitelist()
def get_location_parents(ward=None, sub_county=None):
	"""Given a ward or sub-county, return its parent sub-county and county."""
	result = {"county": None, "sub_county": None}
	if sub_county:
		for county, sc_map in KENYA_LOCATIONS.items():
			if sub_county in sc_map:
				result["county"] = county
				break
	if ward:
		for county, sc_map in KENYA_LOCATIONS.items():
			for sc, wards in sc_map.items():
				if ward in wards:
					result["county"] = county
					result["sub_county"] = sc
					return result
	return result
