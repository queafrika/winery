/* Winery App — Dirty Form Tab Bar
 * When a user navigates away from an unsaved form, it appears as a
 * recoverable tab pinned to the bottom of the screen. Clicking the tab
 * navigates back and restores all unsaved field values.
 */
(function () {
    "use strict";

    var dirtyTabs = {};

    function esc(str) {
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function saveTab(frm) {
        if (!frm || !frm.doctype || !frm.docname) return;
        var key = frm.doctype + "::" + frm.docname;
        dirtyTabs[key] = {
            doctype: frm.doctype,
            docname: frm.docname,
            doc: JSON.parse(JSON.stringify(frm.doc)),
        };
        renderBar();
    }

    function removeTab(key) {
        delete dirtyTabs[key];
        renderBar();
    }

    function getBar() {
        var bar = document.getElementById("winery-dirty-bar");
        if (!bar) {
            bar = document.createElement("div");
            bar.id = "winery-dirty-bar";
            document.body.appendChild(bar);
        }
        return bar;
    }

    function renderBar() {
        var bar = getBar();
        var keys = Object.keys(dirtyTabs);
        bar.innerHTML = "";

        if (!keys.length) {
            bar.classList.remove("winery-dirty-bar--visible");
            return;
        }

        bar.classList.add("winery-dirty-bar--visible");

        var lbl = document.createElement("span");
        lbl.className = "winery-dirty-bar__label";
        lbl.textContent = "Unsaved";
        bar.appendChild(lbl);

        keys.forEach(function (key) {
            var tab = dirtyTabs[key];
            var el = document.createElement("div");
            el.className = "winery-dirty-tab";
            el.innerHTML =
                '<span class="winery-dirty-tab__dot"></span>' +
                '<span class="winery-dirty-tab__name">' +
                    esc(tab.doctype) + " &mdash; " + esc(tab.docname) +
                "</span>" +
                '<button class="winery-dirty-tab__close" title="Discard">\u00d7</button>';

            el.querySelector(".winery-dirty-tab__name").addEventListener("click", function () {
                openTab(key);
            });
            el.querySelector(".winery-dirty-tab__close").addEventListener("click", function (e) {
                e.stopPropagation();
                removeTab(key);
            });

            bar.appendChild(el);
        });
    }

    function openTab(key) {
        var tab = dirtyTabs[key];
        if (!tab) return;
        var savedDoc = tab.doc;

        frappe.set_route("Form", tab.doctype, tab.docname).then(function () {
            // Wait for the form to finish rendering before patching values
            var attempts = 0;
            var restore = setInterval(function () {
                attempts++;
                if (
                    cur_frm &&
                    cur_frm.doctype === tab.doctype &&
                    cur_frm.docname === tab.docname &&
                    cur_frm.fields_dict
                ) {
                    clearInterval(restore);
                    Object.keys(savedDoc).forEach(function (f) {
                        if (f.charAt(0) !== "_" && f !== "docstatus") {
                            cur_frm.doc[f] = savedDoc[f];
                        }
                    });
                    cur_frm.dirty();
                    cur_frm.refresh_fields();
                    removeTab(key);
                    frappe.show_alert({ message: "Unsaved changes restored.", indicator: "orange" });
                } else if (attempts > 20) {
                    clearInterval(restore);
                }
            }, 150);
        });
    }

    function patchFormHide() {
        if (!frappe || !frappe.ui || !frappe.ui.form || !frappe.ui.form.Form) {
            setTimeout(patchFormHide, 300);
            return;
        }
        var proto = frappe.ui.form.Form.prototype;
        var _orig = proto.on_hide;
        proto.on_hide = function () {
            if (this.is_dirty && this.is_dirty()) {
                saveTab(this);
            }
            if (_orig) _orig.call(this);
        };
    }

    patchFormHide();
})();

/* Winery App — Sidebar Header Logo Override
 * Retries on an interval until the logo is injected, then keeps a lightweight
 * poll to re-apply if Frappe ever replaces it.
 */
(function () {
	"use strict";
	
	var LOGO_SRC = "/files/ropen logo.png";
	var LOGO_IMG =
		'<img src="' +
		LOGO_SRC +
		'" data-ropen-logo="1" ' +
		'style="width:100%;height:100%;object-fit:contain;border-radius:3px;" alt="Ropen">';

	function applyLogo() {
		var headerLogo = document.querySelector(
			".body-sidebar .sidebar-header .header-logo"
		);

		var headerName = document.querySelector(
			".sidebar-item-label .header-subtitle"
		);

		if (headerLogo && !headerLogo.querySelector("[data-ropen-logo]")) {
			headerLogo.innerHTML = LOGO_IMG;
		}

		if (headerName) {
			headerName.textContent = "Ropen Coffee and Fine Foods";
		}
	}

	// Try immediately, then at 500 ms, 1 s, 2 s, and 3 s to beat Frappe's render
	[0, 500, 1000, 2000, 3000].forEach(function (delay) {
		setTimeout(applyLogo, delay);
		console.log("Scheduled logo application at " + delay + " ms");
	});

	// After initial burst, keep a light poll every 2 s to handle re-renders
	setInterval(applyLogo, 2000);
})();
