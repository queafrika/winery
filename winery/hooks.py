app_name = "winery"
app_title = "Winery"


fixtures = [
	{
		"dt": "Custom Field",
		"filters": [["module", "=", "Winery"]]
	},
	{
		"dt": "Lab Analysis Test Type"
	}
]

scheduler_events = {
	"daily": [
		"winery.tasks.send_lab_analysis_reminders",
		"winery.tasks.send_ripening_ready_reminders",
		"winery.tasks.check_overdue_ripening_batches",
		"winery.tasks.send_ripening_rack_report",
		"winery.tasks.generate_compliance_tasks",
		"winery.tasks.send_compliance_task_reminders",
	],
	"hourly": [
		"winery.tasks.check_ungraded_adrs",
	],
}

app_publisher = "Finesoft Afrika"
app_description = "Winery Manufacturing System"
app_email = "macharianyota@gmail.com"
app_license = "mit"

# Apps
# ------------------

required_apps = ["erpnext"]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "winery",
# 		"logo": "/assets/winery/logo.png",
# 		"title": "Winery",
# 		"route": "/winery",
# 		"has_permission": "winery.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
app_include_css = ["/assets/winery/css/winery.css"]
app_include_js = ["/assets/winery/js/winery.js"]

# include js, css files in header of web template
web_include_css = ["/assets/winery/css/winery-login.css"]
# web_include_js = "/assets/winery/js/winery.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "winery/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "winery/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "winery.utils.jinja_methods",
# 	"filters": "winery.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "winery.install.before_install"
# after_install = "winery.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "winery.uninstall.before_uninstall"
# after_uninstall = "winery.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "winery.utils.before_app_install"
# after_app_install = "winery.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "winery.utils.before_app_uninstall"
# after_app_uninstall = "winery.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "winery.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events


doc_events = {
	"Purchase Receipt": {
		"on_submit": "winery.winery.utils.qa_hooks.set_batch_qa_pending",
	},
	"Purchase Invoice": {
		"on_submit": "winery.winery.utils.qa_hooks.set_batch_qa_pending",
	},
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"winery.tasks.all"
# 	],
# 	"daily": [
# 		"winery.tasks.daily"
# 	],
# 	"hourly": [
# 		"winery.tasks.hourly"
# 	],
# 	"weekly": [
# 		"winery.tasks.weekly"
# 	],
# 	"monthly": [
# 		"winery.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "winery.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "winery.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "winery.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["winery.utils.before_request"]
# after_request = ["winery.utils.after_request"]

# Job Events
# ----------
# before_job = ["winery.utils.before_job"]
# after_job = ["winery.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"winery.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

