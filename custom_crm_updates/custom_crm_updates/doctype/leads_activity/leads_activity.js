// Copyright (c) 2026, smart and contributors
// For license information, please see license.txt

// A Registration activity needs at least one attachment. The rule itself is
// enforced on the server (LeadsActivity.validate_registration_attachment);
// here it is shown on the form: the Attachments table is marked mandatory as
// soon as the Type is Registration (mandatory_depends_on in
// leads_activity.json), and saving without a file is refused with the same
// message, before Frappe's generic Missing Fields dialog can appear.

const REGISTRATION = "Registration";

// A row the user added but never picked a file for is not an attachment.
function attached_files(frm) {
	return (frm.doc.attachments || []).filter((row) => row.attachment);
}

frappe.ui.form.on("Leads Activity", {
	setup(frm) {
		frm.set_query("assigned_to", () => ({
			query: "frappe.core.doctype.user.user.user_query",
		}));
	},

	validate(frm) {
		if (frm.doc.activity_type === REGISTRATION && !attached_files(frm).length) {
			frappe.throw({
				title: __("مرفق مطلوب"),
				message: __(
					"لا يمكن حفظ Activity من النوع Registration بدون مرفقات. أرفق ملفاً واحداً على الأقل في جدول Attachments."
				),
			});
		}
	},

	link_type(frm) {
		// A Link picked for the previous type points at the wrong doctype.
		frm.set_value("link_name", null);
	},
});
