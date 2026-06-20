import frappe


def execute():
	"""Migrate data from excise_duty_per_litre -> excise_duty_per_dl.

	Frappe schema sync has already added the new excise_duty_per_dl column.
	This patch copies any existing values across and leaves the old column in place
	(Frappe never auto-drops columns; it can be removed manually later if desired).
	"""
	for doctype in ("ABV Tax Band", "Wine Batch", "Bottling"):
		table = f"tab{doctype}"
		if frappe.db.has_column(doctype, "excise_duty_per_litre"):
			frappe.db.sql(
				f"""
				UPDATE `{table}`
				SET `excise_duty_per_dl` = `excise_duty_per_litre`
				WHERE `excise_duty_per_litre` IS NOT NULL
				  AND `excise_duty_per_litre` != 0
				"""
			)
