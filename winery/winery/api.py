import frappe


@frappe.whitelist()
def get_desktop_config():
	"""
	Return the tabs and icons the current user is allowed to see,
	based on role restrictions configured in Winery Desktop Tab and
	Winery Desktop Icon.
	"""
	user_roles = set(frappe.get_roles(frappe.session.user))

	# ── Fetch all tabs ordered by `order` ────────────────────────────────────
	tabs = frappe.get_all(
		"Winery Desktop Tab",
		fields=["name", "tab_name", "order"],
		order_by="order asc",
		ignore_permissions=True,
	)

	# Pre-fetch all tab role rows in one query
	tab_role_rows = frappe.get_all(
		"Winery Desktop Tab Role",
		fields=["parent", "role"],
		ignore_permissions=True,
	)
	tab_roles_map = {}
	for row in tab_role_rows:
		tab_roles_map.setdefault(row.parent, []).append(row.role)

	# ── Fetch all enabled icons ordered by `order` ───────────────────────────
	icons = frappe.get_all(
		"Winery Desktop Icon",
		filters={"enabled": 1},
		fields=["name", "icon_label", "tab", "workspace_sidebar", "order"],
		order_by="order asc",
		ignore_permissions=True,
	)

	# Pre-fetch all icon role rows in one query
	icon_role_rows = frappe.get_all(
		"Winery Desktop Icon Role",
		fields=["parent", "role"],
		ignore_permissions=True,
	)
	icon_roles_map = {}
	for row in icon_role_rows:
		icon_roles_map.setdefault(row.parent, []).append(row.role)

	# ── Filter icons by user roles ────────────────────────────────────────────
	def user_can_see(roles_map, doc_name):
		allowed = roles_map.get(doc_name, [])
		# Empty roles list → visible to everyone
		return not allowed or bool(user_roles & set(allowed))

	icons_by_tab = {}
	for icon in icons:
		if user_can_see(icon_roles_map, icon.name):
			icons_by_tab.setdefault(icon.tab, []).append({
				"icon_label": icon.icon_label,
				"workspace_sidebar": icon.workspace_sidebar,
			})

	# ── Filter tabs by user roles and build result ────────────────────────────
	result = []
	for tab in tabs:
		if not user_can_see(tab_roles_map, tab.name):
			continue
		result.append({
			"tab_name": tab.tab_name,
			"icons": icons_by_tab.get(tab.name, []),
		})

	return result
