"""Opportunity ↔ Project Tender (Project Tender lives in the contracting app).

- A Tendering Leads Activity on an Opportunity creates a Project Tender named
  after the Opportunity, one per activity (create_project_tender_for_activity,
  called from LeadsActivity.on_update), moves the Opportunity to "Tendering"
  and tells the user the tender was created.
- The Opportunity's "Project Tender" tab lists its Project Tenders in a
  read-only table kept in sync from here (sync_opportunity_tenders), oldest
  first.
- A Project Tender becoming "Submitted" marks the activity that created it
  "Done". The Opportunity is left as it is: which tender was approved is the
  user's call, and it is made the other way round — setting the Opportunity to
  "Won" asks which of its tenders was approved (the popup in
  public/js/opportunity.js) and that one becomes "Won" (apply_approved_tender).
  Only Submitted tenders are offered there (APPROVABLE_STATUS): a price that
  was never sent to the client cannot be the one the client approved.
- A Project Tender can only be "Submitted" once its three cost tables all have
  rows (validate_submitted_rows).
- "Submitted Date" and "Won Date": the days the Project Tender's status became
  "Submitted" and "Won" (set_status_dates). Both are shown on the
  Opportunity's own Project Tenders table, in its Project Tender tab.

The link back is two read-only Custom Fields on Project Tender,
custom_opportunity and custom_leads_activity, created by
apply_project_tender_customizations (after_migrate). The approved tender is
held by a third, custom_approved_project_tender on Opportunity (created by
overrides/opportunity.py).
"""

import frappe
from frappe import _
from frappe.utils import get_link_to_form

from frappe.utils import nowdate

from custom_crm_updates.mirror_table import rows_differ, set_mirror_rows

OPPORTUNITY_FIELD = "custom_opportunity"
ACTIVITY_FIELD = "custom_leads_activity"
TENDER_TABLE = "custom_project_tenders"
APPROVED_TENDER_FIELD = "custom_approved_project_tender"
# Deliberately unprefixed: the field names were specified as submitted_date
# and won_date. Each holds the day its status was first reached.
STATUS_DATE_FIELDS = {"Submitted": "submitted_date", "Won": "won_date"}
TENDER_ROW_FIELDS = (
	"project_tender",
	"project_name",
	"client",
	"status",
	"total_sell_price",
	"submitted_date",
	"won_date",
	"leads_activity",
	"creation_date",
)
# Only a Submitted Project Tender can be the approved one behind a Won
# Opportunity: the client can only have approved a price that was sent to
# them. This is what the popup offers (get_opportunity_tenders).
APPROVABLE_STATUS = "Submitted"
# A Project Tender is only ready to be submitted once it is fully costed.
SUBMITTED_REQUIRED_TABLES = (
	"direct_cost_details",
	"indirect_cost_details",
	"overhead_deduction_details",
)

CUSTOM_FIELDS = {
	"Project Tender": [
		{
			"fieldname": OPPORTUNITY_FIELD,
			"fieldtype": "Link",
			"label": "Opportunity",
			"options": "Opportunity",
			"insert_after": "client",
			"read_only": 1,
			"no_copy": 1,
			"in_standard_filter": 1,
			"search_index": 1,
		},
		{
			"fieldname": ACTIVITY_FIELD,
			"fieldtype": "Link",
			"label": "Leads Activity",
			"options": "Leads Activity",
			"insert_after": OPPORTUNITY_FIELD,
			"read_only": 1,
			"no_copy": 1,
		},
		# Beside Status, in the order the two are reached.
		{
			"fieldname": STATUS_DATE_FIELDS["Submitted"],
			"fieldtype": "Date",
			"label": "Submitted Date",
			"insert_after": "status",
			"read_only": 1,
			"no_copy": 1,
			"description": "The day this Project Tender was submitted. Set once, automatically.",
		},
		{
			"fieldname": STATUS_DATE_FIELDS["Won"],
			"fieldtype": "Date",
			"label": "Won Date",
			"insert_after": STATUS_DATE_FIELDS["Submitted"],
			"read_only": 1,
			"no_copy": 1,
			"description": "The day this Project Tender was won. Set once, automatically.",
		},
	],
}


