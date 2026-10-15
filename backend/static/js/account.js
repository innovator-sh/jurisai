// account.html -- closes #25 (account.html was a literal "coming soon" stub).
// Shows the signed-in email and wires up the already-working
// POST /api/auth/delete_account (D059/#61) to a real UI for the first time.
document.addEventListener("DOMContentLoaded", async () => {
  const ok = await ensureAuthenticated();
  if (!ok) return;

  const emailEl = document.getElementById("accountEmail");
  try {
    const res = await apiFetch("/api/auth/me");
    if (res.ok) {
      const user = await res.json();
      emailEl.textContent = user.email; // textContent only -- never innerHTML
      const ROLE_LABELS = {
        citizen: "Citizen / member of the public",
        lawyer: "Lawyer / legal professional",
        police: "Police / law enforcement",
      };
      document.getElementById("accountRole").textContent =
        "Role: " + (ROLE_LABELS[user.role] || user.role);
    } else {
      emailEl.textContent = "Could not load your account.";
    }
  } catch {
    emailEl.textContent = "Could not load your account.";
  }

  document.getElementById("logoutBtn").addEventListener("click", () => {
    logout();
  });

  const passwordInput = document.getElementById("deletePassword");
  const deleteBtn = document.getElementById("deleteAccountBtn");
  const statusEl = document.getElementById("deleteStatus");

  deleteBtn.addEventListener("click", async () => {
    const password = passwordInput.value;
    if (!password) {
      statusEl.textContent = "Enter your password to confirm.";
      statusEl.className = "form-status error";
      return;
    }

    const confirmed = window.confirm(
      "This permanently deletes your account, all chat history, and all " +
        "active sessions. This cannot be undone. Continue?"
    );
    if (!confirmed) return;

    deleteBtn.disabled = true;
    statusEl.textContent = "";
    statusEl.className = "form-status";
    try {
      const res = await apiFetch("/api/auth/delete_account", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (res.ok) {
        window.location.assign("/login");
        return;
      }
      const data = await res.json().catch(() => ({}));
      statusEl.textContent = data.error || "Could not delete your account.";
      statusEl.className = "form-status error";
    } catch {
      statusEl.textContent = "Could not delete your account. Check your connection.";
      statusEl.className = "form-status error";
    } finally {
      deleteBtn.disabled = false;
    }
  });
});
