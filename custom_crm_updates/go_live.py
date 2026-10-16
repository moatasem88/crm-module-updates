"""When this app's rules start applying on a site.

Two rules refuse to save a record that is missing something: a Lead without
Customer Group and Territory (overrides/lead.py) and an Opportunity with no
attachment (overrides/opportunity.py). Both are right for records created
from now on, and wrong for the ones already in the database when the app is
installed — a site going live with years of Leads behind it would find every
one of them unsaveable until somebody filled in a field that did not exist
when the record was created.

So both rules, and the activity rule that follows from the second one, apply
only to records created on or after the moment this app was first set up on
the site. The cutoff is stamped once, by the first migrate that runs the
after_migrate list (hooks.py), and never moved afterwards: re-running migrate
keeps the original moment.

A site can name its own cutoff in site_config.json, which is how you set a
cutover that is not the install date — set it before the first migrate:

    "custom_crm_enforce_from": "2026-11-01 00:00:00"

Records created before the cutoff stay exactly as saveable as they were
before the app arrived. Nothing is hidden from them: the new fields and
tables are on their forms, and filling them in is what moves a record onto
the new rules the next time it is saved.
"""

import frappe
from frappe.utils import get_datetime, now

ENFORCE_FROM = "custom_crm_enforce_from"


def set_go_live():
	"""after_migrate, ahead of everything else: stamp the cutoff the first
	time this app is set up on a site.

	Never overwrites. A site that already has a cutoff — stamped by an
	earlier migrate, or named in site_config — keeps it, so a later migrate
	cannot quietly make every record created since go-live exempt."""
	if frappe.conf.get(ENFORCE_FROM) or frappe.db.get_default(ENFORCE_FROM):
		return

	frappe.db.set_default(ENFORCE_FROM, now())


def enforce_from():
	"""This site's cutoff, or None if one was never stamped. site_config
	wins, so a cutover date can be set without touching the database."""
	return frappe.conf.get(ENFORCE_FROM) or frappe.db.get_default(ENFORCE_FROM)


def applies_to(doc):
	"""True if this app's mandatory rules apply to `doc`.

	They apply to everything created from the cutoff onwards, and to every
	new record. A record older than the cutoff predates the rule, and is
	left as saveable as it was before the app was installed.

	With no cutoff stamped at all — app code present on a site whose first
	migrate has not run yet — the rules apply, which is how this behaved
	before the cutoff existed."""
	if doc.is_new() or not doc.get("creation"):
		return True

	cutoff = enforce_from()
	if not cutoff:
		return True

	return get_datetime(doc.creation) >= get_datetime(cutoff)


def applies_to_record(doctype, name):
	"""The same question about a record we only have the name of.

	Used by the Leads Activity rule, where the record that must have the
	paperwork is the Opportunity being linked to, not the activity being
	saved — a new activity logged against a years-old Opportunity is the
	exact case the cutoff exists for."""
	cutoff = enforce_from()
	if not cutoff:
		return True

	creation = frappe.db.get_value(doctype, name, "creation")
	if not creation:
		return True

	return get_datetime(creation) >= get_datetime(cutoff)
