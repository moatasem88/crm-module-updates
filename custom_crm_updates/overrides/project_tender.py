"""Opportunity ↔ Project Tender (Project Tender lives in the contracting app).

- A Tendering Leads Activity on an Opportunity creates a Project Tender named
  after the Opportunity, one per activity (create_project_tender_for_activity,
  called from LeadsActivity.on_update), and moves the Opportunity to
  "Tendering".
- The Opportunity's "Project Tender" tab lists its Project Tenders in a
  read-only table kept in sync from here (sync_opportunity_tenders).
- A Project Tender becoming "Submitted" marks the activity that created it
  "Done" and the Opportunity "Won".

The link back is two read-only Custom Fields on Project Tender,
custom_opportunity and custom_leads_activity, created by
apply_project_tender_customizations (after_migrate).
"""

import frappe
from frappe import _
from frappe.utils import get_link_to_form

from custom_crm_updates.mirror_table import set_mirror_rows

OPPORTUNITY_FIELD = "custom_opportunity"
ACTIVITY_FIELD = "custom_leads_activity"
TENDER_TABLE = "custom_project_tenders"
TENDER_ROW_FIELDS = (
	"project_tender",
	"project_name",
	"client",
	"status",
	"total_sell_price",
	"leads_activity",
	"creation_date",
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


def on_update(doc, method=None):
	"""doc_events: Project Tender on_update (after contracting's own)."""
	before = doc.get_doc_before_save()
	for opportunity in {doc.get(OPPORTUNITY_FIELD), before and before.get(OPPORTUNITY_FIELD)} - {None}:
		sync_opportunity_tenders(opportunity)

	if doc.status == "Submitted" and doc.has_value_changed("status"):
		mark_activity_done(doc)
		mark_opportunity_won(doc)


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


def mark_opportunity_won(tender):
	name = tender.get(OPPORTUNITY_FIELD)
	if not name or not frappe.db.exists("Opportunity", name):
		return

	opportunity = frappe.get_doc("Opportunity", name)
	if opportunity.status == "Won":
		return
	opportunity.db_set("status", "Won", notify=True)
	opportunity.add_comment(
		"Info",
		_("Status set to {0}: Project Tender {1} was submitted").format(
			frappe.bold(_("Won")), get_link_to_form("Project Tender", tender.name)
		),
	)


def sync_opportunity_tenders(opportunity, exclude=None):
	if not frappe.db.exists("Opportunity", opportunity):
		return

	filters = {OPPORTUNITY_FIELD: opportunity}
	if exclude:
		filters["name"] = ["!=", exclude]
	tenders = frappe.get_all(
		"Project Tender",
		filters=filters,
		fields=[
			"name as project_tender",
			"project_name",
			"client",
			"status",
			"total_sell_price",
			f"{ACTIVITY_FIELD} as leads_activity",
			"date(creation) as creation_date",
		],
		order_by="creation desc",
	)
	set_mirror_rows("Opportunity", opportunity, TENDER_TABLE, tenders, TENDER_ROW_FIELDS)


def backfill_opportunity_tenders():
	"""after_migrate: fill the table for Project Tenders that predate it."""
	if not frappe.db.exists("DocType", "Project Tender"):
		return
	for opportunity in frappe.get_all(
		"Project Tender", filters={OPPORTUNITY_FIELD: ["is", "set"]}, pluck=OPPORTUNITY_FIELD, distinct=True
	):
		sync_opportunity_tenders(opportunity)
