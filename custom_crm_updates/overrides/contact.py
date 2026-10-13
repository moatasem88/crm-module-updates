"""Contacts table on Lead, Opportunity and Customer, in place of core's
contact_html.

A read-only table (Leads Contact Detail rows) whose rows depend on which
document is showing it:

- an Opportunity shows the contacts linked to the Opportunity itself, and only
  those, so a deal's contact list is not diluted by the Lead's (core's own
  contact list, hidden, does merge them in);
- a Customer likewise shows only its own, so a contact added to the client
  after the sale stays out of the deal it came from;
- a Lead shows its own contacts *and* those of every Opportunity made from it
  *and* those of the Customer it became, so the Lead stays the full picture of
  who is involved with that client.

ERPNext's own Lead -> Customer conversion links the Lead's contacts to the
Customer as well, so those are genuinely the Customer's too and appear on both.
On the Lead each contact is still listed once, under the first source that has
it, which for those is the Lead itself.

The "New Contact" button above each table links the contact to the document it
was pressed on (public/js/leads_activity_section.js), and the Opportunity's
Contact Person field lists its own contacts (public/js/opportunity.js).

Kept current two ways: the Lead/Opportunity/Customer recomputes it on its own
save (doc_events validate), and a Contact pushes it to every document it is or
was linked to (doc_events on Contact). Since every save recomputes it, a stale
open form can't leave wrong rows behind, so unlike the activities table this
one doesn't bump the parent's modified timestamp.
"""

import frappe
from frappe import _

from custom_crm_updates.mirror_table import rows_differ, set_mirror_rows

CONTACT_SECTION = "custom_contacts_section"
CONTACT_TABLE = "custom_contacts"
CONTACT_ROW_FIELDS = (
	"contact",
	"full_name",
	"email_id",
	"mobile_no",
	"phone",
	"designation",
	"is_primary_contact",
	"linked_via",
)
TABLE_DOCTYPES = ("Lead", "Opportunity", "Customer")
# Everything a Lead rolls up, and what each one of them is made from a Lead by.
ROLLED_UP = ("Opportunity", "Customer")


def contact_table_fields(insert_after):
	return [
		{
			"fieldname": CONTACT_SECTION,
			"fieldtype": "Section Break",
			"label": "Contacts",
			"insert_after": insert_after,
		},
		{
			"fieldname": CONTACT_TABLE,
			"fieldtype": "Table",
			# the section heading already names the table
			"label": "",
			"options": "Leads Contact Detail",
			"insert_after": CONTACT_SECTION,
			"read_only": 1,
			"no_copy": 1,
		},
	]


def contact_sources(doctype, name, exclude_source=None):
	"""The documents whose contacts this table lists. An Opportunity and a
	Customer list their own; a Lead lists its own first, then those of each
	Opportunity made from it (oldest first), then those of the Customer it
	became.

	A Customer counts as the Lead's whether it was made from the Lead itself
	(From Lead) or from one of its Opportunities (From Opportunity), which is
	the other way ERPNext records the same conversion.

	exclude_source: a (DocType, name) being deleted. It is still in the
	database while on_trash runs, so it has to be left out by hand."""
	sources = [(doctype, name)]
	if doctype != "Lead":
		return sources

	opportunities = frappe.get_all(
		"Opportunity",
		filters={"opportunity_from": "Lead", "party_name": name},
		pluck="name",
		order_by="creation asc",
	)
	customers = frappe.get_all(
		"Customer", filters={"lead_name": name}, pluck="name", order_by="creation asc"
	)
	if opportunities:
		customers += frappe.get_all(
			"Customer",
			filters={"opportunity_name": ["in", opportunities]},
			pluck="name",
			order_by="creation asc",
		)

	sources += [("Opportunity", opportunity) for opportunity in opportunities]
	# dict.fromkeys: a Customer made from the Lead *and* from its Opportunity
	# is one source, listed where it was first found
	sources += [("Customer", customer) for customer in dict.fromkeys(customers)]
	return [source for source in sources if source != exclude_source]


def get_contact_rows(doctype, name, exclude=None, exclude_source=None):
	"""Ascending by creation within each source, so the oldest contact is at
	the top and a new one is appended at the bottom of its group. The primary
	contact is flagged by its own column rather than by being sorted first, so
	the order is the same in every CRM table. A contact linked to both a Lead
	and one of its Opportunities is listed once, under the first source that
	has it."""
	rows, seen = [], {exclude}
	for link_doctype, link_name in contact_sources(doctype, name, exclude_source):
		contacts = frappe.get_all(
			"Contact",
			filters=[
				["Dynamic Link", "link_doctype", "=", link_doctype],
				["Dynamic Link", "link_name", "=", link_name],
			],
			fields=[
				"name",
				"first_name",
				"last_name",
				"email_id",
				"mobile_no",
				"phone",
				"designation",
				"is_primary_contact",
			],
			# qualified: the Dynamic Link join has its own creation column
			order_by="`tabContact`.creation asc",
		)
		for c in contacts:
			if c.name in seen:
				continue
			seen.add(c.name)
			rows.append(
				{
					"contact": c.name,
					"full_name": " ".join(filter(None, (c.first_name, c.last_name))),
					"email_id": c.email_id,
					"mobile_no": c.mobile_no,
					"phone": c.phone,
					"designation": c.designation,
					"is_primary_contact": c.is_primary_contact,
					"linked_via": f"{_(link_doctype)} {link_name}",
				}
			)
	return rows


