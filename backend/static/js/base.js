// Shared across every page via base.html. Runs unblocked (no defer) so the
// theme class applies before first paint -- only touches document.body,
// which already exists at this point in <body>. Sidebar-expand state is
// deferred to DOMContentLoaded since the sidebar markup (rendered by pages
// that include _sidebar.html) hasn't been parsed yet when this line runs.
(function () {
  try {
    if (localStorage.getItem("theme") === "light") {
      document.body.classList.add("light-theme");
    }
  } catch {
    // Private browsing / blocked storage -- fall back to the default theme.
  }
})();

document.addEventListener("DOMContentLoaded", () => {
  const sidebar = document.getElementById("sidebar");
  if (!sidebar) return;

  let expanded = true;
  try {
    const saved = localStorage.getItem("sidebarExpanded");
    expanded = saved === "true" || (saved === null && window.innerWidth > 768);
  } catch {
    expanded = window.innerWidth > 768;
  }
  sidebar.classList.toggle("expanded", expanded);

  const toggleBtn = document.getElementById("toggleSidebar");
  if (toggleBtn) {
    toggleBtn.addEventListener("click", () => {
      const isExpanded = sidebar.classList.toggle("expanded");
      try {
        localStorage.setItem("sidebarExpanded", String(isExpanded));
      } catch {
        // Per-viewer convenience only -- fine if it can't persist.
      }
    });
  }

  // Each nav item holds a real <a href> (keyboard, middle-click and screen
  // readers all work natively). The extra row handler only widens the click
  // target to the <li>'s padding.
  document.querySelectorAll(".sidebar-menu li").forEach((item) => {
    const link = item.querySelector("a.nav-link");
    if (!link) return;
    item.addEventListener("click", (e) => {
      if (e.target.closest("a")) return;
      window.location.assign(link.getAttribute("href"));
    });
  });
});
