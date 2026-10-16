"""Lead customizations.

- "Is Company" flag: a company lead has no person behind it, so ticking the
  flag hides the person-only fields and clears them on save.
- Organization section moved above Contact Info.
- "Address & Contacts" moved out of the Details tab into its own tab, before
  Activities. Its contact list is shown as a read-only Contacts table
  (custom_crm_updates/overrides/contact.py) instead of core's contact_html.
- Customer Group (custom) and Territory (core) are mandatory: the Customer a
  Lead is converted into takes them from the Lead.
- convert_lead_to_customer: used by Leads Activity (Registration -> Done) and
  by Project Tender creation.
- "Date of Convert": the day the Lead's status first became "Converted",
  recorded by set_date_of_convert (its own save) and
  set_date_of_convert_from_customer (the Customer ERPNext raises from it,
  which flips the status straight in the database).
- "Leads Activities" section at the top of the Activities tab: a read-only
  table kept in sync by Leads Activity (see sync_activity_table), plus a
  Connections entry for Leads Activity.

Applied on every migrate by `apply_lead_customizations` (hooks.py
after_migrate); every step is idempotent, so re-running is safe.
"""

import json

import frappe
from frappe import _
from frappe.utils import get_link_to_form, nowdate

from custom_crm_updates.go_live import applies_to
from custom_crm_updates.overrides.contact import CONTACT_SECTION, contact_table_fields
from custom_crm_updates.custom_crm_updates.doctype.leads_activity.leads_activity import (
	activity_table_fields,
	add_to_dashboard,
)

IS_COMPANY = "custom_is_company"
# Deliberately unprefixed: the field name was specified as date_of_convert.
CONVERT_DATE = "date_of_convert"
CONVERTED = "Converted"
ADDRESS_TAB = "custom_address_contacts_tab"
CUSTOMER_GROUP = "custom_customer_group"
# What convert_lead_to_customer needs from the Lead.
CUSTOMER_FIELDS = (CUSTOMER_GROUP, "territory")

PERSON_FIELDS = ("salutation", "first_name", "middle_name", "last_name", "gender", "job_title")

CUSTOM_FIELDS = {
	"Lead": [
		{
			"fieldname": IS_COMPANY,
			"fieldtype": "Check",
			"label": "Is Company",
			"default": "0",
			"insert_after": "naming_series",
		},
		# Its real position (with the address section moved after it) is set
		# by apply_field_order; insert_after only matters if that is reset.
		{
			"fieldname": ADDRESS_TAB,
			"fieldtype": "Tab Break",
			"label": "Address & Contacts",
			"insert_after": "blog_subscriber",
		},
		# beside Territory in the Organization section
		{
			"fieldname": CUSTOMER_GROUP,
			"fieldtype": "Link",
			"label": "Customer Group",
			"options": "Customer Group",
			"insert_after": "territory",
			"in_standard_filter": 1,
		},
		{
			"fieldname": CONVERT_DATE,
			"fieldtype": "Date",
			"label": "Date of Convert",
			"insert_after": "status",
			"read_only": 1,
			"no_copy": 1,
			"allow_on_submit": 0,
			"description": "The day this Lead was converted. Set once, automatically.",
		},
		*activity_table_fields("Leads Activities"),
		# moved to the end of the Address & Contacts tab by apply_field_order
		*contact_table_fields(insert_after="contact_html"),
	],
}

# Superseded by the custom_leads_activities table.
OBSOLETE_CUSTOM_FIELDS = ("Lead-custom_leads_activities_html",)

SECTION_BREAKS = ("Section Break", "Tab Break")

# Core makes first_name mandatory whenever company_name is blank (and vice
# versa). With first_name hidden that would demand a field the user can't
# see, so a company lead always requires Organization Name instead.
MANDATORY_DEPENDS_ON = {
	"first_name": "eval: !doc.%s && !(doc.company_name)" % IS_COMPANY,
	"company_name": "eval: doc.%s || !(doc.first_name)" % IS_COMPANY,
	# Not reqd: Frappe enforces reqd on every insert, including the Leads
	# ERPNext creates by itself (website contact form, an Opportunity made
	# from an email address, appointments), which have no one to ask. The form
	# enforces mandatory_depends_on; validate_customer_fields covers the rest.
	**{fieldname: "eval:1" for fieldname in CUSTOMER_FIELDS},
}

# In its own tab the section needn't repeat the tab's title, and collapsible
# would open the tab with the section folded.
ADDRESS_SECTION_PROPERTIES = (("label", "", "Data"), ("collapsible", "0", "Check"))

# Replaced by the Contacts table; core still renders into it, just unseen.
HIDDEN_FIELDS = ("contact_html",)


