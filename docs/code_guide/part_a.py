"""Guide content, part A: primer, architecture, steps 1-8."""

from lib import doctype_table, js, json_field, py, py_lines


def step(no, anchor, title, summary, files, body):
	chips = "".join(f'<span class="chip">{f}</span>' for f in files)
	return f"""
<article class="step" id="{anchor}">
  <div class="step-head"><div class="step-no">{no:02d}</div>
    <div><h3>{title}</h3><p>{summary}</p></div></div>
  <div class="meta-row">{chips}</div>
  {body}
</article>"""


def why(text):
	return f'<div class="why"><b>Why this way</b><span>{text}</span></div>'


def explain(items, intro=""):
	lis = "".join(f"<li>{i}</li>" for i in items)
	return f'<div class="explain">{intro}<ol>{lis}</ol></div>'


PRIMER = """
<section class="sheet" id="primer">
  <div class="sheet-head"><div class="sheet-no">Part 1</div><h2>Frappe building blocks</h2>
  <p>Every change in this guide uses one of these few tools. Read this once and the rest of the code reads easily.</p></div>
  <div class="table-box"><table>
    <thead><tr><th>Tool</th><th>What it is</th><th>How we used it</th></tr></thead>
    <tbody>
      <tr><td><b>DocType</b></td><td>A record type: its fields are stored in a JSON file, its rules in a Python class (the "controller").</td><td>New: <code>Leads Activity</code> and 4 child tables.</td></tr>
      <tr><td><b>Child table</b></td><td>A DocType with <code>istable: 1</code>. Its rows live inside a parent document, shown as a grid.</td><td>Attachments, the activity / tender / contact tables.</td></tr>
      <tr><td><b>Custom Field</b></td><td>A field added to an existing DocType (Lead, Opportunity) without editing ERPNext's files.</td><td>Is Company, Customer Group, new tabs, sections and tables.</td></tr>
      <tr><td><b>Property Setter</b></td><td>Changes one property of an existing field (hidden, label, options, mandatory…) or the field order.</td><td>Hide person fields, new Opportunity statuses, section order.</td></tr>
      <tr><td><b>hooks.py</b></td><td>The app's wiring file. Frappe reads it to know which of our functions to call and when.</td><td><code>doc_events</code>, <code>doctype_js</code>, <code>after_migrate</code>, <code>override_doctype_dashboards</code>.</td></tr>
      <tr><td><b>Form script</b></td><td>JavaScript that runs inside a form in the browser: buttons, menus, field behaviour.</td><td>Create ▸ Activity, New Activity / New Contact buttons.</td></tr>
      <tr><td><b>bench migrate</b></td><td>Applies DocType JSON changes to the database, then runs the <code>after_migrate</code> hooks.</td><td>Re-creates all custom fields and property setters, fills the tables.</td></tr>
    </tbody></table></div>

  <div class="panel">
    <h3>When our code runs during a save</h3>
    <p>Frappe calls a fixed series of methods every time a document is saved. <code>doc_events</code> in <code>hooks.py</code> attach our functions to these moments; a DocType's own controller can define them as methods. Highlighted boxes are where this app plugs in.</p>
    <div class="flow" aria-label="Save lifecycle">
      <div class="node ours"><b>before_validate</b><span>Lead: clear person fields</span></div><div class="arrow">→</div>
      <div class="node ours"><b>validate</b><span>Lead: require group + territory; Lead/Opp: refresh Contacts</span></div><div class="arrow">→</div>
      <div class="node"><b>database write</b><span>row saved</span></div><div class="arrow">→</div>
      <div class="node ours"><b>on_update</b><span>Activity: automations; Contact / Tender: sync tables</span></div><div class="arrow">→</div>
      <div class="node ours"><b>after_insert</b><span>new records only (Lead: contacts)</span></div>
    </div>
    <p>Deleting runs <b>on_trash</b> first, before Frappe checks whether other records still link to the one being deleted. That ordering is used three times in this app (Sheet steps 06, 11, 14).</p>
  </div>

  <div class="panel">
    <h3>Words used in the code</h3>
    <div class="table-box" style="border:0"><table style="min-width:0">
      <tbody>
        <tr><td><code>doc</code> / <code>self</code></td><td>The document being saved (a Python object with one attribute per field).</td></tr>
        <tr><td><code>get_doc_before_save()</code></td><td>A copy of the document as it was in the database before this save; <code>None</code> when the document is new. Used to detect "status <em>changed</em> to Done".</td></tr>
        <tr><td><code>db_set()</code></td><td>Writes field values straight to the database without running the document's validations.</td></tr>
        <tr><td><code>frappe.get_all()</code></td><td>Database query returning a list of rows, ignoring permissions.</td></tr>
        <tr><td><code>frappe.throw()</code></td><td>Stops the save, rolls back everything done in it, and shows the message to the user.</td></tr>
        <tr><td><code>add_comment("Info", …)</code></td><td>Adds a line to the record's timeline, so users can see why something changed.</td></tr>
        <tr><td>idempotent</td><td>Safe to run again: running twice gives the same result as once. All setup code is written this way.</td></tr>
      </tbody></table></div>
  </div>
</section>
"""

