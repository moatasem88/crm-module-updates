"""Contracting features this app carries until the contracting app ships them.

Four things were built on Project Tender and Tender in October 2026 but never
committed to the contracting app's own repository, so a site that installs
contracting from git does not have them:

- Create ▸ Tender on the Project Tender form, and the mapper behind it;
- a new Tender joining its Project Tender's Direct Cost Details on insert;
- the Cancelled Tender status, and cancelled Tenders leaving those tables;
- Submitted and Won requiring every costed Tender to be Complete.

They are carried here so a site can have them without waiting for that
repository, in the same way as everything else in this app: Custom Fields,
property setters and hooks from outside, with no contracting file edited.

Every one of them stands down the moment contracting provides its own
(`contracting_provides`), so updating that app later is not a conflict and
not a duplicate — it simply takes over. This module is meant to be deleted
once that has happened everywhere; nothing else in the app imports it.
"""

import frappe
from frappe import _
from frappe.model.mapper import get_mapped_doc

PROJECT_TENDER_MODULE = "contracting.contracting.doctype.project_tender.project_tender"

CANCELLED = "Cancelled"
# While the Project Tender is still being put together, a Tender that names
# it joins the Direct Cost table by itself. Later statuses are left alone:
# the price has gone out, and on a Won one a new row would raise its own
# Project and Sales Order.
AUTO_DIRECT_COST_STATUSES = ("Draft", "Under Review")
# A price only leaves the office, or is booked as won, once every Tender
# behind it is final.
STATUSES_REQUIRING_COMPLETE_TENDERS = ("Submitted", "Won")


def contracting_provides(name):
	"""True if the contracting app already defines `name` itself, in which
	case this module keeps out of the way. Checked at call time rather than
	at import, so updating contracting takes effect on the next restart
	without touching this app.

	Both places are looked at: that app keeps some of this as module-level
	functions (make_tender, add_tender_to_direct_cost) and some as methods
	on the controller (validate_linked_tenders_complete). Checking only the
	module would have left the gate running twice once contracting caught
	up."""
	try:
		module = frappe.get_module(PROJECT_TENDER_MODULE)
	except Exception:
		return False

	if hasattr(module, name):
		return True

	controller = getattr(module, "ProjectTender", None)
	return bool(controller is not None and hasattr(controller, name))


def installed():
	return bool(frappe.db.exists("DocType", "Project Tender"))


# --------------------------------------------------------------- setup

def apply_contracting_backport():
	"""after_migrate: add the Cancelled option to Tender's Status.

	Built from the original DocField row and not from a literal, exactly as
	the Opportunity's own statuses are (overrides/opportunity.py), so the
	options contracting ships keep theirs when it is upgraded."""
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	if not installed() or not frappe.db.exists("DocType", "Tender"):
		return

	options = frappe.db.get_value("DocField", {"parent": "Tender", "fieldname": "status"}, "options")
	if not options:
		return

	options = options.split("\n")
	if CANCELLED in options:  # contracting ships it now; nothing to add
		return

	make_property_setter(
		"Tender", "status", "options", "\n".join(options + [CANCELLED]), "Text",
		validate_fields_for_doctype=False,
	)


# ------------------------------------------------- Create ▸ Tender

@frappe.whitelist()
def make_tender(source_name, target_doc=None):
	"""Create ▸ Tender on the Project Tender form: a new Tender that already
	belongs to this Project Tender, so it turns up in the Direct Cost Detail
	picker straight away without anyone having to pick the Project Tender by
	hand — and so it cannot be claimed by a second one.

	Only the link is really needed: project_name, client and site_location
	are fetch_from fields of project_tender, so the mapper hands over the
	same values the form would have fetched anyway. Three same-named fields
	are deliberately left out: naming_series, because the series belongs to
	the Tender (TND-) and not to the Project Tender (PT-), and the two cost
	totals, which each document works out from its own rows. Status is
	no_copy on both, so a Won or Submitted Project Tender still opens a
	Draft Tender."""
	return get_mapped_doc(
		"Project Tender",
		source_name,
		{
			"Project Tender": {
				"doctype": "Tender",
				"field_map": {"name": "project_tender"},
				"field_no_map": ["naming_series", "total_direct_cost", "total_indirect_cost"],
			}
		},
		target_doc,
	)


# ------------------------------------- a Tender joins the cost table

