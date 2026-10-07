"""Assemble the offline code guide: python3 build.py <output.html>"""

import re
import sys

import lib
from part_a import ARCH, PRIMER, steps_a
from part_b import steps_b

# Every function, with when it runs and what it does. Checked against the
# source below, so a function added later without a line here fails the build.
REF = [
	("overrides/lead.py", "apply_lead_customizations", "after_migrate", "Creates Lead custom fields and property setters, then applies the field order."),
	("overrides/lead.py", "apply_field_order", "called by the above", "Rebuilds the Lead's field_order: Organization up, Address & Contacts into its tab, Contacts last."),
	("overrides/lead.py", "move_section", "called by the above", "Moves one section block (optionally behind a header field) before a target field."),
	("overrides/lead.py", "get_dashboard_data", "Lead Connections tab", "Adds Leads Activity to the Lead's Connections."),
	("overrides/lead.py", "convert_lead_to_customer", "Registration Done; Tendering", "Returns the Lead's Customer, creating it from the Lead if needed."),
	("overrides/lead.py", "insert_customer", "called by conversions", "Saves a mapped Customer, or explains which of Customer Group / Territory is missing."),
	("overrides/lead.py", "validate_customer_fields", "Lead validate", "Requires Customer Group and Territory when a person saves a Lead."),
	("overrides/lead.py", "clear_person_fields", "Lead before_validate", "Empties person fields of a company Lead and sets Full Name to the company name."),
	("overrides/opportunity.py", "apply_opportunity_customizations", "after_migrate", "Creates Opportunity custom fields, adds Tendering/Won, hides contact_html."),
	("overrides/opportunity.py", "get_dashboard_data", "Opportunity Connections tab", "Adds Leads Activity to the Opportunity's Connections."),
	("overrides/project_tender.py", "apply_project_tender_customizations", "after_migrate", "Adds the Opportunity and Leads Activity links to Project Tender (if contracting is installed)."),
	("overrides/project_tender.py", "create_project_tender_for_activity", "Tendering activity saved", "Creates the activity's Project Tender (once) and sets the Opportunity to Tendering."),
	("overrides/project_tender.py", "get_opportunity_customer", "called by the above", "Finds or creates the Customer for the tender's Client."),
	("overrides/project_tender.py", "convert_prospect_to_customer", "called by the above", "Reuses or creates the Customer for a Prospect."),
	("overrides/project_tender.py", "on_update", "Project Tender saved", "Refreshes the Opportunity's tender table; Submitted → activity Done, Opportunity Won."),
	("overrides/project_tender.py", "on_trash", "Project Tender deleted", "Removes the tender's row from its Opportunity first."),
	("overrides/project_tender.py", "mark_activity_done", "tender Submitted", "Sets the creating activity to Done with a full save."),
	("overrides/project_tender.py", "mark_opportunity_won", "tender Submitted", "Sets the Opportunity to Won and comments on its timeline."),
	("overrides/project_tender.py", "sync_opportunity_tenders", "tender saved / deleted", "Rebuilds the Opportunity's Project Tender table."),
	("overrides/project_tender.py", "backfill_opportunity_tenders", "after_migrate", "Fills the tender tables for existing tenders."),
	("overrides/contact.py", "contact_table_fields", "setup", "Returns the Contacts section and table custom fields."),
	("overrides/contact.py", "get_contact_rows", "called by syncs", "Builds the contact rows for a record (plus its party for an Opportunity)."),
	("overrides/contact.py", "party_of", "called by the above", "The (DocType, name) an Opportunity is for."),
	("overrides/contact.py", "sync_contact_table", "contact saved / deleted", "Rebuilds one record's Contacts table in the database."),
	("overrides/contact.py", "refresh_own_table", "Lead / Opportunity validate", "Recomputes the Contacts table on the record being saved."),
	("overrides/contact.py", "refresh_after_insert", "Lead after_insert", "Adds the auto-created contact of a new Lead to its table."),
	("overrides/contact.py", "contact_links", "called by contact events", "The (DocType, name) pairs a Contact links to."),
	("overrides/contact.py", "affected_docs", "called by contact events", "Leads/Opportunities whose table a contact change affects."),
	("overrides/contact.py", "on_contact_update", "Contact saved", "Refreshes every table the contact is or was in."),
	("overrides/contact.py", "on_contact_trash", "Contact deleted", "Removes the contact's rows first."),
	("overrides/contact.py", "backfill_contact_tables", "after_migrate", "Fills the Contacts tables for existing contacts."),
	("mirror_table.py", "rows_differ", "called by set_mirror_rows", "True if the new rows differ from the stored ones."),
	("mirror_table.py", "set_mirror_rows", "every table sync", "Writes a read-only table's rows directly; optionally bumps modified and reloads open forms."),
	("custom_crm_updates/doctype/leads_activity/leads_activity.py", "LeadsActivity.on_update", "activity saved", "Syncs tables; Tendering → tender; qualification rules; Registration Done → Customer."),
	("custom_crm_updates/doctype/leads_activity/leads_activity.py", "LeadsActivity.on_trash", "activity deleted", "Removes the activity's rows first."),
	("custom_crm_updates/doctype/leads_activity/leads_activity.py", "LeadsActivity.linked_docs", "called by the above", "Current and previous records the activity is linked to."),
	("custom_crm_updates/doctype/leads_activity/leads_activity.py", "LeadsActivity.set_lead_qualification", "called by on_update", "Sets the Lead's Qualification Status with db_set and a timeline comment."),
	("custom_crm_updates/doctype/leads_activity/leads_activity.py", "sync_activity_table", "activity saved / deleted", "Rebuilds a Lead's or Opportunity's activities table."),
	("custom_crm_updates/doctype/leads_activity/leads_activity.py", "backfill_activity_tables", "after_migrate", "Fills the activities tables for existing activities."),
	("custom_crm_updates/doctype/leads_activity/leads_activity.py", "activity_table_fields", "setup", "Returns the activities section and table custom fields."),
	("custom_crm_updates/doctype/leads_activity/leads_activity.py", "add_to_dashboard", "Connections tabs", "Adds Leads Activity to a Connections tab."),
]
JS_REF = [
	("public/js/leads_activity_section.js", "custom_crm_updates.show_when_empty", "form setup", "Keeps empty read-only tables visible."),
	("public/js/leads_activity_section.js", "custom_crm_updates.make_activity", "buttons", "Opens a new Leads Activity linked to the current record."),
	("public/js/leads_activity_section.js", "custom_crm_updates.setup_activity_make_method", "form setup", "Makes the Connections “+” use make_activity."),
	("public/js/leads_activity_section.js", "custom_crm_updates.add_activity_buttons", "form refresh", "Adds Create ▸ Activity and the grid's New Activity button."),
	("public/js/leads_activity_section.js", "custom_crm_updates.add_contact_button", "form refresh", "Adds the grid's New Contact button."),
	("public/js/lead.js", "custom_crm_updates.LeadController", "Lead form", "Subclass of ERPNext's Lead controller: removes Create ▸ Prospect, adds our buttons."),
	("public/js/opportunity.js", "custom_crm_updates.OpportunityController", "Opportunity form", "Subclass of ERPNext's Opportunity controller: adds our buttons."),
	("custom_crm_updates/doctype/leads_activity/leads_activity.js", "link_type handler", "Leads Activity form", "Clears Link when Link Type changes; limits Assigned To to users."),
	("custom_crm_updates/doctype/leads_activity/leads_activity_list.js", "get_indicator", "Leads Activity list", "Colours each row's status pill."),
]
SOURCES = [
	"overrides/lead.py", "overrides/opportunity.py", "overrides/project_tender.py", "overrides/contact.py",
	"mirror_table.py", "custom_crm_updates/doctype/leads_activity/leads_activity.py",
]

