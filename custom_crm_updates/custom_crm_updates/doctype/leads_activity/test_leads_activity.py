# Copyright (c) 2026, smart and contributors
# For license information, please see license.txt

from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.desk.notifications import get_open_count
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate

from erpnext.crm.doctype.lead.lead import make_opportunity

from custom_crm_updates.overrides.opportunity import ATTACHMENTS_FIELD
from custom_crm_updates.custom_crm_updates.doctype.leads_activity.leads_activity import (
	ACTIVITY_TABLE,
	backfill_activity_tables,
)

# Every record here is created by the tests themselves (and rolled back by
# FrappeTestCase), so don't let the runner commit ERPNext's global test records.
test_ignore = ["Lead", "Prospect", "Opportunity", "User"]


def leaf(doctype):
	return frappe.get_all(doctype, {"is_group": 0}, pluck="name", order_by="name", limit=1)[0]


def make_lead(**kwargs):
	# Customer Group and Territory are mandatory on Lead (overrides/lead.py)
	values = {
		"doctype": "Lead",
		"first_name": "_Test Activity Lead " + frappe.generate_hash(length=6),
		"custom_customer_group": leaf("Customer Group"),
		"territory": leaf("Territory"),
	}
	values.update(kwargs)
	return frappe.get_doc(values).insert()


def make_activity(lead, **kwargs):
	values = {
		"doctype": "Leads Activity",
		"activity_type": "Call",
		"link_type": "Lead",
		"link_name": lead,
		"date": nowdate(),
	}
	values.update(kwargs)
	# An activity on a Lead or an Opportunity cannot be saved without one, and
	# neither can a Registration (see TestActivityAttachment); every other
	# test that uses an activity is about what it does to the Lead, not about
	# the attachment.
	if "attachments" not in values:
		values["attachments"] = [{"attachment": "/files/_test_activity.pdf"}]
	return frappe.get_doc(values).insert()


@contextmanager
def customer_defaults(customer_group=True, territory=True):
	"""Registration -> Done converts the Lead to a Customer, and ERPNext fills
	its group and territory from these defaults. Stand them in rather than
	writing real defaults, which are cached and would outlive the rollback."""
	values = {
		"Customer Group": customer_group
		and frappe.get_all("Customer Group", {"is_group": 0}, pluck="name", limit=1)[0],
		"Territory": territory and frappe.get_all("Territory", {"is_group": 0}, pluck="name", limit=1)[0],
	}
	original = frappe.db.get_default

	def get_default(key, *args, **kwargs):
		return values[key] if key in values else original(key, *args, **kwargs)

	with patch.object(frappe.db, "get_default", get_default):
		yield


def make_opportunity_from(lead):
	opportunity = make_opportunity(lead)
	opportunity.company = opportunity.company or frappe.db.get_value("Company", {}, "name")
	# An Opportunity cannot be saved with an empty Attachments table, and no
	# activity can be logged against one (overrides/opportunity.py; see
	# tests/test_opportunity.py). Every test here is about the activities of an
	# Opportunity, not about its attachment.
	opportunity.append(ATTACHMENTS_FIELD, {"attachment": "/files/_test_opportunity.pdf"})
	return opportunity.insert()


def table_rows(name, doctype="Lead"):
	return frappe.get_doc(doctype, name).get(ACTIVITY_TABLE)


def table_activities(name, doctype="Lead"):
	return [row.activity for row in table_rows(name, doctype)]


def qualification(lead):
	return frappe.db.get_value("Lead", lead, "qualification_status")