def apply_project_tender_customizations():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	if not frappe.db.exists("DocType", "Project Tender"):  # contracting not installed
		return
	create_custom_fields(CUSTOM_FIELDS, update=True)


def create_project_tender_for_activity(activity):
	"""One Project Tender per Tendering activity: re-saving the activity (or
	changing its type back and forth) never creates a second one."""
	if frappe.db.exists("Project Tender", {ACTIVITY_FIELD: activity.name}):
		return

	opportunity = frappe.get_doc("Opportunity", activity.link_name)
	tender = frappe.get_doc(
		{
			"doctype": "Project Tender",
			"project_name": opportunity.title or opportunity.customer_name or opportunity.name,
			"client": get_opportunity_customer(opportunity),
			OPPORTUNITY_FIELD: opportunity.name,
			ACTIVITY_FIELD: activity.name,
		}
	)
	# Automation: the user logging the activity (e.g. Sales User) may have no
	# Project Tender permissions of their own.
	tender.insert(ignore_permissions=True)

	if opportunity.status not in ("Won", "Converted"):
		opportunity.db_set("status", "Tendering", notify=True)
	opportunity.add_comment(
		"Info",
		_("Project Tender {0} created by {1}").format(
			get_link_to_form("Project Tender", tender.name), get_link_to_form(activity.doctype, activity.name)
		),
	)

	# The activity is saved from its own form, where nothing else would say
	# that a Project Tender had just appeared on the Opportunity.
	# Arabic message, English DocType and record names (see README).
	frappe.msgprint(
		_("تم إنشاء Project Tender {0} للـ Opportunity {1} بنجاح.").format(
			get_link_to_form("Project Tender", tender.name),
			get_link_to_form("Opportunity", opportunity.name),
		),
		title=_("تم إنشاء Project Tender"),
		indicator="green",
	)


def get_opportunity_customer(opportunity):
	"""Project Tender's Client is a mandatory Customer link."""
	if opportunity.opportunity_from == "Customer":
		return opportunity.party_name

	if opportunity.opportunity_from == "Lead":
		from custom_crm_updates.overrides.lead import convert_lead_to_customer

		return convert_lead_to_customer(opportunity.party_name, source=opportunity)

	if opportunity.opportunity_from == "Prospect":
		return convert_prospect_to_customer(opportunity.party_name)

	frappe.throw(
		_("Cannot create a Project Tender: Opportunity {0} has no Customer, Lead or Prospect.").format(
			opportunity.name
		)
	)


def convert_prospect_to_customer(prospect):
	# Customer has no link back to a Prospect; ERPNext's own conversion names
	# the Customer after the Prospect, so match on that.
	existing = frappe.db.get_value("Customer", {"customer_name": prospect})
	if existing:
		return existing

	from erpnext.crm.doctype.prospect.prospect import make_customer

	from custom_crm_updates.overrides.lead import insert_customer

	return insert_customer(
		make_customer(prospect),
		_("Prospect {0}").format(prospect),
		_("Set a Customer Group and Territory on the Prospect (or defaults in Selling Settings)."),
	)


def validate_submitted_rows(doc, method=None):
	"""doc_events: Project Tender validate. Submitting a tender is sending a
	price to the client, so all three cost tables have to be filled in first.
	Checked on validate rather than on the status change alone, so emptying a
	table on an already-submitted tender is refused too."""
	if doc.status != "Submitted":
		return

	# Labels are left untranslated: field names stay as they are in the system.
	empty = [doc.meta.get_label(fieldname) for fieldname in SUBMITTED_REQUIRED_TABLES if not doc.get(fieldname)]
	if empty:
		frappe.throw(
			_("لا يمكن تحويل Project Tender إلى الحالة Submitted قبل استكمال بيانات الجداول الفرعية. أضف صفاً واحداً على الأقل في: {0}.").format(
				"، ".join(empty)
			),
			title=_("Project Tender غير مكتمل"),
		)


