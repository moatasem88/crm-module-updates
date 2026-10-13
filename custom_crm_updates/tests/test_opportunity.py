# Copyright (c) 2026, smart and contributors
# For license information, please see license.txt

"""The Opportunity's own fields: Opportunity Name as its title, the Attachments
table it cannot be saved without (and without which no activity can be logged
against it), the Opportunity Breakdown rows, and where the moved Opportunity
Value section sits (custom_crm_updates/overrides/opportunity.py)."""

import frappe
from frappe.desk.notifications import get_open_count
from frappe.tests.utils import FrappeTestCase

from custom_crm_updates.overrides.opportunity import (
	ATTACHMENTS_FIELD,
	ATTACHMENTS_SECTION,
	BREAKDOWN_SECTION,
	CONTRIBUTIONS_FIELD,
	DESCRIPTION_FIELD,
	NAME_FIELD,
	ORGANIZATION_LAST_FIELD,
	ORGANIZATION_SECTION,
	PARTY_FIELDS,
	TARGETED_AMOUNT,
	VALUE_SECTION,
	backfill_party_links,
)
from custom_crm_updates.custom_crm_updates.doctype.leads_activity.test_leads_activity import (
	make_activity,
	make_lead,
)

# Records are created by the tests and rolled back by FrappeTestCase.
test_ignore = ["Lead", "Prospect", "Opportunity", "User", "Customer", "Contact"]


def opportunity_values(**kwargs):
	values = {
		"doctype": "Opportunity",
		"opportunity_from": "Lead",
		"party_name": make_lead().name,
		"company": frappe.db.get_value("Company", {}, "name"),
	}
	values.update(kwargs)
	return values


def make_opportunity(**kwargs):
	"""An Opportunity with the one attachment it cannot be saved without
	(validate_attachments)."""
	values = opportunity_values(**kwargs)
	values.setdefault(ATTACHMENTS_FIELD, [{"attachment": "/files/_test_opportunity.pdf"}])
	return frappe.get_doc(values).insert()


def make_customer(**kwargs):
	values = {
		"doctype": "Customer",
		"customer_name": "_Test Opportunity Customer " + frappe.generate_hash(length=6),
		"customer_group": frappe.get_all("Customer Group", {"is_group": 0}, pluck="name", limit=1)[0],
		"territory": frappe.get_all("Territory", {"is_group": 0}, pluck="name", limit=1)[0],
	}
	values.update(kwargs)
	return frappe.get_doc(values).insert().name


def make_opportunity_without_attachments():
	"""An Opportunity with an empty Attachments table: one saved before the
	rule existed, or one ERPNext created by itself. Both reach the database by
	skipping mandatory fields, which is what validate_attachments allows."""
	opportunity = frappe.get_doc(opportunity_values())
	opportunity.flags.ignore_mandatory = True
	return opportunity.insert()


class TestOpportunityTitle(FrappeTestCase):
	"""The Opportunity Name is the Opportunity's title (set_title)."""

	def test_name_becomes_the_title(self):
		opportunity = make_opportunity(**{NAME_FIELD: "Riyadh Tower Fit-out"})
		self.assertEqual(opportunity.title, "Riyadh Tower Fit-out")

	def test_title_follows_a_renamed_opportunity(self):
		opportunity = make_opportunity(**{NAME_FIELD: "First name"})
		opportunity.set(NAME_FIELD, "Second name")
		opportunity.save()
		self.assertEqual(frappe.db.get_value("Opportunity", opportunity.name, "title"), "Second name")

	def test_opportunity_without_a_name_keeps_the_core_title(self):
		# core's own fallback is the party's name
		opportunity = make_opportunity()
		self.assertEqual(opportunity.title, opportunity.customer_name)


class TestOpportunityAttachments(FrappeTestCase):
	"""An Opportunity is only saved with its paperwork on file
	(validate_attachments)."""

	def test_without_attachments_is_refused(self):
		with self.assertRaises(frappe.ValidationError) as error:
			make_opportunity(**{ATTACHMENTS_FIELD: []})

		message = str(error.exception)
		# Arabic message; field and DocType names stay as they are in the system
		self.assertIn("مرفقات", message)
		self.assertIn("Opportunity", message)
		self.assertIn("Attachments", message)

	def test_with_an_attachment_saves(self):
		opportunity = make_opportunity(
			**{
				ATTACHMENTS_FIELD: [
					{"attachment": "/files/enquiry.pdf", "description": "Enquiry"},
					{"attachment": "/files/drawings.pdf"},
				]
			}
		)
		self.assertEqual(len(opportunity.get(ATTACHMENTS_FIELD)), 2)

	def test_row_without_a_file_does_not_count(self):
		# an empty row the user added and never filled: our own message, not
		# Frappe's "mandatory field in row 1"
		with self.assertRaises(frappe.ValidationError) as error:
			make_opportunity(**{ATTACHMENTS_FIELD: [{"description": "x"}]})
		self.assertIn("مرفقات", str(error.exception))

	def test_emptying_the_table_is_refused(self):
		opportunity = make_opportunity()
		opportunity.set(ATTACHMENTS_FIELD, [])
		with self.assertRaises(frappe.ValidationError):
			opportunity.save()

	def test_erpnext_can_still_create_one_by_itself(self):
		# an Opportunity from an incoming email has nothing to attach
		self.assertTrue(make_opportunity_without_attachments().name)


