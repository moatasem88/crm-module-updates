## Custom CRM Updates

CRM customizations for ERPNext v14: Lead and Opportunity layout changes, the
Leads Activity DocType and its automations, Opportunity tendering (with the
contracting app's Project Tender), and contacts tables.

### Installation

```bash
cd ~/frappe-bench
bench get-app https://github.com/moatasem88/crm-module.git
bench --site <site> install-app custom_crm_updates
bench --site <site> migrate
bench build --app custom_crm_updates
bench restart
```

`install-app` creates the DocTypes; `migrate` runs the `after_migrate` hooks
that add the Custom Fields and Property Setters to Lead, Opportunity and
Project Tender and fill the read-only tables. Requires ERPNext; the
tendering automation also needs the **contracting** app (without it, that
part is skipped).

Documentation: `docs/custom-crm-updates.html` (overview, for presentations)
and `docs/custom-crm-updates-code-guide.html` (code walkthrough). Both work
offline.

### Lead customizations

Layout changes are applied on every `bench migrate` by
`custom_crm_updates.overrides.lead.apply_lead_customizations` (`after_migrate` hook).
The function is idempotent.

- **Is Company** (`custom_is_company`). When this is checked, the person fields
  (Salutation, First/Middle/Last Name, Gender, Job Title) are hidden and
  Organization Name becomes mandatory. On save, the person fields are cleared
  and Full Name is set to Organization Name (`clear_person_fields`,
  `before_validate`).
- **Customer Group and Territory** are mandatory. Customer Group is a new
  field (`custom_customer_group`) placed next to Territory in the Organization
  section; Territory is the core field. When the Lead is converted, the
  Customer takes both from the Lead.
  - They are declared with `mandatory_depends_on`, which the form enforces, and
    checked again on the server for user saves (REST API, Data Import) by
    `validate_customer_fields`.
  - They are not `reqd`, because Frappe would then enforce them on every
    insert. That would break the Leads ERPNext creates by itself (website
    contact form, an Opportunity made from an email address, appointments),
    where there is no one to ask. Those Leads are saved without the fields and
    must be completed before they can be converted.
- **Section order.** The Organization section comes before Contact Info. This
  is stored as a `field_order` Property Setter, the same thing Customize Form
  saves (`apply_field_order` / `move_section`).
- **Address & Contacts tab** (`custom_address_contacts_tab`). The Address &
  Contacts section (address list, City, State, Country, contact list) is moved
  out of Details into its own tab. The tabs are now: Details, Address &
  Contacts, Activities, Comments, Connections.
  - The section is moved to just before Activities. A Tab Break takes every
    field up to the next tab, so this keeps Qualification and Additional
    Information in Details.
  - Inside its own tab, the section's heading is blank (the tab already names
    it) and it is no longer collapsible (Property Setters on `address_section`).
  - The tab also shows on new Leads, so City/State/Country can be filled in
    before saving.
- **Create menu** (`public/js/lead.js`). "Prospect" is removed and "Activity"
  is added. "Activity" opens a new Leads Activity with Link Type = Lead and
  Link = the current Lead. "Action > Add to Prospect" is unchanged.
- **Activities tab.** A new "Leads Activities" section at the top shows the
  Lead's activities in a standard child-table grid (`custom_leads_activities`,
  rows of the **Leads Activity Detail** child DocType). The grid shows activity,
  type, date, status and assigned user. The attachment count is hidden by
  default; add it back with the grid's ⚙ → Add / Remove Columns, where each
  user can also change widths and order.
  - Rows are ordered ascending by creation: oldest at the top, a new activity
    appended at the bottom. Ordering by creation rather than by the activity's
    own Date is what keeps a back-dated activity at the bottom too.
  - The table is read-only because each row mirrors a Leads Activity. Creating,
    editing, re-linking or deleting an activity rebuilds the affected Lead's
    rows (`sync_activity_table`).
  - Each rebuild updates the Lead's modified time. This means a Lead form left
    open elsewhere cannot overwrite the rows when saved, and it reloads
    instead.
  - The "New Activity" button above the grid replaces Add Row.
  - Duplicating a Lead does not copy the rows (`no_copy`).
  - `after_migrate` backfills any Lead whose rows are missing or out of date.
