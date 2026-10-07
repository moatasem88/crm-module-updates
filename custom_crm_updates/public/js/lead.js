// Lead form customizations (fields/layout: custom_crm_updates/overrides/lead.py):
// - Create > Activity replaces Create > Prospect.
// - Activity buttons for the read-only Leads Activities table
//   (leads_activity_section.js).

frappe.provide("custom_crm_updates");

// Subclassed rather than hooked via frappe.ui.form.on: those handlers run
// before erpnext.LeadController.refresh, i.e. before the Create buttons exist.
custom_crm_updates.LeadController = class LeadController extends erpnext.LeadController {
	setup() {
		super.setup();
		custom_crm_updates.setup_activity_make_method(this.frm);
		custom_crm_updates.show_when_empty(this.frm, ["custom_leads_activities", "custom_contacts"]);
	}

	refresh() {
		super.refresh();
		if (this.frm.is_new()) return;

		this.frm.remove_custom_button("Prospect", "Create");
		custom_crm_updates.add_activity_buttons(this.frm);
		custom_crm_updates.add_contact_button(this.frm);
	}
};

extend_cscript(cur_frm.cscript, new custom_crm_updates.LeadController({ frm: cur_frm }));
