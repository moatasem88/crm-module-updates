// Customer form: a "Create ▸ Opportunity" entry.
//
// ERPNext already knows how to turn a Customer into an Opportunity — its
// make_opportunity mapper sets opportunity_from = "Customer" and party_name =
// this Customer — but it only wires that to the Connections tab's "+"
// (frm.make_methods), so there is no way to reach it from the Create menu.
// The same mapper is used here, so the Opportunity is built exactly as the
// rest of ERPNext builds it.

frappe.ui.form.on("Customer", {
	refresh(frm) {
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
