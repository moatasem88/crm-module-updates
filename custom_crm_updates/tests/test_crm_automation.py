# Copyright (c) 2026, smart and contributors
# For license information, please see license.txt

"""Tendering -> Project Tender, Lead -> Customer conversion and the Contacts
table (custom_crm_updates/overrides/{project_tender,lead,contact}.py)."""

import frappe
from frappe.tests.utils import FrappeTestCase

from custom_crm_updates.overrides.contact import CONTACT_TABLE
from custom_crm_updates.overrides.project_tender import TENDER_TABLE
from custom_crm_updates.custom_crm_updates.doctype.leads_activity.test_leads_activity import (
	customer_defaults,
	make_activity,
	make_lead,
	make_opportunity_from,
)

# Records are created by the tests and rolled back by FrappeTestCase.
test_ignore = ["Lead", "Prospect", "Opportunity", "User", "Customer", "Contact", "Project Tender"]


def customer_of(lead):
	return frappe.db.get_value("Customer", {"lead_name": lead})


def tenders_of(activity):
	return frappe.get_all("Project Tender", {"custom_leads_activity": activity}, pluck="name")


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

	def test_submitted_tender_marks_activity_done_and_opportunity_won(self):
		activity = self.tendering()
		other = self.tendering()
		tender = frappe.get_doc("Project Tender", tenders_of(activity.name)[0])

		tender.status = "Submitted"
		tender.save()
		self.assertEqual(frappe.db.get_value("Leads Activity", activity.name, "status"), "Done")
		self.assertEqual(frappe.db.get_value("Leads Activity", other.name, "status"), "Planned")
		self.assertEqual(frappe.db.get_value("Opportunity", self.opportunity.name, "status"), "Won")

		# the Opportunity's activities table followed the activity
		rows = frappe.get_doc("Opportunity", self.opportunity.name).custom_leads_activities
		self.assertEqual({r.activity: r.status for r in rows}[activity.name], "Done")

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
			}
		).insert()

		activity = make_activity(opportunity.name, link_type="Opportunity", activity_type="Tendering")
		self.assertEqual(frappe.db.get_value("Project Tender", tenders_of(activity.name)[0], "client"), customer.name)


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

	def test_opportunity_lists_own_and_party_contacts(self):
		lead_contact = self.make_contact(("Lead", self.lead))
		opportunity = make_opportunity_from(self.lead).name
		own_contact = self.make_contact(("Opportunity", opportunity))

		rows = {r.contact: r.linked_via for r in self.rows("Opportunity", opportunity)}
		self.assertEqual(rows[lead_contact.name], f"Lead {self.lead}")
		self.assertEqual(rows[own_contact.name], f"Opportunity {opportunity}")
		# and the Lead doesn't get the Opportunity's own contact
		self.assertNotIn(own_contact.name, [r.contact for r in self.rows("Lead", self.lead)])

	def test_party_contact_added_later_reaches_opportunity(self):
		opportunity = make_opportunity_from(self.lead).name
		contact = self.make_contact(("Lead", self.lead))
		self.assertIn(contact.name, [r.contact for r in self.rows("Opportunity", opportunity)])

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
			["custom_project_tender_tab", TENDER_TABLE],
		)
