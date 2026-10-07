"""Read-only "mirror" tables: child tables on a form (Lead, Opportunity) whose
rows are a copy of records that live elsewhere (Leads Activity, Project
Tender, Contact) and are rebuilt whenever those records change."""

import frappe
from frappe.utils import now


def rows_differ(existing, rows, fields):
	"""Compare as strings so a date loaded from the DB equals one from a query."""

	def normalize(row):
		return [None if row.get(f) is None else str(row.get(f)) for f in fields]

	return [normalize(r) for r in existing] != [normalize(r) for r in rows]


def set_mirror_rows(doctype, name, fieldname, rows, fields, bump_modified=True):
	"""Write `rows` into `name`'s `fieldname` table directly, without a full
	save (no validations or hooks of the parent run). No-op when unchanged.

	bump_modified: makes a stale open form refuse to save (and so overwrite
	these rows) and reloads it instead. Tables that the parent recomputes on
	its own save don't need it."""
	doc = frappe.get_doc(doctype, name)
	if not rows_differ(doc.get(fieldname), rows, fields):
		return False

	doc.set(fieldname, rows)
	doc.update_child_table(fieldname)
	if bump_modified:
		doc.db_set("modified", now(), update_modified=False, notify=True)
	return True