ARCH = """
<section class="sheet" id="architecture">
  <div class="sheet-head"><div class="sheet-no">Part 2</div><h2>How the files fit together</h2>
  <p><code>hooks.py</code> is the switchboard. It routes events from ERPNext records to our modules; the modules then read and write those records. Everything lives in <code>apps/custom_crm_updates/custom_crm_updates/</code>.</p></div>
  <figure class="fig">
    <div class="diagram">
      <svg viewBox="0 0 980 400" role="img" aria-label="Architecture: hooks.py sends Lead, Opportunity, Contact and Project Tender events to lead.py, contact.py and project_tender.py. The Leads Activity controller calls project_tender.py and lead.py. All table updates go through mirror_table.py. The form scripts lead.js and opportunity.js share leads_activity_section.js.">
        <defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="currentColor"/></marker></defs>
        <g font-size="11" font-weight="700" letter-spacing="1.1" style="fill:var(--muted)">
          <text x="20" y="26">ERPNEXT RECORDS</text><text x="300" y="26">WIRING</text><text x="530" y="26">SERVER CODE (PYTHON)</text><text x="20" y="300">BROWSER (JAVASCRIPT)</text>
        </g>
        <g font-size="12.5">
          <g transform="translate(20,40)"><rect width="180" height="34" rx="6" style="fill:var(--surface);stroke:var(--line)"/><rect width="4" height="34" rx="2" style="fill:var(--c-lead)"/><text x="14" y="22" fill="currentColor">Lead</text></g>
          <g transform="translate(20,84)"><rect width="180" height="34" rx="6" style="fill:var(--surface);stroke:var(--line)"/><rect width="4" height="34" rx="2" style="fill:var(--c-opp)"/><text x="14" y="22" fill="currentColor">Opportunity</text></g>
          <g transform="translate(20,128)"><rect width="180" height="34" rx="6" style="fill:var(--surface);stroke:var(--line)"/><rect width="4" height="34" rx="2" style="fill:var(--muted)"/><text x="14" y="22" fill="currentColor">Contact</text></g>
          <g transform="translate(20,172)"><rect width="180" height="34" rx="6" style="fill:var(--surface);stroke:var(--line)"/><rect width="4" height="34" rx="2" style="fill:var(--c-tender)"/><text x="14" y="22" fill="currentColor">Project Tender</text></g>
          <g transform="translate(20,216)"><rect width="180" height="34" rx="6" style="fill:var(--accent-soft);stroke:var(--accent)"/><text x="14" y="22" fill="currentColor">Leads Activity (new)</text></g>

          <g transform="translate(290,100)"><rect width="150" height="70" rx="6" style="fill:var(--surface);stroke:var(--ink);stroke-width:1.5"/><text x="75" y="31" text-anchor="middle" font-weight="700" fill="currentColor">hooks.py</text><text x="75" y="50" text-anchor="middle" style="fill:var(--ink-2)">doc_events</text></g>

          <g transform="translate(530,40)"><rect width="200" height="34" rx="6" style="fill:var(--surface);stroke:var(--line)"/><text x="12" y="22" fill="currentColor" font-family="var(--f-mono)">overrides/lead.py</text></g>
          <g transform="translate(530,104)"><rect width="200" height="34" rx="6" style="fill:var(--surface);stroke:var(--line)"/><text x="12" y="22" fill="currentColor">overrides/contact.py</text></g>
          <g transform="translate(530,168)"><rect width="200" height="34" rx="6" style="fill:var(--surface);stroke:var(--line)"/><text x="12" y="22" fill="currentColor">overrides/project_tender.py</text></g>
          <g transform="translate(530,216)"><rect width="200" height="34" rx="6" style="fill:var(--accent-soft);stroke:var(--accent)"/><text x="12" y="22" fill="currentColor">leads_activity.py</text></g>
          <g transform="translate(790,128)"><rect width="170" height="44" rx="6" style="fill:var(--surface);stroke:var(--ink);stroke-width:1.5"/><text x="85" y="20" text-anchor="middle" font-weight="700" fill="currentColor">mirror_table.py</text><text x="85" y="36" text-anchor="middle" style="fill:var(--ink-2)">writes table rows</text></g>

          <g transform="translate(20,312)"><rect width="150" height="34" rx="6" style="fill:var(--surface);stroke:var(--line)"/><text x="12" y="22" fill="currentColor">lead.js</text></g>
          <g transform="translate(20,356)"><rect width="150" height="34" rx="6" style="fill:var(--surface);stroke:var(--line)"/><text x="12" y="22" fill="currentColor">opportunity.js</text></g>
          <g transform="translate(290,334)"><rect width="230" height="34" rx="6" style="fill:var(--surface);stroke:var(--line)"/><text x="12" y="22" fill="currentColor">leads_activity_section.js (shared)</text></g>
        </g>
        <g stroke="currentColor" stroke-width="1.4" fill="none" marker-end="url(#a)">
          <line x1="200" y1="57" x2="288" y2="118"/>
          <line x1="200" y1="101" x2="288" y2="128"/>
          <line x1="200" y1="145" x2="288" y2="140"/>
          <line x1="200" y1="189" x2="288" y2="155"/>
          <line x1="440" y1="115" x2="528" y2="60"/>
          <line x1="440" y1="132" x2="528" y2="121"/>
          <line x1="440" y1="150" x2="528" y2="182"/>
          <line x1="200" y1="233" x2="528" y2="233"/>
          <line x1="630" y1="216" x2="630" y2="204"/>
          <polyline points="730,233 760,233 760,57 732,57"/>
          <line x1="730" y1="121" x2="788" y2="144"/>
          <line x1="730" y1="185" x2="788" y2="158"/>
          <polyline points="730,240 775,240 775,170 788,170"/>
          <line x1="170" y1="329" x2="288" y2="347"/>
          <line x1="170" y1="373" x2="288" y2="357"/>
        </g>
        <g font-size="11" style="fill:var(--ink-2)">
          <text x="210" y="226">its own controller</text>
          <text x="640" y="212">Tendering</text>
          <text x="766" y="100">Registration Done</text>
          <text x="196" y="322">use</text>
        </g>
      </svg>
    </div>
    <figcaption>Leads Activity has its own controller (no hook needed). When it saves, it calls <code>project_tender.py</code> for Tendering and <code>lead.py</code> for the Customer conversion. Every read-only table is written through <code>mirror_table.py</code>.</figcaption>
  </figure>
  <div class="table-box"><table>
    <thead><tr><th>File</th><th>Type</th><th>Responsible for</th></tr></thead>
    <tbody>
      <tr><td><code>hooks.py</code></td><td>wiring</td><td>Connects events and scripts to the functions below</td></tr>
      <tr><td><code>overrides/lead.py</code></td><td>Python</td><td>Lead fields and layout, Is Company, mandatory fields, Lead → Customer</td></tr>
      <tr><td><code>overrides/opportunity.py</code></td><td>Python</td><td>Opportunity fields, statuses, Project Tender tab</td></tr>
      <tr><td><code>overrides/project_tender.py</code></td><td>Python</td><td>Tendering → Project Tender, Submitted → activity Done, Opportunity Won → approved tender, tender table</td></tr>
      <tr><td><code>overrides/contact.py</code></td><td>Python</td><td>Contacts tables on Lead and Opportunity</td></tr>
      <tr><td><code>mirror_table.py</code></td><td>Python</td><td>Shared writer for all read-only tables</td></tr>
      <tr><td><code>custom_crm_updates/doctype/leads_activity/</code></td><td>DocType</td><td>The activity record, its automations, list colours, form script, tests</td></tr>
      <tr><td><code>custom_crm_updates/doctype/…_detail, …_attachment, opportunity_project_tender</code></td><td>DocType (child)</td><td>Row layouts for the tables</td></tr>
      <tr><td><code>public/js/lead.js</code>, <code>opportunity.js</code></td><td>JavaScript</td><td>Form controllers: Create menu, buttons</td></tr>
      <tr><td><code>public/js/leads_activity_section.js</code></td><td>JavaScript</td><td>Button and table helpers shared by both forms</td></tr>
      <tr><td><code>tests/test_crm_automation.py</code></td><td>tests</td><td>Tendering, conversion, contacts and mandatory-field tests</td></tr>
    </tbody></table></div>
</section>
"""