def set_status_dates(doc, method=None):
	"""doc_events: Project Tender validate. Records the day the status became
	"Submitted" and the day it became "Won", each in its own field.

	Written only on the save that actually changes the status, and only while
	the field is still empty, so a tender that is re-submitted keeps the date
	of the first submission. The two are independent: a Project Tender that
	goes straight to Won without passing through Submitted gets a Won Date and
	no Submitted Date.

	validate rather than on_update, so the date is part of the same write as
	the status itself.
	"""
	if not doc.has_value_changed("status"):
		return

	fieldname = STATUS_DATE_FIELDS.get(doc.status)
	if fieldname and not doc.get(fieldname):
		doc.set(fieldname, nowdate())


def on_update(doc, method=None):
	"""doc_events: Project Tender on_update (after contracting's own)."""
	before = doc.get_doc_before_save()
	# skip_opportunity_sync: saved from apply_approved_tender, i.e. from the
	# Opportunity's own save, which refreshes its table itself (see there).
	if not doc.flags.get("skip_opportunity_sync"):
		for opportunity in {doc.get(OPPORTUNITY_FIELD), before and before.get(OPPORTUNITY_FIELD)} - {None}:
			sync_opportunity_tenders(opportunity)

	# The Opportunity is deliberately left alone here: see the module docstring.
	if doc.status == "Submitted" and doc.has_value_changed("status"):
		mark_activity_done(doc)


def on_trash(doc, method=None):
	# Runs before delete_doc's link check, so our row can't block the delete.
	if doc.get(OPPORTUNITY_FIELD):
		sync_opportunity_tenders(doc.get(OPPORTUNITY_FIELD), exclude=doc.name)


def mark_activity_done(tender):
	name = tender.get(ACTIVITY_FIELD)
	if not name or not frappe.db.exists("Leads Activity", name):
		return

	activity = frappe.get_doc("Leads Activity", name)
	if activity.status == "Done":
		return
	activity.status = "Done"
	activity.flags.ignore_permissions = True
	# A full save, so the Opportunity's activities table and any other
	# activity automation stay in step.
	activity.save()


@frappe.whitelist()
def get_opportunity_tenders(opportunity):
	"""The list behind the "which tender was approved?" popup
	(public/js/opportunity.js), oldest first like the Opportunity's own table.

	Only the Submitted ones: a Draft or Under Review tender is a price that
	never left this office, a Lost or Cancelled one was not approved, and a
	Won one already is the approved tender. Filtered here rather than in the
	popup so the rule has one home, next to the status it is about.

	Read as the system, exactly like that table: Project Tender is a
	contracting doctype, and the Sales User closing the Opportunity has no
	role on it."""
	frappe.has_permission("Opportunity", doc=opportunity, throw=True)

	return frappe.get_all(
		"Project Tender",
		filters={OPPORTUNITY_FIELD: opportunity, "status": APPROVABLE_STATUS},
		fields=["name", "project_name", "client", "status", "total_sell_price"],
		order_by="creation asc",
	)


def validate_approved_tender(doc, method=None):
	"""doc_events: Opportunity validate. The field is read-only and the popup
	only offers this Opportunity's own tenders; this covers a save made over
	the API or from the bench console."""
	tender = doc.get(APPROVED_TENDER_FIELD)
	if not tender or not frappe.db.exists("Project Tender", tender):
		return

	if frappe.db.get_value("Project Tender", tender, OPPORTUNITY_FIELD) != doc.name:
		frappe.throw(
			_("Project Tender {0} لم يُنشأ على هذا الـ Opportunity، ولا يمكن اعتماده له.").format(
				get_link_to_form("Project Tender", tender)
			),
			title=_("Project Tender غير صحيح"),
		)


