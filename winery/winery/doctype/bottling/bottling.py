# Copyright (c) 2026, Finesoft Afrika and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt, cint


class Bottling(Document):
	def validate(self):
		self._compute_line_totals()
		self._compute_summary()
		self._match_abv_tax_band()
		self._compute_excise_duty()

	# ------------------------------------------------------------------ #
	#  Calculations                                                        #
	# ------------------------------------------------------------------ #

	def _compute_line_totals(self):
		for row in self.bottling_lines:
			row.net_bottles = max(cint(row.actual_bottles) - cint(row.qc_bottles), 0)
			row.volume_litres = round(cint(row.actual_bottles) * cint(row.bottle_size_ml) / 1000, 4)

		for row in self.packaging_lines:
			row.total_bottles = cint(row.cartons) * cint(row.bottles_per_carton)

	def _compute_summary(self):
		self.total_volume_bottled = round(
			sum(flt(r.volume_litres) for r in self.bottling_lines), 4
		)
		input_vol = flt(self.input_quantity)
		self.process_loss = round(max(input_vol - self.total_volume_bottled, 0), 4)
		self.yield_efficiency_pct = round(
			(self.total_volume_bottled / input_vol) * 100, 2
		) if input_vol else 0.0

	def _match_abv_tax_band(self):
		if not self.abv_percentage:
			self.abv_tax_band = None
			return
		band = frappe.db.sql(
			"""
			SELECT name FROM `tabABV Tax Band`
			WHERE min_abv <= %s AND max_abv > %s
			ORDER BY min_abv DESC LIMIT 1
			""",
			(self.abv_percentage, self.abv_percentage),
			as_dict=True,
		)
		self.abv_tax_band = band[0].name if band else None

	def _compute_excise_duty(self):
		rate = flt(self.excise_duty_per_litre)
		if not rate and self.abv_tax_band:
			rate = flt(frappe.db.get_value("ABV Tax Band", self.abv_tax_band, "excise_duty_per_litre"))
			self.excise_duty_per_litre = rate
		self.excise_duty_amount = round(flt(self.total_volume_bottled) * rate, 4)

	# ------------------------------------------------------------------ #
	#  Submit / Cancel                                                     #
	# ------------------------------------------------------------------ #

	def on_submit(self):
		self._validate_submission()
		self._create_output_batches()
		self._create_stock_entry()
		self._update_wine_batch()

	def on_cancel(self):
		if self.stock_entry:
			se = frappe.get_doc("Stock Entry", self.stock_entry)
			if se.docstatus == 1:
				se.cancel()
			self.db_set("stock_entry", None)
		self._revert_wine_batch()

	# ------------------------------------------------------------------ #
	#  Validation                                                          #
	# ------------------------------------------------------------------ #

	def _validate_submission(self):
		if not self.bottling_lines:
			frappe.throw("Please add at least one Bottling Line.")
		if not any(cint(r.actual_bottles) > 0 for r in self.bottling_lines):
			frappe.throw("At least one Bottling Line must have actual bottles filled.")
		if not self.packaging_lines:
			frappe.throw("Please add at least one Packaging Line.")
		if not all(r.output_item for r in self.packaging_lines):
			frappe.throw("All Packaging Lines must have an Output Item.")
		if not self.abv_percentage:
			frappe.throw("ABV (%) is required before submitting.")
		if not self.abv_tax_band:
			frappe.throw(
				f"No ABV Tax Band matched for ABV {self.abv_percentage}%. "
				"Please configure ABV Tax Bands in Setup."
			)

	# ------------------------------------------------------------------ #
	#  Batch creation                                                      #
	# ------------------------------------------------------------------ #

	def _create_output_batches(self):
		"""
		Create one ERPNext Batch for this Wine Batch.
		batch_id  = Wine Batch name  (e.g. WB-2026-00001)
		item      = output_item on the Wine Batch
		All packaging lines receive this same batch_no.
		"""
		output_item = 'BW-375' #frappe.db.get_value("Wine Batch", self.wine_batch, "output_item")
		if not output_item:
			frappe.throw(
				f"Wine Batch <b>{self.wine_batch}</b> does not have an Output Item set. "
				"Please set it before submitting the Bottling."
			)

		# Reuse if already created (e.g. amendment)
		existing = frappe.db.get_value(
			"Batch", {"batch_id": self.wine_batch, "item": output_item}, "name"
		)
		if existing:
			batch_name = existing
		else:
			batch = frappe.new_doc("Batch")
			batch.item = output_item
			batch.batch_id = self.wine_batch
			batch.description = f"Wine Batch {self.wine_batch}"
			batch.insert(ignore_permissions=True)
			batch_name = batch.name

		self.db_set("erpnext_batch_no", batch_name)

		# Stamp batch_no on every packaging line
		for row in self.packaging_lines:
			frappe.db.set_value("Packaging Line", row.name, "output_batch_no", batch_name)

	# ------------------------------------------------------------------ #
	#  Stock Entry                                                         #
	# ------------------------------------------------------------------ #

	def _create_stock_entry(self):
		"""
		Manufacture SE:
		  Consume → bottles + sealing items (per bottling line)
		  Produce → packaged output items (per packaging line, with batch)
		"""
		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Manufacture"
		se.posting_date = self.bottling_date

		# --- Consume: bottles and sealing items from each bottling line ---
		for row in self.bottling_lines:
			if not cint(row.actual_bottles):
				continue
			# Empty bottles
			se.append("items", {
				"item_code": row.bottle_item,
				"qty": cint(row.actual_bottles),
				"s_warehouse": row.bottle_source_warehouse,
				"is_finished_item": 0,
			})
			# Sealing items (one per bottle)
			if row.sealing_item and row.sealing_source_warehouse:
				se.append("items", {
					"item_code": row.sealing_item,
					"qty": cint(row.actual_bottles),
					"s_warehouse": row.sealing_source_warehouse,
					"is_finished_item": 0,
				})

		# --- Produce: packaged cartons per packaging line ---
		# Reload rows to get the batch_no we just stamped
		self.reload()
		for row in self.packaging_lines:
			if not row.output_item or not cint(row.cartons):
				continue
			se.append("items", {
				"item_code": row.output_item,
				"qty": cint(row.cartons),
				"t_warehouse": row.output_warehouse,
				"batch_no": row.output_batch_no or None,
				"is_finished_item": 1,
			})

		se.insert(ignore_permissions=True)
		se.submit()
		self.db_set("stock_entry", se.name)
		frappe.msgprint(
			f"Stock Entry <b>{se.name}</b> created — bottling & packaging complete.",
			alert=True,
		)

	# ------------------------------------------------------------------ #
	#  Wine Batch update                                                   #
	# ------------------------------------------------------------------ #

	def _update_wine_batch(self):
		frappe.db.set_value("Wine Batch", self.wine_batch, {
			"actual_batch_size": self.total_volume_bottled,
			"process_loss": self.process_loss,
			"erpnext_batch_no": self.erpnext_batch_no,
			"status": "Completed",
		})

	def _revert_wine_batch(self):
		frappe.db.set_value("Wine Batch", self.wine_batch, {
			"actual_batch_size": 0,
			"process_loss": 0,
			"erpnext_batch_no": None,
			"status": "Active",
		})


# --------------------------------------------------------------------------- #
#  Whitelisted helpers                                                          #
# --------------------------------------------------------------------------- #

@frappe.whitelist()
def get_abv_tax_band(abv_percentage):
	abv = flt(abv_percentage)
	band = frappe.db.sql(
		"""
		SELECT name, excise_duty_per_litre
		FROM `tabABV Tax Band`
		WHERE min_abv <= %s AND max_abv > %s
		ORDER BY min_abv DESC LIMIT 1
		""",
		(abv, abv),
		as_dict=True,
	)
	return band[0] if band else {}


@frappe.whitelist()
def create_bottling(wine_batch):
	"""Called from Wine Batch custom button — creates and opens a new Bottling doc."""
	existing = frappe.db.get_value("Bottling", {"wine_batch": wine_batch, "docstatus": ["!=", 2]})
	if existing:
		return {"existing": existing}

	wb = frappe.get_doc("Wine Batch", wine_batch)
	return {
		"wine_batch": wine_batch,
		"bottling_date": frappe.utils.today(),
		"input_quantity": wb.target_batch_size or 0,
	}
