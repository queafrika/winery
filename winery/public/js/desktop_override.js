// Inject the Ropen logo panel into the desktop page each time it renders.
// 'desktop_screen' is triggered by DesktopPage.setup() after make() completes,
// so .desktop-container already exists and icons have been appended.
$(document).on("desktop_screen", function () {
	var container = document.querySelector(".desktop-container");
	if (container && !container.querySelector(".desktop-logo-panel")) {
		var panel = document.createElement("div");
		panel.className = "desktop-logo-panel";
		panel.innerHTML =
			'<img src="/files/ropen logo.png" alt="Ropen Logo" class="desktop-brand-logo">';
		container.appendChild(panel);
	}
});
