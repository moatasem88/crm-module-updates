// Copyright (c) 2026, smart and contributors
// For license information, please see license.txt

frappe.ui.form.on("Leads Activity", {
	setup(frm) {
		frm.set_query("assigned_to", () => ({
			query: "frappe.core.doctype.user.user.user_query",
		}));
	},

	link_type(frm) {
		// A Link picked for the previous type points at the wrong doctype.
		frm.set_value("link_name", null);
	},
});
