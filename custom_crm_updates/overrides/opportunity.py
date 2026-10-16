"""Opportunity customizations.

- Opportunity Name and Opportunity Description at the top of the form. The
  name is also the Opportunity's title (set_title), so it is what the list
  view, links, breadcrumbs and reports show instead of the party's name.
- Attachments section: a table of files (Opportunity Attachment rows, the same
  Attachment + Description pair the Leads Activity uses). An Opportunity
  cannot be saved while it is empty (validate_attachments), and no Activity
  can be logged against one that is (validate_activity_source).
- The Opportunity Value section is moved directly above Organization
  (apply_field_order) and holds the new Targeted Amount.
- "Opportunity Breakdown" section, below Organization: Opportunity
  Contribution rows splitting the Targeted Amount between trades (civil, mec,
  elec, elev), each a percentage of it or a fixed amount. Final Value is
  recomputed on every save (calculate_contributions) and as the user types
  (public/js/opportunity.js).
- "Opportunity Activities" section at the top of the Activities tab: a
  read-only table of the Leads Activity records linked to this Opportunity
  (Link Type = Opportunity), kept in sync by Leads Activity (see
  sync_activity_table). Activities of the Lead it came from are not shown.
- "Project Tender" tab (before Activities): read-only table of the Project
  Tenders created for this Opportunity, plus the "Approved Project Tender"
  picked when the Opportunity is Won
  (custom_crm_updates/overrides/project_tender.py).
- Status options "Tendering" and "Won": "Tendering" is set by that Project
  Tender automation, "Won" by the user. The day it becomes "Won" is recorded
  in "Won Date" (set_won_date), beside the approved tender in that tab.
- Contacts tab: the contact list is shown as a read-only Contacts table
  (custom_crm_updates/overrides/contact.py) instead of core's contact_html.
- Connections entry for Leads Activity.

Applied on every migrate by `apply_opportunity_customizations` (hooks.py
after_migrate); idempotent, so re-running is safe.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, nowdate

from custom_crm_updates.go_live import applies_to, applies_to_record
from custom_crm_updates.overrides.contact import contact_table_fields
from custom_crm_updates.overrides.lead import move_section
from custom_crm_updates.overrides.project_tender import (
	APPROVED_TENDER_FIELD,
	OPPORTUNITY_FIELD,
	TENDER_TABLE,
)
from custom_crm_updates.custom_crm_updates.doctype.leads_activity.leads_activity import (
	activity_table_fields,
	add_to_dashboard,
)

PROJECT_TENDER_TAB = "custom_project_tender_tab"
NAME_FIELD = "custom_opportunity_name"
DESCRIPTION_FIELD = "custom_opportunity_description"
TARGETED_AMOUNT = "custom_targeted_amount"
BREAKDOWN_SECTION = "custom_opportunity_breakdown_section"
CONTRIBUTIONS_FIELD = "custom_opportunity_contributions"
ATTACHMENTS_SECTION = "custom_opportunity_attachments_section"
ATTACHMENTS_FIELD = "custom_opportunity_attachments"
# Deliberately unprefixed: the field name was specified as won_date.
WON_DATE = "won_date"
WON = "Won"

# The party is a Dynamic Link (opportunity_from + party_name), which a
# Connections card cannot follow: an internal dashboard link reads one plain
# field. So each party type has its own mirror, filled on save by
# set_party_links, and the Connections tab points at those.
PARTY_FIELDS = {
	"Lead": "custom_party_lead",
	"Customer": "custom_party_customer",
	"Prospect": "custom_party_prospect",
}

# Core's sections. The Opportunity Value one is moved above Organization, so
# the sections added below Organization go after its last field instead.
VALUE_SECTION = "section_break_14"
ORGANIZATION_SECTION = "organization_details_section"
ORGANIZATION_LAST_FIELD = "territory"

# Contribution Type: the Contribution Value is a percentage of the Targeted
# Amount, rather than an amount of its own.
PERCENTAGE = "Percentage"

# Leads Activity link types that must have attachments before an activity can
# be logged against them, and the table the attachments are in.
ACTIVITY_SOURCE_TABLES = {"Opportunity": ATTACHMENTS_FIELD}

EXTRA_STATUSES = ("Tendering", "Won")
# Replaced by the Contacts table; core still renders into it, just unseen.
HIDDEN_FIELDS = ("contact_html",)

CUSTOM_FIELDS = {
	"Opportunity": [
		{
			"fieldname": NAME_FIELD,
			"fieldtype": "Data",
			"label": "Opportunity Name",
			"insert_after": "naming_series",
			"in_standard_filter": 1,
			"description": "Also the Opportunity's title: what the list view, links and reports show.",
		},
		{
			"fieldname": DESCRIPTION_FIELD,
			"fieldtype": "Small Text",
			"label": "Opportunity Description",
			"insert_after": NAME_FIELD,
		},
		# Mirrors of party_name, one per party type, so the Connections tab
		# can link to it (see PARTY_FIELDS). Hidden: the party is already on
		# the form as Opportunity From / Party, and these only ever repeat it.
		*[
			{
				"fieldname": fieldname,
				"fieldtype": "Link",
				"label": f"Party {party_type}",
				"options": party_type,
				"insert_after": "party_name",
				"hidden": 1,
				"read_only": 1,
				"no_copy": 1,
				"description": "Set from Party on save; what the Connections tab links to.",
			}
			for party_type, fieldname in PARTY_FIELDS.items()
		],
		# last field of core's Opportunity Value section, so this lands inside
		# it and travels with it when apply_field_order moves it
		{
			"fieldname": TARGETED_AMOUNT,
			"fieldtype": "Currency",
			"label": "Targeted Amount",
			"options": "currency",
			"insert_after": "base_opportunity_amount",
		},
		# After Organization's last field: the Opportunity Value section is
		# moved to directly above Organization, so these sections cannot be
		# placed after it without coming between the two.
		{
			"fieldname": BREAKDOWN_SECTION,
			"fieldtype": "Section Break",
			"label": "Opportunity Breakdown",
			"insert_after": ORGANIZATION_LAST_FIELD,
		},
		{
			"fieldname": CONTRIBUTIONS_FIELD,
			"fieldtype": "Table",
			"label": "Contributions",
			"options": "Opportunity Contribution",
			"insert_after": BREAKDOWN_SECTION,
			"description": "Splits the Targeted Amount between trades. Final Value is worked out for you.",
		},
		{
			"fieldname": ATTACHMENTS_SECTION,
			"fieldtype": "Section Break",
			"label": "Attachments",
			"insert_after": CONTRIBUTIONS_FIELD,
		},
		{
			"fieldname": ATTACHMENTS_FIELD,
			"fieldtype": "Table",
			"label": "Attachments",
			"options": "Opportunity Attachment",
			"insert_after": ATTACHMENTS_SECTION,
		},
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
		# Set by the popup that asks which tender was approved when the
		# status is changed to Won (public/js/opportunity.js), and applied by
		# project_tender.apply_approved_tender on save.
		{
			"fieldname": APPROVED_TENDER_FIELD,
			"fieldtype": "Link",
			"label": "Approved Project Tender",
			"options": "Project Tender",
			"insert_after": TENDER_TABLE,
			"read_only": 1,
			"no_copy": 1,
			"description": "The Project Tender that was approved. Chosen when this Opportunity is set to Won, which also sets that tender to Won.",
		},
		# In the Project Tender tab, below the tender that was approved: the
		# two are set by the same move to Won.
		{
			"fieldname": WON_DATE,
			"fieldtype": "Date",
			"label": "Won Date",
			"insert_after": APPROVED_TENDER_FIELD,
			"read_only": 1,
			"no_copy": 1,
			"description": "The day this Opportunity was won. Set once, automatically.",
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

	apply_field_order()


def apply_field_order():
	"""Move the Opportunity Value section (core's section_break_14, with the
	Targeted Amount in it) to directly above Organization.

	Standard fields can only be reordered through a `field_order` Property
	Setter (what Customize Form saves), so rebuild it from the current order
	with that one move applied. Other reorderings made through Customize Form
	are preserved, and the sections added after Organization's last field stay
	where they are."""
	fields = frappe.get_meta("Opportunity", cached=False).fields
	order = [df.fieldname for df in fields]
	fieldtypes = {df.fieldname: df.fieldtype for df in fields}

	new_order = move_section(order, fieldtypes, VALUE_SECTION, before=ORGANIZATION_SECTION)
	if new_order == order:
		return

	frappe.make_property_setter(
		{
			"doctype": "Opportunity",
			"doctype_or_field": "DocType",
			"property": "field_order",
			"value": json.dumps(new_order),
		},
		validate_fields_for_doctype=False,
	)


def set_party_links(doc, method=None):
	"""validate: copy the party into the mirror field for its type, and clear
	the others, so an Opportunity re-pointed from a Lead to a Customer does
	not keep both. These fields exist only for the Connections tab
	(get_dashboard_data); party_name stays the field anyone edits."""
	for party_type, fieldname in PARTY_FIELDS.items():
		doc.set(fieldname, doc.party_name if doc.opportunity_from == party_type else None)


def backfill_party_links():
	"""after_migrate: fill the mirrors for the Opportunities that predate
	them, so their Connections tab is right without waiting for a re-save.
	Written straight to the database with no modified bump: the value is
	derived from party_name, not a change anyone made."""
	fields = ["name", "opportunity_from", "party_name", *PARTY_FIELDS.values()]
	for opportunity in frappe.get_all("Opportunity", fields=fields):
		values = {
			fieldname: (opportunity.party_name if opportunity.opportunity_from == party_type else None)
			for party_type, fieldname in PARTY_FIELDS.items()
		}
		if all(opportunity.get(fieldname) == value for fieldname, value in values.items()):
			continue

		frappe.db.set_value("Opportunity", opportunity.name, values, update_modified=False)


def set_won_date(doc, method=None):
	"""validate: the day the Opportunity's status became "Won".

	Written only on the save that actually changes the status, and only while
	the field is still empty, so an Opportunity reopened and won again keeps
	the date of the first win. validate rather than on_update, so the date is
	part of the same write as the status.
	"""
	if doc.get(WON_DATE) or doc.status != WON:
		return

	if doc.has_value_changed("status"):
		doc.set(WON_DATE, nowdate())


def set_title(doc, method=None):
	"""validate, after core's own (which falls back to the party's name): the
	Opportunity Name is the Opportunity's title, so it is what the list view,
	links, breadcrumbs and reports show. An Opportunity with no name keeps
	core's title."""
	if doc.get(NAME_FIELD):
		doc.title = doc.get(NAME_FIELD)


