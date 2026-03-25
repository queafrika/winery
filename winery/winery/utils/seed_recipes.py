import frappe

STAGES = [
	{"operation_type": "Cutting and Mushing", "expected_duration": 2},
	{"operation_type": "Mixing",              "expected_duration": 2},
	{"operation_type": "Fermentation",        "expected_duration": 672},
	{"operation_type": "Holding",             "expected_duration": 24},
	{"operation_type": "Chilling",            "expected_duration": 72},
]

LAB_ANALYSES = [
	{"operation_type": "Cutting and Mushing", "test_type": "Temperature Test",    "hours_after_start": 0,   "is_mandatory": 1, "is_recurring": 0, "recurrence_interval_hrs": 0},
	{"operation_type": "Mixing",              "test_type": "pH Test",             "hours_after_start": 0,   "is_mandatory": 1, "is_recurring": 0, "recurrence_interval_hrs": 0},
	{"operation_type": "Mixing",              "test_type": "Temperature Test",    "hours_after_start": 0,   "is_mandatory": 1, "is_recurring": 0, "recurrence_interval_hrs": 0},
	{"operation_type": "Fermentation",        "test_type": "Temperature Test",    "hours_after_start": 0,   "is_mandatory": 1, "is_recurring": 1, "recurrence_interval_hrs": 24},
	{"operation_type": "Fermentation",        "test_type": "Brix Test",           "hours_after_start": 24,  "is_mandatory": 1, "is_recurring": 1, "recurrence_interval_hrs": 24},
	{"operation_type": "Fermentation",        "test_type": "pH Test",             "hours_after_start": 72,  "is_mandatory": 1, "is_recurring": 1, "recurrence_interval_hrs": 72},
	{"operation_type": "Fermentation",        "test_type": "Gravity Test",        "hours_after_start": 48,  "is_mandatory": 1, "is_recurring": 1, "recurrence_interval_hrs": 48},
	{"operation_type": "Fermentation",        "test_type": "Residual Sugar Test", "hours_after_start": 336, "is_mandatory": 1, "is_recurring": 0, "recurrence_interval_hrs": 0},
	{"operation_type": "Fermentation",        "test_type": "Dissolution Test",    "hours_after_start": 168, "is_mandatory": 0, "is_recurring": 0, "recurrence_interval_hrs": 0},
	{"operation_type": "Holding",             "test_type": "Residual Sugar Test", "hours_after_start": 0,   "is_mandatory": 1, "is_recurring": 0, "recurrence_interval_hrs": 0},
	{"operation_type": "Holding",             "test_type": "pH Test",             "hours_after_start": 0,   "is_mandatory": 1, "is_recurring": 0, "recurrence_interval_hrs": 0},
	{"operation_type": "Holding",             "test_type": "Temperature Test",    "hours_after_start": 0,   "is_mandatory": 1, "is_recurring": 0, "recurrence_interval_hrs": 0},
	{"operation_type": "Chilling",            "test_type": "Cold Stability Test", "hours_after_start": 24,  "is_mandatory": 1, "is_recurring": 0, "recurrence_interval_hrs": 0},
	{"operation_type": "Chilling",            "test_type": "Temperature Test",    "hours_after_start": 0,   "is_mandatory": 1, "is_recurring": 1, "recurrence_interval_hrs": 24},
]

RECIPES = ["Dry Wine", "Medium Dry Wine", "Semi Sweet Wine", "Sweet Wine"]


def seed_recipe_data():
	"""Seed Recipe Stage and Lab Analysis rows for all winery recipes.

	Only seeds a recipe if it currently has NO stages — this preserves any
	user-edited data on subsequent migrations while recovering from a wipe.
	"""
	for recipe_name in RECIPES:
		if not frappe.db.exists("Recipe", recipe_name):
			continue
		doc = frappe.get_doc("Recipe", recipe_name)
		if doc.stages:
			# User has data — skip to preserve their changes
			continue
		for s in STAGES:
			doc.append("stages", s.copy())
		for la in LAB_ANALYSES:
			doc.append("lab_analyses", la.copy())
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		frappe.logger().info(
			f"[seed_recipe_data] Seeded {recipe_name}: "
			f"{len(doc.stages)} stages, {len(doc.lab_analyses)} lab analyses"
		)
		print(f"Seeded {recipe_name}: {len(doc.stages)} stages, {len(doc.lab_analyses)} lab analyses")
