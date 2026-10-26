// Opportunity form customizations (fields: custom_crm_updates/overrides/opportunity.py):
// - activity buttons for the read-only Opportunity Activities table
//   (leads_activity_section.js);
// - Status set to "Won": a popup lists this Opportunity's Submitted Project
//   Tenders and asks which one was approved. Saving then sets that tender to
//   "Won" (custom_crm_updates/overrides/project_tender.py,
//   apply_approved_tender). Tenders in any other status are not offered: the
//   list comes from get_opportunity_tenders, which filters on Submitted;
// - Contact Person lists the Opportunity's own contacts, not its party's
//   (custom_crm_updates/overrides/contact.py).
// - Opportunity Breakdown: each row's Final Value follows the Targeted Amount
//   and the row's own Contribution Type / Value as they are typed. The server
//   works them out again on save (overrides/opportunity.py), which is what
//   makes them right for the API and a Data Import.
// - Saving without an attachment is refused with the same message as the
//   server, before Frappe's generic Missing Fields dialog can appear.

frappe.provide("custom_crm_updates");

const WON = "Won";
const APPROVED_TENDER_FIELD = "custom_approved_project_tender";
const TENDER_TABLE = "custom_project_tenders";
// What get_opportunity_tenders offers; named here only for the message shown
// when nothing qualifies.
const APPROVABLE_STATUS = "Submitted";
const TARGETED_AMOUNT = "custom_targeted_amount";
const CONTRIBUTIONS_FIELD = "custom_opportunity_contributions";
const ATTACHMENTS_FIELD = "custom_opportunity_attachments";
const PERCENTAGE = "Percentage";

// Subclassed like lead.js so our buttons are added after the core ones.
custom_crm_updates.OpportunityController = class OpportunityController extends erpnext.crm.Opportunity {
	setup() {
		// erpnext.crm.Opportunity defines no setup of its own
		super.setup?.();
		custom_crm_updates.setup_activity_make_method(this.frm);
		custom_crm_updates.show_when_empty(this.frm, [
			"custom_leads_activities",
			TENDER_TABLE,
			"custom_contacts",
		]);
	}

	refresh() {
		super.refresh();
		if (is_approved(this.frm)) custom_crm_updates.add_activity_buttons(this.frm);
		custom_crm_updates.add_contact_button(this.frm);
		set_contact_person_query(this.frm);
		remember_status(this.frm);
		// last: after every button core and the code above added
		apply_workflow_rules(this.frm);
	}
};

// Approval workflow ("opportunity"); the server holds the same rules
// (overrides/opportunity_workflow.py), these show them on the form.
const WORKFLOW_FIELD = "workflow_state";
const APPROVED = "Go";
const REJECTED = "No Go";
// stage -> the fields its approver fills in. Shown from that stage on (their
// depends_on), required and editable in that stage only.
const STAGE_FIELDS = {
	"Pending BD Manager": ["custom_bd_manager_recommendation", "custom_bd_manager_notes"],
	"Pending BD Director": ["custom_bd_director_recommendation", "custom_bd_director_note"],
	"Pending CEO Approval": ["custom_ceo_recommendation", "custom_ceo_note"],
};
// core's Create buttons: nothing is done on an Opportunity before it is
// approved, nor on a rejected one
const CREATE_BUTTONS = ["Quotation", "Supplier Quotation", "Request For Quotation", "Customer", "Activity"];
const STATUS_BUTTONS = ["Close", "Reopen"];

function is_approved(frm) {
	// no workflow state: an Opportunity that predates the workflow
	return !frm.doc[WORKFLOW_FIELD] || frm.doc[WORKFLOW_FIELD] === APPROVED;
}

// Read by custom_crm_updates.make_activity (leads_activity_section.js), which
// also serves the Connections tab "+".
custom_crm_updates.can_log_activity = function (frm) {
	if (frm.doctype !== "Opportunity" || is_approved(frm)) return true;

	frappe.msgprint({
		title: __("الـ Opportunity لم يُعتمد بعد"),
		message: __("لا يمكن إنشاء Activity أو Project Tender قبل اعتماد الـ Opportunity ({0}).", [__(APPROVED)]),
		indicator: "orange",
	});
	return false;
};

function apply_workflow_rules(frm) {
	const state = frm.doc[WORKFLOW_FIELD];
	if (!state) return;

	for (const [stage, fieldnames] of Object.entries(STAGE_FIELDS)) {
		const own_stage = state === stage;
		for (const fieldname of fieldnames) {
			frm.set_df_property(fieldname, "reqd", own_stage ? 1 : 0);
			frm.set_df_property(fieldname, "read_only", own_stage ? 0 : 1);
		}
	}

	if (state === APPROVED || state === REJECTED) {
		// frozen: only the Status stays editable, and only once approved
		for (const df of frm.meta.fields) {
			const layout = frappe.model.no_value_type.includes(df.fieldtype) && !frappe.model.table_fields.includes(df.fieldtype);
			if (layout || df.fieldname === "status") continue;
			frm.set_df_property(df.fieldname, "read_only", 1);
		}
	}
	frm.set_df_property("status", "read_only", state === APPROVED ? 0 : 1);

	if (state !== APPROVED) {
		for (const label of CREATE_BUTTONS) frm.remove_custom_button(__(label), __("Create"));
		for (const label of STATUS_BUTTONS) frm.remove_custom_button(__(label));
	}
}

frappe.ui.form.on("Opportunity", {
	status(frm) {
		// A new Opportunity has no tenders yet, so nothing to approve.
		if (frm.doc.status !== WON || frm.is_new()) {
			remember_status(frm);
			return;
		}
		ask_which_tender_was_approved(frm);
	},

	validate(frm) {
		require_attachment(frm);
	},

	[TARGETED_AMOUNT](frm) {
		// every percentage row is a share of it
		calculate_contributions(frm);
	},
});

