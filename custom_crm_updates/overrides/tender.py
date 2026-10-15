"""Tender customizations (Tender lives in the contracting app).

- "Completion Date": the day the Tender's status became "Complete", recorded
  by set_completion_date on the save that marks it Complete (contracting's
  mark_tender_complete, or any other save that sets the status).
- The same date is shown on the Project Tender's Direct Cost Details table,
  the table its Tenders are added to, as a read-only fetch_from column beside
  Tender Status.
- "Submission Deadline" is pre-filled from the Expected Closing Date of the
  Opportunity behind the Project Tender the Tender is raised under
  (set_submission_deadline), and stays editable afterwards.

The link chain this relies on:
  Tender.project_tender -> Project Tender
  Project Tender.custom_opportunity -> Opportunity  (overrides/project_tender.py)
  Opportunity.expected_closing                      (ERPNext core)

Applied on every migrate by `apply_tender_customizations` (hooks.py
after_migrate); idempotent, so re-running is safe.
"""

import frappe
from frappe.utils import nowdate

from custom_crm_updates.overrides.project_tender import OPPORTUNITY_FIELD

# Deliberately unprefixed: the field name was specified as completion_date.
COMPLETION_DATE = "completion_date"
COMPLETE = "Complete"
# The table on Project Tender that its Tenders are added to.
DIRECT_COST_TABLE = "Project Tender Direct Cost Detail"

CUSTOM_FIELDS = {
	"Tender": [
		{
			"fieldname": COMPLETION_DATE,
			"fieldtype": "Date",
			"label": "Completion Date",
			"insert_after": "submission_deadline",
			"read_only": 1,
			"no_copy": 1,
			"description": "The day this Tender was marked Complete. Set once, automatically.",
		},
	],
	# Mirrored onto the row the Tender occupies in Project Tender's Direct
	# Cost Details, exactly as tender_status already is. fetch_from is
	# refreshed on every save of the parent, and contracting's cross-sync
	# saves every linked Project Tender whenever a Tender is saved, so the
	# column follows the Tender by itself.
	DIRECT_COST_TABLE: [
		{
			"fieldname": COMPLETION_DATE,
			"fieldtype": "Date",
			"label": "Completion Date",
			"insert_after": "tender_status",
			"fetch_from": f"tender.{COMPLETION_DATE}",
			"read_only": 1,
			"in_list_view": 1,
			"columns": 1,
		},
	],
}


def apply_tender_customizations():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	if not frappe.db.exists("DocType", "Tender"):  # contracting not installed
		return
	create_custom_fields(CUSTOM_FIELDS, update=True)


def set_completion_date(doc, method=None):
	"""doc_events: Tender validate, which runs after the controller's own -
	after validate_not_complete_locked, so writing the field here is not read
	as an edit of a locked Tender.

	Written only on the save that actually changes the status, and only while
	the field is still empty, so the date of the first completion is the one
	that stays. Saving on validate rather than on_update means it is part of
	the same write as the status itself: a Complete Tender is locked
	immediately afterwards, and a later save could not add it.
	"""
	if doc.get(COMPLETION_DATE) or doc.status != COMPLETE:
		return

	if doc.has_value_changed("status"):
		doc.set(COMPLETION_DATE, nowdate())


def push_completion_date_to_rows(doc, method=None):
	"""doc_events: Tender on_update. The fetch_from column above is refreshed
	whenever the Project Tender itself is saved, which contracting's
	cross-sync does on every Tender save - this writes the same value
	straight onto the rows as well, the way cross_sync writes tender_total,
	so the grid is right even when that save is skipped.

	No modified bump and no document save: the value is a copy of the
	Tender's own field, not a change anyone made to the Project Tender.
	"""
	if not doc.get(COMPLETION_DATE):
		return

	frappe.db.set_value(
		DIRECT_COST_TABLE,
		{"tender": doc.name},
		COMPLETION_DATE,
		doc.get(COMPLETION_DATE),
		update_modified=False,
	)


def set_submission_deadline(doc, method=None):
	"""doc_events: Tender before_insert. A Tender raised under a Project
	Tender that came from an Opportunity inherits that Opportunity's Expected
	Closing Date as its Submission Deadline.

	On insert only, and only into an empty field: the deadline stays an
	ordinary, editable field afterwards, and a value the user (or
	contracting's "Create > Tender" mapper) already put there wins.

	Covers both ways a Tender is raised - "Create > Tender" on the Project
	Tender form, and a Tender created with the Project Tender picked by hand -
	because both end up with project_tender set before the insert.
	"""
	if doc.get("submission_deadline") or not doc.get("project_tender"):
		return

	opportunity = frappe.db.get_value("Project Tender", doc.project_tender, OPPORTUNITY_FIELD)
	if not opportunity:
		return

	doc.submission_deadline = frappe.db.get_value("Opportunity", opportunity, "expected_closing")


def backfill_completion_date():
	"""after_migrate: Tenders that were already Complete before the field
	existed. A Complete Tender is locked - contracting refuses any further
	edit and its cross-sync skips it - so `modified` is the day it was marked
	Complete.
	"""
	if not frappe.db.exists("DocType", "Tender"):
		return
	if COMPLETION_DATE not in frappe.db.get_table_columns("Tender"):
		return

	for tender in frappe.get_all(
		"Tender",
		filters={"status": COMPLETE, COMPLETION_DATE: ["is", "not set"]},
		fields=["name", "modified"],
	):
		completion_date = tender.modified.date()
		frappe.db.set_value(
			"Tender", tender.name, COMPLETION_DATE, completion_date, update_modified=False
		)
		frappe.db.set_value(
			DIRECT_COST_TABLE,
			{"tender": tender.name},
			COMPLETION_DATE,
			completion_date,
			update_modified=False,
		)
