# Copyright (c) 2026, smart and contributors
# For license information, please see license.txt

"""Tendering -> Project Tender, the approved tender behind a Won Opportunity,
Lead -> Customer conversion and the Contacts table
(custom_crm_updates/overrides/{project_tender,lead,contact}.py)."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, get_datetime, nowdate
from unittest.mock import patch

from custom_crm_updates.go_live import ENFORCE_FROM, applies_to, enforce_from, set_go_live
from custom_crm_updates.overrides import contracting_backport as backport
from custom_crm_updates.overrides.contact import CONTACT_TABLE, backfill_contact_tables
from custom_crm_updates.overrides.lead import CONVERT_DATE
from custom_crm_updates.overrides.tender import COMPLETION_DATE
from custom_crm_updates.overrides.opportunity import ATTACHMENTS_FIELD
from custom_crm_updates.overrides.opportunity import WON_DATE as OPPORTUNITY_WON_DATE
from custom_crm_updates.overrides.project_tender import (
	APPROVED_TENDER_FIELD,
	OPPORTUNITY_FIELD,
	STATUS_DATE_FIELDS,
	SUBMITTED_REQUIRED_TABLES,
	TENDER_TABLE,
)
from custom_crm_updates.custom_crm_updates.doctype.leads_activity.test_leads_activity import (
	customer_defaults,
	leaf,
	make_activity,
	make_lead,
	make_opportunity_from,
)

# Records are created by the tests and rolled back by FrappeTestCase.
test_ignore = [
	"Lead",
	"Prospect",
	"Opportunity",
	"User",
	"Customer",
	"Contact",
	"Project Tender",
	"Tender",
]


def customer_of(lead):
	return frappe.db.get_value("Customer", {"lead_name": lead})


def tenders_of(activity):
	return frappe.get_all("Project Tender", {"custom_leads_activity": activity}, pluck="name")


def status_of(tender):
	return frappe.db.get_value("Project Tender", tender, "status")


def fill_cost_tables(tender):
	"""A Project Tender can only be Submitted once all three of its cost
	tables have rows (validate_submitted_rows). The rows are as thin as the
	tables allow: Tender and Cost Component are mandatory links, and standing
	real ones up would be testing the contracting app rather than this rule,
	so the save ignores mandatory fields."""
	for fieldname in SUBMITTED_REQUIRED_TABLES:
		tender.append(fieldname, {})
	tender.flags.ignore_mandatory = True


def submit_tender(name):
	tender = frappe.get_doc("Project Tender", name)
	fill_cost_tables(tender)
	tender.status = "Submitted"
	tender.save()
	return tender


class TestLeadToCustomer(FrappeTestCase):
	def setUp(self):
		self.lead = make_lead().name

	def test_registration_done_converts_lead(self):
		with customer_defaults():
			make_activity(self.lead, activity_type="Registration", status="Done")

		customer = customer_of(self.lead)
		self.assertTrue(customer)
		self.assertEqual(frappe.db.get_value("Lead", self.lead, "status"), "Converted")

	def test_registration_converts_when_it_becomes_done(self):
		with customer_defaults():
			activity = make_activity(self.lead, activity_type="Registration")
			self.assertIsNone(customer_of(self.lead))

			activity.status = "Done"
			activity.save()
		self.assertTrue(customer_of(self.lead))

	def test_other_done_activities_do_not_convert(self):
		with customer_defaults():
			make_activity(self.lead, activity_type="Meeting", status="Done")
		self.assertIsNone(customer_of(self.lead))

	def test_converts_only_once(self):
		with customer_defaults():
			make_activity(self.lead, activity_type="Registration", status="Done")
			make_activity(self.lead, activity_type="Registration", status="Done")
		self.assertEqual(frappe.db.count("Customer", {"lead_name": self.lead}), 1)

	def test_customer_takes_group_and_territory_from_lead(self):
		groups = frappe.get_all("Customer Group", {"is_group": 0}, pluck="name", order_by="name desc", limit=1)
		frappe.db.set_value("Lead", self.lead, "custom_customer_group", groups[0])
		# no Selling Settings defaults at all: the Lead's values must be enough
		with customer_defaults(customer_group=False, territory=False):
			make_activity(self.lead, activity_type="Registration", status="Done")

		lead = frappe.db.get_value("Lead", self.lead, ["custom_customer_group", "territory"], as_dict=True)
		customer = frappe.db.get_value(
			"Customer", customer_of(self.lead), ["customer_group", "territory"], as_dict=True
		)
		self.assertEqual(
			(customer.customer_group, customer.territory), (lead.custom_customer_group, lead.territory)
		)

	def test_lead_without_fields_explains_what_to_set(self):
		# e.g. a Lead ERPNext created itself, saved before the fields existed
		frappe.db.set_value("Lead", self.lead, {"custom_customer_group": None, "territory": None})
		with customer_defaults(customer_group=False, territory=False), self.assertRaises(
			frappe.ValidationError
		) as error:
			make_activity(self.lead, activity_type="Registration", status="Done")
		self.assertIn("Customer Group", str(error.exception))
		self.assertIn("Set them on the Lead", str(error.exception))


class TestLeadCustomerFields(FrappeTestCase):
	def test_mandatory_when_saved_by_a_user(self):
		for missing in ("custom_customer_group", "territory"):
			with self.assertRaises(frappe.MandatoryError):
				make_lead(**{missing: None})

	def test_erpnext_created_leads_are_not_blocked(self):
		# website contact form, Opportunity from an email address, ...
		lead = frappe.get_doc(
			{"doctype": "Lead", "lead_name": "_Test Auto Lead", "email_id": "auto-lead@example.com"}
		).insert(ignore_permissions=True)
		self.assertTrue(frappe.db.exists("Lead", lead.name))

	def test_layout_and_form_mandatory(self):
		meta = frappe.get_meta("Lead")
		order = [df.fieldname for df in meta.fields]
		self.assertEqual(order[order.index("territory") + 1], "custom_customer_group")
		for fieldname in ("custom_customer_group", "territory"):
			self.assertEqual(meta.get_field(fieldname).mandatory_depends_on, "eval:1")


class TestTendering(FrappeTestCase):
	def setUp(self):
		self.lead = make_lead(company_name="_Test Tender Co " + frappe.generate_hash(length=6)).name
		self.opportunity = make_opportunity_from(self.lead)

	def tendering(self, **kwargs):
		with customer_defaults():
			return make_activity(
				self.opportunity.name, link_type="Opportunity", activity_type="Tendering", **kwargs
			)

	def test_tendering_creates_project_tender(self):
		activity = self.tendering()

		(name,) = tenders_of(activity.name)
		tender = frappe.get_doc("Project Tender", name)
		self.assertEqual(tender.project_name, self.opportunity.title)
		self.assertEqual(tender.custom_opportunity, self.opportunity.name)
		self.assertEqual(tender.status, "Draft")
		# the Opportunity's Lead was converted to supply the Client
		self.assertEqual(tender.client, customer_of(self.lead))
		self.assertEqual(frappe.db.get_value("Opportunity", self.opportunity.name, "status"), "Tendering")

	def test_each_tendering_activity_gets_its_own_tender(self):
		first = self.tendering()
		second = self.tendering()
		self.assertEqual(len(tenders_of(first.name)), 1)
		self.assertEqual(len(tenders_of(second.name)), 1)
		self.assertEqual(frappe.db.count("Project Tender", {"custom_opportunity": self.opportunity.name}), 2)

	def test_resaving_activity_does_not_create_another(self):
		activity = self.tendering()
		activity.status = "In Process"
		activity.save()
		self.assertEqual(len(tenders_of(activity.name)), 1)

	def test_other_types_and_lead_links_create_none(self):
		make_activity(self.opportunity.name, link_type="Opportunity", activity_type="Meeting")
		with customer_defaults():
			make_activity(self.lead, activity_type="Tendering")
		self.assertEqual(frappe.db.count("Project Tender", {"custom_opportunity": self.opportunity.name}), 0)

	def test_opportunity_table_lists_its_tenders(self):
		activity = self.tendering()
		(name,) = tenders_of(activity.name)

		(row,) = frappe.get_doc("Opportunity", self.opportunity.name).get(TENDER_TABLE)
		self.assertEqual(
			(row.project_tender, row.project_name, row.status, row.leads_activity),
			(name, self.opportunity.title, "Draft", activity.name),
		)

		tender = frappe.get_doc("Project Tender", name)
		tender.status = "Under Review"
		tender.save()
		(row,) = frappe.get_doc("Opportunity", self.opportunity.name).get(TENDER_TABLE)
		self.assertEqual(row.status, "Under Review")

	def test_submitted_tender_marks_only_its_activity_done(self):
		activity = self.tendering()
		other = self.tendering()

		submit_tender(tenders_of(activity.name)[0])
		self.assertEqual(frappe.db.get_value("Leads Activity", activity.name, "status"), "Done")
		self.assertEqual(frappe.db.get_value("Leads Activity", other.name, "status"), "Planned")

		# the Opportunity is left alone: which tender was approved is decided
		# when the Opportunity itself is set to Won, not by submitting one
		self.assertEqual(
			frappe.db.get_value("Opportunity", self.opportunity.name, "status"), "Tendering"
		)

		# the Opportunity's activities table followed the activity
		rows = frappe.get_doc("Opportunity", self.opportunity.name).custom_leads_activities
		self.assertEqual({r.activity: r.status for r in rows}[activity.name], "Done")

	def test_tender_creation_tells_the_user(self):
		frappe.clear_messages()
		activity = self.tendering()

		(name,) = tenders_of(activity.name)
		messages = " ".join(message.get("message", "") for message in frappe.get_message_log())
		self.assertIn("تم إنشاء", messages)
		self.assertIn(name, messages)
		self.assertIn(self.opportunity.name, messages)

	def test_won_opportunity_is_not_set_back_to_tendering(self):
		frappe.db.set_value("Opportunity", self.opportunity.name, "status", "Won")
		self.tendering()
		self.assertEqual(frappe.db.get_value("Opportunity", self.opportunity.name, "status"), "Won")

	def test_opportunity_accepts_new_statuses_on_save(self):
		opportunity = frappe.get_doc("Opportunity", self.opportunity.name)
		for status in ("Tendering", "Won"):
			opportunity.status = status
			opportunity.save()
			self.assertEqual(frappe.db.get_value("Opportunity", opportunity.name, "status"), status)

	def test_opportunity_table_lists_tenders_oldest_first(self):
		first = tenders_of(self.tendering().name)[0]
		second = tenders_of(self.tendering().name)[0]

		rows = frappe.get_doc("Opportunity", self.opportunity.name).get(TENDER_TABLE)
		self.assertEqual([row.project_tender for row in rows], [first, second])

	def test_deleting_tender_removes_row(self):
		activity = self.tendering()
		frappe.delete_doc("Project Tender", tenders_of(activity.name)[0], force=True)
		self.assertEqual(frappe.get_doc("Opportunity", self.opportunity.name).get(TENDER_TABLE), [])

	def test_customer_opportunity_uses_its_customer(self):
		with customer_defaults():
			customer = frappe.get_doc(
				{"doctype": "Customer", "customer_name": "_Test Tender Customer " + frappe.generate_hash(length=6)}
			)
			customer.customer_group = frappe.db.get_default("Customer Group")
			customer.territory = frappe.db.get_default("Territory")
			customer.insert()
		opportunity = frappe.get_doc(
			{
				"doctype": "Opportunity",
				"opportunity_from": "Customer",
				"party_name": customer.name,
				"company": frappe.db.get_value("Company", {}, "name"),
				# an Opportunity cannot be saved without one
				# (overrides/opportunity.py: validate_attachments)
				ATTACHMENTS_FIELD: [{"attachment": "/files/_test_opportunity.pdf"}],
			}
		).insert()

		activity = make_activity(opportunity.name, link_type="Opportunity", activity_type="Tendering")
		self.assertEqual(frappe.db.get_value("Project Tender", tenders_of(activity.name)[0], "client"), customer.name)


class TestSubmittedRequirements(FrappeTestCase):
	"""A Project Tender needs rows in all three of its cost tables before it
	can be Submitted (overrides/project_tender.py: validate_submitted_rows)."""

	def setUp(self):
		self.lead = make_lead(company_name="_Test Submit Co " + frappe.generate_hash(length=6)).name
		self.opportunity = make_opportunity_from(self.lead).name
		with customer_defaults():
			activity = make_activity(
				self.opportunity, link_type="Opportunity", activity_type="Tendering"
			)
		self.activity = activity.name
		self.tender = tenders_of(self.activity)[0]

	def submit(self, *tables):
		tender = frappe.get_doc("Project Tender", self.tender)
		for fieldname in tables:
			tender.append(fieldname, {})
		tender.status = "Submitted"
		# see fill_cost_tables: the rows are deliberately thin
		tender.flags.ignore_mandatory = True
		tender.save()

	def label(self, fieldname):
		return frappe.get_meta("Project Tender").get_label(fieldname)

	def test_tender_with_no_costing_cannot_be_submitted(self):
		with self.assertRaises(frappe.ValidationError) as error:
			self.submit()

		message = str(error.exception)
		# Arabic message; the table names stay as they are in the system
		self.assertIn("لا يمكن", message)
		self.assertIn("Submitted", message)
		for fieldname in SUBMITTED_REQUIRED_TABLES:
			self.assertIn(self.label(fieldname), message)
		self.assertEqual(status_of(self.tender), "Draft")
		self.assertEqual(frappe.db.get_value("Leads Activity", self.activity, "status"), "Planned")

	def test_every_one_of_the_three_tables_is_required(self):
		for missing in SUBMITTED_REQUIRED_TABLES:
			filled = [f for f in SUBMITTED_REQUIRED_TABLES if f != missing]
			with self.assertRaises(frappe.ValidationError) as error:
				self.submit(*filled)

			message = str(error.exception)
			self.assertIn(self.label(missing), message)
			for fieldname in filled:
				self.assertNotIn(self.label(fieldname), message)

	def test_submitted_once_all_three_have_rows(self):
		self.submit(*SUBMITTED_REQUIRED_TABLES)
		self.assertEqual(status_of(self.tender), "Submitted")
		self.assertEqual(frappe.db.get_value("Leads Activity", self.activity, "status"), "Done")

	def test_other_statuses_need_no_rows(self):
		for status in ("Under Review", "Lost", "Cancelled"):
			tender = frappe.get_doc("Project Tender", self.tender)
			tender.status = status
			tender.save()
			self.assertEqual(status_of(self.tender), status)

	def test_emptying_a_table_on_a_submitted_tender_is_refused(self):
		self.submit(*SUBMITTED_REQUIRED_TABLES)

		tender = frappe.get_doc("Project Tender", self.tender)
		tender.indirect_cost_details = []
		with self.assertRaises(frappe.ValidationError):
			tender.save()


class TestApprovedTender(FrappeTestCase):
	"""Setting an Opportunity to Won marks the Project Tender the user picked
	in the popup (public/js/opportunity.js) as the approved one
	(overrides/project_tender.py: apply_approved_tender)."""

	def setUp(self):
		self.lead = make_lead(company_name="_Test Won Co " + frappe.generate_hash(length=6)).name
		self.opportunity = make_opportunity_from(self.lead).name
		with customer_defaults():
			self.first = self.make_tender()
			self.second = self.make_tender()

	def make_tender(self, opportunity=None):
		activity = make_activity(
			opportunity or self.opportunity, link_type="Opportunity", activity_type="Tendering"
		)
		return tenders_of(activity.name)[0]

	def win(self, tender=None, status="Won"):
		opportunity = frappe.get_doc("Opportunity", self.opportunity)
		opportunity.status = status
		opportunity.set(APPROVED_TENDER_FIELD, tender)
		opportunity.save()
		return opportunity

	def test_the_selected_tender_is_won_and_the_others_are_not(self):
		opportunity = self.win(self.first)

		self.assertEqual(status_of(self.first), "Won")
		self.assertEqual(status_of(self.second), "Draft")
		self.assertEqual(frappe.db.get_value("Opportunity", self.opportunity, "status"), "Won")
		self.assertEqual(
			frappe.db.get_value("Opportunity", self.opportunity, APPROVED_TENDER_FIELD), self.first
		)

		# the table on the form that did the saving is up to date, and so is
		# the one in the database
		for doc in (opportunity, frappe.get_doc("Opportunity", self.opportunity)):
			statuses = {row.project_tender: row.status for row in doc.get(TENDER_TABLE)}
			self.assertEqual(statuses, {self.first: "Won", self.second: "Draft"})

	def test_the_saved_form_is_not_left_behind_the_database(self):
		opportunity = self.win(self.first)
		self.assertEqual(
			str(opportunity.modified), str(frappe.db.get_value("Opportunity", self.opportunity, "modified"))
		)

	def test_won_without_a_selection_changes_no_tender(self):
		self.win()
		self.assertEqual(frappe.db.get_value("Opportunity", self.opportunity, "status"), "Won")
		self.assertEqual((status_of(self.first), status_of(self.second)), ("Draft", "Draft"))

	def test_a_submitted_tender_can_be_the_approved_one(self):
		# written straight to the database: submit_tender's rows are thin
		# enough to skip mandatory fields (see fill_cost_tables), and winning
		# the tender saves it again, this time in full
		frappe.db.set_value("Project Tender", self.first, "status", "Submitted")

		self.win(self.first)
		self.assertEqual(status_of(self.first), "Won")

	def test_changing_the_selection_wins_the_new_one(self):
		self.win(self.first)
		self.win(self.second)
		self.assertEqual((status_of(self.first), status_of(self.second)), ("Won", "Won"))

	def test_resaving_a_won_opportunity_does_not_win_it_again(self):
		self.win(self.first)
		# as if the tender had been moved on by hand afterwards
		frappe.db.set_value("Project Tender", self.first, "status", "Lost")

		self.win(self.first)
		self.assertEqual(status_of(self.first), "Lost")

	def test_a_tender_of_another_opportunity_is_refused(self):
		other = make_opportunity_from(make_lead().name).name
		with customer_defaults():
			stranger = self.make_tender(other)

		with self.assertRaises(frappe.ValidationError) as error:
			self.win(stranger)
		self.assertIn("لم يُنشأ", str(error.exception))
		self.assertIn(stranger, str(error.exception))
		self.assertEqual(status_of(stranger), "Draft")

	def test_the_popup_lists_this_opportunitys_tenders_oldest_first(self):
		from custom_crm_updates.overrides.project_tender import get_opportunity_tenders

		other = make_opportunity_from(make_lead().name).name
		with customer_defaults():
			stranger = self.make_tender(other)
		for tender in (stranger, self.first, self.second):
			submit_tender(tender)

		tenders = get_opportunity_tenders(self.opportunity)
		self.assertEqual([tender.name for tender in tenders], [self.first, self.second])
		self.assertEqual(
			set(tenders[0].keys()),
			{"name", "project_name", "client", "status", "total_sell_price"},
		)

	def test_the_popup_offers_submitted_tenders_only(self):
		from custom_crm_updates.overrides.project_tender import get_opportunity_tenders

		# a price that never left the office cannot be the one that was approved
		self.assertEqual(get_opportunity_tenders(self.opportunity), [])

		submit_tender(self.first)
		self.assertEqual(
			[tender.name for tender in get_opportunity_tenders(self.opportunity)], [self.first]
		)

	def test_a_tender_past_submitted_is_not_offered_either(self):
		from custom_crm_updates.overrides.project_tender import get_opportunity_tenders

		submit_tender(self.first)
		for status in ("Lost", "Cancelled", "Won"):
			frappe.db.set_value("Project Tender", self.first, "status", status)
			self.assertEqual(get_opportunity_tenders(self.opportunity), [], status)

	def test_status_other_than_won_leaves_the_tenders_alone(self):
		self.win(self.first, status="Quotation")
		self.assertEqual(status_of(self.first), "Draft")


class TestContactsTable(FrappeTestCase):
	def setUp(self):
		self.lead = make_lead().name

	def make_contact(self, *links, **kwargs):
		return frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": "_Test Contact " + frappe.generate_hash(length=6),
				"email_ids": [{"email_id": frappe.generate_hash(length=8) + "@example.com", "is_primary": 1}],
				"links": [{"link_doctype": dt, "link_name": name} for dt, name in links],
				**kwargs,
			}
		).insert()

	def rows(self, doctype, name):
		return frappe.get_doc(doctype, name).get(CONTACT_TABLE)

	def test_lead_lists_its_contacts(self):
		contact = self.make_contact(("Lead", self.lead), designation="Manager")
		(row,) = [r for r in self.rows("Lead", self.lead) if r.contact == contact.name]
		self.assertEqual((row.full_name, row.designation), (contact.first_name, "Manager"))
		self.assertEqual(row.email_id, contact.email_id)

	def test_contacts_are_listed_oldest_first(self):
		# the primary contact is flagged by its own column, not by being
		# sorted to the top, so every CRM table reads the same way
		first = self.make_contact(("Lead", self.lead))
		primary = self.make_contact(("Lead", self.lead), is_primary_contact=1)

		rows = [r.contact for r in self.rows("Lead", self.lead)]
		self.assertEqual(rows[-2:], [first.name, primary.name])

	def test_contact_edits_and_unlinking_follow(self):
		contact = self.make_contact(("Lead", self.lead))
		contact.designation = "CEO"
		contact.save()
		self.assertEqual(
			{r.contact: r.designation for r in self.rows("Lead", self.lead)}[contact.name], "CEO"
		)

		contact.links = []
		contact.save()
		self.assertNotIn(contact.name, [r.contact for r in self.rows("Lead", self.lead)])

	def test_deleting_contact_removes_row(self):
		contact = self.make_contact(("Lead", self.lead))
		frappe.delete_doc("Contact", contact.name)
		self.assertNotIn(contact.name, [r.contact for r in self.rows("Lead", self.lead)])

	def test_opportunity_shows_only_its_own_contacts(self):
		lead_contact = self.make_contact(("Lead", self.lead))
		opportunity = make_opportunity_from(self.lead).name
		own_contact = self.make_contact(("Opportunity", opportunity))

		# the Opportunity shows its own contact and nothing else - not the
		# contacts of the Lead it was made from
		rows = {r.contact: r.linked_via for r in self.rows("Opportunity", opportunity)}
		self.assertEqual(rows, {own_contact.name: f"Opportunity {opportunity}"})
		self.assertNotIn(lead_contact.name, rows)

	def test_lead_rolls_up_its_opportunity_contacts(self):
		lead_contact = self.make_contact(("Lead", self.lead))
		opportunity = make_opportunity_from(self.lead).name
		own_contact = self.make_contact(("Opportunity", opportunity))

		# the Lead shows both, and says where each one came from
		rows = {r.contact: r.linked_via for r in self.rows("Lead", self.lead)}
		self.assertEqual(rows.get(lead_contact.name), f"Lead {self.lead}")
		self.assertEqual(rows.get(own_contact.name), f"Opportunity {opportunity}")
		# the Lead's own contacts come first, the Opportunity's after them
		order = [r.contact for r in self.rows("Lead", self.lead)]
		self.assertLess(order.index(lead_contact.name), order.index(own_contact.name))

	def test_opportunity_contact_added_later_reaches_the_lead(self):
		opportunity = make_opportunity_from(self.lead).name
		contact = self.make_contact(("Opportunity", opportunity))
		self.assertIn(contact.name, [r.contact for r in self.rows("Lead", self.lead)])

		# and follows the contact being unlinked again
		contact.links = []
		contact.save()
		self.assertNotIn(contact.name, [r.contact for r in self.rows("Lead", self.lead)])

	def test_lead_contact_added_later_stays_with_the_lead(self):
		opportunity = make_opportunity_from(self.lead).name
		contact = self.make_contact(("Lead", self.lead))

		self.assertNotIn(contact.name, [r.contact for r in self.rows("Opportunity", opportunity)])
		self.assertIn(contact.name, [r.contact for r in self.rows("Lead", self.lead)])

	def test_a_contact_on_both_is_listed_once(self):
		opportunity = make_opportunity_from(self.lead).name
		contact = self.make_contact(("Lead", self.lead), ("Opportunity", opportunity))

		rows = [r.contact for r in self.rows("Lead", self.lead)]
		self.assertEqual(rows.count(contact.name), 1)

	def test_only_this_leads_opportunities_roll_up(self):
		other_lead = make_lead().name
		other_opportunity = make_opportunity_from(other_lead).name
		stranger = self.make_contact(("Opportunity", other_opportunity))

		self.assertNotIn(stranger.name, [r.contact for r in self.rows("Lead", self.lead)])
		self.assertIn(stranger.name, [r.contact for r in self.rows("Lead", other_lead)])

	def test_deleting_the_opportunity_drops_its_contacts_from_the_lead(self):
		opportunity = make_opportunity_from(self.lead)
		contact = self.make_contact(("Opportunity", opportunity.name))
		self.assertIn(contact.name, [r.contact for r in self.rows("Lead", self.lead)])

		# Frappe refuses an ordinary delete while a Contact links to it, so
		# this is the forced path - which is the one on_trash has to cover.
		frappe.delete_doc("Opportunity", opportunity.name, force=True)
		self.assertNotIn(contact.name, [r.contact for r in self.rows("Lead", self.lead)])

	def test_repointing_the_opportunity_moves_its_contacts(self):
		opportunity = make_opportunity_from(self.lead)
		contact = self.make_contact(("Opportunity", opportunity.name))
		other_lead = make_lead().name

		opportunity.party_name = other_lead
		opportunity.save()
		self.assertNotIn(contact.name, [r.contact for r in self.rows("Lead", self.lead)])
		self.assertIn(contact.name, [r.contact for r in self.rows("Lead", other_lead)])

	def make_customer(self, **kwargs):
		"""A Customer of this Lead. Built by hand rather than through
		convert_lead_to_customer: ERPNext's conversion also links the Lead's
		own contacts to the Customer, and these tests are about which document
		a contact was linked to."""
		values = {
			"doctype": "Customer",
			"customer_name": "_Test Contacts Customer " + frappe.generate_hash(length=6),
			"customer_group": leaf("Customer Group"),
			"territory": leaf("Territory"),
			"lead_name": self.lead,
		}
		values.update(kwargs)
		return frappe.get_doc(values).insert().name

	def test_customer_shows_only_its_own_contacts(self):
		opportunity = make_opportunity_from(self.lead).name
		opportunity_contact = self.make_contact(("Opportunity", opportunity))
		customer = self.make_customer()
		own_contact = self.make_contact(("Customer", customer))
		# after the conversion, so ERPNext cannot have linked it to the Customer
		lead_contact = self.make_contact(("Lead", self.lead))

		rows = {r.contact: r.linked_via for r in self.rows("Customer", customer)}
		self.assertEqual(rows.get(own_contact.name), f"Customer {customer}")
		# not an exact list: ERPNext's own Lead -> Customer conversion links the
		# Lead's contacts to the Customer too, and those are its contacts
		self.assertNotIn(lead_contact.name, rows)
		self.assertNotIn(opportunity_contact.name, rows)

		# and the contact added on the Customer stays out of the Opportunity
		self.assertNotIn(own_contact.name, [r.contact for r in self.rows("Opportunity", opportunity)])

	def test_lead_rolls_up_its_customer_contacts(self):
		lead_contact = self.make_contact(("Lead", self.lead))
		opportunity = make_opportunity_from(self.lead).name
		opportunity_contact = self.make_contact(("Opportunity", opportunity))
		customer = self.make_customer()
		customer_contact = self.make_contact(("Customer", customer))

		rows = {r.contact: r.linked_via for r in self.rows("Lead", self.lead)}
		self.assertEqual(rows.get(lead_contact.name), f"Lead {self.lead}")
		self.assertEqual(rows.get(opportunity_contact.name), f"Opportunity {opportunity}")
		self.assertEqual(rows.get(customer_contact.name), f"Customer {customer}")

		# the Lead's own first, then its Opportunities', then its Customer's
		order = [r.contact for r in self.rows("Lead", self.lead)]
		self.assertLess(order.index(lead_contact.name), order.index(opportunity_contact.name))
		self.assertLess(order.index(opportunity_contact.name), order.index(customer_contact.name))

	def test_customer_contact_added_later_reaches_the_lead(self):
		customer = self.make_customer()
		contact = self.make_contact(("Customer", customer))
		self.assertIn(contact.name, [r.contact for r in self.rows("Lead", self.lead)])

		# and follows the contact being unlinked again
		contact.links = []
		contact.save()
		self.assertNotIn(contact.name, [r.contact for r in self.rows("Lead", self.lead)])

	def test_customer_made_from_an_opportunity_rolls_up_too(self):
		# the other way ERPNext records the same conversion
		opportunity = make_opportunity_from(self.lead).name
		customer = self.make_customer(lead_name=None, opportunity_name=opportunity)
		contact = self.make_contact(("Customer", customer))

		rows = {r.contact: r.linked_via for r in self.rows("Lead", self.lead)}
		self.assertEqual(rows.get(contact.name), f"Customer {customer}")

	def test_only_this_leads_customers_roll_up(self):
		other_lead = make_lead().name
		stranger = self.make_contact(("Customer", self.make_customer(lead_name=other_lead)))

		self.assertNotIn(stranger.name, [r.contact for r in self.rows("Lead", self.lead)])
		self.assertIn(stranger.name, [r.contact for r in self.rows("Lead", other_lead)])

	def test_deleting_the_customer_drops_its_contacts_from_the_lead(self):
		customer = self.make_customer()
		contact = self.make_contact(("Customer", customer))
		self.assertIn(contact.name, [r.contact for r in self.rows("Lead", self.lead)])

		# forced, like the Opportunity above: a Contact links to it
		frappe.delete_doc("Customer", customer, force=True)
		self.assertNotIn(contact.name, [r.contact for r in self.rows("Lead", self.lead)])

	def test_repointing_the_customer_moves_its_contacts(self):
		customer = self.make_customer()
		contact = self.make_contact(("Customer", customer))
		other_lead = make_lead().name

		customer_doc = frappe.get_doc("Customer", customer)
		customer_doc.lead_name = other_lead
		customer_doc.save()
		self.assertNotIn(contact.name, [r.contact for r in self.rows("Lead", self.lead)])
		self.assertIn(contact.name, [r.contact for r in self.rows("Lead", other_lead)])

	def test_contacts_table_on_customer_layout(self):
		meta = frappe.get_meta("Customer")
		order = [df.fieldname for df in meta.fields]
		self.assertEqual(
			order[order.index("contact_html") + 1 : order.index("primary_address_and_contact_detail")],
			["custom_contacts_section", CONTACT_TABLE],
		)
		self.assertTrue(meta.get_field("contact_html").hidden)

	def test_backfill_covers_customers(self):
		customer = self.make_customer()
		contact = self.make_contact(("Customer", customer))
		frappe.db.delete("Leads Contact Detail", {"parenttype": "Customer", "parent": customer})

		backfill_contact_tables()
		self.assertIn(contact.name, [r.contact for r in self.rows("Customer", customer)])

	def test_backfill_drops_contacts_mirrored_before_the_split(self):
		# an Opportunity whose table still lists its Lead's contacts, as it
		# would after migrating from the version that showed both
		opportunity = make_opportunity_from(self.lead)
		lead_contact = self.make_contact(("Lead", self.lead))
		opportunity.append(CONTACT_TABLE, {"contact": lead_contact.name, "full_name": "stale row"})
		opportunity.update_child_table(CONTACT_TABLE)
		self.assertTrue(self.rows("Opportunity", opportunity.name))

		backfill_contact_tables()
		self.assertEqual(self.rows("Opportunity", opportunity.name), [])
		self.assertIn(lead_contact.name, [r.contact for r in self.rows("Lead", self.lead)])

	def test_new_lead_shows_auto_created_contact(self):
		# CRM Settings' auto contact creation links the contact in
		# Lead.after_insert, after validate; the returned doc must still carry it
		if not frappe.db.get_single_value("CRM Settings", "auto_creation_of_contact"):
			self.skipTest("CRM Settings: auto creation of contact is off")

		lead = make_lead()
		contacts = [r.contact for r in lead.get(CONTACT_TABLE)]
		self.assertEqual(len(contacts), 1)
		self.assertEqual(contacts, [r.contact for r in self.rows("Lead", lead.name)])

	def test_contact_tables_on_lead_and_opportunity_layout(self):
		lead_order = [df.fieldname for df in frappe.get_meta("Lead").fields]
		self.assertEqual(
			lead_order[lead_order.index("contact_html") + 1 : lead_order.index("activities_tab")],
			["custom_contacts_section", CONTACT_TABLE],
		)
		self.assertTrue(frappe.get_meta("Lead").get_field("contact_html").hidden)
		self.assertTrue(frappe.get_meta("Opportunity").get_field("contact_html").hidden)

		opp_order = [df.fieldname for df in frappe.get_meta("Opportunity").fields]
		self.assertEqual(
			opp_order[opp_order.index("contact_display") + 1 : opp_order.index("items_section")],
			["custom_contacts_section", CONTACT_TABLE],
		)
		self.assertEqual(
			opp_order[opp_order.index("total") + 1 : opp_order.index("activities_tab")],
			["custom_project_tender_tab", TENDER_TABLE, APPROVED_TENDER_FIELD, OPPORTUNITY_WON_DATE],
		)


class TestLeadConvertDate(FrappeTestCase):
	"""Date of Convert: the day the Lead's status became "Converted"
	(overrides/lead.py)."""

	def setUp(self):
		self.lead = make_lead().name

	def convert_date(self):
		return frappe.db.get_value("Lead", self.lead, CONVERT_DATE)

	def test_an_open_lead_has_no_date(self):
		self.assertIsNone(self.convert_date())

	def test_set_when_the_status_is_changed_on_the_lead_itself(self):
		lead = frappe.get_doc("Lead", self.lead)
		lead.status = "Converted"
		lead.save()

		self.assertEqual(str(lead.get(CONVERT_DATE)), nowdate())
		self.assertEqual(str(self.convert_date()), nowdate())

	def test_set_when_a_customer_is_raised_from_the_lead(self):
		# Registration -> Done converts the Lead, and ERPNext marks it
		# Converted with frappe.db.set_value, where no Lead hook can see it
		with customer_defaults():
			make_activity(self.lead, activity_type="Registration", status="Done")

		self.assertEqual(frappe.db.get_value("Lead", self.lead, "status"), "Converted")
		self.assertEqual(str(self.convert_date()), nowdate())

	def test_another_status_sets_no_date(self):
		lead = frappe.get_doc("Lead", self.lead)
		lead.status = "Interested"
		lead.save()
		self.assertIsNone(self.convert_date())

	def test_the_first_conversion_is_the_one_that_is_kept(self):
		earlier = add_days(nowdate(), -30)
		frappe.db.set_value("Lead", self.lead, {"status": "Converted", CONVERT_DATE: earlier})

		lead = frappe.get_doc("Lead", self.lead)
		lead.status = "Open"
		lead.save()
		lead.status = "Converted"
		lead.save()

		self.assertEqual(str(lead.get(CONVERT_DATE)), earlier)

	def test_an_ordinary_resave_leaves_the_date_alone(self):
		earlier = add_days(nowdate(), -30)
		frappe.db.set_value("Lead", self.lead, {"status": "Converted", CONVERT_DATE: earlier})

		lead = frappe.get_doc("Lead", self.lead)
		lead.company_name = "_Test Renamed Co"
		lead.save()

		self.assertEqual(str(lead.get(CONVERT_DATE)), earlier)


class TestProjectTenderStatusDates(FrappeTestCase):
	"""Submitted Date and Won Date on Project Tender, and the same two
	columns on the Opportunity's Project Tenders table
	(overrides/project_tender.py)."""

	def setUp(self):
		self.opportunity = make_opportunity_from(make_lead().name).name
		with customer_defaults():
			activity = make_activity(
				self.opportunity, link_type="Opportunity", activity_type="Tendering"
			)
		self.tender = tenders_of(activity.name)[0]

	def dates(self):
		return frappe.db.get_value(
			"Project Tender", self.tender, list(STATUS_DATE_FIELDS.values()), as_dict=True
		)

	def mirrored_row(self):
		return next(
			row
			for row in frappe.get_doc("Opportunity", self.opportunity).get(TENDER_TABLE)
			if row.project_tender == self.tender
		)

	def test_a_draft_tender_has_neither_date(self):
		self.assertEqual(self.dates(), {"submitted_date": None, "won_date": None})

	def test_submitted_date_is_set_on_submission(self):
		submit_tender(self.tender)

		dates = self.dates()
		self.assertEqual(str(dates.submitted_date), nowdate())
		self.assertIsNone(dates.won_date)
		self.assertEqual(str(self.mirrored_row().submitted_date), nowdate())

	def test_won_date_is_set_when_the_opportunity_approves_it(self):
		opportunity = frappe.get_doc("Opportunity", self.opportunity)
		opportunity.status = "Won"
		opportunity.set(APPROVED_TENDER_FIELD, self.tender)
		opportunity.save()

		self.assertEqual(str(self.dates().won_date), nowdate())
		# the Opportunity's own Won Date, and the table in the same tab
		self.assertEqual(str(opportunity.get(OPPORTUNITY_WON_DATE)), nowdate())
		self.assertEqual(str(self.mirrored_row().won_date), nowdate())

	def test_a_status_with_no_date_of_its_own_sets_nothing(self):
		tender = frappe.get_doc("Project Tender", self.tender)
		tender.status = "Under Review"
		tender.save()
		self.assertEqual(self.dates(), {"submitted_date": None, "won_date": None})

	def test_the_first_submission_is_the_one_that_is_kept(self):
		earlier = add_days(nowdate(), -10)
		submit_tender(self.tender)
		frappe.db.set_value("Project Tender", self.tender, "submitted_date", earlier)

		tender = frappe.get_doc("Project Tender", self.tender)
		# the cost rows submit_tender added are as thin as the tables allow
		tender.flags.ignore_mandatory = True
		tender.status = "Under Review"
		tender.save()
		tender.flags.ignore_mandatory = True
		tender.status = "Submitted"
		tender.save()

		self.assertEqual(str(tender.submitted_date), earlier)


class TestOpportunityWonDate(FrappeTestCase):
	"""Won Date on Opportunity (overrides/opportunity.py)."""

	def setUp(self):
		self.opportunity = make_opportunity_from(make_lead().name).name

	def won_date(self):
		return frappe.db.get_value("Opportunity", self.opportunity, OPPORTUNITY_WON_DATE)

	def test_an_open_opportunity_has_no_date(self):
		self.assertIsNone(self.won_date())

	def test_set_when_the_opportunity_is_won(self):
		opportunity = frappe.get_doc("Opportunity", self.opportunity)
		opportunity.status = "Won"
		opportunity.save()
		self.assertEqual(str(self.won_date()), nowdate())

	def test_the_first_win_is_the_one_that_is_kept(self):
		earlier = add_days(nowdate(), -5)
		frappe.db.set_value(
			"Opportunity", self.opportunity, {"status": "Won", OPPORTUNITY_WON_DATE: earlier}
		)

		opportunity = frappe.get_doc("Opportunity", self.opportunity)
		opportunity.status = "Open"
		opportunity.save()
		opportunity.status = "Won"
		opportunity.save()

		self.assertEqual(str(opportunity.get(OPPORTUNITY_WON_DATE)), earlier)


class TestTenderDates(FrappeTestCase):
	"""Completion Date on Tender, its column on the Project Tender's Direct
	Cost Details, and the Submission Deadline a Tender inherits from the
	Opportunity behind its Project Tender (overrides/tender.py). Tender lives
	in the contracting app."""

	def setUp(self):
		if not frappe.db.exists("DocType", "Tender"):
			self.skipTest("the contracting app is not installed")

		self.expected_closing = add_days(nowdate(), 30)
		self.opportunity = make_opportunity_from(make_lead().name).name
		frappe.db.set_value("Opportunity", self.opportunity, "expected_closing", self.expected_closing)
		with customer_defaults():
			activity = make_activity(
				self.opportunity, link_type="Opportunity", activity_type="Tendering"
			)
		self.project_tender = tenders_of(activity.name)[0]

	def make_tender(self, **kwargs):
		values = {
			"doctype": "Tender",
			"project_tender": self.project_tender,
			"project_name": "_Test Tender " + frappe.generate_hash(length=6),
		}
		values.update(kwargs)
		return frappe.get_doc(values).insert()

	def complete(self, tender):
		tender.status = "Complete"
		tender.save()
		return tender

	def direct_cost_row(self, tender):
		return next(
			row
			for row in frappe.get_doc("Project Tender", self.project_tender).direct_cost_details
			if row.tender == tender.name
		)

	def test_submission_deadline_comes_from_the_opportunity(self):
		tender = self.make_tender()
		self.assertEqual(str(tender.submission_deadline), self.expected_closing)

	def test_a_deadline_given_at_creation_is_not_overwritten(self):
		chosen = add_days(nowdate(), 3)
		tender = self.make_tender(submission_deadline=chosen)
		self.assertEqual(str(tender.submission_deadline), chosen)

	def test_the_deadline_stays_editable(self):
		tender = self.make_tender()
		chosen = add_days(nowdate(), 7)
		tender.submission_deadline = chosen
		tender.save()
		self.assertEqual(
			str(frappe.db.get_value("Tender", tender.name, "submission_deadline")), chosen
		)

	def test_no_opportunity_behind_the_project_tender_leaves_it_empty(self):
		frappe.db.set_value("Project Tender", self.project_tender, OPPORTUNITY_FIELD, None)
		self.assertIsNone(self.make_tender().submission_deadline)

	def test_completion_date_is_set_when_the_tender_is_completed(self):
		tender = self.make_tender()
		self.assertIsNone(tender.get(COMPLETION_DATE))

		self.complete(tender)
		self.assertEqual(str(tender.get(COMPLETION_DATE)), nowdate())
		self.assertEqual(
			str(frappe.db.get_value("Tender", tender.name, COMPLETION_DATE)), nowdate()
		)

	def test_the_date_shows_on_the_project_tenders_table(self):
		tender = self.complete(self.make_tender())
		self.assertEqual(str(self.direct_cost_row(tender).get(COMPLETION_DATE)), nowdate())

	def test_an_unfinished_tender_has_no_date(self):
		tender = self.make_tender()
		self.assertIsNone(self.direct_cost_row(tender).get(COMPLETION_DATE))


class TestGoLiveCutoff(FrappeTestCase):
	"""Records that predate the app keep saving as they always did
	(custom_crm_updates/go_live.py)."""

	def setUp(self):
		self.cutoff = enforce_from()
		if not self.cutoff:
			self.skipTest("no go-live cutoff stamped on this site")

	def age(self, doctype, name, days=30):
		"""Push a record's creation back behind the cutoff, as a record that
		predates the app would be."""
		frappe.db.set_value(
			doctype, name, "creation", add_days(get_datetime(self.cutoff), -days), update_modified=False
		)

	def test_a_cutoff_is_stamped_on_migrate(self):
		self.assertTrue(self.cutoff)

	def test_it_is_never_moved_by_a_later_migrate(self):
		set_go_live()
		self.assertEqual(enforce_from(), self.cutoff)

	def test_a_new_record_is_covered(self):
		self.assertTrue(applies_to(make_lead()))

	def test_a_lead_from_before_the_cutoff_saves_without_the_fields(self):
		lead = make_lead()
		self.age("Lead", lead.name)
		frappe.db.set_value(
			"Lead", lead.name, {"custom_customer_group": None, "territory": None}, update_modified=False
		)

		lead = frappe.get_doc("Lead", lead.name)
		self.assertFalse(applies_to(lead))
		lead.company_name = "_Test Legacy Co"
		lead.save()  # the rule does not apply: no MandatoryError

	def test_a_lead_from_after_the_cutoff_still_needs_them(self):
		lead = make_lead()
		frappe.db.set_value(
			"Lead", lead.name, {"custom_customer_group": None, "territory": None}, update_modified=False
		)

		lead = frappe.get_doc("Lead", lead.name)
		with self.assertRaises(frappe.MandatoryError):
			lead.save()

	def test_an_opportunity_from_before_the_cutoff_saves_without_an_attachment(self):
		opportunity = make_opportunity_from(make_lead().name)
		self.age("Opportunity", opportunity.name)
		frappe.db.delete("Opportunity Attachment", {"parent": opportunity.name})

		opportunity = frappe.get_doc("Opportunity", opportunity.name)
		self.assertFalse(applies_to(opportunity))
		opportunity.save()  # the rule does not apply

	def test_an_opportunity_from_after_the_cutoff_still_needs_one(self):
		opportunity = make_opportunity_from(make_lead().name)
		frappe.db.delete("Opportunity Attachment", {"parent": opportunity.name})

		opportunity = frappe.get_doc("Opportunity", opportunity.name)
		with self.assertRaises(frappe.ValidationError):
			opportunity.save()

	def test_an_activity_can_be_logged_against_an_older_opportunity(self):
		# the exemption above would be worth nothing if the Opportunity
		# stayed unusable for the thing it exists for
		opportunity = make_opportunity_from(make_lead().name)
		self.age("Opportunity", opportunity.name)
		frappe.db.delete("Opportunity Attachment", {"parent": opportunity.name})

		activity = make_activity(opportunity.name, link_type="Opportunity")
		self.assertTrue(frappe.db.exists("Leads Activity", activity.name))

	def test_site_config_overrides_the_stamped_cutoff(self):
		with patch.dict(frappe.conf, {ENFORCE_FROM: "2099-01-01 00:00:00"}):
			self.assertEqual(enforce_from(), "2099-01-01 00:00:00")
			# everything that exists is older than that, so nothing is covered
			self.assertFalse(applies_to(frappe.get_doc("Lead", make_lead().name)))


class TestContractingBackport(FrappeTestCase):
	"""Create ▸ Tender and the three rules that go with it, carried here
	until the contracting app ships them
	(custom_crm_updates/overrides/contracting_backport.py).

	This bench runs contracting's own working tree, which already has all
	four, so the guards stand them down — which is exactly the first thing
	worth asserting. The rest patch the guard off to exercise the carried
	code as a site without them would run it."""

	def setUp(self):
		if not frappe.db.exists("DocType", "Project Tender"):
			self.skipTest("the contracting app is not installed")

		self.opportunity = make_opportunity_from(make_lead().name).name
		with customer_defaults():
			activity = make_activity(
				self.opportunity, link_type="Opportunity", activity_type="Tendering"
			)
		self.project_tender = tenders_of(activity.name)[0]

	def stand_alone(self):
		"""Pretend contracting does not provide these, i.e. a site on the
		released version of that app."""
		return patch.object(backport, "contracting_provides", lambda name: False)

	def rows(self):
		return frappe.get_doc("Project Tender", self.project_tender).direct_cost_details

	def make_tender_doc(self):
		return frappe.get_doc({
			"doctype": "Tender",
			"project_tender": self.project_tender,
			"project_name": "_Test Backport " + frappe.generate_hash(length=6),
		}).insert()

	def test_it_defers_to_contracting_where_that_app_has_it(self):
		for name in (
			"make_tender",
			"add_tender_to_direct_cost",
			"remove_cancelled_tender_rows",
			"validate_linked_tenders_complete",
		):
			self.assertTrue(backport.contracting_provides(name), name)

	def test_an_unknown_name_is_not_reported_as_provided(self):
		self.assertFalse(backport.contracting_provides("no_such_function_here"))

	def test_make_tender_links_the_new_tender_back(self):
		tender = backport.make_tender(self.project_tender)

		self.assertEqual(tender.doctype, "Tender")
		self.assertEqual(tender.project_tender, self.project_tender)
		# the series belongs to the Tender, not to the Project Tender
		self.assertNotEqual(tender.get("naming_series"), "PT-.YYYY.-")
		# each document works its own totals out from its own rows
		self.assertFalse(tender.get("total_direct_cost"))

	def test_the_tender_joins_the_direct_cost_table(self):
		tender = self.make_tender_doc()
		# contracting's own after_insert already did it on this bench
		self.assertIn(tender.name, [row.tender for row in self.rows()])

		# ours puts it back on a site where that code does not exist
		project_tender = frappe.get_doc("Project Tender", self.project_tender)
		project_tender.set(
			"direct_cost_details",
			[r for r in project_tender.direct_cost_details if r.tender != tender.name],
		)
		project_tender.flags.skip_cross_sync = True
		project_tender.save()
		self.assertNotIn(tender.name, [row.tender for row in self.rows()])

		with self.stand_alone():
			backport.add_tender_to_direct_cost(tender)
		self.assertIn(tender.name, [row.tender for row in self.rows()])

	def test_adding_it_twice_does_not_duplicate_the_row(self):
		tender = self.make_tender_doc()
		with self.stand_alone():
			backport.add_tender_to_direct_cost(tender)

		rows = [row.tender for row in self.rows()]
		self.assertEqual(rows.count(tender.name), 1)

	def test_submitted_is_refused_while_a_tender_is_unfinished(self):
		self.make_tender_doc()  # Draft, and now in the cost table

		project_tender = frappe.get_doc("Project Tender", self.project_tender)
		fill_cost_tables(project_tender)
		project_tender.status = "Submitted"

		with self.stand_alone(), self.assertRaises(frappe.ValidationError) as error:
			backport.validate_linked_tenders_complete(project_tender)
		self.assertIn("Complete", str(error.exception))

	def test_a_status_that_needs_no_complete_tender_passes(self):
		self.make_tender_doc()

		project_tender = frappe.get_doc("Project Tender", self.project_tender)
		project_tender.status = "Under Review"
		with self.stand_alone():
			backport.validate_linked_tenders_complete(project_tender)  # no throw
