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
	("overrides/lead.py", "set_date_of_convert", "Lead validate", "Stamps Date of Convert the first time the status becomes Converted."),
	("overrides/lead.py", "set_date_of_convert_from_customer", "Customer on_update", "Stamps the same date when ERPNext converts the Lead by raising its Customer."),
	("overrides/lead.py", "backfill_date_of_convert", "after_migrate", "Fills the date for Leads converted before the field existed, from their Customer."),
	("overrides/opportunity.py", "apply_opportunity_customizations", "after_migrate", "Creates Opportunity custom fields, adds Tendering/Won, hides contact_html, applies the field order."),
	("overrides/opportunity.py", "apply_field_order", "called by the above", "Rebuilds the Opportunity's field_order: the Opportunity Value section above Organization."),
	("overrides/opportunity.py", "set_party_links", "Opportunity validate", "Mirrors the party into a plain Link field per type, for the Connections tab."),
	("overrides/opportunity.py", "backfill_party_links", "after_migrate", "Fills those mirrors for Opportunities that predate them."),
	("overrides/opportunity.py", "set_title", "Opportunity validate", "Makes the Opportunity Name the Opportunity's title."),
	("overrides/opportunity.py", "set_won_date", "Opportunity validate", "Stamps Won Date the first time the status becomes Won."),
	("overrides/opportunity.py", "validate_attachments", "Opportunity validate", "Refuses an Opportunity whose Attachments table holds no file."),
	("overrides/opportunity.py", "calculate_contributions", "Opportunity validate", "Works out every breakdown row's Final Value from the Targeted Amount."),
	("overrides/opportunity.py", "validate_activity_source", "Leads Activity validate", "Refuses an activity on an Opportunity that has no attachment saved."),
	("overrides/opportunity.py", "get_dashboard_data", "Opportunity Connections tab", "Adds Leads Activity, the client (Lead/Customer/Prospect) and Project Tender to Connections."),
	("overrides/customer.py", "apply_customer_customizations", "after_migrate", "Adds the Customer's Contacts table and hides core's contact list."),
	("overrides/tender.py", "apply_tender_customizations", "after_migrate", "Adds Completion Date to Tender and its column to Project Tender's Direct Cost Details."),
	("overrides/tender.py", "set_completion_date", "Tender validate", "Stamps Completion Date on the save that marks the Tender Complete."),
	("overrides/tender.py", "push_completion_date_to_rows", "Tender on_update", "Writes that date onto every Direct Cost Details row naming the Tender."),
	("overrides/tender.py", "set_submission_deadline", "Tender before_insert", "Fills Submission Deadline from the Expected Closing Date of the Opportunity behind the Project Tender."),
	("overrides/tender.py", "backfill_completion_date", "after_migrate", "Fills the date for Tenders completed before the field existed."),
	("overrides/project_tender.py", "apply_project_tender_customizations", "after_migrate", "Adds the Opportunity and Leads Activity links to Project Tender (if contracting is installed)."),
	("overrides/project_tender.py", "create_project_tender_for_activity", "Tendering activity saved", "Creates the activity's Project Tender (once), sets the Opportunity to Tendering and tells the user."),
	("overrides/project_tender.py", "get_opportunity_customer", "called by the above", "Finds or creates the Customer for the tender's Client."),
	("overrides/project_tender.py", "convert_prospect_to_customer", "called by the above", "Reuses or creates the Customer for a Prospect."),
	("overrides/project_tender.py", "validate_submitted_rows", "Project Tender validate", "Refuses Submitted until all three cost tables have rows."),
	("overrides/project_tender.py", "set_status_dates", "Project Tender validate", "Stamps Submitted Date and Won Date the first time each status is reached."),
	("overrides/project_tender.py", "on_update", "Project Tender saved", "Refreshes the Opportunity's tender table; Submitted → activity Done."),
	("overrides/project_tender.py", "on_trash", "Project Tender deleted", "Removes the tender's row from its Opportunity first."),
	("overrides/project_tender.py", "mark_activity_done", "tender Submitted", "Sets the creating activity to Done with a full save."),
	("overrides/project_tender.py", "get_opportunity_tenders", "Won popup", "Lists the Opportunity's Submitted tenders for the popup to choose from."),
	("overrides/project_tender.py", "validate_approved_tender", "Opportunity validate", "Refuses an approved tender belonging to another Opportunity."),
	("overrides/project_tender.py", "apply_approved_tender", "Opportunity saved as Won", "Sets the picked Project Tender to Won and comments on both timelines."),
	("overrides/project_tender.py", "set_tender_won", "called by the above", "Saves the approved tender as Won, as the system."),
	("overrides/project_tender.py", "tender_rows", "called by the syncs", "The Opportunity's tender rows, oldest first."),
	("overrides/project_tender.py", "sync_opportunity_tenders", "tender saved / deleted", "Rebuilds the Opportunity's Project Tender table."),
	("overrides/project_tender.py", "refresh_tender_rows", "called by apply_approved_tender", "Rewrites the table of the Opportunity being saved, with no modified bump."),
	("overrides/project_tender.py", "backfill_opportunity_tenders", "after_migrate", "Fills the tender tables for existing tenders."),
	("overrides/contact.py", "contact_table_fields", "setup", "Returns the Contacts section and table custom fields."),
	("overrides/contact.py", "contact_sources", "called by get_contact_rows", "Where a table's rows come from: an Opportunity itself, or a Lead plus its Opportunities."),
	("overrides/contact.py", "get_contact_rows", "called by syncs", "Builds the contact rows of a record from each of its sources, de-duplicated."),
	("overrides/contact.py", "sync_contact_table", "contact saved / deleted", "Rebuilds one record's Contacts table in the database."),
	("overrides/contact.py", "refresh_own_table", "Lead / Opportunity validate", "Recomputes the Contacts table on the record being saved."),
	("overrides/contact.py", "refresh_after_insert", "Lead after_insert", "Adds the auto-created contact of a new Lead to its table."),
	("overrides/contact.py", "contact_links", "called by contact events", "The (DocType, name) pairs a Contact links to."),
	("overrides/contact.py", "lead_of", "called by affected_docs", "The Lead an Opportunity or a Customer was made from, read from the database."),
	("overrides/contact.py", "lead_in", "called by refresh_party_lead", "The same Lead, read from a document in hand (before a save, or while deleting)."),
	("overrides/contact.py", "affected_docs", "called by contact events", "Leads/Opportunities/Customers whose table a contact change affects, plus the Lead behind each."),
	("overrides/contact.py", "refresh_party_lead", "Opportunity/Customer saved or deleted", "Keeps the Lead's rolled-up contacts level with its Opportunities and its Customer."),
	("overrides/contact.py", "on_contact_update", "Contact saved", "Refreshes every table the contact is or was in."),
	("overrides/contact.py", "on_contact_trash", "Contact deleted", "Removes the contact's rows first."),
	("overrides/contact.py", "backfill_contact_tables", "after_migrate", "Fills the Contacts tables for existing contacts."),
	("mirror_table.py", "rows_differ", "called by set_mirror_rows", "True if the new rows differ from the stored ones."),
	("mirror_table.py", "set_mirror_rows", "every table sync", "Writes a read-only table's rows directly; optionally bumps modified and reloads open forms."),
	("custom_crm_updates/doctype/leads_activity/leads_activity.py", "LeadsActivity.validate", "activity saved", "Runs the activity's own rules."),
	("custom_crm_updates/doctype/leads_activity/leads_activity.py", "LeadsActivity.validate_attachment", "activity validate", "Refuses an activity on a Lead/Opportunity, or any Registration, with an empty Attachments table."),
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
	("public/js/leads_activity_section.js", "custom_crm_updates.has_attachment", "Create ▸ Activity", "False, with an alert, while the record's attachments table is empty."),
	("public/js/leads_activity_section.js", "custom_crm_updates.setup_activity_make_method", "form setup", "Makes the Connections “+” use make_activity."),
	("public/js/leads_activity_section.js", "custom_crm_updates.add_activity_buttons", "form refresh", "Adds Create ▸ Activity and the grid's New Activity button."),
	("public/js/leads_activity_section.js", "custom_crm_updates.add_contact_button", "form refresh", "Adds the grid's New Contact button."),
	("public/js/lead.js", "custom_crm_updates.LeadController", "Lead form", "Subclass of ERPNext's Lead controller: removes Create ▸ Prospect, adds our buttons."),
	("public/js/opportunity.js", "custom_crm_updates.OpportunityController", "Opportunity form", "Subclass of ERPNext's Opportunity controller: adds our buttons."),
	("public/js/opportunity.js", "validate handler", "Opportunity form", "Refuses an Opportunity with no attached file, with the same message as the server."),
	("public/js/opportunity.js", "calculate_contribution", "breakdown row edited", "Fills a row's Final Value as the Targeted Amount, Type or Value is typed."),
	("public/js/opportunity.js", "nothing_to_approve", "Won with nothing to pick", "Says whether the Opportunity has no tenders at all or none Submitted."),
	("public/js/customer.js", "refresh handler", "Customer form", "Adds Create ▸ Opportunity, using ERPNext's own Customer → Opportunity mapper."),
	("public/js/tender.js", "set_submission_deadline", "Tender form", "Fills an empty Submission Deadline from the Opportunity, in the form."),
	("custom_crm_updates/doctype/leads_activity/leads_activity.js", "validate handler", "Leads Activity form", "Refuses a Registration activity with no attached file, with the same message as the server."),
	("custom_crm_updates/doctype/leads_activity/leads_activity.js", "link_type handler", "Leads Activity form", "Clears Link when Link Type changes; limits Assigned To to users."),
	("custom_crm_updates/doctype/leads_activity/leads_activity_list.js", "get_indicator", "Leads Activity list", "Colours each row's status pill."),
]
SOURCES = [
	"overrides/lead.py", "overrides/opportunity.py", "overrides/customer.py",
	"overrides/project_tender.py", "overrides/tender.py", "overrides/contact.py",
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
      <tr><td>Require something else before Submitted</td><td>Add the fieldname to <code>SUBMITTED_REQUIRED_TABLES</code> in <code>overrides/project_tender.py</code>.</td></tr>
      <tr><td>Change which activities need an attachment</td><td><code>ATTACHMENT_LINK_TYPES</code> / <code>LeadsActivity.validate_attachment</code> in <code>leads_activity.py</code>, and <code>mandatory_depends_on</code> of <code>attachments</code> in <code>leads_activity.json</code>.</td></tr>
      <tr><td>Show the Contacts table on another DocType</td><td>Add <code>contact_table_fields(...)</code> to its custom fields, add it to <code>TABLE_DOCTYPES</code> (and <code>ROLLED_UP</code> if a Lead should roll it up) in <code>overrides/contact.py</code>, and wire its <code>validate</code> to <code>refresh_own_table</code>.</td></tr>
      <tr><td>Add a trade to the Opportunity Breakdown (e.g. hvac)</td><td>Add it to <code>options</code> of <code>type</code> in <code>opportunity_contribution.json</code>, then migrate.</td></tr>
      <tr><td>Change how Final Value is worked out</td><td><code>calculate_contributions</code> in <code>overrides/opportunity.py</code> <em>and</em> <code>calculate_contribution</code> in <code>public/js/opportunity.js</code> — the two must agree.</td></tr>
      <tr><td>Stop requiring an Opportunity attachment</td><td>Remove the <code>validate_attachments</code> (and <code>validate_activity_source</code>) entries from <code>doc_events</code> in <code>hooks.py</code>, and the <code>validate</code> handler from <code>public/js/opportunity.js</code>; migrate and <code>bench build</code>.</td></tr>
      <tr><td>Show another DocType in the Opportunity's Connections</td><td>Add it to <code>transactions</code> in <code>get_dashboard_data</code> (<code>overrides/opportunity.py</code>), with a <code>non_standard_fieldnames</code> entry if its link field isn't called <code>opportunity</code>.</td></tr>
      <tr><td>Require attachments on the Lead too</td><td>Add the Lead's table to <code>ACTIVITY_SOURCE_TABLES</code> in <code>overrides/opportunity.py</code> and to <code>ATTACHMENT_TABLES</code> in <code>public/js/leads_activity_section.js</code>.</td></tr>
      <tr><td>Show other columns in the Won popup</td><td><code>get_opportunity_tenders</code> (fields) and <code>tender_label</code> in <code>public/js/opportunity.js</code>.</td></tr>
      <tr><td>Offer another status in the Won popup</td><td><code>APPROVABLE_STATUS</code> in <code>overrides/project_tender.py</code> — make it a tuple and the filter <code>["in", …]</code>.</td></tr>
      <tr><td>Record the date of another Project Tender status (e.g. Lost)</td><td>Add <code>"Lost": "lost_date"</code> to <code>STATUS_DATE_FIELDS</code> in <code>overrides/project_tender.py</code> and a matching custom field to its <code>CUSTOM_FIELDS</code>; add it to <code>TENDER_ROW_FIELDS</code>, <code>tender_rows</code> and the child DocType to show it on the Opportunity too.</td></tr>
      <tr><td>Stop a date being stamped automatically</td><td>Remove the hook from <code>doc_events</code> in <code>hooks.py</code>. The field and everything already recorded in it stay.</td></tr>
      <tr><td>Fill another Tender field from the Opportunity</td><td><code>set_submission_deadline</code> in <code>overrides/tender.py</code> (and the matching lookup in <code>public/js/tender.js</code>, which must agree).</td></tr>
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
