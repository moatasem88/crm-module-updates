// Submission Deadline on a Tender raised under a Project Tender that came
// from an Opportunity: it is the Opportunity's Expected Closing Date.
//
// The server does the same on before_insert
// (custom_crm_updates/overrides/tender.py, set_submission_deadline), which is
// what makes the rule hold for the REST API and Data Import. This fills the
// field in the form as soon as the Project Tender is known - on "Create >
// Tender" from the Project Tender, and when the link is picked by hand - so
// the user sees the date before saving rather than after.
//
// Only ever fills an empty field: once there is a deadline, it is the user's
// to change.

frappe.ui.form.on('Tender', {
	project_tender(frm) {
		set_submission_deadline(frm);
	},

	onload(frm) {
		// "Create > Tender" opens an unsaved Tender that already names its
		// Project Tender, so no project_tender change event ever fires.
		if (frm.is_new()) {
			set_submission_deadline(frm);
		}
	},
});

function set_submission_deadline(frm) {
	if (!frm.doc.project_tender || frm.doc.submission_deadline) {
		return;
	}

	frappe.db.get_value('Project Tender', frm.doc.project_tender, 'custom_opportunity')
		.then(({ message }) => {
			const opportunity = message && message.custom_opportunity;
			if (!opportunity) {
				return;
			}
			return frappe.db.get_value('Opportunity', opportunity, 'expected_closing');
		})
		.then((response) => {
			const expected_closing = response && response.message && response.message.expected_closing;
			// Re-checked: the user may have typed a deadline while this was
			// in flight.
			if (expected_closing && !frm.doc.submission_deadline) {
				frm.set_value('submission_deadline', expected_closing);
			}
		});
}