def validate_attachments(doc, method=None):
	"""validate: an Opportunity is only saved with its paperwork on file.

	Enforced here rather than with `reqd` on the table: Frappe enforces reqd on
	every insert, including the Opportunities ERPNext creates by itself (from
	an incoming email, from a Communication), which have nothing to attach.
	Those pass ignore_permissions or ignore_mandatory, so they are skipped
	here, exactly like the Lead's own mandatory fields (overrides/lead.py).

	A row the user added but never picked a file for is not an attachment:
	counting it would hand them Frappe's generic "mandatory field in row 1"
	error instead of this one, which says what is actually needed.

	Opportunities created before this app was installed are exempt — see
	custom_crm_updates/go_live.py."""
	if doc.flags.ignore_permissions or doc.flags.ignore_mandatory:
		return

	# An Opportunity that predates this app is left as saveable as it was:
	# the table did not exist when it was created (go_live.py).
	if not applies_to(doc):
		return

	# `or []`: the field is None until apply_opportunity_customizations has
	# created it, i.e. on the very migrate that installs this app
	if any(row.attachment for row in doc.get(ATTACHMENTS_FIELD) or []):
		return

	frappe.throw(
		_("لا يمكن حفظ Opportunity بدون مرفقات. أرفق ملفاً واحداً على الأقل في جدول Attachments."),
		title=_("مرفق مطلوب"),
	)


