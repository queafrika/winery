"""Shared constants for the Winery Sales Agent POS backend."""

# Role granted to the linked User of every Sales Agent. No desk access.
SALES_AGENT_ROLE = "Winery Sales Agent"

# Customer Group used for POS walk-in / quick customers. Deliberately NOT
# flagged as KRA-PIN-mandatory so csf_ke's validate_customer_kra (which runs on
# Sales Invoice before_submit) does not block field sales.
POS_CUSTOMER_GROUP = "Walk-in (POS)"

# Parent (group) warehouse under which each agent's warehouse is created.
AGENT_PARENT_WAREHOUSE = "Sales Agents"

# Modes of Payment the POS app supports, with their ERPNext "type".
POS_MODES_OF_PAYMENT = {
    "Cash": "Cash",
    "M-Pesa": "Phone",
    "Bank": "Bank",
}

# Default POS Profile created for agents.
POS_PROFILE_NAME = "Winery Field Sales"

# Application error codes returned to the mobile client (see technical docs §9).
class ErrorCode:
    AGENT_INACTIVE = "AGENT_INACTIVE"
    STOCK_SHORT = "STOCK_SHORT"
    PAYMENT_MISMATCH = "PAYMENT_MISMATCH"
    DISCOUNT_EXCEEDED = "DISCOUNT_EXCEEDED"
    MPESA_NOT_CONFIRMED = "MPESA_NOT_CONFIRMED"
    INVALID_PHONE = "INVALID_PHONE"
    DUPLICATE_MPESA_CODE = "DUPLICATE_MPESA_CODE"
    DARAJA_UNREACHABLE = "DARAJA_UNREACHABLE"
    ALREADY_CLOSED = "ALREADY_CLOSED"
