// settings.html -- pure client-side preferences, no backend field needed.
//
// localStorage keys this file owns:
//   "theme"             -- "light" | "dark" (base.js reads this same key on
//                           every page load to apply body.light-theme before
//                           first paint; any value other than "light" is
//                           treated as dark, matching base.js's check).
//   "defaultCorpusMode" -- "" | "bns" | "ipc" ("" means Auto/hybrid). Meant
//                           to be read by chat.js as the default value of
//                           the chat page's corpus toggle; chat.js didn't
//                           exist yet when this was written, so it must
//                           tolerate the key being absent (treat as "").
document.addEventListener("DOMContentLoaded", async () => {
  const ok = await ensureAuthenticated();
  if (!ok) return;

  const themeToggle = document.getElementById("themeToggle");
  let currentTheme = "dark";
  try {
    currentTheme = localStorage.getItem("theme") === "light" ? "light" : "dark";
  } catch {
    // Fall back to the in-memory default above.
  }
  themeToggle.checked = currentTheme === "light";

  themeToggle.addEventListener("change", () => {
    const light = themeToggle.checked;
    document.body.classList.toggle("light-theme", light);
    try {
      localStorage.setItem("theme", light ? "light" : "dark");
    } catch {
      // Per-viewer convenience only -- fine if it can't persist.
    }
  });

  const corpusButtons = document.querySelectorAll("#corpusPrefGroup .corpus-pref-option");
  let savedCorpus = "";
  try {
    savedCorpus = localStorage.getItem("defaultCorpusMode") || "";
  } catch {
    savedCorpus = "";
  }

  function setActiveCorpusButton(value) {
    corpusButtons.forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.corpus === value);
    });
  }
  setActiveCorpusButton(savedCorpus);

  corpusButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const value = btn.dataset.corpus;
      setActiveCorpusButton(value);
      try {
        localStorage.setItem("defaultCorpusMode", value);
      } catch {
        // Per-viewer convenience only -- fine if it can't persist.
      }
    });
  });
});
