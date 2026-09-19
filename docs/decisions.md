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

## Sprint 3 — RAG correctness, corpus abstraction, and the LLM layer

**What landed:** `corpora/registry.py` + `definitions.yaml` (ipc enabled, bns
declared but not built); LangChain and Chroma removed entirely in favour of
direct clients (`qdrant-client`, `sentence-transformers`, `pypdf`); a
section-aware chunker built and validated against the *real* source PDF
rather than assumed (see below); `rag/router.py` implementing the plan's
full 4-rule precedence, tested against a registry with both corpora enabled
since the real one only has ipc; `rag/prompts.py` (system/context/user
separation, with a `build_hybrid_context` seam for Sprint 3B); the
`LLMProvider` protocol with Groq (default) and Mistral (alternate)
implementations — both verified against the actual installed SDKs' real
APIs, not assumed from memory — plus Anthropic/Bedrock stubs; a
self-contained retrieval-hit-rate eval harness (`scripts/eval.py`).

**The source PDF is not a bare-act text.** It's a ~1,870-page annotated
commentary edition (statute text interleaved with case law, footnotes, and
`[s N]` cross-references) — discovered by inspecting it before writing a
parser, not by assuming its shape. That inspection caught three real bugs
before they shipped, each verified against known sections (302, 379, 420,
34, 149, 300, 499, ...) before trusting the parser:
1. The `[s N]` marker also appears inline inside footnotes quoting
   superseded law (a footnote on section 375 recites the pre-2013 wording,
   complete with its own `[s 375]` tag) — a naive first-match search would
   have retrieved repealed text as current law. Fixed by requiring a
   genuine heading to start a line (optionally after a footnote-number
   artifact like section 34's actual `170.[[s 34]`).
2. Titles that wrap across two lines (e.g. section 149) were truncated by
   an end-of-line assumption, corrupting the body text with a leftover
   title fragment. Fixed by accumulating text to the first `.`/em-dash
   wherever it falls, not at end-of-line.
3. Seven heavily-amended sections (107, 108, 109, 121, 375, 376, 464) don't
   have a detectable "COMMENT" boundary or matching next-heading in this
   format, so extraction ran on and swallowed a neighbouring section's text
   (content that is actually section 376 turned up labelled 375). Rather
   than ingest unverified, possibly-mislabelled content, sections whose raw
   block exceeds 10,000 chars are excluded and logged — chosen because
   there's a clean gap in the length distribution between the longest
   confirmed-correct section (8,637 chars, defamation's ten exceptions,
   verified to end correctly) and the shortest confirmed-contaminated one
   (13,058 chars). `scripts/ingest.py` prints exactly which sections were
   skipped on every run.

**Retrieval threshold calibrated on real data, not guessed.** Ran a real
ingest + query test before picking `RETRIEVAL_SCORE_THRESHOLD`: relevant
queries scored 0.58-0.70 (cosine similarity), a clearly off-topic control
query ("how do I bake a chocolate cake?") topped out at 0.29 — a clean
separation, with the chosen default of 0.5 sitting in the gap.

**Eval harness baseline: 18/20 (90%) hit-rate** on IPC (`backend/tests/eval/
ipc_questions.yaml`, run via `scripts/eval.py --corpus ipc`, self-contained
against an in-memory Qdrant so it needs no live service). Both misses are
semantic near-confusions with adjacent sections in the same chapter, not
wild errors: "voluntarily causing hurt" (323) retrieved 322/334/325, all
closely related hurt-family offences; "theft in a dwelling house" (380)
retrieved trespass-adjacent sections (451/450) instead. Recorded as the
honest baseline the exit criteria asks for, not tuned toward 100% on a
20-question set that would just be overfitting to it.

**Not done, tracked open:**
- **D056/D057 (multilingual + hybrid dense/sparse embeddings)** — still
  English-only `multi-qa-mpnet-base-dot-v1`, dense-only. The BGE-M3 swap
  needs a ~2GB model download and the `FlagEmbedding` package for its
  sparse output, neither of which this sprint's time budget covered testing
  properly. Deliberately deferred, not silently dropped.
- **Streaming.** `LLMProvider` only has `complete()` — no route consumes
  SSE until Sprint 5 rebuilds the frontend, so `stream()` isn't on the
  protocol yet; adding it when something actually calls it avoids dead code.
- **Hybrid retrieval across corpora** is Sprint 3B's job by design — the
  router already returns `needs_clarification` rather than guessing when
  more than one corpus is enabled with no date/citation to disambiguate.

**Scope decision:** an offence date after 1 Jul 2024 correctly returns
"needs clarification" today, not a forced IPC answer — "the router always
resolves to ipc for now" (the plan's phrasing) describes the *default*
case, not one where applying IPC would be a real legal-correctness error.
Silently answering a post-cutover query under superseded law would be
worse than asking.

## Sprint 3B — Onboard BNS and the hybrid model

**Source:** NCRB's published BNS bare-act PDF (`data/bns/bns-data.pdf`,
sha256 `a83f12a93e32c9e0b39a85f75850a448dc4682b1b44b2d6bd680165bb9931549`,
retrieved 2026-09-18), chosen over the MHA Gazette copy (also downloaded and
compared) because NCRB's includes both a clean section-title index and the
official IPC↔BNS "Corresponding Section Table" in one document — the MHA
Gazette has neither. India Code's canonical copy (`a2023-45.pdf`) 302-redirects
to an HTML wall and isn't scriptable; worth citing as the canonical reference
even though NCRB's copy is what's actually ingested. Section count verified
against public sources (358) before trusting the extraction: exact match.

