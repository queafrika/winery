# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

from frappe.utils.nestedset import NestedSet


class FarmLocation(NestedSet):
	nsm_parent_field = "parent_farm_location"
