// Customer form: a "Create ▸ Opportunity" entry, and the read-only Contacts
// table that replaces core's contact list (fields:
// custom_crm_updates/overrides/customer.py; rows:
// custom_crm_updates/overrides/contact.py). A Customer lists its own contacts
// only — the Lead it was made from is where they are rolled up with the
// Lead's own and its Opportunities'.
//
// ERPNext already knows how to turn a Customer into an Opportunity — its
// make_opportunity mapper sets opportunity_from = "Customer" and party_name =
// this Customer — but it only wires that to the Connections tab's "+"
// (frm.make_methods), so there is no way to reach it from the Create menu.
// The same mapper is used here, so the Opportunity is built exactly as the
// rest of ERPNext builds it.

frappe.provide("custom_crm_updates");

frappe.ui.form.on("Customer", {
	setup(frm) {
		// an empty read-only table would be hidden, and its button with it
		custom_crm_updates.show_when_empty(frm, ["custom_contacts"]);
	},

	refresh(frm) {
		// the grid's own "New Contact" button, linked to this Customer
		custom_crm_updates.add_contact_button(frm);

		if (frm.is_new() || !frappe.model.can_create("Opportunity")) return;

		frm.add_custom_button(
			__("Opportunity"),
			() =>
				frappe.model.open_mapped_doc({
					method: "erpnext.selling.doctype.customer.customer.make_opportunity",
					frm: frm,
				}),
			__("Create")
		);
	},
});