- **Connections tab.** It shows a Leads Activity count, and its "+" button
  creates an activity already linked to the Lead.

### Opportunity customizations

These are applied on every `bench migrate` by
`custom_crm_updates.overrides.opportunity.apply_opportunity_customizations`.

- **Activities tab.** A new "Opportunity Activities" section works like the
  Lead's. It is the same read-only grid (`custom_leads_activities`, made of
  Leads Activity Detail rows), with a "New Activity" button and ⚙ column
  settings. It lists only the activities whose Link Type is Opportunity and
  whose Link is this Opportunity. **Each Opportunity has its own activities,
  separate from the Lead's.** An Opportunity made from a Lead does not show or
  copy that Lead's activities, and the Lead does not show the Opportunity's.
- **Create menu.** An "Activity" item is added. The core items are unchanged.
- **Connections tab.** It shows a Leads Activity count, and its "+" button
  creates an activity already linked to the Opportunity.
- Opportunity activities do not change any Lead's Qualification Status. That
  automation applies only to activities linked to a Lead.
- **Project Tender tab** (between Items and Activities). It is a read-only
  table (`custom_project_tenders`, made of Opportunity Project Tender rows) of
  the Project Tenders created for this Opportunity, oldest first. It shows the
  tender, project name, client, status and total sell price; the activity and
  creation date are available via ⚙. Below it is **Approved Project Tender**
  (`custom_approved_project_tender`), a read-only link set by the popup
  described next. See "Tendering → Project Tender" below.
- **Status.** "Tendering" and "Won" are added to the Status options (a Property
  Setter extending core's list). ERPNext only recomputes Opportunity status on
  quotation events, so these are kept on a normal save.
- **Status → Won asks which tender was approved.** Choosing "Won" on the form
  opens a popup listing this Opportunity's Project Tenders (tender, project
  name, status, total sell price). The tender picked there is stored in
  Approved Project Tender, and saving the Opportunity sets that tender to
  **Won** (`apply_approved_tender`). The other tenders are left as they are.
  - Dismissing the popup puts the Status back to what it was, so a Won is never
    left behind without an approved tender.
  - An Opportunity with no Project Tenders at all says so and stays Won.
  - Setting the status to Won outside the form (list view, bulk edit, API)
    marks no tender: there is nobody to ask.
- **Contact Person** lists the Opportunity's own contacts, not its party's
  (core filters it by `frappe.dynamic_link`, i.e. by the Lead/Customer/Prospect
  the Opportunity is for).
- **Contacts tab.** Core's contact list (`contact_html`) is hidden and replaced
  by a read-only **Contacts** table; see "Contacts table" below.

The Lead and Opportunity sections share code:

- `activity_table_fields`, `sync_activity_table` and `add_to_dashboard` in
  `leads_activity.py`. Adding another doctype to `TABLE_DOCTYPES` there, plus
  its custom fields, extends the feature to it.
- `public/js/leads_activity_section.js` for the buttons, and
  `show_when_empty`. Frappe hides a read-only field with no value, so without
  it an empty table, its "New …" button and possibly its whole tab would
  disappear.
- `custom_crm_updates/mirror_table.py` writes the rows of all these read-only tables.
- `backfill_activity_tables` (`after_migrate`), which fills the tables of both
  doctypes.

### Customer customizations

- **Create > Opportunity** (`public/js/customer.js`, wired by `doctype_js`).
  ERPNext already maps a Customer to an Opportunity (`make_opportunity` sets
  `opportunity_from` = Customer and `party_name` = this Customer) but only
  offers it through the Connections tab's "+". The same mapper is added to the
  Create menu, so the Opportunity is built exactly as the rest of ERPNext
  builds it. Nothing else on the Customer form is changed.

