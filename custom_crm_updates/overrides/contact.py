"""Contacts table on Lead and Opportunity, in place of core's contact_html.

A read-only table (Leads Contact Detail rows) of the same contacts core's
contact list shows:
- Lead: contacts linked to the Lead;
- Opportunity: contacts linked to the Opportunity, plus those of its party
  (the Lead / Customer / Prospect it is for).

Kept current two ways: the Lead/Opportunity recomputes it on its own save
(doc_events validate), and a Contact pushes it to every document it is or was
linked to (doc_events on Contact). Since every save recomputes it, a stale
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
TABLE_DOCTYPES = ("Lead", "Opportunity")
# What an Opportunity can be for (Opportunity.opportunity_from).
PARTY_DOCTYPES = ("Lead", "Customer", "Prospect")


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


def get_contact_rows(doctype, name, party=None, exclude=None):
	"""party: (opportunity_from, party_name) of an Opportunity."""
	sources = [(doctype, name)]
	if party and all(party):
		sources.append(tuple(party))

	rows, seen = [], {exclude}
	for link_doctype, link_name in sources:
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
			order_by="`tabContact`.is_primary_contact desc, `tabContact`.creation asc",
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


def party_of(doc):
	if doc.doctype == "Opportunity":
		return (doc.opportunity_from, doc.party_name)


def sync_contact_table(doctype, name, exclude=None):
	if not frappe.db.exists(doctype, name):
		return

	party = None
	if doctype == "Opportunity":
		party = frappe.db.get_value("Opportunity", name, ["opportunity_from", "party_name"])
	rows = get_contact_rows(doctype, name, party, exclude)
	set_mirror_rows(doctype, name, CONTACT_TABLE, rows, CONTACT_ROW_FIELDS, bump_modified=False)


def refresh_own_table(doc, method=None):
	"""doc_events validate (Lead, Opportunity): recompute in the save itself."""
	rows = get_contact_rows(doc.doctype, doc.name, party_of(doc))
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


def affected_docs(links):
	docs = set()
	for link_doctype, link_name in links:
		if link_doctype in TABLE_DOCTYPES:
			docs.add((link_doctype, link_name))
		if link_doctype in PARTY_DOCTYPES:
			for opportunity in frappe.get_all(
				"Opportunity",
				filters={"opportunity_from": link_doctype, "party_name": link_name},
				pluck="name",
			):
				docs.add(("Opportunity", opportunity))
	return docs


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
		filters={"parenttype": "Contact", "link_doctype": ["in", TABLE_DOCTYPES + PARTY_DOCTYPES]},
		fields=["link_doctype", "link_name"],
		distinct=True,
	)
	for doctype, name in affected_docs({(link.link_doctype, link.link_name) for link in links}):
		sync_contact_table(doctype, name)
