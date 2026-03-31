// Copyright (c) 2026, Finesoft Afrika and contributors
// Calendar view configuration for Compliance License

frappe.views.calendar["Compliance License"] = {
	field_map: {
		start: "expiry_date",
		end: "expiry_date",
		id: "name",
		title: "license_name",
		color: "calendar_color",
		allDay: "allDay",
	},
	gantt: false,
	filters: [
		{
			fieldtype: "Select",
			fieldname: "status",
			options: "\nActive\nPending Renewal\nExpired\nSuspended\nCancelled",
			label: __("Status"),
		},
	],
	get_events_method: "frappe.desk.calendar.get_events",
};