def sync_contact_table(doctype, name, exclude=None, exclude_source=None):
	if not frappe.db.exists(doctype, name):
		return

	rows = get_contact_rows(doctype, name, exclude, exclude_source)
	set_mirror_rows(doctype, name, CONTACT_TABLE, rows, CONTACT_ROW_FIELDS, bump_modified=False)


def refresh_own_table(doc, method=None):
	"""doc_events validate (Lead, Opportunity, Customer): recompute in the save
	itself."""
	rows = get_contact_rows(doc.doctype, doc.name)
	if rows_differ(doc.get(CONTACT_TABLE), rows, CONTACT_ROW_FIELDS):
		doc.set(CONTACT_TABLE, rows)


def refresh_after_insert(doc, method=None):
	"""doc_events after_insert (Lead): Lead.after_insert links the contact
	created in before_insert, after validate has already run; update the
	in-memory doc too so the form opens with it."""
	refresh_own_table(doc)
	doc.update_child_table(CONTACT_TABLE)


def contact_links(contact):
	if not contact:
		return set()
	return {(link.link_doctype, link.link_name) for link in contact.links if link.link_name}


def lead_of(doctype, name):
	"""The Lead an Opportunity or a Customer was made from, read from the
	database, if it was made from one."""
	if doctype == "Customer":
		lead, opportunity = frappe.db.get_value(
			"Customer", name, ["lead_name", "opportunity_name"]
		) or (None, None)
		return lead or (opportunity and lead_of("Opportunity", opportunity))

	party = frappe.db.get_value("Opportunity", name, ["opportunity_from", "party_name"])
	if party and party[0] == "Lead":
		return party[1]


def lead_in(doc):
	"""The Lead an Opportunity or a Customer names, read from the document
	rather than the database: also right for the version before a save, and for
	one being deleted."""
	if doc.doctype == "Customer":
		return doc.lead_name or (doc.opportunity_name and lead_of("Opportunity", doc.opportunity_name))

	if doc.opportunity_from == "Lead":
		return doc.party_name


def affected_docs(links):
	"""The documents whose table a contact change affects: the Leads,
	Opportunities and Customers it is linked to, plus the Lead behind each of
	those, which rolls their contacts up."""
	docs = set()
	for link_doctype, link_name in links:
		if link_doctype not in TABLE_DOCTYPES:
			continue
		docs.add((link_doctype, link_name))

		if link_doctype in ROLLED_UP:
			lead = lead_of(link_doctype, link_name)
			if lead:
				docs.add(("Lead", lead))
	return docs


def refresh_party_lead(doc, method=None):
	"""doc_events Opportunity / Customer on_update, on_trash: a Lead rolls up
	the contacts of its Opportunities and of the Customer it became, so it has
	to follow one being created, re-pointed at another Lead, or deleted. Both
	Leads are refreshed when it is re-pointed: the one it left and the one it
	joined."""
	leads = {lead_in(doc)}
	before = doc.get_doc_before_save()
	if before:
		leads.add(lead_in(before))

	for lead in leads - {None}:
		sync_contact_table(
			"Lead",
			lead,
			exclude_source=(doc.doctype, doc.name) if method == "on_trash" else None,
		)


def on_contact_update(doc, method=None):
	"""doc_events Contact on_update: current links and any just removed."""
	for doctype, name in affected_docs(contact_links(doc) | contact_links(doc.get_doc_before_save())):
		sync_contact_table(doctype, name)


def on_contact_trash(doc, method=None):
	# Runs before delete_doc's link check, so our rows can't block the delete.
	for doctype, name in affected_docs(contact_links(doc)):
		sync_contact_table(doctype, name, exclude=doc.name)


def backfill_contact_tables():
	"""after_migrate: fill the tables for contacts that predate them."""
	links = frappe.get_all(
		"Dynamic Link",
		filters={"parenttype": "Contact", "link_doctype": ["in", TABLE_DOCTYPES]},
		fields=["link_doctype", "link_name"],
		distinct=True,
	)
	docs = affected_docs({(link.link_doctype, link.link_name) for link in links})
	# Also everything that already has rows, so the party contacts the
	# Opportunities mirrored before the two were separated are dropped - those
	# Opportunities have no contact link of their own to be found above.
	docs |= {
		(row.parenttype, row.parent)
		for row in frappe.get_all(
			"Leads Contact Detail",
			filters={"parenttype": ["in", TABLE_DOCTYPES], "parentfield": CONTACT_TABLE},
			fields=["parenttype", "parent"],
			distinct=True,
		)
	}
	for doctype, name in docs:
		sync_contact_table(doctype, name)
