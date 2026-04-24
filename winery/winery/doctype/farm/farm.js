// Copyright (c) 2026, Finesoft Afrika and contributors
// For license information, please see license.txt

frappe.ui.form.on("Farm", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Purchase Bananas"), () => {
				frappe.route_options = { farmer: frm.doc.farmer, farm: frm.doc.name };
				frappe.set_route("purchase-bananas");
			}, __("Actions"));
		}

		// Load all 47 counties into dropdown immediately
		frappe.call({
			method: "winery.winery.doctype.farmer.farmer.get_kenya_counties",
			callback(r) {
				if (r.message)
					frm.set_df_property("county", "options", ["", ...r.message].join("\n"));
			},
		});

		// Restore sub-counties and wards if already saved
		if (frm.doc.county) _load_sub_counties(frm, frm.doc.county);
		if (frm.doc.sub_county) _load_wards(frm, frm.doc.sub_county);

		// Show map based on saved location
		_render_map(frm);
	},

	// County selected → load sub-counties, clear downstream
	county(frm) {
		frm.set_value("sub_county", "");
		frm.set_value("village", "");
		frm.set_df_property("sub_county", "options", "");
		frm.set_df_property("village", "options", "");
		if (frm.doc.county) _load_sub_counties(frm, frm.doc.county);
		_render_map(frm);
	},

	// Sub-County selected → load wards, auto-fill county if blank
	sub_county(frm) {
		frm.set_value("village", "");
		frm.set_df_property("village", "options", "");
		if (frm.doc.sub_county) {
			_load_wards(frm, frm.doc.sub_county);
			if (!frm.doc.county) {
				frappe.call({
					method: "winery.winery.doctype.farmer.farmer.get_location_parents",
					args: { sub_county: frm.doc.sub_county },
					callback(r) {
						if (r.message && r.message.county)
							frm.set_value("county", r.message.county);
					},
				});
			}
		}
		_render_map(frm);
	},

	// Village selected → auto-fill county and sub-county
	village(frm) {
		if (!frm.doc.village) return;
		frappe.call({
			method: "winery.winery.doctype.farmer.farmer.get_location_parents",
			args: { ward: frm.doc.village },
			callback(r) {
				if (!r.message) return;
				if (r.message.county && !frm.doc.county)
					frm.set_value("county", r.message.county);
				if (r.message.sub_county && !frm.doc.sub_county) {
					frm.set_value("sub_county", r.message.sub_county);
					_load_wards(frm, r.message.sub_county);
				}
			},
		});
		_render_map(frm);
	},
});

function _load_sub_counties(frm, county) {
	frappe.call({
		method: "winery.winery.doctype.farmer.farmer.get_kenya_sub_counties",
		args: { county },
		callback(r) {
			if (r.message)
				frm.set_df_property("sub_county", "options", ["", ...r.message].join("\n"));
		},
	});
}

function _load_wards(frm, sub_county) {
	frappe.call({
		method: "winery.winery.doctype.farmer.farmer.get_kenya_wards",
		args: { sub_county },
		callback(r) {
			if (r.message)
				frm.set_df_property("village", "options", ["", ...r.message].join("\n"));
		},
	});
}

function _render_map(frm) {
	const parts = [frm.doc.village, frm.doc.sub_county, frm.doc.county, "Kenya"]
		.filter(Boolean);

	const map_field = frm.get_field("google_map");
	if (!map_field) return;

	if (parts.length < 2) {
		map_field.$wrapper.html(
			`<div style="padding:14px;color:#888;font-size:13px;background:#f8f8f8;border-radius:4px;">
				Select a County to show the map.
			</div>`
		);
		return;
	}

	// Zoom level: village=13, sub-county=11, county=9
	const zoom = frm.doc.village ? 13 : frm.doc.sub_county ? 11 : 9;
	const query = encodeURIComponent(parts.join(", "));

	map_field.$wrapper.html(`
		<div style="border-radius:6px;overflow:hidden;margin-bottom:6px;border:1px solid #ddd;">
			<iframe
				width="100%"
				height="400"
				frameborder="0"
				style="border:0;display:block;"
				src="https://maps.google.com/maps?q=${query}&output=embed&z=${zoom}"
				allowfullscreen>
			</iframe>
		</div>
		<div style="font-size:11px;color:#888;">
			Showing: <b>${parts.filter(p => p !== "Kenya").join(" → ")}</b>
			&nbsp;|&nbsp; Use <b>Exact Pin Location</b> below for a precise farm pin.
		</div>
	`);
}
