// Shared by lead.js, opportunity.js and customer.js (loaded ahead of them via
// doctype_js): buttons for the read-only tables those forms get from
// custom_crm_updates — custom_leads_activities (Activities tab) and
// custom_contacts (Contacts). The Customer has only the contacts table.

frappe.provide("custom_crm_updates");

// Documents whose attachments table must hold a file before an activity can
// be logged against them, so that the activity is a follow-up on paperwork
// that is on file. The same rule on the server refuses the activity even if
// it is reached another way (overrides/opportunity.py:
// validate_activity_source); here it is caught before the activity form is
// opened, so nothing is typed into a form that cannot be saved.
const ATTACHMENT_TABLES = { Opportunity: "custom_opportunity_attachments" };

// Frappe hides a read-only field with no value, so an empty mirror table
// would vanish, and with it its "New ..." button (and, if nothing else is
// in it, its whole tab). Keep it shown, still read-only, once the doc is
// saved. Call from the controller's setup: the controls outlive doc switches.
custom_crm_updates.show_when_empty = function (frm, fieldnames) {
	for (const fieldname of fieldnames) {
		const control = frm.fields_dict[fieldname];
		if (!control) continue;

		const get_status = control.get_status;
		control.get_status = function (explain) {
			const status = get_status.call(this, explain);
			// "None" for any other reason (hidden, permissions) still wins
			const hidden = cint(this.df.hidden) || cint(this.df.hidden_due_to_dependency);
			return status === "None" && !hidden && !frm.is_new() && frm.perm[this.df.permlevel || 0]?.read
				? "Read"
				: status;
		};
	}
};

// New Leads Activity pre-linked to the current Lead/Opportunity.
custom_crm_updates.make_activity = function (frm) {
	const { doctype, name } = frm.doc;
	// opportunity.js: no Activity before the Opportunity is approved
	if (custom_crm_updates.can_log_activity && !custom_crm_updates.can_log_activity(frm)) return;
	if (!custom_crm_updates.has_attachment(frm)) return;

	frappe.model.with_doctype("Leads Activity", () => {
		const activity = frappe.model.get_new_doc("Leads Activity");
		activity.link_type = doctype;
		activity.link_name = name;
		frappe.set_route("Form", "Leads Activity", activity.name);
	});
};

// False, with an alert saying so, while this document's attachments table is
// empty. A row with no file picked is not an attachment.
custom_crm_updates.has_attachment = function (frm) {
	const fieldname = ATTACHMENT_TABLES[frm.doc.doctype];
	if (!fieldname || (frm.doc[fieldname] || []).some((row) => row.attachment)) return true;

	frappe.msgprint({
		title: __("مرفق مطلوب"),
		// DocType and field names stay in English, as in the system
		message: __(
			"لا يمكن إنشاء Activity على {0} بدون مرفقات. أرفق ملفاً واحداً على الأقل في جدول Attachments داخل {0} واحفظه، ثم أعد المحاولة.",
			[frm.doc.doctype]
		),
		indicator: "red",
	});
	return false;
};

// Call from the controller's setup.
custom_crm_updates.setup_activity_make_method = function (frm) {
	// Connections tab "+": the default make_new can't fill a Dynamic Link.
	frm.make_methods = {
		...frm.make_methods,
		"Leads Activity": () => custom_crm_updates.make_activity(frm),
	};
};

// Call from the controller's refresh, after the core buttons are added.
custom_crm_updates.add_activity_buttons = function (frm) {
	if (frm.is_new() || !frappe.model.can_create("Leads Activity")) return;

	const make = () => custom_crm_updates.make_activity(frm);
	frm.add_custom_button(__("Activity"), make, __("Create"));

	// The table is read-only (rows mirror Leads Activity records), so it has
	// no Add Row; offer this instead.
	frm.fields_dict.custom_leads_activities?.grid?.add_custom_button(__("New Activity"), make, "top");
};

// The Contacts table replaces core's contact list, so it also takes over its
// "New Contact" button. The table lists the contacts linked to this document
// and only those, so the new contact is linked to this document too — on an
// Opportunity that means the Opportunity itself, not its party, which is what
// core's refresh leaves in frappe.dynamic_link (and what the Contact form
// reads to fill in Links). On a Lead it is the same link core set.
custom_crm_updates.add_contact_button = function (frm) {
	if (frm.is_new() || !frappe.model.can_create("Contact")) return;

	frm.fields_dict.custom_contacts?.grid?.add_custom_button(
		__("New Contact"),
		() => {
			frappe.dynamic_link = { doc: frm.doc, fieldname: "name", doctype: frm.doc.doctype };
			frappe.new_doc("Contact");
		},
		"top"
	);
};