class TestLeadsActivity(FrappeTestCase):
	def setUp(self):
		self.lead = make_lead().name

	def test_registration_sets_lead_in_process(self):
		make_activity(self.lead, activity_type="Registration")
		self.assertEqual(qualification(self.lead), "In Process")

	def test_other_types_leave_lead_unchanged(self):
		for activity_type in ("Call", "Meeting", "Site Visit", "Other"):
			make_activity(self.lead, activity_type=activity_type)
		self.assertEqual(qualification(self.lead), "Unqualified")

	def test_registration_only_counts_on_creation(self):
		activity = make_activity(self.lead, activity_type="Call")
		activity.activity_type = "Registration"
		activity.append("attachments", {"attachment": "/files/_test_registration.pdf"})
		activity.save()
		self.assertEqual(qualification(self.lead), "Unqualified")

	def test_registration_does_not_downgrade_qualified_lead(self):
		frappe.db.set_value("Lead", self.lead, "qualification_status", "Qualified")
		make_activity(self.lead, activity_type="Registration")
		self.assertEqual(qualification(self.lead), "Qualified")

	def test_done_qualifies_lead(self):
		activity = make_activity(self.lead, activity_type="Registration", assigned_to="Administrator")
		self.assertEqual(qualification(self.lead), "In Process")

		activity.status = "Done"
		with customer_defaults():
			activity.save()
		lead = frappe.db.get_value(
			"Lead", self.lead, ["qualification_status", "qualified_by", "qualified_on"], as_dict=True
		)
		self.assertEqual(lead.qualification_status, "Qualified")
		self.assertEqual(lead.qualified_by, "Administrator")
		self.assertEqual(str(lead.qualified_on), nowdate())
		self.assertTrue(
			frappe.db.exists(
				"Comment",
				{"reference_doctype": "Lead", "reference_name": self.lead, "comment_type": "Info"},
			)
		)

	def test_created_as_done_qualifies_lead(self):
		with customer_defaults():
			make_activity(self.lead, activity_type="Registration", status="Done")
		self.assertEqual(qualification(self.lead), "Qualified")

	def test_other_statuses_do_not_qualify(self):
		activity = make_activity(self.lead)
		for status in ("In Process", "Failed", "Closed", "Waiting Reply"):
			activity.status = status
			activity.save()
			self.assertEqual(qualification(self.lead), "Unqualified")

	def test_done_activity_moved_to_other_lead_qualifies_it(self):
		activity = make_activity(self.lead, status="Done")
		other = make_lead().name

		activity.link_name = other
		activity.save()
		self.assertEqual(qualification(other), "Qualified")

	def test_non_lead_links_are_ignored(self):
		prospect = frappe.get_doc(
			{"doctype": "Prospect", "company_name": "_Test Activity Prospect " + frappe.generate_hash(length=6)}
		).insert()
		make_activity(prospect.name, link_type="Prospect", activity_type="Registration", status="Done")
		self.assertEqual(qualification(self.lead), "Unqualified")

	def test_link_must_exist(self):
		with self.assertRaises(frappe.LinkValidationError):
			make_activity("CRM-LEAD-DOES-NOT-EXIST")

	def test_link_must_match_link_type(self):
		# a Lead's name is not a valid Opportunity
		with self.assertRaises(frappe.LinkValidationError):
			make_activity(self.lead, link_type="Opportunity")

	def test_lead_with_activity_cannot_be_deleted(self):
		make_activity(self.lead)
		with self.assertRaises(frappe.LinkExistsError):
			frappe.delete_doc("Lead", self.lead)

	def test_lead_table_lists_activities_oldest_first(self):
		older = make_activity(self.lead, date="2026-01-01")
		newer = make_activity(
			self.lead,
			activity_type="Meeting",
			assigned_to="Administrator",
			attachments=[
				{"attachment": "/files/a.pdf", "description": "Agenda"},
				{"attachment": "/files/b.pdf"},
			],
		)
		make_activity(make_lead().name)  # someone else's activity

		# oldest at the top, the new one appended at the bottom
		rows = table_rows(self.lead)
		self.assertEqual([r.activity for r in rows], [older.name, newer.name])
		self.assertEqual(
			(rows[1].activity_type, rows[1].status, rows[1].assigned_to, rows[1].attachments),
			("Meeting", "Planned", "Administrator", 2),
		)
		self.assertEqual(str(rows[0].date), "2026-01-01")
		# the one every activity on a Lead needs
		self.assertEqual(rows[0].attachments, 1)

	def test_back_dated_activity_is_still_appended_at_the_bottom(self):
		# the order is by creation, so a date in the past does not jump the row
		# to the top of the table
		first = make_activity(self.lead)
		back_dated = make_activity(self.lead, date="2020-01-01")
		self.assertEqual([r.activity for r in table_rows(self.lead)], [first.name, back_dated.name])

	def test_lead_table_follows_edits(self):
		activity = make_activity(self.lead)
		activity.status = "Waiting Reply"
		activity.append("attachments", {"attachment": "/files/c.pdf"})
		activity.save()

		(row,) = table_rows(self.lead)
		# the one it was created with, plus the one just added
		self.assertEqual((row.status, row.attachments), ("Waiting Reply", 2))

	def test_repointed_activity_moves_between_lead_tables(self):
		activity = make_activity(self.lead)
		other = make_lead().name

		activity.link_name = other
		activity.save()
		self.assertEqual(table_rows(self.lead), [])
		self.assertEqual([r.activity for r in table_rows(other)], [activity.name])

		activity.link_type = "Prospect"
		activity.link_name = frappe.get_doc(
			{"doctype": "Prospect", "company_name": "_Test Activity Prospect " + frappe.generate_hash(length=6)}
		).insert().name
		activity.save()
		self.assertEqual(table_rows(other), [])

	def test_deleting_activity_removes_row(self):
		keep = make_activity(self.lead)
		drop = make_activity(self.lead)

		# the Lead's row links to the activity; on_trash must clear it first
		frappe.delete_doc("Leads Activity", drop.name)
		self.assertEqual([r.activity for r in table_rows(self.lead)], [keep.name])

	def test_sync_invalidates_stale_lead_form(self):
		stale = frappe.get_doc("Lead", self.lead)
		make_activity(self.lead)

		# saving the stale copy would wipe the new row, so it must be refused
		with self.assertRaises(frappe.TimestampMismatchError):
			stale.save()

	def test_backfill_fills_missing_rows_and_is_idempotent(self):
		activity = make_activity(self.lead)
		frappe.db.delete("Leads Activity Detail", {"parent": self.lead})

		backfill_activity_tables()
		self.assertEqual([r.activity for r in table_rows(self.lead)], [activity.name])

		modified = frappe.db.get_value("Lead", self.lead, "modified")
		backfill_activity_tables()
		self.assertEqual(frappe.db.get_value("Lead", self.lead, "modified"), modified)

	def test_duplicating_lead_does_not_copy_activity_rows(self):
		make_activity(self.lead)
		# ignore_no_copy=False is what the Duplicate menu does
		copy = frappe.copy_doc(frappe.get_doc("Lead", self.lead), ignore_no_copy=False)
		self.assertEqual(copy.get(ACTIVITY_TABLE), [])

	def test_lead_dashboard_counts_activities(self):
		make_activity(self.lead)
		make_activity(self.lead)
		counts = get_open_count("Lead", self.lead)["count"]
		activity_count = next(c for c in counts["external_links_found"] if c["doctype"] == "Leads Activity")
		self.assertEqual(activity_count["count"], 2)


