# Decisions

ADR-style notes, one per sprint, per the plan's working method. Short — the
"why," not a changelog (that's what `git log` is for).

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
