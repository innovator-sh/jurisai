// Login page. Deliberately does NOT use auth.js's apiFetch/accessToken --
// this page is what *creates* the session, there's nothing to refresh yet.
// Ported from the original inline <script> (now external -- CSP is
// default-src 'self', no 'unsafe-inline'), same "access token stays in
// memory only" reasoning: it's read once here just to confirm success,
// then thrown away -- the real post-navigation bootstrap on every other
// page is POST /api/auth/refresh against the httpOnly cookie (auth.js).

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("auth-form");
  const statusEl = document.getElementById("status");

  function setStatus(text, kind) {
    statusEl.textContent = text; // textContent, never innerHTML
    statusEl.className = "form-status" + (kind ? ` ${kind}` : "");
  }

  async function submitAuth(path) {
    const email = document.getElementById("email").value;
    const password = document.getElementById("password").value;
    const payload = { email, password };

    if (path === "signup") {
      // DPDP: consent is an affirmative act and the role is required -- the
      // server enforces both too (422), this just fails fast with a clear message.
      const role = document.getElementById("role").value;
      if (!role) {
        setStatus("Please choose whether you are a citizen, lawyer, or police.", "error");
        return;
      }
      if (!document.getElementById("consent").checked) {
        setStatus("Please confirm you are 18+ and accept the Privacy Notice to sign up.", "error");
        return;
      }
      payload.role = role;
      payload.consent = true;
    }

    let res;
    try {
      res = await fetch(`/api/auth/${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include", // receive the refresh_token cookie
        body: JSON.stringify(payload),
      });
    } catch {
      setStatus("Could not reach the server. Please try again.", "error");
      return;
    }

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      // Every error body is {"error": "<message>", "request_id": ...}
      // (core/errors.py); a 422 validation failure is the one exception.
      const message = typeof data.error === "string" ? data.error : null;
      setStatus(message || "Please check the details you entered.", "error");
      return;
    }

    setStatus("Signed in — redirecting...", "success");
    window.location.assign("/");
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    submitAuth("login");
  });
  document.getElementById("signup-btn").addEventListener("click", () => submitAuth("signup"));
});
