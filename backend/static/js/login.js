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

    let res;
    try {
      res = await fetch(`/api/auth/${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include", // receive the refresh_token cookie
        body: JSON.stringify({ email, password }),
      });
    } catch {
      setStatus("Could not reach the server. Please try again.", "error");
      return;
    }

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setStatus(data.detail || "Something went wrong.", "error");
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
