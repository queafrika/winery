"""Idempotent setup helpers for the Winery Sales Agent POS backend.

All helpers are safe to run repeatedly. They can be called from a patch, from
`bench console`, or from the Sales Agent lifecycle hooks. Nothing here creates a
document that already exists.
"""

import frappe
from frappe import _

from winery.winery.pos.constants import (
    AGENT_PARENT_WAREHOUSE,
    POS_CUSTOMER_GROUP,
    POS_MODES_OF_PAYMENT,
    POS_PROFILE_NAME,
    SALES_AGENT_ROLE,
)


def get_default_company():
    company = frappe.defaults.get_global_default("company")
    if not company:
        company = frappe.db.get_value("Company", {}, "name")
    if not company:
        frappe.throw(_("No Company found. Please create a Company first."))
    return company


def get_company_abbr(company):
    return frappe.db.get_value("Company", company, "abbr")


def ensure_role():
    """Create the Winery Sales Agent role with no desk access."""
    if not frappe.db.exists("Role", SALES_AGENT_ROLE):
        role = frappe.new_doc("Role")
        role.role_name = SALES_AGENT_ROLE
        role.desk_access = 0
        role.insert(ignore_permissions=True)
    ensure_role_permissions()
    return SALES_AGENT_ROLE


# Doctypes the agent's session reads while the POS engine builds/prices/submits a
# sale (ERPNext enforces hard read checks on these, e.g. get_party_details on
# Customer). The invoice itself is created with ignore_permissions in the engine.
_AGENT_READ_DOCTYPES = (
    "Customer",
    "Item",
    "Item Price",
    "Price List",
    "Batch",
    "Warehouse",
    "UOM",
    "Sales Invoice",
    "Sales Taxes and Charges Template",
    "Mode of Payment",
    "POS Profile",
)


def ensure_role_permissions():
    """Grant the role read access to the core doctypes the engine reads.

    Idempotent — skips any doctype that already has a rule for the role.
    """
    from frappe.permissions import add_permission

    for dt in _AGENT_READ_DOCTYPES:
        exists = frappe.db.get_value(
            "Custom DocPerm",
            {"parent": dt, "role": SALES_AGENT_ROLE, "permlevel": 0, "if_owner": 0},
        )
        if not exists:
            add_permission(dt, SALES_AGENT_ROLE, permlevel=0, ptype="read")


def ensure_pos_customer_group():
    """Walk-in customer group that does NOT mandate a KRA PIN.

    csf_ke's validate_customer_kra runs on Sales Invoice before_submit and throws
    when a customer's group mandates a KRA PIN and none is set. Field sales use
    walk-in customers with no PIN, so this group must never be flagged mandatory.
    """
    if not frappe.db.exists("Customer Group", POS_CUSTOMER_GROUP):
        parent = frappe.db.get_value(
            "Customer Group", {"is_group": 1}, "name"
        ) or "All Customer Groups"
        cg = frappe.new_doc("Customer Group")
        cg.customer_group_name = POS_CUSTOMER_GROUP
        cg.parent_customer_group = parent
        cg.is_group = 0
        cg.insert(ignore_permissions=True)
    # Defensively clear the csf_ke mandatory flag if the field exists.
    if frappe.db.has_column("Customer Group", "custom_is_kra_pin_mandatory_in"):
        frappe.db.set_value(
            "Customer Group",
            POS_CUSTOMER_GROUP,
            "custom_is_kra_pin_mandatory_in",
            0,
        )
    return POS_CUSTOMER_GROUP


def ensure_agent_parent_warehouse(company=None):
    """Group warehouse under which each agent's warehouse is created."""
    company = company or get_default_company()
    abbr = get_company_abbr(company)
    name = f"{AGENT_PARENT_WAREHOUSE} - {abbr}"
    if not frappe.db.exists("Warehouse", name):
        root = frappe.db.get_value(
            "Warehouse",
            {"company": company, "is_group": 1, "parent_warehouse": ["in", ["", None]]},
            "name",
        )
        wh = frappe.new_doc("Warehouse")
        wh.warehouse_name = AGENT_PARENT_WAREHOUSE
        wh.company = company
        wh.is_group = 1
        if root:
            wh.parent_warehouse = root
        wh.insert(ignore_permissions=True)
    return name


def ensure_agent_warehouse(agent_name, company=None):
    """Leaf warehouse holding one agent's consignment stock."""
    company = company or get_default_company()
    abbr = get_company_abbr(company)
    parent = ensure_agent_parent_warehouse(company)
    wh_name = f"Agent - {agent_name} - {abbr}"
    if not frappe.db.exists("Warehouse", wh_name):
        wh = frappe.new_doc("Warehouse")
        wh.warehouse_name = f"Agent - {agent_name}"
        wh.company = company
        wh.is_group = 0
        wh.parent_warehouse = parent
        wh.insert(ignore_permissions=True)
        wh_name = wh.name
    return wh_name


def ensure_walk_in_customer(agent_name):
    """Per-agent default walk-in customer in the non-KRA customer group."""
    ensure_pos_customer_group()
    customer_name = f"Walk-in - {agent_name}"
    if not frappe.db.exists("Customer", {"customer_name": customer_name}):
        cust = frappe.new_doc("Customer")
        cust.customer_name = customer_name
        cust.customer_group = POS_CUSTOMER_GROUP
        cust.customer_type = "Individual"
        territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
        if territory:
            cust.territory = territory
        cust.insert(ignore_permissions=True)
        return cust.name
    return frappe.db.get_value("Customer", {"customer_name": customer_name}, "name")


