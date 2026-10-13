"""Customer customizations.

- Contact & Address tab: the contact list is shown as a read-only Contacts
  table (custom_crm_updates/overrides/contact.py) instead of core's
  contact_html, exactly as on the Lead and the Opportunity. A Customer shows
  the contacts linked to the Customer itself; the Lead it was made from rolls
  those up together with its own and its Opportunities'.

Applied on every migrate by `apply_customer_customizations` (hooks.py
after_migrate); idempotent, so re-running is safe.
"""

import frappe

from custom_crm_updates.overrides.contact import contact_table_fields

# Replaced by the Contacts table; core still renders into it, just unseen.
HIDDEN_FIELDS = ("contact_html",)

CUSTOM_FIELDS = {
	# last field of the Address and Contact section, so the table follows the
	# address block and comes before Primary Address and Contact Detail
	"Customer": [*contact_table_fields(insert_after="contact_html")]
}


def apply_customer_customizations():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	create_custom_fields(CUSTOM_FIELDS, update=True)

	for fieldname in HIDDEN_FIELDS:
		make_property_setter(
			"Customer", fieldname, "hidden", 1, "Check", validate_fields_for_doctype=False
		)