RECIPES = """
<section class="sheet" id="recipes">
  <div class="sheet-head"><div class="sheet-no">Part 5</div><h2>How to change things later</h2>
  <p>Common follow-up changes and exactly where to make them. After any Python or hooks change: <code>bench --site site1.local migrate</code> then <code>bench restart</code>.</p></div>
  <div class="table-box"><table>
    <thead><tr><th>I want to…</th><th>Change this</th></tr></thead>
    <tbody>
      <tr><td>Add an activity type (e.g. Negotiation)</td><td>Add it to <code>options</code> of <code>activity_type</code> in <code>leads_activity.json</code> (or via the DocType form in developer mode), then migrate.</td></tr>
      <tr><td>Add a status to Opportunity</td><td>Add it to <code>EXTRA_STATUSES</code> in <code>overrides/opportunity.py</code>.</td></tr>
      <tr><td>Show activities on Prospect too</td><td>Add <code>"Prospect"</code> to <code>TABLE_DOCTYPES</code> in <code>leads_activity.py</code>, add <code>activity_table_fields(...)</code> to a Prospect custom-fields setup, and a <code>get_dashboard_data</code> for Prospect.</td></tr>
      <tr><td>Show another column in a table</td><td>Add the field to the child DocType JSON (e.g. <code>leads_activity_detail.json</code>), fill it in the matching sync query, and add its name to the <code>…_FIELDS</code> tuple used to compare rows.</td></tr>
      <tr><td>Name tenders differently</td><td><code>project_name</code> in <code>create_project_tender_for_activity</code>.</td></tr>
      <tr><td>Stop setting the Opportunity to Tendering</td><td>Remove the <code>db_set("status", "Tendering")</code> lines in <code>create_project_tender_for_activity</code>.</td></tr>
      <tr><td>Make Customer Group optional again</td><td>Remove the <code>CUSTOMER_FIELDS</code> line from <code>MANDATORY_DEPENDS_ON</code> and the <code>validate_customer_fields</code> hook; migrate.</td></tr>
      <tr><td>Check everything still works</td><td>On a test site: <code>bench --site &lt;test-site&gt; run-tests --app custom_crm_updates</code>.</td></tr>
    </tbody></table></div>
</section>
"""


