import frappe
from frappe.model.document import Document
from frappe.utils import flt


class AgentDeliveryReceipt(Document):

	def validate(self):
		self._rebuild_items_from_pending_pis()
		self._compute_shortages()
		self._compute_totals()

	def on_submit(self):
		self.db_set("status", "Received")
		self._stamp_invoices_with_adr()
		self._create_stock_transfer()

	def on_cancel(self):
		self._cancel_stock_transfer()
		self.db_set("status", "Draft")
		self._clear_invoice_adr_stamp()

	# ------------------------------------------------------------------
	# Internal helpers
	# ------------------------------------------------------------------

	def _rebuild_items_from_pending_pis(self):
		"""Expand all pending PIs for this agent into item lines.

		Preserves received_qty already entered by the user, keyed by
		(purchase_invoice, item_code).  Re-aggregation happens on every
		save so newly created PIs are automatically included.
		"""
		if not self.agent:
			frappe.throw("Agent is required.")

		# Preserve received_qty entered by the user
		received_map = {
			(row.purchase_invoice, row.item_code): flt(row.received_qty)
			for row in self.items
			if row.purchase_invoice and row.item_code
		}

		pending_pis = frappe.db.get_all(
			"Purchase Invoice",
			filters={
				"agent": self.agent,
				"docstatus": 1,
				"agent_delivery_receipt": ["in", ["", None]],
			},
			fields=["name", "posting_date", "farmer", "custom_farm"],
			order_by="posting_date",
		)

		if not pending_pis:
			frappe.throw(
				f"No pending Purchase Invoices found for agent <b>{self.agent}</b>."
			)

		self.set("items", [])
		for pi in pending_pis:
			pi_items = frappe.db.get_all(
				"Purchase Invoice Item",
				filters={"parent": pi.name},
				fields=["item_code", "item_name", "qty"],
			)
			for r in pi_items:
				expected = flt(r.qty)
				self.append("items", {
					"purchase_invoice": pi.name,
					"posting_date":     pi.posting_date,
					"farmer":           pi.custom_farm or "",
					"item_code":        r.item_code,
					"item_name":        r.item_name,
					"expected_qty":     expected,
					"received_qty":     received_map.get((pi.name, r.item_code), expected),
				})

	def _compute_shortages(self):
		"""Per-row shortage = expected − received."""
		for row in self.items:
			row.shortage = flt(row.expected_qty) - flt(row.received_qty)

	def _compute_totals(self):
		self.total_bunches  = sum(flt(r.expected_qty) for r in self.items)
		self.total_received = sum(flt(r.received_qty) for r in self.items)
		self.total_shortage = sum(flt(r.shortage)     for r in self.items)
		# total_amount = sum of grand totals from all pending PIs for this agent
		self.total_amount = flt(
			frappe.db.sql(
				"""SELECT COALESCE(SUM(grand_total), 0)
				   FROM `tabPurchase Invoice`
				   WHERE agent = %s AND docstatus = 1
				     AND (agent_delivery_receipt IS NULL OR agent_delivery_receipt = '')""",
				self.agent,
			)[0][0]
		)

	def _stamp_invoices_with_adr(self):
		"""Link all pending PIs for this agent to this ADR."""
		pis = frappe.db.get_all(
			"Purchase Invoice",
			filters={
				"agent": self.agent,
				"docstatus": 1,
				"agent_delivery_receipt": ["in", ["", None]],
			},
			fields=["name"],
		)
		for pi in pis:
			frappe.db.set_value(
				"Purchase Invoice", pi.name, "agent_delivery_receipt", self.name
			)

	def _create_stock_transfer(self):
		"""Create a submitted Material Transfer Stock Entry moving received qty
		from the agent's transit warehouse to the ADR's receiving warehouse."""
		agent_doc = frappe.get_doc("Agent", self.agent)
		from_warehouse = agent_doc.transit_warehouse
		to_warehouse = self.receiving_warehouse

		if not from_warehouse:
			frappe.throw(
				f"Agent <b>{self.agent}</b> does not have a Transit Warehouse configured. "
				"Please set it on the Agent record before submitting."
			)
		if not to_warehouse:
			frappe.throw(
				"Please set a <b>Receiving Warehouse</b> on this receipt before submitting."
			)

		company = frappe.db.get_value(
			"Warehouse", to_warehouse, "company"
		) or frappe.defaults.get_global_default("company")

		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Material Transfer"
		se.posting_date = self.delivery_date
		se.company = company
		se.from_warehouse = from_warehouse
		se.to_warehouse = to_warehouse
		se.remarks = f"Stock transfer on submission of Agent Delivery Receipt {self.name}"

		for row in self.items:
			if flt(row.received_qty) <= 0:
				continue
			se.append("items", {
				"item_code":        row.item_code,
				"qty":              flt(row.received_qty),
				"s_warehouse":      from_warehouse,
				"t_warehouse":      to_warehouse,
				"is_finished_item": 1,
			})

		if not se.items:
			frappe.throw("No items with a positive received quantity — cannot create stock transfer.")

		se.insert()
		se.submit()
		self.db_set("stock_entry", se.name)

	def _cancel_stock_transfer(self):
		"""Cancel the linked Stock Entry when the ADR is cancelled."""
		if not self.stock_entry:
			return
		se_doc = frappe.get_doc("Stock Entry", self.stock_entry)
		if se_doc.docstatus == 1:
			se_doc.cancel()
		self.db_set("stock_entry", None)

	def _clear_invoice_adr_stamp(self):
		"""Remove ADR link from all PIs that reference this ADR."""
		pis = frappe.db.get_all(
			"Purchase Invoice",
			filters={"agent_delivery_receipt": self.name},
			fields=["name"],
		)
		for pi in pis:
			frappe.db.set_value(
				"Purchase Invoice", pi.name, "agent_delivery_receipt", None
			)


@frappe.whitelist()
def get_adr_for_invoice(purchase_invoice):
	"""Return the Agent Delivery Receipt name that contains this PI, or None."""
	adr = frappe.db.get_value("Purchase Invoice", purchase_invoice, "agent_delivery_receipt")
	return adr or None


@frappe.whitelist()
def get_lcv_for_adr(stock_entry):
	"""Return the Landed Cost Voucher name that references this stock entry, or None."""
	result = frappe.db.get_value(
		"Landed Cost Purchase Receipt",
		{
			"receipt_document_type": "Stock Entry",
			"receipt_document": stock_entry,
		},
		"parent",
	)
	return result or None


@frappe.whitelist()
def get_pending_items_for_agent(agent):
	"""Expand all pending PIs for this agent into individual item lines."""
	pis = frappe.db.get_all(
		"Purchase Invoice",
		filters={
			"agent": agent,
			"docstatus": 1,
			"agent_delivery_receipt": ["in", ["", None]],
		},
		fields=["name", "posting_date", "farmer", "custom_farm"],
		order_by="posting_date",
	)

	lines = []
	for pi in pis:
		pi_items = frappe.db.get_all(
			"Purchase Invoice Item",
			filters={"parent": pi.name},
			fields=["item_code", "item_name", "qty"],
		)
		for r in pi_items:
			lines.append({
				"purchase_invoice": pi.name,
				"posting_date":     pi.posting_date,
				"farmer":           pi.custom_farm or "",
				"item_code":        r.item_code,
				"item_name":        r.item_name,
				"expected_qty":     flt(r.qty),
			})

	return lines
