"""Guide content, part B: steps 9-18."""

from lib import js, json_field, py, py_lines
from part_a import explain, step, why

LA = "custom_crm_updates/doctype/leads_activity/leads_activity.py"
PT = "overrides/project_tender.py"
CT = "overrides/contact.py"
OP = "overrides/opportunity.py"
LD = "overrides/lead.py"


def steps_b():
	s = []
	s.append(step(9, "s-statuses", "Tendering type and two new Opportunity statuses",
		"Activity Type gains Tendering; Opportunity Status gains Tendering and Won.",
		["leads_activity.json", "overrides/opportunity.py → apply_opportunity_customizations"],
		why("Leads Activity is our own DocType, so its option list is edited directly in its JSON file. Opportunity belongs to ERPNext, so its Status options are changed with a <b>property setter</b>. The setter is built from ERPNext's original list plus ours, so options ERPNext adds in a future upgrade are kept.")
		+ json_field(LA.replace(".py", ".json"), "activity_type")
		+ py(OP, "EXTRA_STATUSES", "apply_opportunity_customizations")
		+ explain([
			"<code>frappe.db.get_value(\"DocField\", …, \"options\")</code> reads ERPNext's <em>original</em> options (the DocField table), not the already-customized ones, so running this again never adds duplicates.",
			"ERPNext only recalculates an Opportunity's status when a Quotation is made, ordered or lost, so Tendering and Won stay put through normal saves.",
			"<code>create_custom_fields(CUSTOM_FIELDS, update=True)</code> creates or updates every Opportunity custom field (steps 7, 11, 14); <code>HIDDEN_FIELDS</code> is explained in step 14.",
		])))

	s.append(step(10, "s-tendering", "Tendering activity creates a Project Tender",
		"Saving a Tendering activity on an Opportunity creates one Project Tender named after it, and moves the Opportunity to Tendering.",
		["leads_activity.py → on_update", "overrides/project_tender.py"],
		why("Project Tender belongs to the <b>contracting</b> app, which we do not modify. Two read-only custom fields added from our app link each tender back to its Opportunity and to the activity that created it. That link is also how \"one tender per activity\" is guaranteed: before creating, we check whether a tender already points at this activity.")
		+ py_lines(LA, 43, 46, "leads_activity.py · inside LeadsActivity.on_update · lines 43–46")
		+ py(PT, "CUSTOM_FIELDS", "apply_project_tender_customizations", "create_project_tender_for_activity")
		+ explain([
			"The import sits inside the function (a <em>local import</em>) so the two modules can call each other without a circular import at load time.",
			"<code>frappe.db.exists(\"Project Tender\", {ACTIVITY_FIELD: activity.name})</code>: if a tender already exists for this activity, stop. Saving the activity again never creates a second one; a new Tendering activity creates a new one.",
			"Project Name = the Opportunity's title (falling back to customer name, then its ID).",
			"<code>insert(ignore_permissions=True)</code>: Sales Users have no Project Tender role, but the automation must still work for them.",
			"The Opportunity moves to Tendering unless it is already Won or Converted, and a timeline comment records which activity created which tender.",
			"<code>apply_project_tender_customizations</code> does nothing if the contracting app is missing, so the app still installs cleanly without it.",
		])
		+ py(PT, "get_opportunity_customer", "convert_prospect_to_customer")
		+ explain([
			"Project Tender's <b>Client</b> is a mandatory link to a Customer. An Opportunity for a Customer uses it directly.",
			"An Opportunity for a Lead converts that Lead first (step 13), or reuses the Customer already made from it.",
			"An Opportunity for a Prospect: Customer has no link back to a Prospect, but ERPNext's own conversion names the Customer after the Prospect, so we match on that name and only create a new Customer if none exists.",
			"If the Customer cannot be created (missing Customer Group/Territory), <code>frappe.throw</code> cancels the whole activity save, so no half-created tender is left behind.",
		])))

	s.append(step(11, "s-tender-tab", "The Opportunity's Project Tender tab",
		"A new tab between Items and Activities lists every tender created for the Opportunity.",
		["overrides/opportunity.py → CUSTOM_FIELDS", "overrides/project_tender.py → on_update, sync_opportunity_tenders…", "Opportunity Project Tender (child DocType)"],
		why("Same mirror-table pattern as the activities (step 6). Here the source records are Project Tenders, so the sync is triggered by a <b>doc_event</b> on Project Tender in <code>hooks.py</code>: our <code>on_update</code> runs after the contracting app's own.")
		+ py(OP, "CUSTOM_FIELDS")
		+ py(PT, "on_update", "on_trash", "sync_opportunity_tenders", "backfill_opportunity_tenders")
		+ explain([
			"<code>insert_after: \"total\"</code>: the last field of the Items tab, so the new tab appears right before Activities. <code>depends_on: \"eval:!doc.__islocal\"</code> hides the tab on an unsaved Opportunity.",
			"<code>on_update</code> syncs both the current Opportunity and the previous one if the link changed (the <code>before</code> copy), then checks for Submitted (step 12).",
			"<code>\"date(creation) as creation_date\"</code> asks the database for just the date part of when the tender was created.",
			"<code>backfill_opportunity_tenders</code> fills the table after a migrate for tenders that already exist.",
		])))

	s.append(step(12, "s-submitted", "Submitted tender → activity Done, Opportunity Won",
		"When a Project Tender's status becomes Submitted, the activity that created it is marked Done and the Opportunity becomes Won.",
		["overrides/project_tender.py → mark_activity_done, mark_opportunity_won"],
		why("<code>doc.has_value_changed(\"status\")</code> is true only on the save where the status actually changes, so re-saving a Submitted tender does nothing. The activity gets a <b>full save</b> (not <code>db_set</code>) so its own <code>on_update</code> runs too and the Opportunity's activities table shows Done.")
		+ py(PT, "mark_activity_done", "mark_opportunity_won")
		+ explain([
			"Both functions return early if there is nothing to do (no linked record, or already Done / Won).",
			"<code>activity.flags.ignore_permissions = True</code>: whoever submits the tender may not have rights on activities.",
			"Saving the activity re-runs its <code>on_update</code>; the Tendering check there finds the existing tender and does not create another.",
			"The contracting app's own logic for a tender marked <b>Won</b> (creating Projects and Sales Orders) is untouched.",
		])))

	s.append(step(13, "s-convert", "Registration Done → the Lead becomes a Customer",
		"When a Registration activity on a Lead is Done, the Lead is converted to a Customer using its own Customer Group and Territory.",
		["leads_activity.py → on_update", "overrides/lead.py → convert_lead_to_customer, insert_customer"],
		why("We reuse ERPNext's own Lead → Customer mapping (<code>_make_customer</code>), the same code behind the Lead's Create ▸ Customer button. It copies the Lead's details and, when the Customer is saved, links the Lead's contacts and addresses to it and marks the Lead Converted. We only fill in what the mapping leaves out.")
		+ py_lines(LA, 65, 70, "leads_activity.py · inside LeadsActivity.on_update · lines 65–70")
		+ py(LD, "convert_lead_to_customer", "insert_customer")
		+ explain([
			"The trigger fires when a Registration activity <em>becomes</em> Done, or a Done activity is changed to Registration.",
			"<code>frappe.db.get_value(\"Customer\", {\"lead_name\": lead})</code>: ERPNext stores the source Lead on the Customer, so an already-converted Lead is never converted twice.",
			"The mapping copies Territory (same field name on both) but takes Customer Group from the Selling Settings default; the Lead's own Customer Group (step 16) overrides it.",
			"<code>insert_customer</code> checks both fields first and throws a clear message naming what is missing and where to set it, instead of ERPNext's bare \"mandatory field\" error.",
		])))

	s.append(step(14, "s-contacts", "Contacts shown as a table",
		"On Lead and Opportunity, ERPNext's contact list is replaced by a read-only Contacts table with a New Contact button.",
		["overrides/contact.py", "Leads Contact Detail (child DocType)", "hooks.py → Lead, Opportunity, Contact events"],
		why("Contacts are linked to records through rows in the Contact's <b>links</b> table (Dynamic Links). The table is a mirror of those, kept current from two directions: a Lead/Opportunity recomputes its own table whenever <em>it</em> is saved, and a Contact pushes its rows to every record it is (or was) linked to whenever <em>the Contact</em> is saved or deleted. Because the record recomputes on its own save, a stale form cannot leave wrong rows, so this table does not need the modified-timestamp bump.")
		+ py(CT, "contact_table_fields", "get_contact_rows", "party_of", "sync_contact_table")
		+ explain([
			"<code>filters=[[\"Dynamic Link\", \"link_doctype\", \"=\", …], …]</code> is a child-table filter: Contacts that have a link row pointing at the given record.",
			"For an Opportunity, the Opportunity's own contacts are followed by its <b>party's</b> (the Lead, Customer or Prospect it is for), the same set ERPNext's contact list showed. <code>linked_via</code> says which one each row came from.",
			"A contact that appears twice is listed once (<code>seen</code>).",
			"<code>order_by=\"`tabContact`.…\"</code> names the table explicitly because the Dynamic Link join also has a <code>creation</code> column.",
		])
		+ py(CT, "refresh_own_table", "refresh_after_insert", "contact_links", "affected_docs", "on_contact_update", "on_contact_trash", "backfill_contact_tables")
		+ explain([
			"<code>refresh_own_table</code> (Lead and Opportunity <b>validate</b>) sets the rows on the document being saved, so they are written with it.",
			"<code>refresh_after_insert</code>: ERPNext links a new Lead's auto-created contact in <em>its</em> after_insert, after validate has run, so we refresh once more and write the rows.",
			"<code>affected_docs</code> turns a contact's links into the records to update: linked Leads/Opportunities directly, plus every Opportunity whose party is a linked Lead, Customer or Prospect.",
			"<code>on_contact_update</code> merges links before and after the save, so unlinking a contact removes its row from the old record.",
		])
		+ py(LD, "HIDDEN_FIELDS")
		+ js("public/js/leads_activity_section.js", 60, 72)
		+ explain([
			"ERPNext's own contact list (<code>contact_html</code>) is hidden by a property setter on both DocTypes. ERPNext still renders into it, just unseen, so nothing in its code breaks.",
			"The New Contact button repeats what ERPNext's button did: <code>frappe.new_doc(\"Contact\")</code>. ERPNext's form already set <code>frappe.dynamic_link</code>, which links the new Contact to the Lead (or to the Opportunity's party).",
		])))

	s.append(step(15, "s-visible", "Empty tables stay visible",
		"A table with no rows yet (and its New Activity / New Contact button) stays on screen.",
		["public/js/leads_activity_section.js → show_when_empty"],
		why("Frappe hides any <b>read-only</b> field that has no value. An empty read-only table therefore disappeared, taking its button with it (and the whole Project Tender tab, which has nothing else in it). Each field's control decides its visibility in a method called <code>get_status</code>; we wrap that method for our tables only.")
		+ js("public/js/leads_activity_section.js", 7, 26)
		+ explain([
			"<code>get_status</code> returns \"Write\", \"Read\" or \"None\" (hidden). Our wrapper calls the original first.",
			"Only when the original says \"None\" <em>and</em> the field is not hidden on purpose, the record is saved, and the user can read it, the answer becomes \"Read\": shown, still read-only.",
			"It is installed in the controller's <code>setup</code>, which runs once per form; the controls are reused when switching between records.",
		])))

	s.append(step(16, "s-mandatory", "Customer Group and Territory mandatory on Lead",
		"A new Customer Group field beside Territory; both must be filled before a Lead can be saved, and the Customer inherits them.",
		["overrides/lead.py → CUSTOMER_FIELDS, MANDATORY_DEPENDS_ON, validate_customer_fields"],
		why("The obvious switch, <code>reqd</code>, is enforced on <em>every</em> insert. ERPNext also creates Leads by itself (website contact form, an Opportunity made from an email address, appointments) with nobody to ask, and those would start failing. So the form is made mandatory with <code>mandatory_depends_on: \"eval:1\"</code> (always true), and a server check covers people saving by API or import while letting ERPNext's own inserts through.")
		+ py(LD, "CUSTOMER_GROUP", "CUSTOMER_FIELDS", "MANDATORY_DEPENDS_ON", "validate_customer_fields")
		+ py_lines(LD, 58, 66, "overrides/lead.py · the Customer Group custom field · lines 58–66")
		+ explain([
			"In Frappe v14, <code>mandatory_depends_on</code> is checked by the form only (red asterisk, \"Missing Fields\" dialog), never by the server.",
			"<code>validate_customer_fields</code> runs on the server for every Lead save. ERPNext's automatic inserts pass <code>ignore_permissions</code> or <code>ignore_mandatory</code>; those are skipped. Everyone else gets the same error the form shows.",
			"Customer Group is placed right after Territory (<code>insert_after: \"territory\"</code>). Step 13 copies both into the Customer.",
		])))

	s.append(step(17, "s-wiring", "Wiring: hooks.py and the setup functions",
		"How Frappe finds all of the above, and how it is re-applied on every migrate.",
		["hooks.py", "overrides/lead.py → apply_lead_customizations"],
		why("All layout changes (custom fields, property setters, field order) are created by code, not by clicking in Customize Form. That makes them repeatable on any site: <code>bench migrate</code> runs the <code>after_migrate</code> list in order, and every function in it is idempotent.")
		+ py("hooks.py", "doctype_js", "after_migrate", "doc_events", "override_doctype_dashboards")
		+ explain([
			"<code>doctype_js</code>: a list per DocType; the shared helper is loaded before the form's controller so its functions exist when the controller runs.",
			"<code>after_migrate</code>: the three setup functions first (they create the fields), then the three backfills (they fill the tables).",
			"<code>doc_events</code>: dotted paths to our functions. Frappe calls each one with <code>(doc, method)</code>; a list runs in order.",
			"<code>override_doctype_dashboards</code>: lets us add Leads Activity to ERPNext's Connections tab without editing ERPNext.",
		])
		+ py(LD, "CUSTOM_FIELDS", "OBSOLETE_CUSTOM_FIELDS", "apply_lead_customizations")
		+ explain([
			"<code>create_custom_fields(…, update=True)</code> creates missing fields and updates existing ones.",
			"<code>make_property_setter</code> replaces any existing setter for the same field and property, so re-running never duplicates.",
			"<code>OBSOLETE_CUSTOM_FIELDS</code> removes the HTML field used by the very first version of the activities section, replaced by the table in step 6.",
		])))

	s.append(step(18, "s-tests", "Automated tests",
		"57 tests check every rule above against a real ERPNext database, then undo everything they created.",
		["custom_crm_updates/doctype/leads_activity/test_leads_activity.py", "tests/test_crm_automation.py"],
		why("Each test class extends Frappe's <code>FrappeTestCase</code>, which rolls the database back after the class finishes. Tests create their own Leads, Opportunities and activities, so they never depend on (or change) real data. This site has no default Customer Group, so the tests stand one in with a <b>mock</b> instead of writing a real default.")
		+ py("custom_crm_updates/doctype/leads_activity/test_leads_activity.py", "make_lead", "customer_defaults")
		+ py("tests/test_crm_automation.py", "TestTendering.test_submitted_tender_marks_activity_done_and_opportunity_won")
		+ explain([
			"<code>make_lead</code> creates a test Lead with the mandatory Customer Group and Territory filled in.",
			"<code>customer_defaults</code> temporarily replaces <code>frappe.db.get_default</code> so ERPNext sees a Customer Group and Territory; a real default would stay in the cache after the rollback.",
			"The sample test follows the whole Tendering flow: two Tendering activities, Submit one tender, then check that only <em>its</em> activity became Done and the Opportunity became Won.",
			"Run them on a dedicated test site: <code>bench --site &lt;test-site&gt; run-tests --app custom_crm_updates</code>. On a live site ERPNext saves its sample test records permanently.",
		])))
	return "".join(s)
