"""Opportunity approval workflow ("opportunity": Draft -> Pending BD Manager ->
Pending BD Director -> Pending CEO Approval -> Go / No Go).

- Each approval stage has its own Recommendation and Notes fields. They are
  shown from that stage on (their depends_on, set on the Custom Fields), must
  be filled before the Opportunity can leave the stage, and are read-only
  once it has: only the stage they belong to may write them.
- Before Go nothing is done on the Opportunity yet: no Activity (and so no
  Project Tender) can be logged against it, and its Status cannot change.
- Go is the approval: from then on the data is frozen. Only the Status (and
  what a Status change brings with it: the approved Project Tender of a Won,
  the reasons of a Lost) may change, and Activities / Project Tenders can be
  logged.
- No Go is the rejection: everything is frozen, Status included, and no
  Activity can be logged.

The form shows the same rules (public/js/opportunity.js); these are the ones
that hold for the API, a Data Import and the bench console too. Saves made by
the automation (flags.ignore_permissions, e.g. ERPNext's auto-close) and
db_set writes (a Tendering activity setting the Status) are not user edits
and are left alone.
"""

import frappe
from frappe import _
from frappe.model import no_value_fields, table_fields

WORKFLOW_STATE_FIELD = "workflow_state"
APPROVED = "Go"
REJECTED = "No Go"

# stage -> the fields its approver fills in
STAGE_FIELDS = {
	"Pending BD Manager": ("custom_bd_manager_recommendation", "custom_bd_manager_notes"),
	"Pending BD Director": ("custom_bd_director_recommendation", "custom_bd_director_note"),
	"Pending CEO Approval": ("custom_ceo_recommendation", "custom_ceo_note"),
}

# What may still change on an approved (Go) Opportunity: the Status, and the
# fields a Status change fills in (the Won popup's approved tender, ERPNext's
# Declare Lost dialog).
EDITABLE_WHEN_APPROVED = (
	"status",
	"custom_approved_project_tender",
	"lost_reasons",
	"competitors",
	"order_lost_reason",
)

# Child rows: bookkeeping columns that change without anyone editing the row.
ROW_IGNORED = {"name", "idx", "parent", "parentfield", "parenttype", "owner", "creation", "modified", "modified_by", "doctype", "docstatus"}


def enforce_workflow(doc, method=None):
	"""doc_events: Opportunity before_validate. Runs on what the user sent,
	before ERPNext's validate fills empty fields from the party (map_fields)
	and this app's validators work out theirs: neither is a user edit."""
	if doc.is_new() or doc.flags.ignore_permissions:
		return

	before = doc.get_doc_before_save()
	if not before:
		return

	state_before = before.get(WORKFLOW_STATE_FIELD)
	if not state_before:
		# never went through the workflow (predates it)
		return

	validate_stage_fields(doc, before, state_before)

	if state_before in (APPROVED, REJECTED):
		validate_frozen(doc, before, state_before)
	elif before.status != doc.status:
		frappe.throw(
			_("لا يمكن تغيير الـ Status قبل اعتماد الـ Opportunity. الحالة الحالية في الـ Workflow هي {0}، والـ Status يتغير بعد الوصول إلى {1}.").format(
				frappe.bold(_(state_before)), frappe.bold(_(APPROVED))
			),
			title=_("الـ Opportunity لم يُعتمد بعد"),
		)