**New loader architecture: `corpora/loaders/`.** Confirmed, not assumed,
that BNS needs a different parser: running the IPC loader's `[s N]` pattern
against the BNS PDF finds zero sections, and vice versa — these are
different document formats, not different dialects of one format. `Corpus`
gained a `loader` field (`ipc_commentary` / `bns_bare_act`), dispatched by
name in `rag/ingest.py`'s `LOADERS` dict, matching the plan's original
"per-format loaders" design more literally than Sprint 3's single-format
`rag/chunking.py` needed to.

**`bns_bare_act.py` — genuinely a bare act, no case-law commentary
interleaved**, unlike IPC's source. All 358 sections extracted with zero
exclusions needed (versus IPC's 7 low-confidence exclusions) — a real
structural difference between the two documents, not a quality gap in this
parser. Three bugs caught by testing against known sections (63, 103, 129,
144, 154, 303, 318, ...) before trusting it:
1. The marginal title for a section sits on its own line *immediately
   before* the number, not just in the arrangement-of-sections index — and
   a handful of these lines have a single stray leading space ("Criminal
   force. \n 129. Whoever...", confirmed to be a PDF-extraction artifact,
   not a real second markup convention).
2. Titles wrap across two lines, same class of bug as the IPC loader, but
   discovered from the opposite direction: because the title sits *before*
   its own number here, the fix also has to trim the *previous* section's
   body, which was otherwise running on to swallow the next section's
   title (found on section 2, which was absorbing "General explanations."
   — section 3's title — at its tail).
3. Chapter headings ("CHAPTER II") and Title-Case sub-chapter group
   headings ("Of Theft", "Of sexual offences") both sit between sections
   and must not be swept into a title — missing the Title-Case form first
   produced "Of sexual offences Rape." for section 63.

**Hybrid retrieval and the answer contract landed as part of this sprint,
not Sprint 3.** Sprint 3's router already had a "default: hybrid" branch in
the precedence rules, but it was never actually reachable — only one
corpus was ever enabled, so every path collapsed to it, and the branch
returned `needs_clarification` instead of a real hybrid result (a mistake
in the original implementation, not a deliberate deferral — caught only
once bns was actually enabled and the branch ran for real). Fixed:
`RoutingResult` now carries `corpora: list[Corpus]` (primary/superseding
corpus first — a corpus with `supersedes` set is definitionally current
law, so this doesn't hardcode "bns"), `/api/chat` retrieves from every
corpus in that list and builds a combined context, and
`build_hybrid_system_prompt` implements the plan's answer contract
structure (current position first, earlier-act counterpart second, explicit
note on new/changed provisions) — though without automated crosswalk-backed
relation flags yet, since the crosswalk itself is unreviewed (see below).

**The crosswalk (`data/crosswalk/ipc_bns.csv`, `scripts/build_crosswalk.py`)
is a draft scaffold for human review, not reviewed data — every one of its
377 rows is `confidence=unreviewed`, and nothing in the app consults it for
live answers.** This was, by a wide margin, the hardest parsing problem
this project has hit: NCRB's "Corresponding Section Table" is a two-column
layout that pypdf extracts inconsistently — sometimes each cell lands on
its own line, sometimes both cells' content is glued onto one line when
short ("Punishments.  53. Punishments."). Both the BNS and IPC columns use
the identical "N. Title." lexical pattern with no positional signal to
tell them apart from text alone. What the build script actually does,
adopted after three earlier approaches failed in testing:
- Row boundaries are found using the **already-verified, ordered list of
  real BNS section numbers** (from `bns_bare_act`'s own extraction) as
  ground truth, not a numeric-ascending heuristic — IPC numbers ascend
  within their own chapters too, so "ascending" alone can't tell the
  columns apart. A lookahead-and-resync step (search up to 6 entries ahead
  in the known sequence, not just the immediate next one) was necessary
  because a single missed match anywhere in the ~55-page table otherwise
  desyncs every row after it — confirmed by watching the row count jump
  from 316 to 352 (of 356 possible) once this was added.
- BNS sections 2 (Definitions) and 3 (General explanations) are excluded
  entirely. Their table entries are bracketed sub-clauses ("2(1)", "2(2)",
  ...) with no period, which don't fit the row-boundary pattern and
  corrupted grouping when included — and they're term definitions, not
  offences, which is what this crosswalk is actually for.
- Titles are **not** taken from the table's own (unreliably-interleaved)
  text at all. Each row's title is looked up from the same
  already-validated `ipc_commentary`/`bns_bare_act` extractions that build
  the retrieval index — so a crosswalk title is only ever as trustworthy as
  data already proven correct elsewhere, never a second unverified source.
- `relation: repealed_candidate` is inferred **indirectly**: any IPC
  section the loader extracted that never appears in any row's mapping is
  flagged as a candidate, rather than parsing the table's "Deleted" marker
  directly (instances of it weren't reliably distinguishable from
  surrounding noise in testing). This can't tell a genuine repeal apart
  from a row this script simply missed — the resulting list is
  qualitatively sensible (many flagged sections literally say "[Repealed]"
  or "[Omitted]" in their own IPC text, e.g. the Thuggee provisions and
  attempted suicide) but is exactly the kind of ambiguity a human review
  is for, not a claim this script is making.
- Result: 352 of 356 in-scope BNS sections mapped (4 — sections 6, 7, 9,
  319 — never matched; investigate those four specifically during review),
  plus 25 repeal candidates. Relation counts: 276 renumbered, 61 merged, 15
  new, 25 repealed_candidate.

**Not done — deliberately, pending the crosswalk's human review:**
- No crosswalk-backed relation flags in live answers. Wiring "this
  provision was `modified`/`new`" into the hybrid prompt from unreviewed
  data would be exactly the "hallucinated section mapping" failure mode the
  plan calls the worst one this product can have — the loader
  (`corpora/crosswalk.py`) exists and is tested, but nothing calls it from
  `api/chat.py` yet.
- No UI corpus selector, no FIR-form registry wiring (plan items 6-7) —
  same reasoning as every prior sprint: no frontend exists beyond
  `login.html` until Sprint 5, and building a selector for a page that
  doesn't exist would be speculative. `containsIPC()` in the legacy
  `index.js` was never going to be touched either way (legacy tree is
  read-only) — D039 is closed anyway, because corpus detection is now
  genuinely server-side in `rag/router.py`, which is the substance of what
  that issue asked for.
- Crosswalk questions in the eval set (plan item 8's "~15 crosswalk
  questions") are deferred until the crosswalk itself is reviewed — an
  eval question whose expected answer comes from unreviewed data would be
  testing against a source no more trustworthy than what it's grading.

**Eval baselines, both run for real (not estimated), both reproduced
identically when re-run:**
- IPC: 18/20 (90%), unchanged from Sprint 3.
- BNS: 12/14 (86%). Both misses are the same *kind* of miss seen in IPC's
  eval — semantic confusion with an adjacent section in the same chapter
  (hurt-family offences, 117/118/122) and one weak-recall miss on a
  deliberately generic query ("general definitions") against section 2's
  sub-split chunks. No new failure category; not tuned toward 100% on a
  14-question set.