class TestActivityAttachment(FrappeTestCase):
	"""Every activity on a Lead or an Opportunity needs at least one
	attachment, and so does a Registration whatever it is linked to
	(LeadsActivity.validate_attachment)."""

	def setUp(self):
		self.lead = make_lead().name

	def test_registration_without_attachments_is_refused(self):
		with self.assertRaises(frappe.ValidationError) as error:
			make_activity(self.lead, activity_type="Registration", attachments=[])
		message = str(error.exception)
		# Arabic message, English field and DocType names
		self.assertIn("مرفقات", message)
		self.assertIn("Registration", message)
		self.assertIn("Attachments", message)

	def test_registration_with_an_attachment_saves(self):
		activity = make_activity(
			self.lead,
			activity_type="Registration",
			attachments=[{"attachment": "/files/trade-licence.pdf", "description": "Trade licence"}],
		)
		self.assertEqual(len(activity.attachments), 1)

	def test_row_without_a_file_does_not_count(self):
		# an empty row the user added and never filled: our own message, not
		# Frappe's "mandatory field in row 1"
		with self.assertRaises(frappe.ValidationError) as error:
			make_activity(self.lead, activity_type="Registration", attachments=[{"description": "x"}])
		self.assertIn("مرفقات", str(error.exception))

	def test_the_form_marks_the_table_mandatory(self):
		# the red asterisk and Frappe's own form check follow the Type and the
		# Link Type
		field = frappe.get_meta("Leads Activity").get_field("attachments")
		self.assertEqual(
			field.mandatory_depends_on,
			'eval:doc.activity_type=="Registration" || ["Lead", "Opportunity"].includes(doc.link_type)',
		)

	def test_every_type_on_a_lead_needs_one(self):
		for activity_type in ("Call", "Meeting", "Site Visit", "Tendering", "Other"):
			with self.assertRaises(frappe.ValidationError) as error:
				make_activity(self.lead, activity_type=activity_type, attachments=[])

			message = str(error.exception)
			self.assertIn("مرفقات", message)
			# the message names what it is linked to, not the type
			self.assertIn("Lead", message)

	def test_every_type_on_an_opportunity_needs_one(self):
		opportunity = make_opportunity_from(self.lead).name
		for activity_type in ("Call", "Meeting", "Other"):
			with self.assertRaises(frappe.ValidationError) as error:
				make_activity(
					opportunity, link_type="Opportunity", activity_type=activity_type, attachments=[]
				)
			self.assertIn("Opportunity", str(error.exception))

	def test_every_type_on_a_lead_saves_with_one(self):
		for activity_type in ("Call", "Meeting", "Site Visit", "Other"):
			activity = make_activity(self.lead, activity_type=activity_type)
			self.assertEqual(len(activity.attachments), 1)

	def test_a_prospect_only_needs_one_for_a_registration(self):
		prospect = frappe.get_doc(
			{"doctype": "Prospect", "company_name": "_Test Activity Prospect " + frappe.generate_hash(length=6)}
		).insert()

		# a Prospect has no attachments table of its own to follow up on
		for activity_type in ("Call", "Meeting", "Other"):
			activity = make_activity(
				prospect.name, link_type="Prospect", activity_type=activity_type, attachments=[]
			)
			self.assertEqual(activity.attachments, [])

		with self.assertRaises(frappe.ValidationError):
			make_activity(prospect.name, link_type="Prospect", activity_type="Registration", attachments=[])

	def test_becoming_a_registration_needs_one_too(self):
		# on a Prospect, which is the only link type that can hold an activity
		# with no attachment at all
		prospect = frappe.get_doc(
			{"doctype": "Prospect", "company_name": "_Test Activity Prospect " + frappe.generate_hash(length=6)}
		).insert()
		activity = make_activity(prospect.name, link_type="Prospect", activity_type="Call", attachments=[])

		activity.activity_type = "Registration"
		with self.assertRaises(frappe.ValidationError):
			activity.save()

	def test_being_moved_to_a_lead_needs_one_too(self):
		prospect = frappe.get_doc(
			{"doctype": "Prospect", "company_name": "_Test Activity Prospect " + frappe.generate_hash(length=6)}
		).insert()
		activity = make_activity(prospect.name, link_type="Prospect", activity_type="Call", attachments=[])

		activity.link_type = "Lead"
		activity.link_name = self.lead
		with self.assertRaises(frappe.ValidationError):
			activity.save()

	def test_emptying_the_table_is_refused(self):
		activity = make_activity(self.lead, activity_type="Registration")
		activity.attachments = []
		with self.assertRaises(frappe.ValidationError):
			activity.save()