class TestOpportunityBreakdown(FrappeTestCase):
	"""Each row's Final Value is worked out from the Targeted Amount
	(calculate_contributions)."""

	def rows(self, *contributions, targeted_amount=20000):
		opportunity = make_opportunity(
			**{TARGETED_AMOUNT: targeted_amount, CONTRIBUTIONS_FIELD: list(contributions)}
		)
		return opportunity.get(CONTRIBUTIONS_FIELD)

	def test_percentage_is_a_share_of_the_targeted_amount(self):
		(row,) = self.rows({"type": "civil", "contribution_type": "Percentage", "contribution_value": 20})
		self.assertEqual(row.final_value, 4000)

	def test_fixed_amount_is_the_value_itself(self):
		(row,) = self.rows({"type": "mec", "contribution_type": "Fixed Amount", "contribution_value": 7500})
		self.assertEqual(row.final_value, 7500)

	def test_every_row_is_worked_out_on_its_own(self):
		rows = self.rows(
			{"type": "civil", "contribution_type": "Percentage", "contribution_value": 20},
			{"type": "elec", "contribution_type": "Percentage", "contribution_value": 5.5},
			{"type": "elev", "contribution_type": "Fixed Amount", "contribution_value": 1200},
		)
		self.assertEqual([row.final_value for row in rows], [4000, 1100, 1200])

	def test_a_sent_final_value_is_overwritten(self):
		# read-only on the form, so whatever reaches the server is recomputed
		(row,) = self.rows(
			{
				"type": "elec",
				"contribution_type": "Percentage",
				"contribution_value": 10,
				"final_value": 999999,
			}
		)
		self.assertEqual(row.final_value, 2000)

	def test_changing_the_targeted_amount_recalculates_every_row(self):
		opportunity = make_opportunity(
			**{
				TARGETED_AMOUNT: 20000,
				CONTRIBUTIONS_FIELD: [
					{"type": "civil", "contribution_type": "Percentage", "contribution_value": 20},
					{"type": "mec", "contribution_type": "Fixed Amount", "contribution_value": 1000},
				],
			}
		)
		opportunity.set(TARGETED_AMOUNT, 50000)
		opportunity.save()

		rows = frappe.get_doc("Opportunity", opportunity.name).get(CONTRIBUTIONS_FIELD)
		# the percentage row follows the new amount, the fixed one does not
		self.assertEqual([row.final_value for row in rows], [10000, 1000])

	def test_percentage_without_a_targeted_amount_is_nothing(self):
		(row,) = self.rows(
			{"type": "civil", "contribution_type": "Percentage", "contribution_value": 20},
			targeted_amount=0,
		)
		self.assertEqual(row.final_value, 0)


class TestActivityNeedsSourceAttachment(FrappeTestCase):
	"""No activity on an Opportunity whose Attachments table is empty
	(validate_activity_source)."""

	def test_activity_on_an_opportunity_with_an_attachment_is_allowed(self):
		opportunity = make_opportunity()
		self.assertTrue(make_activity(opportunity.name, link_type="Opportunity").name)

	def test_activity_on_an_opportunity_without_attachments_is_refused(self):
		opportunity = make_opportunity_without_attachments()

		with self.assertRaises(frappe.ValidationError) as error:
			make_activity(opportunity.name, link_type="Opportunity")

		message = str(error.exception)
		self.assertIn("مرفقات", message)
		self.assertIn("Opportunity", message)
		# nothing was saved
		self.assertFalse(frappe.get_all("Leads Activity", {"link_name": opportunity.name}))

	def test_a_lead_needs_none(self):
		# a Lead has no attachments table of its own
		self.assertTrue(make_activity(make_lead().name).name)


