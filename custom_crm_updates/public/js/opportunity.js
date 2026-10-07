// Opportunity form customizations (fields: custom_crm_updates/overrides/opportunity.py):
// activity buttons for the read-only Opportunity Activities table
// (leads_activity_section.js).

frappe.provide("custom_crm_updates");

// Subclassed like lead.js so our buttons are added after the core ones.
custom_crm_updates.OpportunityController = class OpportunityController extends erpnext.crm.Opportunity {
	setup() {
		// erpnext.crm.Opportunity defines no setup of its own
		super.setup?.();
		custom_crm_updates.setup_activity_make_method(this.frm);
		custom_crm_updates.show_when_empty(this.frm, [
			"custom_leads_activities",
			"custom_project_tenders",
			"custom_contacts",
		]);
	}

	refresh() {
		super.refresh();
		custom_crm_updates.add_activity_buttons(this.frm);
		custom_crm_updates.add_contact_button(this.frm);
	}
};

extend_cscript(cur_frm.cscript, new custom_crm_updates.OpportunityController({ frm: cur_frm }));
