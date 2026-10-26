app_name = "custom_crm_updates"
app_title = "Custom CRM Updates"
app_publisher = "moatasem88"
app_description = "CRM customizations for Lead and Opportunity: Leads Activity, tendering automation, contacts tables"
app_email = "moatasemmahdy32@gmail.com"
app_license = "MIT"
required_apps = ["erpnext"]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/custom_crm_updates/css/custom_crm_updates.css"
# app_include_js = "/assets/custom_crm_updates/js/custom_crm_updates.js"

# include js, css files in header of web template
# web_include_css = "/assets/custom_crm_updates/css/custom_crm_updates.css"
# web_include_js = "/assets/custom_crm_updates/js/custom_crm_updates.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "custom_crm_updates/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
	"Lead": ["public/js/leads_activity_section.js", "public/js/lead.js"],
	"Opportunity": ["public/js/leads_activity_section.js", "public/js/opportunity.js"],
	"Customer": ["public/js/leads_activity_section.js", "public/js/customer.js"],
	# contracting app; the files are simply never loaded if it isn't installed
	"Tender": "public/js/tender.js",
	"Project Tender": "public/js/project_tender.js",
}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

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
# 	"methods": "custom_crm_updates.utils.jinja_methods",
# 	"filters": "custom_crm_updates.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "custom_crm_updates.install.before_install"
# after_install = "custom_crm_updates.install.after_install"
after_migrate = [
	# first: stamps the go-live cutoff on a site that has none, so the rules
	# added below apply to what is created from now on, not to what is
	# already in the database (custom_crm_updates/go_live.py)
	"custom_crm_updates.go_live.set_go_live",
	"custom_crm_updates.overrides.lead.apply_lead_customizations",
	"custom_crm_updates.overrides.opportunity.apply_opportunity_customizations",
	"custom_crm_updates.overrides.customer.apply_customer_customizations",
	"custom_crm_updates.overrides.project_tender.apply_project_tender_customizations",
	"custom_crm_updates.overrides.tender.apply_tender_customizations",
	"custom_crm_updates.overrides.contracting_backport.apply_contracting_backport",
	# after the three above: they need the custom fields
	"custom_crm_updates.custom_crm_updates.doctype.leads_activity.leads_activity.backfill_activity_tables",
	"custom_crm_updates.overrides.project_tender.backfill_opportunity_tenders",
	"custom_crm_updates.overrides.contact.backfill_contact_tables",
	"custom_crm_updates.overrides.opportunity.backfill_party_links",
	"custom_crm_updates.overrides.lead.backfill_date_of_convert",
	"custom_crm_updates.overrides.tender.backfill_completion_date",
]

# Uninstallation
# ------------