def ensure_modes_of_payment(company=None):
    """Ensure Cash / M-Pesa / Bank modes exist, each mapped to a company account."""
    company = company or get_default_company()
    created = []
    for mop, mop_type in POS_MODES_OF_PAYMENT.items():
        if not frappe.db.exists("Mode of Payment", mop):
            doc = frappe.new_doc("Mode of Payment")
            doc.mode_of_payment = mop
            doc.type = mop_type
            doc.insert(ignore_permissions=True)
            created.append(mop)
        _ensure_mop_account(mop, mop_type, company)
    return created


def _ensure_mop_account(mop, mop_type, company):
    doc = frappe.get_doc("Mode of Payment", mop)
    if any(row.company == company for row in doc.accounts):
        return
    account = _default_account_for_type(mop_type, company)
    if not account:
        return
    doc.append("accounts", {"company": company, "default_account": account})
    doc.save(ignore_permissions=True)


def _default_account_for_type(mop_type, company):
    """Pick a sensible default GL account for a mode-of-payment type."""
    if mop_type == "Cash":
        acc = frappe.db.get_value("Company", company, "default_cash_account")
        if acc:
            return acc
        return frappe.db.get_value(
            "Account",
            {"company": company, "account_type": "Cash", "is_group": 0},
            "name",
        )
    if mop_type == "Phone":  # M-Pesa
        return _ensure_clearing_account(company, "M-Pesa Clearing")
    # Bank — use the company's configured bank account, else a dedicated clearing
    # account. (Do not fall back to a generic Bank-type search: the M-Pesa clearing
    # account is also Bank-typed and would be picked up by mistake.)
    acc = frappe.db.get_value("Company", company, "default_bank_account")
    if acc:
        return acc
    return _ensure_clearing_account(company, "Bank Clearing")


def _ensure_clearing_account(company, account_name):
    """Create (idempotently) a leaf Bank-type clearing account for the company."""
    abbr = get_company_abbr(company)
    full_name = f"{account_name} - {abbr}"
    if frappe.db.exists("Account", full_name):
        return full_name

    parent = (
        frappe.db.get_value(
            "Account", {"company": company, "account_type": "Bank", "is_group": 1}, "name"
        )
        or frappe.db.get_value(
            "Account",
            {"company": company, "account_name": "Bank Accounts", "is_group": 1},
            "name",
        )
        or frappe.db.get_value(
            "Account",
            {"company": company, "root_type": "Asset", "is_group": 1,
             "parent_account": ["not in", ["", None]]},
            "name",
        )
    )
    if not parent:
        return None
    acc = frappe.new_doc("Account")
    acc.account_name = account_name
    acc.company = company
    acc.parent_account = parent
    acc.account_type = "Bank"
    acc.is_group = 0
    acc.insert(ignore_permissions=True)
    return acc.name


def _default_profile_warehouse(company):
    """A leaf warehouse to satisfy POS Profile's mandatory warehouse field.

    Only a placeholder: the sale engine sets the agent's own leaf warehouse on
    every invoice (`si.set_warehouse`), so this value is never used for stock.
    Prefers Stock Settings' default warehouse, then "Stores", then any leaf.
    """
    default = frappe.db.get_single_value("Stock Settings", "default_warehouse")
    if default and frappe.db.get_value("Warehouse", default, "company") == company:
        if not frappe.db.get_value("Warehouse", default, "is_group"):
            return default

    abbr = get_company_abbr(company)
    stores = f"Stores - {abbr}"
    if frappe.db.exists("Warehouse", {"name": stores, "is_group": 0, "company": company}):
        return stores

    return frappe.db.get_value(
        "Warehouse",
        {"company": company, "is_group": 0, "disabled": 0},
        "name",
        order_by="creation asc",
    )


def ensure_pos_profile(company=None):
    """Default POS Profile used by field sales agents."""
    company = company or get_default_company()
    ensure_modes_of_payment(company)
    if frappe.db.exists("POS Profile", POS_PROFILE_NAME):
        return POS_PROFILE_NAME
    warehouse = _default_profile_warehouse(company)
    if not warehouse:
        # No leaf warehouse yet (bare company). Skip — the next migrate retries.
        print(f"Skipping POS Profile {POS_PROFILE_NAME}: no leaf warehouse for {company}")
        return None
    cost_center = frappe.db.get_value("Company", company, "cost_center") or frappe.db.get_value(
        "Cost Center", {"company": company, "is_group": 0}, "name"
    )
    write_off_account = frappe.db.get_value(
        "Company", company, "write_off_account"
    ) or frappe.db.get_value(
        "Account",
        {"company": company, "root_type": "Expense", "is_group": 0},
        "name",
    )
    profile = frappe.new_doc("POS Profile")
    profile.name = POS_PROFILE_NAME
    profile.company = company
    profile.currency = frappe.db.get_value("Company", company, "default_currency")
    # Warehouse is mandatory on POS Profile and must be a leaf, but each agent
    # has their own — the sale engine overrides it per invoice. So set any leaf
    # warehouse here as a placeholder; never a group warehouse, which would be
    # copied into the transaction and rejected.
    profile.warehouse = warehouse
    profile.cost_center = cost_center
    profile.write_off_account = write_off_account
    profile.write_off_cost_center = cost_center
    for mop in POS_MODES_OF_PAYMENT:
        profile.append(
            "payments",
            {"mode_of_payment": mop, "default": 1 if mop == "Cash" else 0},
        )
    profile.insert(ignore_permissions=True)
    return POS_PROFILE_NAME


def run_full_setup(company=None):
    """One-shot idempotent bootstrap of every shared POS artifact."""
    company = company or get_default_company()
    ensure_role()
    ensure_pos_customer_group()
    ensure_agent_parent_warehouse(company)
    ensure_modes_of_payment(company)
    ensure_pos_profile(company)
    frappe.db.commit()
    return {"company": company, "status": "ok"}