def apply_approved_tender(doc, method=None):
	"""doc_events: Opportunity on_update. Setting an Opportunity to "Won" means
	one of its Project Tenders was approved; the user picks which in the popup
	(public/js/opportunity.js), and it is that tender that is now Won."""
	tender = doc.get(APPROVED_TENDER_FIELD)
	if doc.status != "Won" or not tender or not frappe.db.exists("Project Tender", tender):
		return

	before = doc.get_doc_before_save()
	# An ordinary re-save of an Opportunity that is already Won: nothing new.
	if before and before.status == "Won" and before.get(APPROVED_TENDER_FIELD) == tender:
		return

	if not set_tender_won(tender, doc):
		return

	doc.add_comment(
		"Info",
		_("Project Tender {0} set to {1}: it is the approved one").format(
			get_link_to_form("Project Tender", tender), frappe.bold(_("Won"))
		),
	)
	refresh_tender_rows(doc)


def set_tender_won(tender_name, opportunity):
	"""Mark the approved Project Tender "Won"; contracting's own Won automation
	then raises its Project and Sales Order. Saved as the system, like every
	other tender write from here.

	Anything that automation refuses (a linked Tender that isn't Complete, say)
	rolls this save back, Opportunity included, rather than leaving a Won
	Opportunity whose approved tender never got there. Returns False if the
	tender was already Won."""
	tender = frappe.get_doc("Project Tender", tender_name)
	if tender.status == "Won":
		return False

	tender.status = "Won"
	tender.flags.ignore_permissions = True
	# The Opportunity is mid-save; apply_approved_tender refreshes its table.
	tender.flags.skip_opportunity_sync = True
	tender.save()
	tender.add_comment(
		"Info",
		_("Status set to {0}: approved for Opportunity {1}").format(
			frappe.bold(_("Won")), get_link_to_form("Opportunity", opportunity.name)
		),
	)
	return True


def tender_rows(opportunity, exclude=None):
	"""Oldest first, so a new Project Tender is appended at the bottom."""
	filters = {OPPORTUNITY_FIELD: opportunity}
	if exclude:
		filters["name"] = ["!=", exclude]
	return frappe.get_all(
		"Project Tender",
		filters=filters,
		fields=[
			"name as project_tender",
			"project_name",
			"client",
			"status",
			"total_sell_price",
			*STATUS_DATE_FIELDS.values(),
			f"{ACTIVITY_FIELD} as leads_activity",
			"date(creation) as creation_date",
		],
		order_by="creation asc",
	)


def sync_opportunity_tenders(opportunity, exclude=None):
	if not frappe.db.exists("Opportunity", opportunity):
		return

	set_mirror_rows(
		"Opportunity", opportunity, TENDER_TABLE, tender_rows(opportunity, exclude), TENDER_ROW_FIELDS
	)


def refresh_tender_rows(doc):
	"""The table of an Opportunity that is being saved right now: written
	through the document itself, and without the modified bump
	sync_opportunity_tenders makes — the form doing the saving would otherwise
	come back one step behind the database and refuse its next save."""
	rows = tender_rows(doc.name)
	if rows_differ(doc.get(TENDER_TABLE), rows, TENDER_ROW_FIELDS):
		doc.set(TENDER_TABLE, rows)
		doc.update_child_table(TENDER_TABLE)


def backfill_opportunity_tenders():
	"""after_migrate: fill the table for Project Tenders that predate it."""
	if not frappe.db.exists("DocType", "Project Tender"):
		return
	for opportunity in frappe.get_all(
		"Project Tender", filters={OPPORTUNITY_FIELD: ["is", "set"]}, pluck=OPPORTUNITY_FIELD, distinct=True
	):
		sync_opportunity_tenders(opportunity)