### Leads Activity (DocType)

This DocType logs a CRM touchpoint against a Lead, Prospect or Opportunity.
Records are named `CRM-ACT-.YYYY.-.#####`.

| Field | Type | Notes |
| --- | --- | --- |
| Type (`activity_type`) | Select | Call, Meeting, Site Visit, Registration, Tendering, Other |
| Status (`status`) | Select | Planned (default), In Process, Done, Failed, Closed, Waiting Reply |
| Date (`date`) | Date | defaults to today |
| Assigned To (`assigned_to`) | Link → User | `assigned_to_name` is fetched from it |
| Link Type (`link_type`) | Select | Lead, Prospect, Opportunity |
| Link (`link_name`) | Dynamic Link | the list follows Link Type. Changing Link Type clears Link |
| Attachments (`attachments`) | Table → Leads Activity Attachment | one file per row (Attach + Description) |

Validation (`LeadsActivity.validate`):

- An activity of type **Registration** cannot be saved unless its Attachments
  table has at least one file. This holds for every Link Type, for an activity
  that is changed to Registration, for emptying the table on an existing one,
  and for the API and Data Import as well as the form
  (`validate_registration_attachment`).
  - A row with no file picked does not count as an attachment.
  - On the form, the table is marked **mandatory** as soon as the Type is
    Registration (`mandatory_depends_on` on the `attachments` field, so the red
    asterisk follows the Type), and `leads_activity.js` refuses the save with
    the same message. The form's `validate` runs before Frappe's own mandatory
    check, so this message is what the user sees rather than the generic
    "Missing Fields" dialog. Frappe v14 evaluates `mandatory_depends_on` on the
    form only, which is why the server check is the one that holds.

Automation for activities whose Link Type is Lead (`LeadsActivity.on_update`):

- **A Registration activity is created.** The Lead's Qualification Status
  becomes *In Process*. This happens only on creation, and a Lead that is
  already *Qualified* is not downgraded.
- **An activity's status becomes Done.** This includes an activity created
  directly as Done, or a Done activity re-pointed to another Lead. The Lead
  becomes *Qualified*. Qualified By is set to the activity's Assigned To (or
  the current user), and Qualified On is set to today.
- **A Registration activity is Done** (created as Done, changed to Done, or a
  Done activity changed to Registration). The Lead is converted to a Customer
  (`convert_lead_to_customer`) using ERPNext's own Lead → Customer mapping.
  That mapping also links the Lead's contacts and addresses to the Customer and
  sets the Lead's status to *Converted*. A Lead that already has a Customer is
  not converted again.
  - The Customer's Customer Group and Territory come from the Lead. For a
    Lead saved without them, the Selling Settings defaults are used if set;
    otherwise the activity save is refused with a message saying to set them
    on the Lead.

These updates are written with `db_set`. This means a user who can log an
activity but cannot edit the Lead still triggers them, and unrelated Lead
validation errors do not block them. Each update adds a comment to the Lead's
timeline and refreshes the Lead if someone has it open.

A Lead that has activities cannot be deleted until those activities are
deleted.

### Tendering → Project Tender

This is in `custom_crm_updates/overrides/project_tender.py`. Project Tender belongs
to the **contracting** app, which is left unchanged: custom_crm_updates adds two
read-only Custom Fields to it, **Opportunity** (`custom_opportunity`) and
**Leads Activity** (`custom_leads_activity`).

