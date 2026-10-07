"""Opportunity customizations.

- "Opportunity Activities" section at the top of the Activities tab: a
  read-only table of the Leads Activity records linked to this Opportunity
  (Link Type = Opportunity), kept in sync by Leads Activity (see
  sync_activity_table). Activities of the Lead it came from are not shown.
- "Project Tender" tab (before Activities): read-only table of the Project
  Tenders created for this Opportunity (custom_crm_updates/overrides/project_tender.py).
- Status options "Tendering" and "Won", set by that Project Tender automation.
- Contacts tab: the contact list is shown as a read-only Contacts table
  (custom_crm_updates/overrides/contact.py) instead of core's contact_html.
- Connections entry for Leads Activity.

Applied on every migrate by `apply_opportunity_customizations` (hooks.py
after_migrate); idempotent, so re-running is safe.
"""

import frappe

from custom_crm_updates.overrides.contact import contact_table_fields
from custom_crm_updates.overrides.project_tender import TENDER_TABLE
from custom_crm_updates.custom_crm_updates.doctype.leads_activity.leads_activity import (
	activity_table_fields,
	add_to_dashboard,
)

PROJECT_TENDER_TAB = "custom_project_tender_tab"
EXTRA_STATUSES = ("Tendering", "Won")
# Replaced by the Contacts table; core still renders into it, just unseen.
HIDDEN_FIELDS = ("contact_html",)

CUSTOM_FIELDS = {
	"Opportunity": [
		*activity_table_fields("Opportunity Activities"),
		# last field of the Items tab, so the new tab sits before Activities
		{
			"fieldname": PROJECT_TENDER_TAB,
			"fieldtype": "Tab Break",
			"label": "Project Tender",
			"insert_after": "total",
			"depends_on": "eval:!doc.__islocal",
		},
		{
			"fieldname": TENDER_TABLE,
			"fieldtype": "Table",
			"label": "Project Tenders",
			"options": "Opportunity Project Tender",
			"insert_after": PROJECT_TENDER_TAB,
			"read_only": 1,
			"no_copy": 1,
		},
		# last field of the Contacts tab
		*contact_table_fields(insert_after="contact_display"),
	]
}


def apply_opportunity_customizations():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	create_custom_fields(CUSTOM_FIELDS, update=True)

	# Extend core's options (read from the DocField, not the merged meta) so
	# options ERPNext adds later are kept.
	options = frappe.db.get_value(
		"DocField", {"parent": "Opportunity", "fieldname": "status"}, "options"
	).split("\n")
	options += [status for status in EXTRA_STATUSES if status not in options]
	make_property_setter(
		"Opportunity", "status", "options", "\n".join(options), "Text", validate_fields_for_doctype=False
	)

	for fieldname in HIDDEN_FIELDS:
		make_property_setter(
			"Opportunity", fieldname, "hidden", 1, "Check", validate_fields_for_doctype=False
		)


def get_dashboard_data(data):
	"""override_doctype_dashboards"""
	return add_to_dashboard(data, "Opportunity")
