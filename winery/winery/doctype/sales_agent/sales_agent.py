import frappe
from frappe import _
from frappe.model.document import Document

from winery.winery.pos import setup
from winery.winery.pos.constants import SALES_AGENT_ROLE


class SalesAgent(Document):
	def before_insert(self):
		self._provision_warehouse_and_customer()

	def validate(self):
		self._ensure_user_role()
		self._set_default_price_list()
		self._guard_warehouse_change()

	def on_update(self):
		self._sync_api_access()

	# ------------------------------------------------------------------ #
	# provisioning
	# ------------------------------------------------------------------ #
	def _provision_warehouse_and_customer(self):
		company = setup.get_default_company()
		if not self.agent_warehouse:
			self.agent_warehouse = setup.ensure_agent_warehouse(
				self.sales_agent_name, company
			)
		if not self.default_customer:
			self.default_customer = setup.ensure_walk_in_customer(self.sales_agent_name)

	def _set_default_price_list(self):
		if self.selling_price_list:
			return
		self.selling_price_list = frappe.db.get_single_value(
			"Selling Settings", "selling_price_list"
		) or frappe.db.get_value("Price List", {"selling": 1, "enabled": 1}, "name")

	def _guard_warehouse_change(self):
		if self.is_new() or not self.has_value_changed("agent_warehouse"):
			return
		old = self.get_doc_before_save()
		if not old or not old.agent_warehouse:
			return
		balance = frappe.db.sql(
			"""
			SELECT COALESCE(SUM(actual_qty), 0)
			FROM `tabStock Ledger Entry`
			WHERE warehouse = %s AND is_cancelled = 0
			""",
			old.agent_warehouse,
		)[0][0]
		if balance and float(balance) != 0:
			frappe.throw(
				_(
					"Cannot change the agent warehouse while <b>{0}</b> still holds "
					"stock (balance {1}). Transfer the stock out first."
				).format(old.agent_warehouse, balance)
			)

	# ------------------------------------------------------------------ #
	# user / role management
	# ------------------------------------------------------------------ #
	def _ensure_user_role(self):
		if not self.user:
			return
		setup.ensure_role()
		user = frappe.get_doc("User", self.user)
		if SALES_AGENT_ROLE not in {r.role for r in user.roles}:
			user.append("roles", {"role": SALES_AGENT_ROLE})
			user.save(ignore_permissions=True)

	def _sync_api_access(self):
		"""When an agent is not Active, revoke their API keys so the app is locked out."""
		if not self.user or self.status == "Active":
			return
		if frappe.db.get_value("User", self.user, "api_key"):
			frappe.db.set_value("User", self.user, {"api_key": None, "api_secret": None})


def get_agent_for_user(user=None, throw=True):
	"""Resolve the active Sales Agent record for a session user.

	Central helper used by every POS API entrypoint so the agent (and therefore the
	warehouse and price list) is always derived server-side, never trusted from the
	client.
	"""
	user = user or frappe.session.user
	name = frappe.db.get_value("Sales Agent", {"user": user}, "name")
	if not name:
		if throw:
			frappe.throw(_("No Sales Agent is linked to this user."), frappe.PermissionError)
		return None
	agent = frappe.get_doc("Sales Agent", name)
	if agent.status != "Active" and throw:
		frappe.throw(_("This sales agent account is not active."), frappe.PermissionError)
	return agent