// Rows of the Opportunity Breakdown table.
frappe.ui.form.on("Opportunity Contribution", {
	contribution_type(frm, cdt, cdn) {
		calculate_contribution(frm, locals[cdt][cdn]);
	},

	contribution_value(frm, cdt, cdn) {
		calculate_contribution(frm, locals[cdt][cdn]);
	},
});

// A row the user added but never picked a file for is not an attachment.
function attached_files(frm) {
	return (frm.doc[ATTACHMENTS_FIELD] || []).filter((row) => row.attachment);
}

function require_attachment(frm) {
	if (attached_files(frm).length) return;

	frappe.throw({
		title: __("مرفق مطلوب"),
		message: __("لا يمكن حفظ Opportunity بدون مرفقات. أرفق ملفاً واحداً على الأقل في جدول Attachments."),
	});
}

function calculate_contributions(frm) {
	for (const row of frm.doc[CONTRIBUTIONS_FIELD] || []) {
		calculate_contribution(frm, row);
	}
}

// Percentage: the Contribution Value is a share of the Targeted Amount (20
// against 20,000 is 4,000). Fixed Amount: it is the amount itself.
function calculate_contribution(frm, row) {
	const value = flt(row.contribution_value);
	const final_value =
		row.contribution_type === PERCENTAGE ? (flt(frm.doc[TARGETED_AMOUNT]) * value) / 100 : value;

	// set_value rather than an assignment: it redraws the row and marks the
	// form dirty, so the figure the user sees is the one that gets saved
	frappe.model.set_value(row.doctype, row.name, "final_value", final_value);
}

// Core's setup_queries filters Contact Person by frappe.dynamic_link, i.e. by
// the Opportunity's party, which would offer the Lead's contacts. The
// Opportunity's contacts are its own.
function set_contact_person_query(frm) {
	frm.set_query("contact_person", () => ({
		query: "frappe.contacts.doctype.contact.contact.contact_query",
		filters: { link_doctype: "Opportunity", link_name: frm.doc.name },
	}));
}

// A field handler is not told the value before the change, and cancelling the
// popup puts the Status back, so keep track of it by hand. Updated on every
// refresh (load, save) and on every status change that isn't a Won.
function remember_status(frm) {
	frm.__status_before_won = frm.doc.status;
}

function ask_which_tender_was_approved(frm) {
	frappe.call({
		method: "custom_crm_updates.overrides.project_tender.get_opportunity_tenders",
		args: { opportunity: frm.doc.name },
		callback(r) {
			const tenders = r.message || [];
			if (!tenders.length) {
				// Nothing to approve, and the status stands. Two different
				// reasons, so the message says which one: the Opportunity's
				// own table (same tab as this popup) is what tells them
				// apart without a second call.
				nothing_to_approve(frm);
				remember_status(frm);
				return;
			}
			pick_approved_tender(frm, tenders);
		},
	});
}

function nothing_to_approve(frm) {
	// Won without tendering: a direct award, or an Opportunity that never
	// went out to tender.
	if (!(frm.doc[TENDER_TABLE] || []).length) {
		frappe.msgprint({
			title: __("لا يوجد Project Tender"),
			message: __("لا يوجد أي Project Tender مُنشأ على هذا الـ Opportunity لاعتماده."),
			indicator: "orange",
		});
		return;
	}

	// Tenders there are, but none of them was ever sent to the client.
	frappe.msgprint({
		title: __("لا يوجد Project Tender بالحالة {0}", [APPROVABLE_STATUS]),
		message: __(
			"لا يمكن اعتماد Project Tender لم يُرسل إلى العميل. حوّل التندر المعتمد إلى الحالة {0} أولاً، ثم أعد تحويل الـ Opportunity إلى {1}.",
			[APPROVABLE_STATUS, WON]
		),
		indicator: "orange",
	});
}


function pick_approved_tender(frm, tenders) {
	let picked = null;

	const dialog = new frappe.ui.Dialog({
		title: __("أي Project Tender تم اعتماده؟"),
		fields: [
			{
				fieldtype: "Select",
				fieldname: "project_tender",
				// field and DocType names stay in English, as in the system
				label: "Project Tender",
				reqd: 1,
				default: tenders[0].name,
				options: tenders.map((tender) => ({ value: tender.name, label: tender_label(tender) })),
			},
			{
				fieldtype: "HTML",
				fieldname: "note",
				options: `<p class="text-muted small">${__("سيتم تحويله إلى الحالة {0} عند حفظ الـ Opportunity. باقي التندرات لن تتغير.", [WON])}</p>`,
			},
		],
		primary_action_label: __("اعتماد"),
		primary_action(values) {
			picked = values.project_tender;
			dialog.hide();
		},
	});

	// Dismissed (Esc, ✕) without choosing: the status goes back rather than
	// standing as a Won with no approved tender behind it.
	dialog.onhide = () => {
		if (picked) {
			frm.set_value(APPROVED_TENDER_FIELD, picked);
			remember_status(frm);
		} else {
			frm.set_value("status", frm.__status_before_won);
		}
	};

	dialog.show();
}

function tender_label(tender) {
	return [
		tender.name,
		tender.project_name,
		tender.status,
		format_currency(tender.total_sell_price),
	]
		.filter(Boolean)
		.join("  ·  ");
}

extend_cscript(cur_frm.cscript, new custom_crm_updates.OpportunityController({ frm: cur_frm }));