# before_uninstall = "custom_crm_updates.uninstall.before_uninstall"
# after_uninstall = "custom_crm_updates.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "custom_crm_updates.utils.before_app_install"
# after_app_install = "custom_crm_updates.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "custom_crm_updates.utils.before_app_uninstall"
# after_app_uninstall = "custom_crm_updates.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "custom_crm_updates.notifications.get_notification_config"

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
	"Lead": {
		"before_validate": "custom_crm_updates.overrides.lead.clear_person_fields",
		"validate": [
			"custom_crm_updates.overrides.lead.validate_customer_fields",
			"custom_crm_updates.overrides.lead.set_date_of_convert",
			"custom_crm_updates.overrides.contact.refresh_own_table",
		],
		"after_insert": "custom_crm_updates.overrides.contact.refresh_after_insert",
	},
	"Leads Activity": {
		"validate": [
			"custom_crm_updates.overrides.opportunity.validate_activity_source",
			# no Activity before the Opportunity is approved (Go)
			"custom_crm_updates.overrides.opportunity_workflow.validate_activity_opportunity",
		],
	},
	"Opportunity": {
		"validate": [
			"custom_crm_updates.overrides.contact.refresh_own_table",
			"custom_crm_updates.overrides.project_tender.validate_approved_tender",
			"custom_crm_updates.overrides.opportunity.set_party_links",
			"custom_crm_updates.overrides.opportunity.set_title",
			"custom_crm_updates.overrides.opportunity.validate_attachments",
			"custom_crm_updates.overrides.opportunity.calculate_contributions",
			"custom_crm_updates.overrides.opportunity.set_won_date",
		],
		# before validate: judges what the user sent, before ERPNext's validate
		# fills empty fields from the Lead/Customer (map_fields) and the
		# validators above work out theirs
		"before_validate": "custom_crm_updates.overrides.opportunity_workflow.enforce_workflow",
		"on_update": [
			"custom_crm_updates.overrides.project_tender.apply_approved_tender",
			"custom_crm_updates.overrides.contact.refresh_party_lead",
		],
		"on_trash": "custom_crm_updates.overrides.contact.refresh_party_lead",
	},
	"Customer": {
		"validate": "custom_crm_updates.overrides.contact.refresh_own_table",
		"on_update": [
			# the Lead it was made from rolls its contacts up
			"custom_crm_updates.overrides.contact.refresh_party_lead",
			# ERPNext marks that Lead "Converted" from here, straight in the
			# database, where no Lead hook can see it
			"custom_crm_updates.overrides.lead.set_date_of_convert_from_customer",
		],
		"on_trash": "custom_crm_updates.overrides.contact.refresh_party_lead",
	},
	"Contact": {
		"on_update": "custom_crm_updates.overrides.contact.on_contact_update",
		"on_trash": "custom_crm_updates.overrides.contact.on_contact_trash",
	},
	# contracting app; never fires if it isn't installed
	"Tender": {
		"before_insert": "custom_crm_updates.overrides.tender.set_submission_deadline",
		"validate": "custom_crm_updates.overrides.tender.set_completion_date",
		# after_insert/on_update: carried until contracting ships its own,
		# and skipped the moment it does (overrides/contracting_backport.py)
		"after_insert": "custom_crm_updates.overrides.contracting_backport.add_tender_to_direct_cost",
		"on_update": [
			"custom_crm_updates.overrides.contracting_backport.remove_cancelled_tender_rows",
			"custom_crm_updates.overrides.tender.push_completion_date_to_rows",
		],
	},
	"Project Tender": {
		"validate": [
			"custom_crm_updates.overrides.contracting_backport.validate_linked_tenders_complete",
			"custom_crm_updates.overrides.project_tender.validate_submitted_rows",
			"custom_crm_updates.overrides.project_tender.set_status_dates",
			"custom_crm_updates.overrides.opportunity_workflow.validate_tender_opportunity",
		],
		"on_update": "custom_crm_updates.overrides.project_tender.on_update",
		"on_trash": "custom_crm_updates.overrides.project_tender.on_trash",
	},
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"custom_crm_updates.tasks.all"
# 	],
# 	"daily": [
# 		"custom_crm_updates.tasks.daily"
# 	],
# 	"hourly": [
# 		"custom_crm_updates.tasks.hourly"
# 	],
# 	"weekly": [
# 		"custom_crm_updates.tasks.weekly"
# 	],
# 	"monthly": [
# 		"custom_crm_updates.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "custom_crm_updates.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "custom_crm_updates.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
override_doctype_dashboards = {
	"Lead": "custom_crm_updates.overrides.lead.get_dashboard_data",
	"Opportunity": "custom_crm_updates.overrides.opportunity.get_dashboard_data",
}

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["custom_crm_updates.utils.before_request"]
# after_request = ["custom_crm_updates.utils.after_request"]

# Job Events
# ----------
# before_job = ["custom_crm_updates.utils.before_job"]
# after_job = ["custom_crm_updates.utils.after_job"]

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
# 	"custom_crm_updates.auth.validate"
# ]