def apply_lead_customizations():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	for name in OBSOLETE_CUSTOM_FIELDS:
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, ignore_permissions=True)

	create_custom_fields(CUSTOM_FIELDS, update=True)

	# A new Property Setter deletes any existing one for the same
	# doctype/field/property, so these replace rather than duplicate.
	for fieldname in PERSON_FIELDS:
		make_property_setter(
			"Lead", fieldname, "depends_on", "eval: !doc.%s" % IS_COMPANY, "Data",
			validate_fields_for_doctype=False,
		)
	for fieldname, expression in MANDATORY_DEPENDS_ON.items():
		make_property_setter(
			"Lead", fieldname, "mandatory_depends_on", expression, "Data",
			validate_fields_for_doctype=False,
		)

	for prop, value, prop_type in ADDRESS_SECTION_PROPERTIES:
		make_property_setter(
			"Lead", "address_section", prop, value, prop_type, validate_fields_for_doctype=False
		)
	for fieldname in HIDDEN_FIELDS:
		make_property_setter("Lead", fieldname, "hidden", 1, "Check", validate_fields_for_doctype=False)

	apply_field_order()


def apply_field_order():
	"""Standard fields can only be reordered through a `field_order` Property
	Setter (what Customize Form saves), so rebuild it from the current order
	with our moves applied. Other reorderings made through Customize Form are
	preserved."""
	fields = frappe.get_meta("Lead", cached=False).fields
	order = [df.fieldname for df in fields]
	fieldtypes = {df.fieldname: df.fieldtype for df in fields}

	new_order = move_section(order, fieldtypes, "organization_section", before="contact_info_tab")
	# A Tab Break takes every field up to the next one, so the address section
	# has to sit right before Activities rather than mid-Details.
	new_order = move_section(
		new_order, fieldtypes, "address_section", before="activities_tab", header=ADDRESS_TAB
	)
	# after the address section, i.e. last in the Address & Contacts tab
	new_order = move_section(new_order, fieldtypes, CONTACT_SECTION, before="activities_tab")

	if new_order == order:
		return

	frappe.make_property_setter(
		{
			"doctype": "Lead",
			"doctype_or_field": "DocType",
			"property": "field_order",
			"value": json.dumps(new_order),
		},
		validate_fields_for_doctype=False,
	)


def move_section(order, fieldtypes, section, before, header=None):
	"""Move `section` and its fields (up to the next Section/Tab Break) to just
	before `before`, preceded by `header` if given."""
	order = [f for f in order if f != header]
	start = order.index(section)
	end = next(
		(i for i in range(start + 1, len(order)) if fieldtypes[order[i]] in SECTION_BREAKS),
		len(order),
	)
	block = ([header] if header else []) + order[start:end]
	rest = order[:start] + order[end:]
	target = rest.index(before)
	return rest[:target] + block + rest[target:]


def get_dashboard_data(data):
	"""override_doctype_dashboards"""
	return add_to_dashboard(data, "Lead")


def convert_lead_to_customer(lead, source=None):
	"""Return the Lead's Customer, creating it with ERPNext's own Lead ->
	Customer mapping (which also links the Lead's contacts and addresses and
	marks the Lead "Converted") if there isn't one yet."""
	existing = frappe.db.get_value("Customer", {"lead_name": lead})
	if existing:
		return existing

	from erpnext.crm.doctype.lead.lead import _make_customer

	customer = _make_customer(lead, ignore_permissions=True)
	# The mapper copies Territory (same fieldname) but takes Customer Group
	# from the Selling Settings default; the Lead's own wins. The defaults
	# remain a fallback for Leads saved before these fields were mandatory.
	customer.customer_group = frappe.db.get_value("Lead", lead, CUSTOMER_GROUP) or customer.customer_group
	customer.territory = customer.territory or frappe.db.get_default("Territory")
	name = insert_customer(
		customer,
		_("Lead {0}").format(lead),
		_("Set them on the Lead and save it, then try again."),
	)

	customer_link = get_link_to_form("Customer", name)
	if source:
		message = _("Converted to Customer {0} by {1}").format(
			customer_link, get_link_to_form(source.doctype, source.name)
		)
	else:
		message = _("Converted to Customer {0}").format(customer_link)
	frappe.get_doc("Lead", lead).add_comment("Info", message)
	return name


