$(document).on("desktop_screen", function () {
	var container = document.querySelector(".desktop-container");
	if (!container) return;

	// ── Logo panel ────────────────────────────────────────────────────────────
	if (!container.querySelector(".desktop-logo-panel")) {
		var panel = document.createElement("div");
		panel.className = "desktop-logo-panel";
		panel.innerHTML =
			'<img src="/files/ropen logo.png" alt="Ropen Logo" class="desktop-brand-logo">';
		container.appendChild(panel);
	}

	// Prevent double-init
	if (container.querySelector(".winery-tabs")) return;

	var iconsContainer = container.querySelector(".icons-container");
	if (!iconsContainer) return;

	// Wrap tabs + icons in a column so tabs sit above the grid
	var contentArea = document.createElement("div");
	contentArea.className = "winery-content-area";
	iconsContainer.parentNode.insertBefore(contentArea, iconsContainer);
	contentArea.appendChild(iconsContainer);

	// Company title
	var title = document.createElement("h2");
	title.className = "winery-company-title";
	title.textContent = "Ropen Coffee and Fine Foods Ltd";
	contentArea.insertBefore(title, iconsContainer);

	// Tab bar placeholder (populated after API call)
	var tabBar = document.createElement("div");
	tabBar.className = "winery-tabs";
	contentArea.insertBefore(tabBar, iconsContainer);

	// Hide Frappe's native icon grid — we render our own
	iconsContainer.style.display = "none";

	// Custom icon grid
	var customGrid = document.createElement("div");
	customGrid.className = "winery-icon-grid";
	contentArea.appendChild(customGrid);

	// ── Fetch config from server ──────────────────────────────────────────────
	frappe.call({
		method: "winery.winery.api.get_desktop_config",
		callback: function (r) {
			var tabs = r.message || [];

			if (!tabs.length) {
				customGrid.innerHTML =
					"<p class='winery-empty'>No desktop configuration found. " +
					"Add entries in <strong>Winery Desktop Tab</strong> and " +
					"<strong>Winery Desktop Icon</strong>.</p>";
				return;
			}

			var activeTab = tabs[0].tab_name;

			// ── Render icons for a given tab ─────────────────────────────────
			function renderIcons(tabName) {
				customGrid.innerHTML = "";
				var tab = tabs.find(function (t) { return t.tab_name === tabName; });
				if (!tab) return;

				if (!tab.icons.length) {
					customGrid.innerHTML = "<p class='winery-empty'>No icons configured for this tab.</p>";
					return;
				}

				tab.icons.forEach(function (icon) {
					var card = document.createElement("a");
					card.className = "winery-icon-card";
					card.href = "#";

					var letter = (icon.icon_label || "?").charAt(0).toUpperCase();
					card.innerHTML =
						"<div class='winery-icon-badge'>" + letter + "</div>" +
						"<div class='winery-icon-label'>" + frappe.utils.escape_html(icon.icon_label) + "</div>";

					card.addEventListener("click", function (e) {
						e.preventDefault();
						if (icon.workspace_sidebar) {
							// Navigate to the workspace sidebar
							var ws = frappe.boot.workspace_sidebar_item
								? frappe.boot.workspace_sidebar_item[icon.workspace_sidebar.toLowerCase()]
								: null;
							if (ws) {
								frappe.set_route("Workspaces", icon.workspace_sidebar);
							} else {
								frappe.set_route(icon.workspace_sidebar);
							}
						}
					});

					customGrid.appendChild(card);
				});
			}

			// ── Build tab buttons ─────────────────────────────────────────────
			function setActiveTab(tabName) {
				activeTab = tabName;
				tabBar.querySelectorAll(".winery-tab-btn").forEach(function (btn) {
					btn.classList.toggle("active", btn.dataset.tab === tabName);
				});
				renderIcons(tabName);
			}

			tabs.forEach(function (tab, i) {
				var btn = document.createElement("button");
				btn.className = "winery-tab-btn" + (i === 0 ? " active" : "");
				btn.textContent = tab.tab_name;
				btn.dataset.tab = tab.tab_name;
				btn.addEventListener("click", function () {
					setActiveTab(tab.tab_name);
				});
				tabBar.appendChild(btn);
			});

			renderIcons(activeTab);
		},
	});
});