class TestLeadLayout(FrappeTestCase):
	def test_organization_before_contact_info(self):
		order = [df.fieldname for df in frappe.get_meta("Lead").fields]
		self.assertLess(order.index("organization_section"), order.index("contact_info_tab"))
		# the whole Organization block moved, not just its heading
		self.assertLess(order.index("fax"), order.index("contact_info_tab"))
		self.assertLess(order.index("request_type"), order.index("organization_section"))

	def test_address_and_contacts_in_own_tab_before_activities(self):
		meta = frappe.get_meta("Lead")
		order = [df.fieldname for df in meta.fields]
		tab = order.index("custom_address_contacts_tab")
		self.assertEqual(
			order[tab : order.index("activities_tab")],
			[
				"custom_address_contacts_tab",
				"address_section",
				"address_html",
				"column_break_38",
				"city",
				"state",
				"country",
				"column_break2",
				"contact_html",
				"custom_contacts_section",
				"custom_contacts",
			],
		)
		# the sections that followed it stay in the Details tab
		self.assertLess(order.index("qualification_tab"), tab)
		self.assertLess(order.index("other_info_tab"), tab)
		self.assertEqual(meta.get_field("custom_address_contacts_tab").label, "Address & Contacts")
		self.assertFalse(meta.get_field("address_section").collapsible)

	def test_activities_section_in_activities_tab(self):
		order = [df.fieldname for df in frappe.get_meta("Lead").fields]
		self.assertEqual(
			order[order.index("activities_tab") :][:4],
			[
				"activities_tab",
				"custom_leads_activities_section",
				"custom_leads_activities",
				"custom_open_activities_section",
			],
		)