def insert_customer(customer, party_label, hint):
	"""Insert a Customer made by an ERPNext mapper, naming the missing
	Customer Group / Territory (and where to set them) rather than failing on
	a bare mandatory-field error."""
	missing = [
		customer.meta.get_label(fieldname)
		for fieldname in ("customer_group", "territory")
		if not customer.get(fieldname)
	]
	if missing:
		frappe.throw(
			_("Cannot convert {0} to a Customer: no {1}. {2}").format(
				party_label, _(" and ").join(missing), hint
			),
			title=_("Customer Group / Territory missing"),
		)

	customer.flags.ignore_permissions = True
	customer.insert()
	return customer.name


def validate_customer_fields(doc, method=None):
	"""validate: Customer Group and Territory are mandatory for anyone saving a
	Lead (form, REST API, Data Import). Leads ERPNext inserts on its own pass
	ignore_permissions or ignore_mandatory, and are completed later; until
	then convert_lead_to_customer asks for the fields.

	Leads created before this app was installed are exempt — see
	custom_crm_updates/go_live.py. convert_lead_to_customer still asks for
	the fields at the point one of those is actually converted, so the
	Customer is never created without them."""
	if doc.flags.ignore_permissions or doc.flags.ignore_mandatory:
		return

	# A Lead that predates this app is left as saveable as it was: the field
	# did not exist when it was created (custom_crm_updates/go_live.py).
	if not applies_to(doc):
		return

	missing = [doc.meta.get_label(fieldname) for fieldname in CUSTOMER_FIELDS if not doc.get(fieldname)]
	if missing:
		# worded like Frappe's own mandatory-field error
		frappe.throw(
			_("Mandatory fields required in Lead: {0}").format(", ".join(map(_, missing))),
			frappe.MandatoryError,
			title=_("Missing Fields"),
		)


def clear_person_fields(doc, method=None):
	"""before_validate: runs ahead of Lead.validate's set_full_name, so the
	cleared names never make it into lead_name."""
	if not doc.get(IS_COMPANY):
		return

	for fieldname in PERSON_FIELDS:
		doc.set(fieldname, None)

	# set_lead_name only fills lead_name when it's empty, so a lead that was
	# a person before being flagged would otherwise keep the person's name.
	doc.lead_name = doc.company_name


def set_date_of_convert(doc, method=None):
	"""validate: the day the Lead's status became "Converted".

	Written only on the save that actually changes the status, and only while
	the field is still empty: a Lead that goes Converted -> Open -> Converted
	keeps the date of the first conversion, and an ordinary re-save of a
	Converted Lead never moves it.

	This covers the Lead's own form, the REST API and a Data Import. The other
	way a Lead becomes Converted - ERPNext writing the status straight to the
	database when a Customer is raised from it - runs no Lead hook at all and
	is caught by set_date_of_convert_from_customer below.
	"""
	if doc.get(CONVERT_DATE) or doc.status != CONVERTED:
		return

	if doc.has_value_changed("status"):
		doc.set(CONVERT_DATE, nowdate())


def set_date_of_convert_from_customer(doc, method=None):
	"""doc_events: Customer on_update, after core's own update_lead_status,
	which marks the Lead "Converted" with frappe.db.set_value - no Lead
	document is loaded, so no Lead hook (not validate, not on_update) ever
	sees that change.

	Written the same way, straight to the database with no modified bump: the
	user creating the Customer may have no write access to the Lead, and the
	date is derived from a status change that was itself made this way.
	"""
	if not doc.get("lead_name"):
		return

	lead = frappe.db.get_value("Lead", doc.lead_name, ["status", CONVERT_DATE], as_dict=True)
	if not lead or lead.status != CONVERTED or lead.get(CONVERT_DATE):
		return

	frappe.db.set_value("Lead", doc.lead_name, CONVERT_DATE, nowdate(), update_modified=False)


def backfill_date_of_convert():
	"""after_migrate: Leads that were already Converted before the field
	existed. The Customer raised from a Lead is what converts it, so that
	Customer's creation date is the conversion date - a real date rather than
	today's. A Lead marked Converted by hand, with no Customer behind it, is
	left blank: there is nothing on record to say when it happened.
	"""
	if CONVERT_DATE not in frappe.db.get_table_columns("Lead"):
		return

	dates = {}
	for customer in frappe.get_all(
		"Customer",
		filters={"lead_name": ["is", "set"]},
		fields=["lead_name", "creation"],
		order_by="creation asc",
	):
		# the first Customer raised from the Lead is the one that converted it
		dates.setdefault(customer.lead_name, customer.creation.date())

	if not dates:
		return

	for lead in frappe.get_all(
		"Lead",
		filters={"name": ["in", list(dates)], "status": CONVERTED, CONVERT_DATE: ["is", "not set"]},
		pluck="name",
	):
		frappe.db.set_value("Lead", lead, CONVERT_DATE, dates[lead], update_modified=False)
