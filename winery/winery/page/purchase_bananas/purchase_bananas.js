frappe.pages["purchase-bananas"].on_page_load = function (wrapper) {
	new PurchaseBananasPage(wrapper);
};

class PurchaseBananasPage {
	constructor(wrapper) {
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Purchase Bananas"),
			single_column: true,
		});
		this.farmers_data = [];
		this.farms_data = [];
		this.variants = [];
		this.current_farmer_data = null;
		// Remember the auto-detected agent so reset can restore it
		this._locked_agent = null;
		this.setup();
	}

	// ------------------------------------------------------------------ setup

	async setup() {
		// Capture before Frappe clears them on route change
		const prefill = frappe.route_options ? { ...frappe.route_options } : {};
		frappe.route_options = null;

		this.render_html();
		this.bind_buttons();
		await this.load_variants();
		this.setup_link_controls();
		await this.detect_agent();

		if (prefill.farmer) {
			await this._prefill(prefill.farmer, prefill.farm || null);
		}

		this.add_row();
	}

	async _prefill(farmer, farm) {
		const $farmer_sel = $(this.page.body).find("#pb-farmer-select");
		if (!$farmer_sel.find(`option[value="${farmer}"]`).length) return;

		$farmer_sel.val(farmer);
		await this.on_farmer_change();

		if (farm) {
			const $farm_sel = $(this.page.body).find("#pb-farm-select");
			if ($farm_sel.find(`option[value="${farm}"]`).length) {
				$farm_sel.val(farm);
				this.on_farm_change();
			}
		}
	}

	render_html() {
		$(this.page.body).html(`
			<div class="pb-page" style="padding:15px;">

				<!-- Procurement header -->
				<div class="card mb-3">
					<div class="card-header"><strong>${__("Procurement Details")}</strong></div>
					<div class="card-body">
						<div class="row">
							<div class="col-12 col-md-6">
								<div id="pb-agent-wrap" class="form-group"></div>

								<div class="form-group">
									<label class="control-label">
										${__("Farmer")} <span class="text-danger">*</span>
									</label>
									<select id="pb-farmer-select" class="form-control" disabled>
										<option value="">-- ${__("Select Agent first")} --</option>
									</select>
								</div>

								<div class="form-group">
									<label class="control-label">
										${__("Farm")} <span class="text-danger">*</span>
									</label>
									<select id="pb-farm-select" class="form-control" disabled>
										<option value="">-- ${__("Select Farmer first")} --</option>
									</select>
								</div>

								<div id="pb-wh-wrap" class="form-group"></div>
							</div>

							<div class="col-12 col-md-6 mt-2 mt-md-0">
								<div id="pb-farmer-info" class="alert alert-info" style="display:none;">
									<div class="mb-2">
										<span class="text-muted small">${__("Farmer")}</span><br>
										<strong id="pb-farmer-name">—</strong>
									</div>
									<div>
										<span class="text-muted small">${__("Supplier")}</span><br>
										<strong id="pb-supplier-name">—</strong>
									</div>
								</div>
							</div>
						</div>
					</div>
				</div>

				<!-- Items table (horizontally scrollable on mobile) -->
				<div class="card mb-3">
					<div class="card-header"><strong>${__("Banana Bunches Purchased")}</strong></div>
					<div class="card-body px-2 px-md-3 pb-0">
						<div style="overflow-x:auto;">
							<table class="table table-bordered table-sm mb-2"
								id="pb-items-table" style="min-width:480px;">
								<thead class="thead-light">
									<tr>
										<th>${__("Variety")}</th>
										<th style="width:110px">${__("Qty")}</th>
										<th style="width:120px">${__("Rate")}</th>
										<th style="width:110px" class="text-right">${__("Amount")}</th>
										<th style="width:36px"></th>
									</tr>
								</thead>
								<tbody id="pb-items-body"></tbody>
							</table>
						</div>
						<button class="btn btn-sm btn-secondary mb-3" id="pb-add-row">
							+ ${__("Add Variety")}
						</button>
					</div>
				</div>

				<!-- Footer -->
				<div class="d-flex flex-wrap justify-content-between align-items-center
					gap-2 pb-3">
					<div style="font-size:1.1em;">
						${__("Total")}: <strong id="pb-total">0.00</strong>
					</div>
					<button class="btn btn-primary btn-lg w-100 w-md-auto" id="pb-submit"
						style="min-width:200px;">
						${__("Save Purchase Invoice")}
					</button>
				</div>

			</div>
		`);
	}

	bind_buttons() {
		const $body = $(this.page.body);
		$body.find("#pb-farmer-select").on("change", () => this.on_farmer_change());
		$body.find("#pb-farm-select").on("change", () => this.on_farm_change());
		$body.find("#pb-add-row").on("click", () => this.add_row());
		$body.find("#pb-submit").on("click", () => this.submit());
	}

	// ------------------------------------------------- Frappe link controls

	setup_link_controls() {
		this.agent_ctrl = this._make_link_ctrl(
			"#pb-agent-wrap", "agent", __("Agent"), "Agent", true,
			() => this.on_agent_change()
		);
		this.wh_ctrl = this._make_link_ctrl(
			"#pb-wh-wrap", "warehouse", __("Receiving Warehouse"), "Warehouse", true
		);
	}

	_make_link_ctrl(selector, fieldname, label, options, reqd, onchange) {
		const ctrl = frappe.ui.form.make_control({
			df: {
				fieldtype: "Link",
				fieldname,
				label,
				options,
				reqd: reqd ? 1 : 0,
				onchange: onchange || null,
			},
			parent: $(this.page.body).find(selector),
			render_input: true,
		});
		ctrl.refresh();
		return ctrl;
	}

	// ------------------------------------------------- agent detection

	async detect_agent() {
		const agent = await frappe.xcall(
			"winery.winery.page.purchase_bananas.purchase_bananas.get_agent_for_user"
		);
		if (agent) {
			this._locked_agent = agent;
			this.agent_ctrl.set_value(agent);
			this.agent_ctrl.$input.prop("disabled", true);
			await this._apply_agent(agent);
		}
	}

	async on_agent_change() {
		const agent = this.agent_ctrl.get_value();
		this._clear_farmer();
		if (!agent) return;
		await this._apply_agent(agent);
	}

	async _apply_agent(agent) {
		this.current_agent = agent;

		const [farmers, wh] = await Promise.all([
			frappe.xcall(
				"winery.winery.page.purchase_bananas.purchase_bananas.get_farmers_for_agent",
				{ agent }
			),
			frappe.xcall(
				"winery.winery.page.purchase_bananas.purchase_bananas.get_agent_transit_warehouse",
				{ agent }
			),
		]);

		this.farmers_data = farmers;

		const $sel = $(this.page.body).find("#pb-farmer-select");
		$sel.empty().append(`<option value="">-- ${__("Select Farmer")} --</option>`);
		farmers.forEach((f) => {
			$sel.append(`<option value="${f.name}">${f.name}</option>`);
		});
		$sel.prop("disabled", farmers.length === 0);

		if (wh) this.wh_ctrl.set_value(wh);
	}

	// ------------------------------------------------- farmer / farm cascade

	async on_farmer_change() {
		const farmer = $(this.page.body).find("#pb-farmer-select").val();
		this._clear_farm();
		if (!farmer) return;

		this.current_farmer_data = this.farmers_data.find((f) => f.name === farmer) || null;

		const farms = await frappe.xcall(
			"winery.winery.page.purchase_bananas.purchase_bananas.get_farms_for_farmer",
			{ farmer }
		);
		this.farms_data = farms;

		const $sel = $(this.page.body).find("#pb-farm-select");
		$sel.empty().append(`<option value="">-- ${__("Select Farm")} --</option>`);
		farms.forEach((f) => {
			$sel.append(`<option value="${f.farm}">${f.farm}</option>`);
		});
		$sel.prop("disabled", farms.length === 0);

		this._show_farmer_info(this.current_farmer_data);
	}

	on_farm_change() {
		this.current_farm = $(this.page.body).find("#pb-farm-select").val() || null;
	}

	// ------------------------------------------------- clear helpers

	_clear_farmer() {
		this.farmers_data = [];
		this.current_farmer_data = null;
		$(this.page.body)
			.find("#pb-farmer-select")
			.empty()
			.append(`<option value="">-- ${__("Select Agent first")} --</option>`)
			.prop("disabled", true);
		this._clear_farm();
	}

	_clear_farm() {
		this.farms_data = [];
		this.current_farm = null;
		$(this.page.body)
			.find("#pb-farm-select")
			.empty()
			.append(`<option value="">-- ${__("Select Farmer first")} --</option>`)
			.prop("disabled", true);
		this._show_farmer_info(null);
	}

	_show_farmer_info(data) {
		const $info = $(this.page.body).find("#pb-farmer-info");
		if (!data) { $info.hide(); return; }
		$info.show();
		$(this.page.body).find("#pb-farmer-name").text(data.name || "—");
		$(this.page.body).find("#pb-supplier-name").text(data.supplier || "—");
	}

	// ------------------------------------------------- reset after save

	async _reset() {
		// Clear items table and total
		$(this.page.body).find("#pb-items-body").empty();
		$(this.page.body).find("#pb-total").text("0.00");

		if (this._locked_agent) {
			// Agent is auto-detected — keep it locked, re-populate farmers
			// (warehouse was already set; leave it as-is for the next purchase)
			this._clear_farmer();
			await this._apply_agent(this._locked_agent);
		} else {
			// Manual agent — clear everything so user starts fresh
			this.agent_ctrl.set_value("");
			this.wh_ctrl.set_value("");
			this._clear_farmer();
		}

		this.add_row();
	}

	// ------------------------------------------------- variants

	async load_variants() {
		this.variants = await frappe.xcall(
			"winery.winery.page.purchase_bananas.purchase_bananas.get_banana_bunch_variants"
		);
	}

	_variant_options_html() {
		const opts = this.variants
			.map((v) => `<option value="${v.name}">${v.item_name}</option>`)
			.join("");
		return `<option value="">-- ${__("Select Variety")} --</option>${opts}`;
	}

	// ------------------------------------------------- items table

	add_row() {
		const $row = $(`
			<tr>
				<td>
					<select class="form-control form-control-sm pb-variant">
						${this._variant_options_html()}
					</select>
				</td>
				<td>
					<input type="number" class="form-control form-control-sm pb-qty"
						min="0.001" step="0.001" placeholder="0"
						inputmode="decimal">
				</td>
				<td>
					<input type="number" class="form-control form-control-sm pb-rate"
						min="0" step="0.01" placeholder="0.00"
						inputmode="decimal">
				</td>
				<td class="pb-amount text-right" style="vertical-align:middle; white-space:nowrap;">
					0.00
				</td>
				<td style="vertical-align:middle; text-align:center;">
					<button class="btn btn-xs btn-danger pb-remove"
						style="padding:4px 8px; line-height:1.2; font-size:14px;">✕</button>
				</td>
			</tr>
		`);

		$row.find(".pb-qty, .pb-rate").on("input", () => this._recalc_row($row));
		$row.find(".pb-remove").on("click", () => {
			$row.remove();
			this._update_total();
		});

		$(this.page.body).find("#pb-items-body").append($row);
	}

	_recalc_row($row) {
		const qty = parseFloat($row.find(".pb-qty").val()) || 0;
		const rate = parseFloat($row.find(".pb-rate").val()) || 0;
		$row.find(".pb-amount").text(format_number(qty * rate, null, 2));
		this._update_total();
	}

	_update_total() {
		let total = 0;
		$(this.page.body).find("#pb-items-body .pb-amount").each(function () {
			total += parseFloat($(this).text().replace(/,/g, "")) || 0;
		});
		$(this.page.body).find("#pb-total").text(format_number(total, null, 2));
	}

	// ------------------------------------------------- submit

	_collect_items() {
		const items = [];
		let valid = true;

		$(this.page.body).find("#pb-items-body tr").each(function () {
			const item_code = $(this).find(".pb-variant").val();
			const qty = parseFloat($(this).find(".pb-qty").val()) || 0;
			const rate = parseFloat($(this).find(".pb-rate").val()) || 0;

			if (!item_code || qty <= 0 || rate < 0) {
				valid = false;
				return false;
			}
			items.push({ item_code, qty, rate });
		});

		return valid ? items : null;
	}

	async submit() {
		const agent = this.agent_ctrl.get_value();
		const farmer = $(this.page.body).find("#pb-farmer-select").val();
		const farm = $(this.page.body).find("#pb-farm-select").val();
		const warehouse = this.wh_ctrl.get_value();

		if (!agent || !farmer || !farm || !warehouse) {
			frappe.msgprint(__("Please fill in Agent, Farmer, Farm, and Receiving Warehouse."));
			return;
		}
		if (!this.current_farmer_data) {
			frappe.msgprint(__("Farmer details not found. Please re-select the farmer."));
			return;
		}

		const items = this._collect_items();
		if (!items || items.length === 0) {
			frappe.msgprint(__("Please add at least one variety row with a valid quantity and rate."));
			return;
		}

		const $btn = $(this.page.body).find("#pb-submit");
		$btn.prop("disabled", true).text(__("Saving…"));

		try {
			const pi_name = await frappe.xcall(
				"winery.winery.page.purchase_bananas.purchase_bananas.create_purchase_invoice",
				{
					agent,
					farm,
					farmer,
					supplier: this.current_farmer_data.supplier,
					warehouse,
					items: JSON.stringify(items),
				}
			);

			frappe.show_alert(
				{ message: __("Purchase Invoice {0} saved.", [pi_name]), indicator: "green" },
				6
			);

			// Reset the form for the next purchase — do not navigate away
			await this._reset();
		} catch (e) {
			// error already shown by frappe.xcall
		} finally {
			$btn.prop("disabled", false).text(__("Save Purchase Invoice"));
		}
	}
}
