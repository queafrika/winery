// Copyright (c) 2026, Finesoft Afrika and contributors
// For license information, please see license.txt

frappe.ui.form.on("Ripening Rack", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("View Ripening Batches"), () => {
				frappe.set_route("List", "Ripening Batch", { rack: frm.doc.name });
			});
			_load_usage(frm);
		}
	},

	capacity_fingers(frm) {
		if (!frm.is_new()) _load_usage(frm);
	},
});

function _load_usage(frm) {
	frappe.call({
		method: "winery.winery.doctype.ripening_rack.ripening_rack.get_rack_usage",
		args: { rack_name: frm.doc.name },
		callback(r) {
			if (!r.message) return;
			const { fingers_in_use, usage_percentage } = r.message;
			// Use doc + refresh_field for read-only fields to avoid marking form dirty
			frm.doc.fingers_in_use = fingers_in_use;
			frm.doc.usage_percentage = usage_percentage;
			frm.refresh_field("fingers_in_use");
			frm.refresh_field("usage_percentage");
			_render_usage_bar(frm, fingers_in_use, frm.doc.capacity_fingers || 0, usage_percentage);
		},
	});
}

function _render_usage_bar(frm, used, capacity, pct) {
	const f = frm.get_field("usage_indicator");
	if (!f) return;

	const color = pct >= 90 ? "#e74c3c" : pct >= 70 ? "#e67e22" : "#27ae60";
	const label = pct >= 90 ? "Critical" : pct >= 70 ? "High" : pct > 0 ? "Normal" : "Empty";
	const remaining = Math.max(0, capacity - used);

	f.$wrapper.html(`
		<div style="padding:8px 0;">
			<div style="display:flex;justify-content:space-between;margin-bottom:4px;font-size:13px;">
				<span><b>${used.toLocaleString()}</b> fingers in use</span>
				<span style="color:${color};font-weight:600;">${pct}% &mdash; ${label}</span>
			</div>
			<div style="background:#e9ecef;border-radius:6px;height:22px;overflow:hidden;">
				<div style="width:${pct}%;height:100%;background:${color};border-radius:6px;min-width:${pct > 0 ? 4 : 0}px;"></div>
			</div>
			<div style="display:flex;justify-content:space-between;margin-top:4px;font-size:11px;color:#888;">
				<span>Capacity: <b>${capacity.toLocaleString()} fingers</b></span>
				<span>Available: <b>${remaining.toLocaleString()} fingers</b></span>
			</div>
		</div>
	`);
}
