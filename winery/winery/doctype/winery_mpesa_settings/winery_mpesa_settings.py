import frappe
from frappe.model.document import Document


class WineryMpesaSettings(Document):
	def validate(self):
		# Keep the (read-only) callback URL in sync with the site so it can be
		# copied into the Daraja app configuration.
		base = frappe.utils.get_url()
		self.callback_url = (
			f"{base}/api/method/winery.winery.pos.api.mpesa_callback"
		)

	def base_url(self):
		return (
			"https://api.safaricom.co.ke"
			if self.environment == "Production"
			else "https://sandbox.safaricom.co.ke"
		)
