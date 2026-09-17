# Decisions

ADR-style notes, one per sprint, per the plan's working method. Short — the
"why," not a changelog (that's what `git log` is for).

## Dependabot alerts #1-4 (chromadb) — assessed, not actioned

All four are ChromaDB's HTTP-server-mode vulnerabilities (GHSA-f4j7-r4q5-qw2c,
-2wm9-hf6c-p5cr, -xph7-9rjv-w5fr, -36p7-vc44-83pf) — pre/post-auth code
injection and tenant-isolation bugs in the `/api/v2/tenants/.../collections`
endpoints, reachable only via `chromadb.HttpClient`/`chroma run`. This app
uses `langchain_community.vectorstores.Chroma` in embedded/persistent mode —
no HTTP server, no network listener, none of those endpoints exist in this
deployment. No patched version exists for any of them yet regardless. Left
open rather than dismissed (dismissing would overstate confidence given
there's no patch to verify against) — Sprint 3's planned Chroma → Qdrant
swap removes the dependency entirely, which resolves these as a side effect
rather than a targeted fix.

## Sprint 1 — Foundation: repo, deps, config, CI

**What landed:** `jurisai/Backend/app.py` ported module-by-module into
`backend/app/` on FastAPI, matching the target architecture tree. `pyproject.toml`
+ `uv.lock`, `config.py` (pydantic-settings, fails fast on a missing
`MONGO_URI`/`MISTRAL_API_KEY`), Dockerfile (multi-stage, non-root, healthcheck),
`docker-compose.yml` (app + self-hosted Mongo + an as-yet-unused Qdrant service),
GitHub Actions CI (ruff, mypy on `app/`, pytest, pip-audit, gitleaks, docker build),
and a hermetic pytest smoke suite (mocks Mongo and the vector store — production
startup still does both for real).

**Faithfully preserved, not fixed here** (open issues, sprint labels unchanged):
- D004-D008 — no auth, no `user_id` filtering, any `session_id` is readable/
  renameable/deletable by anyone (Sprint 2).
- D013 — CORS still allows all origins (Sprint 4).
- D014 — exception text still reaches the client, now via FastAPI's `detail`
  field rather than Flask's `error` key; the leak itself is unchanged (Sprint 4).
- D015 — no rate limiting on `/api/chat` (Sprint 2).
- D017 — ingestion still runs synchronously at startup, now via a FastAPI
  lifespan hook rather than Flask's top-level module code — same mechanical
  role, same failure mode, just the framework-idiomatic location for it
  (Sprint 3 decouples this into `scripts/ingest.py`).
- D024, D025, D029 — raw `Document` reprs in the prompt, Mistral error strings
  stored as answers, and silent chat-persistence failures are all still there
  (Sprint 3's prompt-construction rework).
- D026, D028 — rename-no-op false-404 and missing `$sort` after `$group`
  (Sprint 4).

**Closed this sprint, as an unavoidable side effect of a working port:**
- D033 (deprecated pre-0.1 `langchain.*` import paths) — these modules don't
  exist in a current `langchain-community` install, so a port that actually
  runs has to use `langchain_community.*` paths. The chunking strategy and
  vector store are unchanged; only the import path moved. (Note: while fixing
  this, `langchain-community` itself started emitting a sunset/deprecation
  warning — one more reason Sprint 3's full LangChain removal is right, not
  scope creep.)

**Scope decisions:**
- **No frontend in this sprint.** Sprint 1's numbered items are module split,
  packaging, config, Docker, CI, and a smoke test — none of them are frontend
  work, and the full page rebuild is explicitly Sprint 5's job. This sprint is
  API-only; `docker compose up` gives you a working backend, not a browsable
  site yet.
- **Routes moved under `/api/*`** (`/chat` → `/api/chat`, etc.), matching the
  target architecture's `api/chat.py` comment. Cosmetic, and safe now because
  nothing outside this repo depends on the old paths yet.
- **The IPC source PDF was copied into `data/ipc/` this sprint**, ahead of
  Sprint 3's ingest-CLI work. Necessary, not scope creep: the ported
  startup-time ingestion literally cannot start without it, and copying this
  one named file is the explicit, blessed exception in `CLAUDE.md` (unlike a
  bulk copy of the legacy tree). Committed via Git LFS, closing part of D045.
- **Self-hosted Mongo from day one**, not Atlas — this was never sprint-gated
  in the plan (unlike the Chroma → Qdrant swap, which is tied to Sprint 3's
  corpus abstraction), so there was no reason to stand up Atlas first and
  tear it down later.

**Not done: branch protection on `main`.** GitHub's branch protection (classic
and the newer Rulesets) both require GitHub Pro on a private repo — free tier
only allows either on a public repo. Both paths conflict with a standing
decision: Pro is a paid tool we ruled out for the MVP, and public would expose
the audit trail (60 findings, several still open) that we specifically moved
to GitHub Issues to keep out of a future-public repo. Decision: skip
GitHub-enforced protection for now, rely on always checking CI status before
treating a PR as mergeable. Revisit once funded (Pro) or once the open
findings are closed down enough that going public is fine either way.

## Sprint 2 — Authentication and authorization

**What landed:** self-hosted JWT auth (argon2 password hashing, 15-minute
access tokens returned in the response body, 7-day refresh tokens as an
httpOnly/SameSite=strict cookie, tracked server-side by `jti` so logout can
actually revoke one). `app/core/security.py`'s `current_user` dependency is a
thin JWT-decode step specifically so a departmental OIDC/SSO provider can
replace it later without touching any route. `/api/auth/{signup,login,
refresh,logout,me}`, all four session routes and `/api/chat` now require it
and scope every query by `user_id`. Rate limiting (`slowapi`, 20/min, keyed by
user where a token is present, IP otherwise) on `/api/chat`. A minimal
`login.html` — plain HTML/JS, `textContent` only, access token held in a JS
variable (never `localStorage`) — replaces the legacy fake-submit page.

**Closed this sprint:**
- D004-D008 (no auth, no ownership anywhere) — every session route and
  `/api/chat` now require a verified token, and `ChatRepository` filters by
  `user_id` on every query, so a session that isn't yours matches nothing.
  Verified by `test_user_cannot_touch_another_users_session`: a 404 (or an
  empty list, for the GET routes) on all of history/session/rename/delete —
  never a 403, which would itself confirm the session_id exists.
- D015 (no rate limiting on the paid LLM route).
- D019 (`login.html` fake `setTimeout` submit) — replaced with a real
  signup/login flow against the new auth API.
- D021 (`toggleForm()` TypeError on a removed field) — moot; the rewritten
  page has no such field to remove.

**Still open, not this sprint's job:**
- D014, D026, D028 — same as Sprint 1's note; still Sprint 4.
- D024, D025, D029 — still Sprint 3.

**Scope decisions:**
- **No separate `/account` page.** The plan's item 5 asks for one "showing
  real data" — the point being to prove auth actually gates something and
  displays real user state end-to-end, not the page itself. `GET /api/auth/me`
  plus `login.html` rendering "Signed in as {email}" after a real login
  already demonstrates that; a dedicated `/account` page with real settings
  is Sprint 5 work once there's an actual account to manage.
- **No automatic access-token refresh loop in `login.html`.** There's nothing
  yet that needs a session to stay alive past login (no chat UI exists until
  Sprint 5) — `/api/auth/refresh` exists and is tested, but wiring a
  refresh-before-expiry timer into a page with nothing to keep logged into
  would be speculative.
- **Phone-OTP signup is still out of scope**, per the plan's MVP note (Indian
  DLT SMS registration is a funded-phase cost) — email/password only.
- **CORS is untouched (still wildcard, D013).** Cookie-based refresh works
  fine same-origin, which is what exists until Sprint 5 introduces a real
  frontend origin — this sprint didn't need to touch it.
findings are closed down enough that going public is fine either way.
