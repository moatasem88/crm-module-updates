// Copyright (c) 2026, smart and contributors
// For license information, please see license.txt

// An activity on a Lead or an Opportunity needs at least one attachment,
// whatever its type; a Registration needs one whatever it is linked to. The
// rule itself is enforced on the server (LeadsActivity.validate_attachment);
// here it is shown on the form: the Attachments table is marked mandatory as
// soon as the Type or the Link Type calls for it (mandatory_depends_on in
// leads_activity.json), and saving without a file is refused with the same
// message, before Frappe's generic Missing Fields dialog can appear.

const REGISTRATION = "Registration";
const ATTACHMENT_LINK_TYPES = ["Lead", "Opportunity"];

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
		const registration = frm.doc.activity_type === REGISTRATION;
		if (!registration && !ATTACHMENT_LINK_TYPES.includes(frm.doc.link_type)) return;
		if (attached_files(frm).length) return;

		// field and DocType names stay in English, as in the system
		frappe.throw({
			title: __("مرفق مطلوب"),
			message: registration
				? __(
						"لا يمكن حفظ Activity من النوع Registration بدون مرفقات. أرفق ملفاً واحداً على الأقل في جدول Attachments."
				  )
				: __("لا يمكن حفظ Activity على {0} بدون مرفقات. أرفق ملفاً واحداً على الأقل في جدول Attachments.", [
						frm.doc.link_type,
				  ]),
		});
	},

	link_type(frm) {
		// A Link picked for the previous type points at the wrong doctype.
		frm.set_value("link_name", null);
	},
});