def calculate_contributions(doc, method=None):
	"""validate: every row's Final Value is worked out again from the Targeted
	Amount, whatever the form sent. The field is read-only and the client
	script fills it as the user types (public/js/opportunity.js); this is what
	makes it right for the REST API, a Data Import, and a Targeted Amount
	changed without touching the rows.

	A Percentage row's Contribution Value is a percentage of the Targeted
	Amount (20 against 20,000 is 4,000); a Fixed Amount row's is the amount."""
	targeted_amount = flt(doc.get(TARGETED_AMOUNT))

	for row in doc.get(CONTRIBUTIONS_FIELD) or []:
		value = flt(row.contribution_value)
		if row.contribution_type == PERCENTAGE:
			value = targeted_amount * value / 100
		row.final_value = flt(value, row.precision("final_value"))


def validate_activity_source(doc, method=None):
	"""Leads Activity validate: no activity on a document whose Attachments
	table is empty. The activity is the follow-up on that paperwork, so the
	activity is refused and nothing is saved until the file is there. The form
	says so earlier, when Create ▸ Activity is pressed
	(public/js/leads_activity_section.js).

	Only the link types in ACTIVITY_SOURCE_TABLES have an attachments table;
	the others (Prospect) are left alone, as are documents created before
	this app was installed. Saves made by the automation are
	skipped: an activity it re-saves (project_tender.mark_activity_done) was
	already allowed when the user created it."""
	fieldname = ACTIVITY_SOURCE_TABLES.get(doc.link_type)
	if not fieldname or not doc.link_name or doc.flags.ignore_permissions:
		return

	# Judged on the Opportunity, not on the activity: logging a new activity
	# against an Opportunity that predates the app must stay possible, or the
	# exemption its own rule is given above would be worth nothing (go_live.py).
	if not applies_to_record(doc.link_type, doc.link_name):
		return

	# None until apply_opportunity_customizations has created the field
	field = frappe.get_meta(doc.link_type).get_field(fieldname)
	if not field:
		return

	# A row with no file is not an attachment: `!= ""` leaves out both the
	# empty and the never-filled (NULL) ones.
	if frappe.db.exists(
		field.options,
		{
			"parenttype": doc.link_type,
			"parentfield": fieldname,
			"parent": doc.link_name,
			"attachment": ["!=", ""],
		},
	):
		return

	frappe.throw(
		_(
			"لا يمكن إنشاء Activity على {0} بدون مرفقات. أرفق ملفاً واحداً على الأقل في جدول Attachments داخل {0} واحفظه، ثم أعد المحاولة."
		).format(doc.link_type),
		title=_("مرفق مطلوب"),
	)


def get_dashboard_data(data):
	"""override_doctype_dashboards: the Connections tab shows the Leads
	Activities logged against this Opportunity, the client it belongs to
	(whether that is a Lead, a Customer or a Prospect), and the Project
	Tenders raised from it.

	The client is an *internal* link: the Opportunity points at it, not the
	other way round, so the card reads one of the PARTY_FIELDS mirrors. When
	a mirror is empty Frappe falls back to the ordinary search for documents
	pointing back here, which is what finds the Customers converted *from*
	this Opportunity (Customer.opportunity_name) on a Lead's Opportunity."""
	data = add_to_dashboard(data, "Opportunity")

	data.setdefault("internal_links", {}).update(
		{party_type: fieldname for party_type, fieldname in PARTY_FIELDS.items()}
	)
	data.setdefault("non_standard_fieldnames", {})["Customer"] = "opportunity_name"
	items = list(PARTY_FIELDS)

	# contracting app; absent on a bench that doesn't have it
	if frappe.db.exists("DocType", "Project Tender"):
		data["non_standard_fieldnames"]["Project Tender"] = OPPORTUNITY_FIELD
		items.append("Project Tender")

	data["transactions"].append({"label": _("Client"), "items": items})
	return data
