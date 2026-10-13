# Copyright (c) 2026, smart and contributors
# For license information, please see license.txt

"""A CRM touchpoint (call, meeting, site visit, ...) logged against a Lead,
Prospect or Opportunity.

Activities linked to a Lead drive its Qualification Status:
- creating a Registration activity moves the Lead to "In Process";
- an activity reaching status "Done" marks the Lead "Qualified";
- a Registration activity reaching "Done" also converts the Lead to a Customer.

An activity on a Lead or an Opportunity cannot be saved without at least one
attachment, whatever its type: what the CRM follows a client up with is its
paperwork, so an activity with nothing on file is not a record of anything. A
Registration activity needs one whatever it is linked to, because it is the
activity that registers the client and its paperwork is what the Customer is
created from.

A Tendering activity on an Opportunity creates a Project Tender for it (one per
activity; see custom_crm_updates/overrides/project_tender.py).

Activities linked to a Lead or an Opportunity are also mirrored into that
document's read-only activities table (Leads Activity Detail rows), kept in
sync on every save and delete, oldest first. Each document only lists the
activities linked to it directly: an Opportunity made from a Lead does not show
the Lead's.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_link_to_form, nowdate

from custom_crm_updates.mirror_table import set_mirror_rows

# Same table fieldname on every doctype that shows its activities; the fields
# are created by custom_crm_updates/overrides/{lead,opportunity}.py.
ACTIVITY_TABLE = "custom_leads_activities"
TABLE_DOCTYPES = ("Lead", "Opportunity")
DETAIL_FIELDS = ("activity", "activity_type", "date", "status", "assigned_to", "attachments")

REGISTRATION = "Registration"
# Link types whose activities always need an attachment, whatever their type.
ATTACHMENT_LINK_TYPES = ("Lead", "Opportunity")


class LeadsActivity(Document):
	def validate(self):
		self.validate_attachment()

	def validate_attachment(self):
		"""An activity on a Lead or an Opportunity needs at least one
		attachment, whatever its type: what the CRM follows a client up with is
		its paperwork. A Registration needs one whatever it is linked to (a
		Prospect included), because it is what converts the Lead into a
		Customer, so the document it was registered with has to be on file.

		Enforced here rather than with `reqd` on the table: the rule depends on
		other fields, and it has to hold for the API and Data Import too. The
		form shows the same rule through the table's mandatory_depends_on and
		repeats these messages before saving (leads_activity.js).

		A row with no file is not an attachment: counting it would hand the
		user Frappe's generic "mandatory field in row 1" error instead of one
		that says what is actually needed."""
		registration = self.activity_type == REGISTRATION
		if not registration and self.link_type not in ATTACHMENT_LINK_TYPES:
			return

		if [row for row in self.attachments if row.attachment]:
			return

		# field and DocType names stay in English, as in the system
		if registration:
			message = _(
				"لا يمكن حفظ Activity من النوع Registration بدون مرفقات. أرفق ملفاً واحداً على الأقل في جدول Attachments."
			)
		else:
			message = _(
				"لا يمكن حفظ Activity على {0} بدون مرفقات. أرفق ملفاً واحداً على الأقل في جدول Attachments."
			).format(self.link_type)

		frappe.throw(message, title=_("مرفق مطلوب"))

	def on_update(self):
		# None on insert: get_doc_before_save is only loaded for existing docs
		before = self.get_doc_before_save()

		for doctype, name in self.linked_docs(before):
			sync_activity_table(doctype, name)

		if self.link_type == "Opportunity" and self.activity_type == "Tendering":
			from custom_crm_updates.overrides.project_tender import create_project_tender_for_activity

			create_project_tender_for_activity(self)

		if self.link_type != "Lead":
			return

		# Registration only counts on creation, and never downgrades a Lead
		# that is already Qualified.
		if before is None and self.activity_type == "Registration":
			self.set_lead_qualification("In Process", skip_if=("In Process", "Qualified"))

		# Also fires when a Done activity is re-pointed at a different Lead.
		became_done = self.status == "Done" and (
			before is None
			or before.status != "Done"
			or (before.link_type, before.link_name) != (self.link_type, self.link_name)
		)
		if became_done:
			self.set_lead_qualification("Qualified")

		if self.activity_type == "Registration" and self.status == "Done" and (
			became_done or before.activity_type != "Registration"
		):
			from custom_crm_updates.overrides.lead import convert_lead_to_customer

			convert_lead_to_customer(self.link_name, source=self)

	def on_trash(self):
		# Runs before delete_doc's link check, so removing our row here keeps
		# the Lead's table from blocking the delete.
		for doctype, name in self.linked_docs():
			sync_activity_table(doctype, name, exclude=self.name)

	def linked_docs(self, before=None):
		"""(doctype, name) of every document whose table must reflect this
		activity: the current link and, if it was re-pointed, the previous one."""
		docs = set()
		for doc in (self, before):
			if doc and doc.link_type in TABLE_DOCTYPES and doc.link_name:
				docs.add((doc.link_type, doc.link_name))
		return docs

	def set_lead_qualification(self, qualification_status, skip_if=None):
		lead = frappe.get_doc("Lead", self.link_name)
		if lead.qualification_status in (skip_if or (qualification_status,)):
			return

		values = {"qualification_status": qualification_status}
		if qualification_status == "Qualified":
			values["qualified_by"] = self.assigned_to or frappe.session.user
			values["qualified_on"] = nowdate()

		# db_set rather than save: the user logging an activity may not have
		# write access to the Lead, and unrelated Lead validations (e.g.
		# duplicate email) must not block recording the activity.
		# notify=True reloads the Lead if it is open in someone's browser.
		lead.db_set(values, notify=True)
		lead.add_comment(
			"Info",
			_("Qualification Status set to {0} by {1}").format(
				frappe.bold(_(qualification_status)), get_link_to_form(self.doctype, self.name)
			),
		)


def sync_activity_table(doctype, name, exclude=None):
	"""Rebuild a Lead's/Opportunity's read-only activities table from the
	activities linked to it, ascending by creation: the oldest at the top and
	every new activity appended at the bottom, like every other CRM table.
	Ordering by creation rather than by the activity's own Date is what keeps
	that true for a back-dated activity. No-op when the table is already
	current, so it is safe to call repeatedly (see backfill_activity_tables)."""
	if not frappe.db.exists(doctype, name):
		return

	filters = {"link_type": doctype, "link_name": name}
	if exclude:
		filters["name"] = ["!=", exclude]
	activities = frappe.get_all(
		"Leads Activity",
		filters=filters,
		fields=["name as activity", "activity_type", "date", "status", "assigned_to"],
		order_by="creation asc",
	)

	attachment_counts = dict(
		frappe.get_all(
			"Leads Activity Attachment",
			filters={"parenttype": "Leads Activity", "parent": ["in", [a.activity for a in activities] or [""]]},
			fields=["parent", "count(name) as count"],
			group_by="parent",
			as_list=True,
		)
	)
	for activity in activities:
		activity.attachments = attachment_counts.get(activity.activity, 0)

	set_mirror_rows(doctype, name, ACTIVITY_TABLE, activities, DETAIL_FIELDS)


def backfill_activity_tables():
	"""after_migrate: fill the tables for activities that predate them.
	sync_activity_table skips documents that are already current."""
	links = frappe.get_all(
		"Leads Activity",
		filters={"link_type": ["in", TABLE_DOCTYPES]},
		fields=["link_type", "link_name"],
		distinct=True,
	)
	for link in links:
		sync_activity_table(link.link_type, link.link_name)


def activity_table_fields(section_label):
	"""Custom Fields for the read-only activities table, placed at the top of
	the doctype's Activities tab. The trailing unlabeled Section Break keeps
	core's open_activities_html out of our section."""
	return [
		{
			"fieldname": "custom_leads_activities_section",
			"fieldtype": "Section Break",
			"label": section_label,
			"insert_after": "activities_tab",
		},
		{
			"fieldname": ACTIVITY_TABLE,
			"fieldtype": "Table",
			# the section heading already names the table
			"label": "",
			"options": "Leads Activity Detail",
			"insert_after": "custom_leads_activities_section",
			"read_only": 1,
			"no_copy": 1,
		},
		{
			"fieldname": "custom_open_activities_section",
			"fieldtype": "Section Break",
			"insert_after": ACTIVITY_TABLE,
		},
	]


def add_to_dashboard(data, doctype):
	"""Leads Activity in a Lead's/Opportunity's Connections tab."""
	data.setdefault("non_standard_fieldnames", {})["Leads Activity"] = "link_name"
	data.setdefault("dynamic_links", {})["link_name"] = [doctype, "link_type"]
	data["transactions"].append({"label": _("Activities"), "items": ["Leads Activity"]})
	return data
