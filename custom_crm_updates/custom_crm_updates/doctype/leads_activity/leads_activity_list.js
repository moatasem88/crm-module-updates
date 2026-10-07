// Copyright (c) 2026, smart and contributors
// For license information, please see license.txt

const LEADS_ACTIVITY_STATUS_COLORS = {
	Planned: "blue",
	"In Process": "orange",
	Done: "green",
	Failed: "red",
	Closed: "gray",
	"Waiting Reply": "yellow",
};

frappe.listview_settings["Leads Activity"] = {
	get_indicator(doc) {
		const color = LEADS_ACTIVITY_STATUS_COLORS[doc.status] || "gray";
		return [__(doc.status), color, "status,=," + doc.status];
	},
};