def add_tender_to_direct_cost(doc, method=None):
	"""doc_events: Tender after_insert. A new Tender that names a Project
	Tender adds itself to that Project Tender's Direct Cost Details, whether
	it came from Create ▸ Tender or was raised on the Tender form with the
	Project Tender picked by hand.

	Four cases are left alone: a Cancelled Tender, which is no part of
	anyone's price; a revised version, where a second row would double-count
	the same scope; a Tender already in the table; and a Project Tender past
	AUTO_DIRECT_COST_STATUSES, where the row would be refused anyway and
	throwing would roll the new Tender back altogether — the user is told
	instead and can still add the row by hand."""
	if contracting_provides("add_tender_to_direct_cost") or not installed():
		return
	if doc.status == CANCELLED or doc.get("previous_tender"):
		return
	if not doc.get("project_tender") or not frappe.db.exists("Project Tender", doc.project_tender):
		return

	project_tender = frappe.get_doc("Project Tender", doc.project_tender)

	if project_tender.status not in AUTO_DIRECT_COST_STATUSES:
		frappe.msgprint(
			_("Tender {0} was created, but not added to Direct Cost Details: Project Tender {1} is "
				"{2}. Add it there by hand if it belongs in this price.").format(
				doc.name, project_tender.name, _(project_tender.status)
			),
			indicator="orange",
			alert=True,
		)
		return

	if any(row.tender == doc.name for row in project_tender.direct_cost_details):
		return

	# tender_category is left for its fetch_from to fill from the Tender.
	project_tender.append("direct_cost_details", {"tender": doc.name})
	# whoever may raise a Tender needn't have write access to the Project Tender
	project_tender.flags.skip_cross_sync = True
	project_tender.save(ignore_permissions=True)


def remove_cancelled_tender_rows(doc, method=None):
	"""doc_events: Tender on_update. Cancelling a Tender takes it out of every
	Project Tender's Direct Cost Details, so the price stops counting work
	nobody is doing — and so a cancelled Tender cannot hold up Submitted or
	Won, which only pass on Complete ones.

	Rows whose Won automation already ran (row.project set) stay where they
	are: a Project and a Sales Order exist against them, and that history is
	not ours to rewrite. Idempotent: it runs on every save of a cancelled
	Tender and does nothing once the rows are gone."""
	if contracting_provides("remove_cancelled_tender_rows") or not installed():
		return
	if doc.status != CANCELLED:
		return

	parents = frappe.get_all(
		"Project Tender Direct Cost Detail",
		filters={"tender": doc.name, "parenttype": "Project Tender"},
		pluck="parent",
		distinct=True,
	)

	for parent in parents:
		if not frappe.db.exists("Project Tender", parent):
			continue

		project_tender = frappe.get_doc("Project Tender", parent)
		kept = [r for r in project_tender.direct_cost_details if r.tender != doc.name or r.project]
		if len(kept) == len(project_tender.direct_cost_details):
			continue

		project_tender.set("direct_cost_details", kept)
		project_tender.flags.skip_cross_sync = True
		project_tender.save(ignore_permissions=True)
		project_tender.add_comment(
			"Info",
			_("Tender {0} was cancelled, so its Direct Cost Details row was removed.").format(doc.name),
		)


# ------------------------------------------- the Complete gate

def validate_linked_tenders_complete(doc, method=None):
	"""doc_events: Project Tender validate. Submitted sends this price to the
	client and Won books it, so neither is allowed while a Tender it is
	costed from is still being worked on: an In Progress Tender's BOQ can
	still change, which would move the Project Tender's totals after the
	number had gone out.

	Rows whose Won automation already ran (row.project is set) are left
	alone, so re-saving an already-Won Project Tender never re-litigates
	settled rows."""
	if contracting_provides("validate_linked_tenders_complete") or not installed():
		return
	if doc.status not in STATUSES_REQUIRING_COMPLETE_TENDERS:
		return

	unfinished = []
	for row in doc.direct_cost_details:
		if not row.tender or row.project:
			continue

		status = frappe.db.get_value("Tender", row.tender, "status")
		if status != "Complete":
			unfinished.append(
				_("row #{0}: Tender {1} is {2}").format(row.idx, row.tender, _(status or "missing"))
			)

	if unfinished:
		frappe.throw(
			_("This Project Tender cannot be set to {0} yet. Every Tender in Direct Cost Details "
				"has to be Complete first, because an unfinished Tender's pricing can still "
				"change - {1}. Open each one and use Mark Complete, then set this status "
				"again.").format(_(doc.status), "; ".join(unfinished)),
			title=_("Linked Tender not Complete"),
		)