- **A Tendering activity is saved on an Opportunity.** A Project Tender is
  created, one per activity. Saving the activity again never creates a second
  one, but each new Tendering activity gets its own.
  - Project Name is the Opportunity's title.
  - Client is the Opportunity's Customer. If the Opportunity is for a Lead,
    that Lead is converted to a Customer first (same conversion as above, using
    the Lead's Customer Group and Territory). If it is for a Prospect, an existing
    Customer with the Prospect's name is used, or one is created.
  - The Opportunity's status becomes **Tendering**, unless it is already *Won*
    or *Converted*.
  - It is created as the system (`ignore_permissions`): Sales Users have no
    Project Tender role.
  - A message names the new tender and links to it, so whoever saved the
    activity knows it was created.
- **A Project Tender can only be Submitted once it is costed.** All three cost
  tables — Direct Cost Details, Indirect Cost Details and Overhead / Deduction
  Details — must have at least one row; otherwise the save is refused, naming
  the tables that are still empty (`validate_submitted_rows`, Project Tender
  `validate`). Emptying one of them on an already-submitted tender is refused
  too.
- **A Project Tender's status becomes Submitted.** The activity that created it
  is set to **Done** (a full save, so its tables update). The Opportunity is
  left as it is: several tenders can be submitted for one Opportunity, and
  which one was approved is decided when the Opportunity itself is set to Won
  (see "Status → Won" above).
- **An Opportunity is saved as Won** with an approved tender. That tender is
  set to **Won** as the system, which runs the contracting app's own Won
  automation (its Project and Sales Order). If that automation refuses the
  tender, the whole save is rolled back — Opportunity included — rather than
  leaving a Won Opportunity whose approved tender never got there.
- The Opportunity's Project Tender table is updated on every Project Tender
  save and delete.
- Each step adds a comment to the Opportunity's (or the tender's) timeline.

### Contacts table (Lead and Opportunity)

This is in `custom_crm_updates/overrides/contact.py`. Core's contact list
(`contact_html`) is hidden and a read-only **Contacts** table
(`custom_contacts`, made of Leads Contact Detail rows) is shown in its place.
On the Lead it is at the end of the Address & Contacts tab; on the Opportunity,
at the end of the Contacts tab.

- **Rows.** Contact, full name, email, mobile, designation and primary flag.
  Phone and "Linked Via" are available via ⚙. Rows are ordered ascending by
  creation, like every table here: oldest at the top, a new contact appended at
  the bottom. The primary contact is shown by its own column rather than by
  being sorted to the top.
  - **On an Opportunity: its own contacts, and only those.** The contacts of
    the Lead it was made from do not appear (core's own contact list does merge
    them in, but it is hidden).
  - **On a Lead: its own contacts *and* those of every Opportunity made from
    it**, so the Lead stays the full picture of who is involved. The Lead's own
    come first, then each Opportunity's, oldest Opportunity first; "Linked Via"
    names the record each row came from, and a contact linked to both is listed
    once.
  - The Lead follows an Opportunity's contacts being added, removed, re-pointed
    at another Lead, or the Opportunity itself being deleted
    (`refresh_party_lead`, Opportunity `on_update` / `on_trash`).
- **Keeping it current.** The table is recomputed on every Lead/Opportunity
  save. Saving or deleting a Contact also updates every Lead and Opportunity it
  is (or was) linked to.
- **New Contact.** The button above the table replaces core's. It creates the
  Contact linked to the record it was pressed on — on an Opportunity that is
  the Opportunity itself, where core's button would have linked it to the
  Opportunity's party.

### Messages

The error messages and alerts of the automations above are written in Arabic,
with field names, DocType names and status values left in English exactly as
they appear in the system (`Project Tender`, `Submitted`, `Registration`,
`Attachments`, …). They are still wrapped in `_()`, so a site can override them
through a translation file.

Every user on this bench has their language set to `en`, which is why the
Arabic is the source string: Frappe resolves `_()` against the user's language,
so an `ar.csv` translation would never be shown to them.

Timeline comments (the audit trail each automation leaves on the record) are
left in English, matching the comments the app already wrote.

Tests: `custom_crm_updates/custom_crm_updates/doctype/leads_activity/test_leads_activity.py`
and `custom_crm_updates/tests/test_crm_automation.py`.

#### License

MIT
