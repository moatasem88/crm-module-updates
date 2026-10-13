"""Guide content, part B: steps 9-18."""

from lib import doctype_table, js, json_field, py, py_lines
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
		+ py_lines(LA, 64, 67, "leads_activity.py · inside LeadsActivity.on_update · lines 64–67")
		+ py(PT, "CUSTOM_FIELDS", "apply_project_tender_customizations", "create_project_tender_for_activity")
		+ explain([
			"The import sits inside the function (a <em>local import</em>) so the two modules can call each other without a circular import at load time.",
			"<code>frappe.db.exists(\"Project Tender\", {ACTIVITY_FIELD: activity.name})</code>: if a tender already exists for this activity, stop. Saving the activity again never creates a second one; a new Tendering activity creates a new one.",
			"Project Name = the Opportunity's title (falling back to customer name, then its ID).",
			"<code>insert(ignore_permissions=True)</code>: Sales Users have no Project Tender role, but the automation must still work for them.",
			"The Opportunity moves to Tendering unless it is already Won or Converted, and a timeline comment records which activity created which tender.",
			"<code>frappe.msgprint</code> then tells whoever saved the activity that the tender was created, with a link to it — the activity's own form would otherwise show nothing.",
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
		+ py(PT, "on_update", "on_trash", "tender_rows", "sync_opportunity_tenders", "backfill_opportunity_tenders")
		+ explain([
			"<code>insert_after: \"total\"</code>: the last field of the Items tab, so the new tab appears right before Activities. <code>depends_on: \"eval:!doc.__islocal\"</code> hides the tab on an unsaved Opportunity.",
			"<code>on_update</code> syncs both the current Opportunity and the previous one if the link changed (the <code>before</code> copy), then checks for Submitted (step 12). <code>skip_opportunity_sync</code> is the one case it skips: step 18, where the Opportunity is mid-save and refreshes its own table.",
			"<code>tender_rows</code> orders by <code>creation asc</code>: oldest tender at the top, each new one appended at the bottom. Every table in this module uses that one rule.",
			"<code>\"date(creation) as creation_date\"</code> asks the database for just the date part of when the tender was created.",
			"<code>backfill_opportunity_tenders</code> fills the table after a migrate for tenders that already exist.",
		])))

	s.append(step(12, "s-submitted", "A tender can only be Submitted when it is costed, and then its activity is Done",
		"A Project Tender needs rows in all three cost tables before it can be Submitted; once it is, the activity that created it is marked Done. The Opportunity is left alone.",
		["overrides/project_tender.py → validate_submitted_rows, mark_activity_done", "hooks.py → Project Tender validate"],
		why("Submitting a tender means sending a price to the client, so the costing has to be there: Direct Cost, Indirect Cost and Overhead / Deduction all need at least one row. The check sits in <b>validate</b> rather than on the status change alone, so emptying a table on an already-submitted tender is refused too. Whether the Opportunity is Won is a separate, human decision — several tenders can be submitted for one Opportunity and only one of them wins (step 18).")
		+ py(PT, "SUBMITTED_REQUIRED_TABLES", "validate_submitted_rows", "mark_activity_done")
		+ explain([
			"The message names the tables that are still empty, using their own labels, instead of failing on whichever field the user reaches first.",
			"<code>doc.has_value_changed(\"status\")</code> (in <code>on_update</code>, step 11) is true only on the save where the status actually changes, so re-saving a Submitted tender does not touch the activity again.",
			"The activity gets a <b>full save</b> (not <code>db_set</code>) so its own <code>on_update</code> runs too and the Opportunity's activities table shows Done.",
			"<code>mark_activity_done</code> returns early if there is nothing to do (no linked activity, or already Done). <code>activity.flags.ignore_permissions = True</code>: whoever submits the tender may not have rights on activities.",
			"Saving the activity re-runs its <code>on_update</code>; the Tendering check there finds the existing tender and does not create another.",
		])))

	s.append(step(13, "s-convert", "Registration Done → the Lead becomes a Customer",
		"When a Registration activity on a Lead is Done, the Lead is converted to a Customer using its own Customer Group and Territory.",
		["leads_activity.py → on_update", "overrides/lead.py → convert_lead_to_customer, insert_customer"],
		why("We reuse ERPNext's own Lead → Customer mapping (<code>_make_customer</code>), the same code behind the Lead's Create ▸ Customer button. It copies the Lead's details and, when the Customer is saved, links the Lead's contacts and addresses to it and marks the Lead Converted. We only fill in what the mapping leaves out.")
		+ py_lines(LA, 86, 91, "leads_activity.py · inside LeadsActivity.on_update · lines 86–91")
		+ py(LD, "convert_lead_to_customer", "insert_customer")
		+ explain([
			"The trigger fires when a Registration activity <em>becomes</em> Done, or a Done activity is changed to Registration.",
			"<code>frappe.db.get_value(\"Customer\", {\"lead_name\": lead})</code>: ERPNext stores the source Lead on the Customer, so an already-converted Lead is never converted twice.",
			"The mapping copies Territory (same field name on both) but takes Customer Group from the Selling Settings default; the Lead's own Customer Group (step 16) overrides it.",
			"<code>insert_customer</code> checks both fields first and throws a clear message naming what is missing and where to set it, instead of ERPNext's bare \"mandatory field\" error.",
		])))

	s.append(step(14, "s-contacts", "Contacts shown as a table",
		"On Lead, Opportunity and Customer, ERPNext's contact list is replaced by a read-only Contacts table with a New Contact button.",
		["overrides/contact.py", "overrides/customer.py", "Leads Contact Detail (child DocType)", "hooks.py → Lead, Opportunity, Customer, Contact events"],
		why("Contacts are linked to records through rows in the Contact's <b>links</b> table (Dynamic Links). An Opportunity lists the contacts linked to <em>it</em> and only those, so a deal's contact list is not diluted by the Lead's, and a Customer likewise lists only its own, so a contact added to the client after the sale stays out of the deal it came from. A Lead lists its own <em>and</em> those of every Opportunity made from it <em>and</em> those of the Customer it became, so the Lead stays the full picture of who is involved. The table is a mirror of those links, kept current from two directions: the record recomputes its own table whenever <em>it</em> is saved, and a Contact pushes its rows to every record it is (or was) linked to whenever <em>the Contact</em> is saved or deleted. Because the record recomputes on its own save, a stale form cannot leave wrong rows, so this table does not need the modified-timestamp bump.")
		+ py(CT, "contact_table_fields", "contact_sources", "get_contact_rows", "sync_contact_table")
		+ explain([
			"<code>filters=[[\"Dynamic Link\", \"link_doctype\", \"=\", …], …]</code> is a child-table filter: Contacts that have a link row pointing at the given record.",
			"<code>contact_sources</code> decides where the rows come from: one source for an Opportunity and for a Customer, and for a Lead itself plus each of its Opportunities (oldest first) and then its Customer. A contact linked to more than one is listed once, under the first source that has it.",
			"A Customer counts as the Lead's whether it carries <b>From Lead</b> or <b>From Opportunity</b> — the two ways ERPNext records the same conversion — so the roll-up holds however the Customer was created.",
			"ERPNext's own Lead → Customer conversion links the Lead's contacts to the Customer as well, so those are the Customer's contacts too and show on both. On the Lead each one is still listed once, under the Lead.",
			"Ascending by creation, like every table here: oldest at the top, a new contact appended at the bottom. The primary contact is shown by its own column rather than sorted to the top. <code>linked_via</code> names the record each row came from.",
			"<code>order_by=\"`tabContact`.…\"</code> names the table explicitly because the Dynamic Link join also has a <code>creation</code> column.",
		])
		+ py(CT, "refresh_own_table", "refresh_after_insert", "contact_links", "lead_of", "lead_in", "affected_docs", "refresh_party_lead", "on_contact_update", "on_contact_trash", "backfill_contact_tables")
		+ explain([
			"<code>refresh_own_table</code> (Lead, Opportunity and Customer <b>validate</b>) sets the rows on the document being saved, so they are written with it.",
			"<code>refresh_after_insert</code>: ERPNext links a new Lead's auto-created contact in <em>its</em> after_insert, after validate has run, so we refresh once more and write the rows.",
			"<code>affected_docs</code> turns a contact's links into the records to update: the Leads, Opportunities and Customers it is linked to, plus the Lead behind each of those, which rolls their contacts up.",
			"<code>lead_of</code> reads that Lead from the database; <code>lead_in</code> reads it from a document in hand, which is the only way to get it from the version <em>before</em> a save and from one being deleted.",
			"<code>refresh_party_lead</code> (Opportunity and Customer <b>on_update</b> / <b>on_trash</b>) keeps the Lead level when one appears, is re-pointed at another Lead, or is deleted - the contact itself never changed, so no Contact event would fire. Both Leads are refreshed on a re-point: the one it left and the one it joined.",
			"<code>backfill_contact_tables</code> also syncs every record that already has rows, which is what drops the party contacts the Opportunities mirrored before the two were separated.",
			"<code>on_contact_update</code> merges links before and after the save, so unlinking a contact removes its row from the old record.",
		])
		+ py("overrides/customer.py", "CUSTOM_FIELDS", "apply_customer_customizations")
		+ js("public/js/leads_activity_section.js", 89, 106)
		+ explain([
			"The Customer gets the same two custom fields from the same helper, inserted after its own <code>contact_html</code>, i.e. at the end of the <b>Address and Contact</b> section of the Contact &amp; Address tab.",
			"ERPNext's own contact list (<code>contact_html</code>) is hidden by a property setter on all three DocTypes. ERPNext still renders into it, just unseen, so nothing in its code breaks.",
			"The New Contact button is <code>frappe.new_doc(\"Contact\")</code>, like ERPNext's. The Contact form fills its Links table from <code>frappe.dynamic_link</code>, so we set that to <em>this</em> record first: on an Opportunity, ERPNext had left its party there, which would have created the contact on the Lead instead. On a Customer this is what keeps a contact added there out of the Opportunity it came from.",
			"<code>public/js/customer.js</code> calls the same two helpers as the Lead and the Opportunity (<code>show_when_empty</code> in setup, <code>add_contact_button</code> in refresh), so <code>leads_activity_section.js</code> is loaded ahead of it in <code>doctype_js</code>.",
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

	s.append(step(18, "s-approved", "Won Opportunity → the approved tender",
		"Setting an Opportunity to Won opens a popup listing its Project Tenders; the one the user picks becomes Won when the Opportunity is saved.",
		["public/js/opportunity.js", "overrides/project_tender.py → apply_approved_tender…", "overrides/opportunity.py → CUSTOM_FIELDS", "hooks.py → Opportunity validate, on_update"],
		why("One Opportunity can have several Project Tenders, so submitting one cannot decide which was approved — only the user knows, and the moment they know is when they close the Opportunity as Won. The popup therefore asks at exactly that point, and the answer is kept in a read-only field (<b>Approved Project Tender</b>) so the whole thing is one ordinary save: picking a tender in a dialog and writing it straight to the database would change the Opportunity under the form that is still open, and the user's own save would then be refused as out of date.")
		+ js("public/js/opportunity.js", 37, 46)
		+ js("public/js/opportunity.js", 58, 127)
		+ explain([
			"The <code>status</code> handler fires on every change of the field. Only a change <em>to</em> Won on a saved Opportunity opens the popup.",
			"<code>get_opportunity_tenders</code> is asked for the list rather than reading the mirror table, so it is the database's answer, and it is read as the system: Project Tender is a contracting DocType the Sales User closing the Opportunity has no role on.",
			"The Select's options are <code>{value, label}</code> pairs: the value is the tender's ID, the label adds project name, status and total sell price so the user can tell them apart. The popup's own text is Arabic; names and status values stay English.",
			"Dismissing the popup (Esc, ✕) puts the Status back to what it was — <code>remember_status</code> keeps that value, because a field handler is not told the old one. A Won with nothing behind it is never left on screen.",
			"No tenders at all (a direct award): a message says so and the Won stands.",
		])
		+ py(PT, "APPROVED_TENDER_FIELD", "get_opportunity_tenders", "validate_approved_tender", "apply_approved_tender", "set_tender_won", "refresh_tender_rows")
		+ explain([
			"<code>apply_approved_tender</code> (Opportunity <b>on_update</b>) acts only when the status is Won and something actually changed, so re-saving a Won Opportunity does not re-win anything.",
			"<code>set_tender_won</code> saves the tender in full, as the system, so the contracting app's own Won automation (its Project and Sales Order) runs exactly as if someone had set it by hand. Anything that automation refuses rolls the whole save back, Opportunity included, rather than leaving a Won Opportunity whose approved tender never got there.",
			"<code>refresh_tender_rows</code> rewrites the Opportunity's tender table through the document being saved and <em>without</em> the modified bump: the form that is saving would otherwise come back one step behind the database and refuse its next save. The tender is saved with <code>skip_opportunity_sync</code> so the usual sync does not do it the other way.",
			"<code>validate_approved_tender</code> guards the field against a save made over the API, where nothing has filtered the list.",
			"The other tenders are left exactly as they are: losing a tender is not the same as cancelling it.",
		])))

	s.append(step(19, "s-registration-attachment", "Every activity on a Lead or an Opportunity needs an attachment",
		"The Attachments table is marked mandatory as soon as the Link Type is Lead or Opportunity, or the Type is Registration, and saving without a file is refused.",
		["leads_activity.json → attachments", "leads_activity.js → validate", "leads_activity.py → LeadsActivity.validate"],
		why("What the CRM follows a client up with is its paperwork, so an activity on a Lead or an Opportunity with nothing on file is not a record of anything — whatever its type. A Registration needs one whatever it is linked to, a Prospect included, because it is the activity that converts the Lead into a Customer (step 13), so the document it was registered with has to be on file. Three layers, each doing what only it can: <code>mandatory_depends_on</code> on the table puts the red asterisk there the moment the Type or the Link Type calls for it (<code>reqd</code> could not, because the rule depends on other fields); the form's <b>validate</b> refuses the save with our own message; and the server's <b>validate</b> is the one that actually holds, for the API and Data Import as well as the form.")
		+ json_field(LA.replace(".py", ".json"), "attachments")
		+ js("custom_crm_updates/doctype/leads_activity/leads_activity.js", 12, 48)
		+ py(LA, "ATTACHMENT_LINK_TYPES", "LeadsActivity.validate", "LeadsActivity.validate_attachment")
		+ explain([
			"Frappe v14 evaluates <code>mandatory_depends_on</code> on the form only (<code>layout.js</code> turns it into <code>reqd</code> on every field change), which is why the server check stays — and why widening it cannot break the activities created over the API.",
			"The form's <code>validate</code> runs <em>before</em> Frappe's own mandatory check (<code>form.js</code> triggers validate, then <code>save.js</code> calls <code>check_mandatory</code>), so the user sees this message rather than the generic Missing Fields dialog.",
			"Two messages, so each says what is actually wrong: the Registration one names the type, the other names what the activity is linked to.",
			"A row with no file picked is not an attachment, on both sides: counting it would hand the user Frappe's \"mandatory field in row 1\" error instead of the one that says what is needed.",
			"It applies to an activity that <em>becomes</em> a Registration, to one moved onto a Lead or an Opportunity, and to emptying the table on an existing one. Only a Prospect can hold an activity with no attachment, and only for the other types.",
			"Separately, the Opportunity itself must have an attachment before any activity can be logged against it (step 23) — that one is about the Opportunity's paperwork, this one about the activity's.",
		])))

	s.append(step(20, "s-opportunity-name", "Opportunity Name, Description and the title",
		"Two fields at the top of the Opportunity: a name and a description. The name is also the Opportunity's title, so it is what lists, links, breadcrumbs and reports show.",
		["overrides/opportunity.py → CUSTOM_FIELDS, set_title", "hooks.py → Opportunity validate"],
		why("ERPNext names an Opportunity <code>CRM-OPP-…</code> and shows its <code>title</code> wherever a readable name is needed, falling back to the party's name — so every Opportunity of the same client reads the same. Rather than add a second “name” the user has to keep in step with the title, <b>validate</b> copies the Opportunity Name into <code>title</code> on every save: one field to fill, and ERPNext's own title stays the thing that is displayed. An Opportunity with no name keeps core's fallback, so nothing that already exists loses its title.")
		+ py(OP, "CUSTOM_FIELDS")
		+ py(OP, "set_title")
		+ explain([
			"<code>insert_after: \"naming_series\"</code> puts both fields at the very top of the Details tab, in the same section as Opportunity From and Status.",
			"Our hook runs <em>after</em> ERPNext's own <code>validate</code> (Frappe runs the controller method first, then the <code>doc_events</code> hooks), so it has the last word on <code>title</code> — core only sets it when it is empty.",
			"<code>title</code> stays hidden, as ERPNext leaves it: it is filled for the user, so there is nothing to type into it.",
			"A side effect worth knowing: a Project Tender created from a Tendering activity takes its <code>project_name</code> from <code>opportunity.title</code> (step 10), so tenders are now named after the Opportunity Name.",
		])))

	s.append(step(21, "s-opportunity-value", "Opportunity Value moved above Organization, with a Targeted Amount",
		"The money section comes before the client's details, and holds a new Targeted Amount — the figure the Opportunity Breakdown splits up.",
		["overrides/opportunity.py → apply_field_order, TARGETED_AMOUNT", "overrides/lead.py → move_section"],
		why("A standard field cannot be moved with a custom field's <code>insert_after</code> — only a <code>field_order</code> property setter can reorder ERPNext's own fields, which is exactly what Customize Form saves when you drag a field. So the order is rebuilt in code from the <em>current</em> one: whatever Customize Form or a future ERPNext upgrade did is kept, and only our one move is applied on top. <code>move_section</code> is the same helper the Lead's layout uses (step 2), because moving a section means moving every field up to the next section break, not just its heading.")
		+ py(OP, "VALUE_SECTION", "apply_field_order")
		+ explain([
			"Targeted Amount is a custom field inserted after <code>base_opportunity_amount</code>, the last field of ERPNext's Opportunity Value section, so it lands <em>inside</em> that section and travels with it when the block moves.",
			"<code>options: \"currency\"</code> makes it show in the Opportunity's own currency, like ERPNext's own amounts.",
			"The Opportunity Breakdown and Attachments sections are created after <code>territory</code> — Organization's last field — rather than after the value section: anything inserted after the value section would come between it and Organization, which is precisely where it must not be.",
			"<code>if new_order == order: return</code> keeps it idempotent: once the setter is there, the next migrate finds the order already right and writes nothing.",
			"Reordering is cosmetic only — no data moves, and the fields themselves are untouched.",
		])))

	s.append(step(22, "s-opportunity-breakdown", "Opportunity Breakdown: the Targeted Amount split between trades",
		"A table under Organization splits the Targeted Amount between civil, mec, elec and elev — each row a percentage of it or a fixed amount, with the Final Value worked out for the user.",
		["custom_crm_updates/doctype/opportunity_contribution/", "overrides/opportunity.py → calculate_contributions", "public/js/opportunity.js"],
		why("Final Value is <b>read-only</b> and computed in two places, each doing what only it can: the client script fills it as the user types, so the figures on screen are the ones they are deciding on; the server's <b>validate</b> works every row out again on save, which is what makes it right for the REST API, a Data Import, and a Targeted Amount changed without the rows being touched. Storing it rather than computing it on the fly keeps it reportable — a Currency field can be totalled and filtered, a formula cannot.")
		+ doctype_table("custom_crm_updates/doctype/opportunity_contribution/opportunity_contribution.json")
		+ js("public/js/opportunity.js", 61, 76)
		+ js("public/js/opportunity.js", 92, 108)
		+ py(OP, "PERCENTAGE", "calculate_contributions")
		+ explain([
			"A <b>Percentage</b> row's Contribution Value is a percentage of the Targeted Amount: 20 against 20,000 is 4,000. A <b>Fixed Amount</b> row's value is the amount itself.",
			"<code>frappe.ui.form.on(\"Opportunity Contribution\", …)</code> is how a child table's own fields are watched; <code>locals[cdt][cdn]</code> is the row that changed. The <code>[TARGETED_AMOUNT](frm)</code> handler on the parent redoes every row, because each percentage row is a share of it.",
			"<code>frappe.model.set_value</code> rather than an assignment: it redraws the grid row and marks the form dirty, so the figure the user sees is the figure that gets saved.",
			"On the server, <code>flt(value, row.precision(\"final_value\"))</code> rounds to the currency's own precision, so the stored number is the one the form shows.",
			"<code>final_value</code> uses <code>options: \"currency\"</code>; for a child row Frappe reads that field from the parent Opportunity, so the breakdown is in the Opportunity's currency.",
		])))

	s.append(step(23, "s-opportunity-attachments", "An Opportunity needs an attachment — and so does an Activity on it",
		"An Opportunity cannot be saved while its Attachments table is empty, and no Activity can be created from one that is.",
		["custom_crm_updates/doctype/opportunity_attachment/", "overrides/opportunity.py → validate_attachments, validate_activity_source", "public/js/leads_activity_section.js"],
		why("The same Attachment + Description pair the Leads Activity uses (step 19), as its own child DocType so the grid reads <b>Opportunity Attachment</b> rather than borrowing the activity's name. The rule is <em>not</em> <code>reqd</code> on the table: Frappe enforces <code>reqd</code> on every insert, including the Opportunities ERPNext creates by itself from an incoming email, which have nothing to attach — and that would break a core feature to enforce one of ours. It is a <b>validate</b> hook instead, skipped for the saves ERPNext makes with <code>ignore_permissions</code>/<code>ignore_mandatory</code>, exactly like the Lead's own mandatory fields (step 5). The activity rule reads the database rather than the form: an Activity is a separate document, and the paperwork has to be <em>saved</em> on the Opportunity, not merely typed into it.")
		+ doctype_table("custom_crm_updates/doctype/opportunity_attachment/opportunity_attachment.json")
		+ js("public/js/opportunity.js", 78, 90)
		+ py(OP, "ATTACHMENTS_FIELD", "validate_attachments")
		+ js("public/js/leads_activity_section.js", 37, 66)
		+ py(OP, "ACTIVITY_SOURCE_TABLES", "validate_activity_source")
		+ explain([
			"A row the user added but never picked a file for is not an attachment, on both sides: counting it would hand them Frappe's \"mandatory field in row 1\" error instead of the one that says what is needed. On the server the filter is <code>attachment != \"\"</code>, which leaves out both the empty and the never-filled rows.",
			"The form's <code>validate</code> runs before Frappe's own mandatory check, so the user sees our message rather than the generic Missing Fields dialog.",
			"<code>has_attachment</code> is checked inside <code>make_activity</code>, so all three ways in — <b>Create ▸ Activity</b>, the activities grid's <b>New Activity</b> and the Connections tab's <b>+</b> — are refused the same way, with an alert, before the activity form is even opened.",
			"<code>ACTIVITY_SOURCE_TABLES</code> is the one place that says which documents have such a table. A Lead and a Prospect have none, so activities on them are untouched; adding a Lead attachments table later means adding one line here.",
			"Activities the automation re-saves (<code>mark_activity_done</code>, step 12) pass <code>ignore_permissions</code> and are skipped: they were already allowed when the user created them.",
			"An Opportunity saved before this rule existed keeps its empty table until someone saves it — at which point the attachment is asked for.",
		])))

	s.append(step(24, "s-connections", "The Opportunity's Connections tab shows its client",
		"Opening an Opportunity shows the Lead, Customer or Prospect it belongs to in Connections, alongside its Activities, its Project Tenders and the Customer it was converted into.",
		["overrides/opportunity.py → PARTY_FIELDS, set_party_links, get_dashboard_data", "hooks.py → Opportunity validate, after_migrate"],
		why("A Connections card follows a link <em>into</em> this document, or an <b>internal link</b> — one plain field on it pointing out. The party is neither: it is a Dynamic Link (<code>opportunity_from</code> + <code>party_name</code>), and <code>get_internal_links</code> reads a single fieldname, so one card would have to serve three different DocTypes and would send a Lead-sourced Opportunity to a Customer that does not exist. Each party type therefore gets its own hidden mirror field, filled from <code>party_name</code> on every save, and each card reads its own. The mirrors are derived values, never typed into: <code>party_name</code> stays the one field anyone edits.")
		+ py(OP, "PARTY_FIELDS", "set_party_links", "backfill_party_links", "get_dashboard_data")
		+ explain([
			"<code>set_party_links</code> (Opportunity <b>validate</b>) fills the mirror for the current type and clears the other two, so an Opportunity re-pointed from a Lead to a Customer never shows both.",
			"<code>internal_links</code> maps each DocType to its mirror, and <code>transactions</code> adds the cards to a <b>Client</b> group. Frappe falls back to an ordinary search when an internal link comes back empty, which is what makes the Customer card show the Customers converted <em>from</em> this Opportunity (<code>Customer.opportunity_name</code>) on a Lead's Opportunity.",
			"Project Tender joins the same group through <code>non_standard_fieldnames</code>, guarded by a check that the contracting app is installed.",
			"<code>backfill_party_links</code> (after_migrate) fills the mirrors for Opportunities that predate the fields, writing straight to the database with no modified bump — the value is derived, not a change anyone made — and skipping rows that already agree, so re-running is free.",
			"Nothing about the party itself changed: the same Dynamic Link still drives the form, the Contacts table and the Opportunity's own rules.",
		])))

	s.append(step(25, "s-tests", "Automated tests",
		"131 tests check every rule above against a real ERPNext database, then undo everything they created.",
		["custom_crm_updates/doctype/leads_activity/test_leads_activity.py", "tests/test_crm_automation.py", "tests/test_opportunity.py"],
		why("Each test class extends Frappe's <code>FrappeTestCase</code>, which rolls the database back after the class finishes. Tests create their own Leads, Opportunities and activities, so they never depend on (or change) real data. This site has no default Customer Group, so the tests stand one in with a <b>mock</b> instead of writing a real default.")
		+ py("custom_crm_updates/doctype/leads_activity/test_leads_activity.py", "make_lead", "customer_defaults")
		+ py("tests/test_crm_automation.py", "TestTendering.test_submitted_tender_marks_only_its_activity_done", "TestApprovedTender.test_the_selected_tender_is_won_and_the_others_are_not")
		+ explain([
			"<code>make_lead</code> creates a test Lead with the mandatory Customer Group and Territory filled in.",
			"<code>customer_defaults</code> temporarily replaces <code>frappe.db.get_default</code> so ERPNext sees a Customer Group and Territory; a real default would stay in the cache after the rollback.",
			"The first sample test follows the whole Tendering flow: two Tendering activities, Submit one tender, then check that only <em>its</em> activity became Done and that the Opportunity was <em>not</em> moved on.",
			"The second closes the Opportunity as Won with one tender picked, and checks that only that tender became Won, that both the saved form and the database show it, and that the other tender is untouched.",
			"<code>tests/test_opportunity.py</code> covers steps 20–24: the title following the Opportunity Name, the attachment an Opportunity cannot be saved without (and the Activity that cannot be created without it), the Final Value arithmetic, and the field order the moved Opportunity Value section produces.",
			"Run them on a dedicated test site: <code>bench --site &lt;test-site&gt; run-tests --app custom_crm_updates</code>. On a live site ERPNext saves its sample test records permanently.",
		])))
	return "".join(s)
