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
  the Project Tenders created for this Opportunity. It shows the tender,
  project name, client, status and total sell price; the activity and creation
  date are available via ⚙. See "Tendering → Project Tender" below.
- **Status.** "Tendering" and "Won" are added to the Status options (a Property
  Setter extending core's list). ERPNext only recomputes Opportunity status on
  quotation events, so these are kept on a normal save.
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
- **A Project Tender's status becomes Submitted.** The activity that created it
  is set to **Done** (a full save, so its tables update), and the Opportunity's
  status becomes **Won**.
- The Opportunity's Project Tender table is updated on every Project Tender
  save and delete.
- Each step adds a comment to the Opportunity's timeline.

### Contacts table (Lead and Opportunity)

This is in `custom_crm_updates/overrides/contact.py`. Core's contact list
(`contact_html`) is hidden and a read-only **Contacts** table
(`custom_contacts`, made of Leads Contact Detail rows) is shown in its place.
On the Lead it is at the end of the Address & Contacts tab; on the Opportunity,
at the end of the Contacts tab.

- **Rows.** The table lists the same contacts core's list showed: contact,
  full name, email, mobile, designation and primary flag. Phone and "Linked
  Via" are available via ⚙.
  - On a Lead: the contacts linked to the Lead.
  - On an Opportunity: the contacts linked to the Opportunity, plus those of
    its party (Lead, Customer or Prospect).
- **Keeping it current.** The table is recomputed on every Lead/Opportunity
  save. Saving or deleting a Contact also updates every Lead and Opportunity it
  is (or was) linked to.
- **New Contact.** The button above the table replaces core's. It creates the
  Contact linked exactly as core's button did: to the Lead, or to the
  Opportunity's party.

Tests: `custom_crm_updates/custom_crm_updates/doctype/leads_activity/test_leads_activity.py`
and `custom_crm_updates/tests/test_crm_automation.py`.

#### License

MIT