class TestOpportunityLayout(FrappeTestCase):
	def order(self):
		return [df.fieldname for df in frappe.get_meta("Opportunity").fields]

	def test_name_and_description_come_first(self):
		self.assertEqual(self.order()[:3], ["naming_series", NAME_FIELD, DESCRIPTION_FIELD])

	def test_value_section_sits_directly_above_organization(self):
		order = self.order()
		# the whole block moved, Targeted Amount with it, and nothing else
		# came between it and Organization
		self.assertEqual(
			order[order.index(VALUE_SECTION) : order.index(ORGANIZATION_SECTION)],
			[
				VALUE_SECTION,
				"currency",
				"column_break_36",
				"conversion_rate",
				"column_break_17",
				"opportunity_amount",
				"base_opportunity_amount",
				TARGETED_AMOUNT,
			],
		)
		self.assertLess(order.index("probability"), order.index(VALUE_SECTION))

	def test_breakdown_and_attachments_follow_organization(self):
		order = self.order()
		self.assertEqual(
			order[order.index(ORGANIZATION_LAST_FIELD) + 1 :][:4],
			[BREAKDOWN_SECTION, CONTRIBUTIONS_FIELD, ATTACHMENTS_SECTION, ATTACHMENTS_FIELD],
		)

	def test_the_tables_hold_their_own_child_doctypes(self):
		meta = frappe.get_meta("Opportunity")
		self.assertEqual(meta.get_field(ATTACHMENTS_FIELD).options, "Opportunity Attachment")
		self.assertEqual(meta.get_field(CONTRIBUTIONS_FIELD).options, "Opportunity Contribution")

	def test_final_value_is_read_only_and_in_the_opportunity_currency(self):
		field = frappe.get_meta("Opportunity Contribution").get_field("final_value")
		self.assertTrue(field.read_only)
		self.assertEqual(field.options, "currency")


class TestOpportunityConnections(FrappeTestCase):
	"""The Connections tab shows the client this Opportunity belongs to,
	whichever type it is (set_party_links, get_dashboard_data)."""

	def mirrors(self, opportunity):
		return {
			party_type: opportunity.get(fieldname) for party_type, fieldname in PARTY_FIELDS.items()
		}

	def test_a_lead_opportunity_mirrors_its_lead(self):
		lead = make_lead().name
		opportunity = make_opportunity(party_name=lead)
		self.assertEqual(self.mirrors(opportunity), {"Lead": lead, "Customer": None, "Prospect": None})

	def test_a_customer_opportunity_mirrors_its_customer(self):
		customer = make_customer()
		opportunity = make_opportunity(opportunity_from="Customer", party_name=customer)
		self.assertEqual(
			self.mirrors(opportunity), {"Lead": None, "Customer": customer, "Prospect": None}
		)

	def test_repointing_moves_the_mirror(self):
		opportunity = make_opportunity()
		customer = make_customer()

		opportunity.opportunity_from = "Customer"
		opportunity.party_name = customer
		opportunity.save()
		# the Lead mirror is cleared, so only one card is ever filled
		self.assertEqual(
			self.mirrors(opportunity), {"Lead": None, "Customer": customer, "Prospect": None}
		)

	def test_the_dashboard_points_at_the_mirrors(self):
		data = frappe.get_meta("Opportunity").get_dashboard_data()

		for party_type, fieldname in PARTY_FIELDS.items():
			self.assertEqual(data["internal_links"][party_type], fieldname)
		# fallback for Customers converted *from* this Opportunity
		self.assertEqual(data["non_standard_fieldnames"]["Customer"], "opportunity_name")

		listed = [item for group in data["transactions"] for item in group["items"]]
		for party_type in PARTY_FIELDS:
			self.assertIn(party_type, listed)

	def test_connections_report_the_lead(self):
		# end to end, through the API the Connections tab itself calls
		lead = make_lead().name
		opportunity = make_opportunity(party_name=lead)

		count = get_open_count("Opportunity", opportunity.name)["count"]
		lead_card = next(c for c in count["internal_links_found"] if c["doctype"] == "Lead")
		self.assertEqual(lead_card["names"], [lead])

	def test_connections_report_a_customer_converted_from_the_opportunity(self):
		# no Customer mirror (the party is a Lead), so Frappe falls back to
		# Customers pointing back here through opportunity_name
		opportunity = make_opportunity()
		customer = make_customer(opportunity_name=opportunity.name)

		count = get_open_count("Opportunity", opportunity.name)["count"]
		customer_card = next(c for c in count["external_links_found"] if c["doctype"] == "Customer")
		self.assertEqual(customer_card["count"], 1)
		self.assertTrue(frappe.db.exists("Customer", customer))

	def test_backfill_fills_an_opportunity_that_predates_the_fields(self):
		lead = make_lead().name
		opportunity = make_opportunity(party_name=lead)
		frappe.db.set_value("Opportunity", opportunity.name, PARTY_FIELDS["Lead"], None)

		backfill_party_links()
		self.assertEqual(
			frappe.db.get_value("Opportunity", opportunity.name, PARTY_FIELDS["Lead"]), lead
		)

		# idempotent, and it never touches the timestamp
		modified = frappe.db.get_value("Opportunity", opportunity.name, "modified")
		backfill_party_links()
		self.assertEqual(frappe.db.get_value("Opportunity", opportunity.name, "modified"), modified)
