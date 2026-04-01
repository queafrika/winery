// Copyright (c) 2026, Finesoft Afrika and contributors
// Calendar view configuration for Compliance Task

frappe.views.calendar["Compliance Task"] = {
	field_map: {
		start: "due_date",
		end: "due_date",
		id: "name",
		title: "task_title",
		color: "calendar_color",
		allDay: "allDay",
	},
	gantt: false,
	filters: [
		{
			fieldtype: "Select",
			fieldname: "status",
			options: "\nOpen\nIn Progress\nCompleted\nOverdue\nCancelled",
			label: __("Status"),
		},
		{
			fieldtype: "Select",
			fieldname: "task_type",
			options: "\nGeneral\nPayment",
			label: __("Task Type"),
		},
	],
	get_events_method: "frappe.desk.calendar.get_events",
};
