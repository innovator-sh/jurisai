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

  document.querySelectorAll(".sidebar-menu li[data-nav-href]").forEach((item) => {
    const navigate = () => window.location.assign(item.getAttribute("data-nav-href"));
    item.addEventListener("click", navigate);
    // role="link" + tabindex="0" makes these keyboard-focusable, but a <li>
    // has no native activation key -- wire Enter/Space ourselves (a11y pass).
    item.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        navigate();
      }
    });
  });
});