def ref_section():
	rows = "".join(
		f"<tr><td><code>{f}</code></td><td><code>{n}</code></td><td>{w}</td><td>{d}</td></tr>"
		for f, n, w, d in REF + JS_REF
	)
	return f"""
<section class="sheet" id="reference">
  <div class="sheet-head"><div class="sheet-no">Part 4</div><h2>Every function</h2>
  <p>All {len(REF)} Python functions and {len(JS_REF)} JavaScript entry points added by this work, with when they run. Paths are relative to <code>apps/custom_crm_updates/custom_crm_updates/</code>.</p></div>
  <div class="table-box"><table>
    <thead><tr><th>File</th><th>Function</th><th>Runs when</th><th>Does</th></tr></thead>
    <tbody>{rows}</tbody></table></div>
</section>"""


def rail(steps):
	links = [("primer", "P1", "Frappe building blocks"), ("architecture", "P2", "How the files fit")]
	items = "".join(f'<a href="#{a}"><span>{n}</span>{t}</a>' for a, n, t in links)
	items += '<div class="rail-title">Part 3 · Steps</div>'
	items += "".join(f'<a href="#{a}"><span>{i:02d}</span>{t}</a>' for i, (a, t) in enumerate(steps, 1))
	items += '<div class="rail-title">Reference</div><a href="#reference"><span>P4</span>Every function</a><a href="#recipes"><span>P5</span>How to change things</a>'
	return f'<nav class="rail" aria-label="Contents"><div class="rail-title">Contents</div>{items}</nav>'


def main(out):
	body_steps = steps_a() + steps_b()
	steps = re.findall(r'<article class="step" id="([^"]+)">.*?<h3>(.*?)</h3>', body_steps, re.S)

	# coverage: every function in the new files is shown in a step and listed
	defined = {d for rel in SOURCES for d in lib.all_python_defs(rel)}
	listed = {f"{f}::{n}" for f, n, _, _ in REF}
	assert not defined - lib.SHOWN, f"not shown: {sorted(defined - lib.SHOWN)}"
	assert not defined - listed, f"not listed: {sorted(defined - listed)}"
	assert not listed - defined, f"listed but missing: {sorted(listed - defined)}"

	fonts_src = open("/home/frappe/frappe-bench/apps/custom_crm_updates/docs/custom-crm-updates.html", encoding="utf-8").read()
	fonts = re.search(r"<style>\n/\* Embedded fonts.*?</style>", fonts_src, re.S).group(0)
	total_lines = sum(lib.count_lines(r) for r in SOURCES)

	page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Custom CRM Updates Code Guide</title>
{fonts}
<style>{lib.CSS}</style>
</head>
<body>
<div class="page">
{rail(steps)}
<main>
  <header class="titleblock">
    <div class="tb-main">
      <div class="eyebrow">Developer reference · how it was built</div>
      <h1>Custom CRM Updates Code Guide</h1>
      <p class="lede">Every change made to the Lead, Opportunity and Project Tender in the <code>custom_crm_updates</code> app: what it does, how it was programmed, and the real code with its line numbers.</p>
    </div>
    <div class="tb-meta">
      <div>App</div><div><code>apps/custom_crm_updates</code></div>
      <div>Platform</div><div>ERPNext v14 · Frappe v14</div>
      <div>Steps</div><div>{len(steps)}</div>
      <div>Functions</div><div>{len(REF)} Python · {len(JS_REF)} JavaScript</div>
      <div>Server code</div><div>{total_lines} lines in {len(SOURCES)} files</div>
      <div>Companion</div><div><code>docs/custom-crm-updates.html</code></div>
    </div>
  </header>
  <section class="panel prose">
    <h3>How to read this guide</h3>
    <p>Part 1 explains the five Frappe tools everything is built from. Part 2 shows how the files connect. Part 3 walks through the work step by step, in the order it was built: for each step, what it does for users, why it was built that way, the actual code (copied from the files when this guide was generated, with real line numbers), and an explanation. Parts 4 and 5 are look-up tables.</p>
  </section>
{PRIMER}
{ARCH}
<section class="sheet" id="steps">
  <div class="sheet-head"><div class="sheet-no">Part 3</div><h2>Step by step</h2>
  <p>{len(steps)} steps, in the order they were built. Files are relative to <code>apps/custom_crm_updates/custom_crm_updates/</code>.</p></div>
  {body_steps}
</section>
{ref_section()}
{RECIPES}
  <footer>Custom CRM Updates Code Guide · generated from the source of <code>apps/custom_crm_updates</code> · works offline</footer>
</main>
</div>
</body>
</html>
"""
	open(out, "w", encoding="utf-8").write(page)
	ext = sorted(set(re.findall(r'(?:src|href)="(https?://[^"]+)"', page)))
	print(f"steps={len(steps)} functions={len(REF)}+{len(JS_REF)} size={len(page.encode()) // 1024}KB external={ext}")


if __name__ == "__main__":
	main(sys.argv[1])
