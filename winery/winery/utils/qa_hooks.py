# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

import frappe


def set_batch_qa_pending(doc, method):
	"""On Purchase Receipt / Purchase Invoice (update_stock) submit:
	mark batches as QA Pending for items that have lab test requirements."""
	if doc.doctype == "Purchase Invoice" and not doc.update_stock:
		return

	for item in doc.items:
		if not item.batch_no or not item.item_code:
			continue
		has_requirements = frappe.db.exists(
			"Item Lab Test Requirement", {"parent": item.item_code}
		)
		if has_requirements:
			frappe.db.set_value("Batch", item.batch_no, "qa_status", "Pending")