class TestOpportunityActivities(FrappeTestCase):
	def setUp(self):
		self.lead = make_lead().name
		self.opportunity = make_opportunity_from(self.lead).name

	def make_opportunity_activity(self, **kwargs):
		return make_activity(self.opportunity, link_type="Opportunity", **kwargs)

	def test_opportunity_and_lead_tables_are_separate(self):
		lead_activity = make_activity(self.lead)
		opportunity_activity = self.make_opportunity_activity(activity_type="Meeting")

		self.assertEqual(table_activities(self.opportunity, "Opportunity"), [opportunity_activity.name])
		self.assertEqual(table_activities(self.lead), [lead_activity.name])

		(row,) = table_rows(self.opportunity, "Opportunity")
		self.assertEqual((row.activity_type, row.status), ("Meeting", "Planned"))

	def test_opportunity_made_from_lead_starts_without_lead_activities(self):
		make_activity(self.lead)
		opportunity = make_opportunity(self.lead)
		self.assertEqual(opportunity.get(ACTIVITY_TABLE), [])

	def test_repointing_moves_row_between_lead_and_opportunity(self):
		activity = make_activity(self.lead)

		activity.link_type = "Opportunity"
		activity.link_name = self.opportunity
		activity.save()
		self.assertEqual(table_activities(self.lead), [])
		self.assertEqual(table_activities(self.opportunity, "Opportunity"), [activity.name])

	def test_opportunity_activity_does_not_change_lead_qualification(self):
		self.make_opportunity_activity(activity_type="Registration", status="Done")
		self.assertEqual(qualification(self.lead), "Unqualified")

	def test_deleting_opportunity_activity_removes_row(self):
		activity = self.make_opportunity_activity()
		frappe.delete_doc("Leads Activity", activity.name)
		self.assertEqual(table_rows(self.opportunity, "Opportunity"), [])

	def test_backfill_covers_opportunities(self):
		activity = self.make_opportunity_activity()
		frappe.db.delete("Leads Activity Detail", {"parent": self.opportunity})

		backfill_activity_tables()
		self.assertEqual(table_activities(self.opportunity, "Opportunity"), [activity.name])

	def test_opportunity_dashboard_counts_its_activities_only(self):
		make_activity(self.lead)
		self.make_opportunity_activity()
		counts = get_open_count("Opportunity", self.opportunity)["count"]
		activity_count = next(c for c in counts["external_links_found"] if c["doctype"] == "Leads Activity")
		self.assertEqual(activity_count["count"], 1)

	def test_activities_section_in_opportunity_activities_tab(self):
		order = [df.fieldname for df in frappe.get_meta("Opportunity").fields]
		self.assertEqual(
			order[order.index("activities_tab") :][:4],
			[
				"activities_tab",
				"custom_leads_activities_section",
				"custom_leads_activities",
				"custom_open_activities_section",
			],
		)
