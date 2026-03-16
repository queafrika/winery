# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class RipeningRack(Document):
	pass


@frappe.whitelist()
def get_rack_usage(rack_name):
	"""Return fingers currently in the rack warehouse from stock ledger."""
	rack = frappe.get_doc("Ripening Rack", rack_name)
	if not rack.warehouse:
		return {"fingers_in_use": 0, "usage_percentage": 0}

	result = frappe.db.sql("""
		SELECT COALESCE(SUM(actual_qty), 0) AS fingers_in_use
		FROM `tabStock Ledger Entry`
		WHERE warehouse = %s
		  AND is_cancelled = 0
	""", rack.warehouse, as_dict=True)

	fingers_in_use = int(result[0].fingers_in_use or 0)
	capacity = rack.capacity_fingers or 0
	usage_pct = round((fingers_in_use / capacity) * 100, 1) if capacity > 0 else 0

	return {
		"fingers_in_use": fingers_in_use,
		"usage_percentage": min(usage_pct, 100),
	}
