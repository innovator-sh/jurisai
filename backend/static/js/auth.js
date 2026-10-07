// Shared by every authenticated page (index/account/settings/legal -- not
// login.html, which doesn't have a session yet). Loaded before the page's
// own script in base.html's {% block scripts %}.
//
// Access token lives in a module-level variable only -- never localStorage
// or sessionStorage, so an XSS payload that survives a page load can't read
// it (same reasoning as login.html's original design). A full page
// navigation wipes this variable, so every page re-establishes it from the
// httpOnly refresh_token cookie via POST /api/auth/refresh on load, rather
// than trying to persist the access token itself across navigations.
let accessToken = null;

async function refreshAccessToken() {
  try {
    const res = await fetch("/api/auth/refresh", {
      method: "POST",
      credentials: "include",
    });
    if (!res.ok) {
      accessToken = null;
      return false;
    }
    const data = await res.json();
    accessToken = data.access_token;
    return true;
  } catch {
    accessToken = null;
    return false;
  }
}

// Call once near the top of each authenticated page. Redirects to /login
// on failure and resolves false, so callers can bail out of further setup.
async function ensureAuthenticated() {
  const ok = await refreshAccessToken();
  if (!ok) {
    window.location.assign("/login");
  }
  return ok;
}

// fetch() wrapper that attaches the bearer token and retries once, after a
// silent refresh, on a 401 (covers the access token expiring mid-session).
async function apiFetch(path, options) {
  options = options || {};
  const doFetch = () =>
    fetch(path, {
      ...options,
      credentials: "include",
      headers: {
        ...(options.headers || {}),
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
    });

  let res = await doFetch();
  if (res.status === 401) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      res = await doFetch();
    } else {
      window.location.assign("/login");
    }
  }
  return res;
}

async function logout() {
  await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
  accessToken = null;
  window.location.assign("/login");
}
