// Create ▸ Tender on the Project Tender form.
//
// This button belongs to the contracting app, which owns Project Tender, but
// it was never released there — see
// custom_crm_updates/overrides/contracting_backport.py. It is added from here
// so a site has it without waiting for that app.
//
// It stands down on its own once contracting ships its own: that script is
// the DocType's own .js and runs before this one, so its button is already in
// the Create group by the time this runs, and Frappe's add_inner_button skips
// a label that is already in the group (page.js). The explicit check below
// says so out loud rather than relying on that.

frappe.ui.form.on('Project Tender', {
	refresh(frm) {
		add_create_tender_button(frm);
	},
});

function add_create_tender_button(frm) {
	// Unsaved Project Tenders have no name to link to, and the mapper reads
	// the saved document, so the button waits for the first save.
	if (frm.doc.__islocal || !frappe.model.can_create('Tender')) return;

	// contracting's own button, if that app has caught up
	if (frm.custom_buttons && frm.custom_buttons[__('Tender')]) return;

	frm.add_custom_button(__('Tender'), () => {
		frappe.model.open_mapped_doc({
			method: 'custom_crm_updates.overrides.contracting_backport.make_tender',
			frm: frm,
		});
	}, __('Create'));
}