def validate_stage_fields(doc, before, state_before):
	meta = doc.meta

	# Leaving a stage: its approver must have filled in both fields.
	if state_before in STAGE_FIELDS and doc.get(WORKFLOW_STATE_FIELD) != state_before:
		missing = [meta.get_label(f) for f in STAGE_FIELDS[state_before] if not doc.get(f)]
		if missing:
			frappe.throw(
				_("لا يمكن تجاوز المرحلة {0} قبل ملء: {1}").format(
					frappe.bold(_(state_before)), ", ".join(frappe.bold(_(label)) for label in missing)
				),
				title=_("حقول مطلوبة"),
			)

	# Each stage's fields are written in that stage only.
	for stage, fieldnames in STAGE_FIELDS.items():
		if stage == state_before:
			continue
		changed = [meta.get_label(f) for f in fieldnames if (before.get(f) or "") != (doc.get(f) or "")]
		if changed:
			frappe.throw(
				_("{0} تُكتب في المرحلة {1} فقط، ولا يمكن تعديلها الآن.").format(
					", ".join(frappe.bold(_(label)) for label in changed), frappe.bold(_(stage))
				),
				title=_("حقول للقراءة فقط"),
			)


def validate_frozen(doc, before, state_before):
	editable = EDITABLE_WHEN_APPROVED if state_before == APPROVED else ()
	changed = [doc.meta.get_label(f) for f in changed_fields(doc, before) if f not in editable]
	if not changed:
		return

	if state_before == APPROVED:
		message = _("الـ Opportunity معتمد ({0})، ولا يمكن تعديل بياناته. المسموح فقط تغيير الـ Status. الحقول المعدلة: {1}")
	else:
		message = _("الـ Opportunity مرفوض ({0})، ولا يمكن تعديل أي شيء فيه. الحقول المعدلة: {1}")
	frappe.throw(
		message.format(frappe.bold(_(state_before)), ", ".join(frappe.bold(_(label)) for label in changed)),
		title=_("الـ Opportunity مغلق"),
	)


def changed_fields(doc, before):
	"""Fieldnames a user could have edited (not read-only, not layout) whose
	value differs from the saved one. Read-only fields are left out: the
	server sets them itself (title, party links, mirror tables of activities,
	tenders and contacts)."""
	changed = []
	for df in doc.meta.fields:
		if df.fieldtype in no_value_fields and df.fieldtype not in table_fields:
			continue
		if df.read_only or df.fieldname == WORKFLOW_STATE_FIELD:
			continue
		if df.fieldtype in table_fields:
			if table_rows(before.get(df.fieldname)) != table_rows(doc.get(df.fieldname)):
				changed.append(df.fieldname)
		elif normalize(before.get(df.fieldname)) != normalize(doc.get(df.fieldname)):
			changed.append(df.fieldname)
	return changed


def table_rows(rows):
	return [
		{key: normalize(value) for key, value in row.as_dict().items() if key not in ROW_IGNORED and not key.startswith("__")}
		for row in rows or []
	]


def normalize(value):
	# "" / None / 0 are the same empty value whichever way it was saved
	if value in (None, "", 0, 0.0):
		return None
	return str(value)


def validate_activity_opportunity(doc, method=None):
	"""Leads Activity validate: a new activity on an Opportunity needs the
	Opportunity approved (Go). Re-saves of existing activities and the
	automation's own saves are left alone."""
	if doc.link_type != "Opportunity" or not doc.link_name or not doc.is_new() or doc.flags.ignore_permissions:
		return
	ensure_approved(doc.link_name, _("Activity"))


def validate_tender_opportunity(doc, method=None):
	"""Project Tender validate: a new tender on an Opportunity needs the
	Opportunity approved (Go). The one a Tendering activity creates passes
	(the activity was already checked)."""
	opportunity = doc.get("custom_opportunity")
	if not opportunity or not doc.is_new() or doc.flags.ignore_permissions:
		return
	ensure_approved(opportunity, _("Project Tender"))


def ensure_approved(opportunity, what):
	state = frappe.db.get_value("Opportunity", opportunity, WORKFLOW_STATE_FIELD)
	if not state or state == APPROVED:
		return
	frappe.throw(
		_("لا يمكن إنشاء {0} على الـ Opportunity {1} قبل اعتماده. حالته الآن {2}، والمطلوب {3}.").format(
			what, frappe.bold(opportunity), frappe.bold(_(state)), frappe.bold(_(APPROVED))
		),
		title=_("الـ Opportunity لم يُعتمد بعد"),
	)