def steps_a():
	s = []
	s.append(step(1, "s-is-company", "Is Company hides the person fields",
		"When a Lead represents a company, the person fields (salutation, first/middle/last name, gender, job title) disappear, and they are cleared when saved.",
		["overrides/lead.py", "hooks.py → before_validate"],
		why("No ERPNext file is edited. Visibility is a <b>property setter</b> (<code>depends_on</code>) on each person field, so the form hides them instantly; clearing the values is a <b>before_validate</b> hook so stale names never reach the saved Lead. This part already existed in the app when the work started and is explained here for completeness.")
		+ py("overrides/lead.py", "IS_COMPANY", "PERSON_FIELDS")
		+ py_lines("overrides/lead.py", 111, 120, "overrides/lead.py · inside apply_lead_customizations · lines 111–120")
		+ py("overrides/lead.py", "clear_person_fields")
		+ explain([
			"<code>depends_on = \"eval: !doc.custom_is_company\"</code> is a tiny JavaScript expression the form evaluates on every change: the field shows only while Is Company is unticked.",
			"Core ERPNext makes First Name mandatory whenever Organization Name is empty. With First Name hidden, that would demand a field the user cannot see, so <code>mandatory_depends_on</code> flips the rule: a company requires Organization Name instead.",
			"<code>clear_person_fields</code> runs before ERPNext's own <code>validate</code>. It empties the person fields and sets <code>lead_name</code> (Full Name) to the company name, because ERPNext only fills <code>lead_name</code> when it is empty.",
		])))

	s.append(step(2, "s-org-order", "Organization section before Contact Info",
		"The Organization block moves up so it sits right after the main details.",
		["overrides/lead.py → apply_field_order, move_section"],
		why("ERPNext's own fields cannot be moved with <code>insert_after</code> (that only works for custom fields). The only supported way is a <code>field_order</code> property setter: the full list of fieldnames in display order, exactly what Customize Form saves when you drag fields. We rebuild that list in code so it is reapplied on every migrate.")
		+ py("overrides/lead.py", "apply_field_order", "move_section")
		+ explain([
			"<code>frappe.get_meta(\"Lead\", cached=False).fields</code> gives every field in its current display order, including custom fields.",
			"<code>move_section</code> finds the section's first field, walks forward until the next Section Break or Tab Break, cuts that block out, and inserts it before the target field. Example: <code>[type, CONTACT_INFO, email, phone, ORGANIZATION, company_name, fax, ADDRESS]</code> becomes <code>[type, ORGANIZATION, company_name, fax, CONTACT_INFO, email, phone, ADDRESS]</code>.",
			"The optional <code>header</code> is a field (the new Tab Break, step 8) that is placed in front of the moved block.",
			"If the new order equals the current one, nothing is written. That makes the function idempotent: running it on every migrate is safe, and any other ordering someone saved in Customize Form is kept.",
		])))

	s.append(step(3, "s-activity-doctype", "The Leads Activity DocType",
		"A new record type for every touchpoint: type, status, date, who is responsible, what it is linked to, and files.",
		["leads_activity.json", "leads_activity_attachment.json", "leads_activity.js", "leads_activity_list.js"],
		why("A DocType is defined by its JSON file; <code>bench migrate</code> creates the database table from it. The <b>Link</b> field has to point at Lead, Prospect <em>or</em> Opportunity, so it is a <b>Dynamic Link</b>: its target DocType is read from another field (<code>link_type</code>).")
		+ '<h4>Fields (read from the JSON file)</h4>' + doctype_table("custom_crm_updates/doctype/leads_activity/leads_activity.json")
		+ json_field("custom_crm_updates/doctype/leads_activity/leads_activity.json", "link_name")
		+ explain([
			"<code>\"options\": \"link_type\"</code> makes it dynamic: Frappe reads the value of <code>link_type</code> (\"Lead\") and lists Leads, validates the value exists, and shows it as a clickable link.",
			"Because Frappe knows about this dynamic link, it refuses to delete a Lead that still has activities. That integrity comes for free.",
			"Records are named <code>CRM-ACT-.YYYY.-.#####</code> (the JSON <code>autoname</code>), e.g. CRM-ACT-2026-00001.",
			"Attachments is a <b>Table</b> field whose rows are the child DocType <code>Leads Activity Attachment</code> (an Attach field and a description), so any number of files can be added.",
		])
		+ js("custom_crm_updates/doctype/leads_activity/leads_activity.js")
		+ explain([
			"<code>frappe.ui.form.on(\"Leads Activity\", {...})</code> registers handlers for this form. A handler named after a field runs when that field changes.",
			"<code>link_type(frm)</code>: when Link Type changes, the old Link points at the wrong kind of record, so it is cleared.",
			"<code>set_query(\"assigned_to\", …)</code> limits Assigned To to enabled system users.",
		])
		+ js("custom_crm_updates/doctype/leads_activity/leads_activity_list.js")
		+ explain(["<code>listview_settings[…].get_indicator</code> returns <code>[label, colour, filter]</code> for each row; Frappe draws the coloured status pill in the list, and clicking it filters by that status."])))

	s.append(step(4, "s-qualification", "Activities drive the Lead's qualification",
		"A new Registration activity sets the Lead to In Process; any activity reaching Done sets it to Qualified.",
		["leads_activity.py → LeadsActivity.on_update, set_lead_qualification"],
		why("The rule belongs to the activity, so it lives in the activity's own controller (<code>class LeadsActivity</code>), in <code>on_update</code>, which Frappe calls after every save. The Lead is updated with <code>db_set</code>, not a full save, so a salesperson without edit rights on the Lead can still log activities, and an unrelated problem on the Lead (for example a duplicate email) cannot block recording the activity.")
		+ py("custom_crm_updates/doctype/leads_activity/leads_activity.py", "LeadsActivity.on_update", "LeadsActivity.set_lead_qualification")
		+ explain([
			"<code>before = self.get_doc_before_save()</code> is <code>None</code> for a brand-new activity. So <code>before is None</code> means \"just created\".",
			"Registration rule: only on creation, and <code>skip_if=(\"In Process\", \"Qualified\")</code> means a Lead that is already further along is never moved back.",
			"<code>became_done</code> is true when the status is Done now and was not Done before (or the activity is new, or it was moved to another Lead). Re-saving a Done activity therefore does nothing.",
			"<code>set_lead_qualification</code> also fills Qualified By (the activity's Assigned To, or the current user) and Qualified On (today).",
			"<code>db_set(values, notify=True)</code> writes the fields and tells any browser that has this Lead open to reload it. <code>add_comment</code> writes the timeline line \"Qualification Status set to Qualified by CRM-ACT-…\".",
			"The Tendering and Registration-to-Customer parts of <code>on_update</code> are explained in steps 10 and 13.",
		])))

	s.append(step(5, "s-create-menu", "Create ▸ Activity (and no Prospect)",
		"On the Lead, the Create menu loses Prospect and gains Activity, which opens a new activity already linked to the Lead.",
		["public/js/lead.js", "public/js/leads_activity_section.js", "hooks.py → doctype_js"],
		why("ERPNext builds the Lead's Create menu inside its controller class <code>erpnext.LeadController</code>. Frappe runs handlers registered with <code>frappe.ui.form.on</code> <em>before</em> that class's <code>refresh</code>, so a normal handler would try to remove Prospect before it exists. The solution is to <b>subclass</b> ERPNext's controller and run our code after <code>super.refresh()</code>.")
		+ js("public/js/lead.js")
		+ explain([
			"<code>hooks.py → doctype_js</code> appends our files after ERPNext's own Lead script, so <code>erpnext.LeadController</code> already exists when ours runs.",
			"<code>class … extends erpnext.LeadController</code> inherits everything; <code>super.setup()</code> / <code>super.refresh()</code> run ERPNext's version first.",
			"<code>extend_cscript(cur_frm.cscript, new …)</code> is the same call ERPNext uses to install its controller; calling it again installs ours in its place.",
			"<code>remove_custom_button(\"Prospect\", \"Create\")</code> removes the menu item ERPNext just added.",
		])
		+ js("public/js/leads_activity_section.js", 28, 58)
		+ explain([
			"<code>make_activity</code> creates an unsaved Leads Activity in the browser, sets Link Type and Link from the current form, and opens it. Values are set directly, so the \"Link Type changed → clear Link\" handler of step 3 does not fire.",
			"<code>setup_activity_make_method</code> registers the same function for the Connections tab's \"+\" button, because Frappe's default cannot fill a Dynamic Link.",
			"<code>add_activity_buttons</code> adds Create ▸ Activity and the grid's New Activity button, only for saved records and only if the user may create activities.",
		])))

	s.append(step(6, "s-mirror", "Activities shown as a real table",
		"The Lead's Activities tab gets a standard ERPNext grid listing its activities, with the ⚙ column settings.",
		["Leads Activity Detail (child DocType)", "leads_activity.py → sync_activity_table…", "mirror_table.py"],
		why("A child table needs its rows stored inside the parent. So the activities are <b>mirrored</b>: whenever an activity changes, the affected Lead's table is rebuilt from the activities. This pattern (a read-only <em>mirror table</em>) is reused for Opportunity activities, Project Tenders and Contacts, so the writing part is in one shared module.")
		+ py("custom_crm_updates/doctype/leads_activity/leads_activity.py", "activity_table_fields")
		+ explain([
			"Three custom fields: a labelled Section Break, the Table (rows of <code>Leads Activity Detail</code>), and a second, unlabelled Section Break so ERPNext's own Open Tasks/Events stay outside our section.",
			"<code>read_only: 1</code>: users cannot edit rows. <code>no_copy: 1</code>: Duplicate does not copy them.",
		])
		+ py("custom_crm_updates/doctype/leads_activity/leads_activity.py", "sync_activity_table", "LeadsActivity.on_trash", "LeadsActivity.linked_docs")
		+ explain([
			"<code>sync_activity_table</code> queries every activity linked to the Lead (ascending by <code>creation</code>, so a new one is appended at the bottom and a back-dated one does not jump to the top) plus a count of each one's attachments, then hands the rows to <code>set_mirror_rows</code>.",
			"<code>linked_docs</code> returns the current link <em>and</em> the previous one when an activity is moved to another record, so the old record loses the row and the new one gains it.",
			"<code>on_trash</code> passes <code>exclude=self.name</code>: the row is removed before Frappe's link check, otherwise the row itself (a Link to the activity) would block the deletion.",
		])
		+ py("mirror_table.py", "rows_differ", "set_mirror_rows")
		+ explain([
			"<code>rows_differ</code> compares old and new rows as strings, so a date loaded from the database equals the same date from a query. If nothing changed, nothing is written.",
			"<code>update_child_table</code> writes only the child rows (no full save of the Lead, so none of its validations run).",
			"<code>bump_modified</code>: updating the Lead's <em>modified</em> timestamp means a copy of the Lead that is open in someone's browser can no longer be saved over the new rows (Frappe refuses with \"document has been modified\"), and <code>notify=True</code> reloads it.",
		])
		+ py("custom_crm_updates/doctype/leads_activity/leads_activity.py", "backfill_activity_tables", "add_to_dashboard")
		+ py("overrides/lead.py", "get_dashboard_data")
		+ explain([
			"<code>backfill_activity_tables</code> runs after every migrate and syncs every record that has activities, for activities created before the table existed. Thanks to <code>rows_differ</code> it touches nothing that is already correct.",
			"<code>add_to_dashboard</code> adds Leads Activity to the Connections tab: count by <code>link_name</code>, filtered by <code>link_type</code>. It is registered per DocType through <code>override_doctype_dashboards</code>.",
		])))

	s.append(step(7, "s-opp-activities", "Opportunity gets its own activities",
		"The same table on the Opportunity, listing only activities whose Link Type is Opportunity.",
		["leads_activity.py → TABLE_DOCTYPES", "overrides/opportunity.py", "public/js/opportunity.js"],
		why("Because step 6 was written around a list of DocTypes, extending it was one word: <code>TABLE_DOCTYPES = (\"Lead\", \"Opportunity\")</code>. The same table fieldname on both, the same child DocType, the same sync. Separation is automatic: the query filters on <code>link_type</code> = the record's own DocType.")
		+ py("custom_crm_updates/doctype/leads_activity/leads_activity.py", "ACTIVITY_TABLE", "TABLE_DOCTYPES")
		+ py("overrides/opportunity.py", "get_dashboard_data")
		+ js("public/js/opportunity.js")
		+ explain([
			"<code>get_dashboard_data</code> is the Opportunity's twin of the Lead's (step 6): it adds Leads Activity to the Opportunity's Connections tab.",
			"The Opportunity controller is subclassed exactly like the Lead's (step 5). ERPNext's Opportunity class has no <code>setup</code>, hence <code>super.setup?.()</code> (call it only if it exists).",
			"An Opportunity made from a Lead does not inherit the Lead's activity rows: ERPNext's Lead → Opportunity mapping never copies table fields.",
		])))

	s.append(step(8, "s-address-tab", "Address & Contacts in its own tab",
		"The address/contact section moves out of the Details tab into a new tab before Activities.",
		["overrides/lead.py → ADDRESS_TAB, move_section(header=…), ADDRESS_SECTION_PROPERTIES"],
		why("A Tab Break swallows every field after it up to the next tab. Dropping one in front of the address section would also drag Qualification and Additional Information into the new tab. So the address block is first <b>moved</b> to just before the Activities tab, with the new Tab Break placed in front of it (the <code>header</code> argument of <code>move_section</code>).")
		+ py_lines("overrides/lead.py", 50, 57, "overrides/lead.py · the Tab Break custom field · lines 50–57")
		+ py("overrides/lead.py", "ADDRESS_SECTION_PROPERTIES")
		+ explain([
			"Inside its own tab the section no longer needs its heading (the tab already says it), and <code>collapsible</code> would open the tab with the section folded, so both are switched off with property setters.",
			"The order is applied by <code>apply_field_order</code> from step 2: <code>move_section(…, \"address_section\", before=\"activities_tab\", header=ADDRESS_TAB)</code>.",
		])))
	return "".join(s)
