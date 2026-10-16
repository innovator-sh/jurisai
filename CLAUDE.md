# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

JurisAI is a RAG-based legal assistant for Indian criminal law, being built for real use
by police, lawyers, and the general public — not a demo or student project. It answers
questions against the Indian Penal Code (IPC) today and is being designed so the
Bharatiya Nyaya Sanhita (BNS), which replaced the IPC for offences on or after 1 July
2024, can be onboarded as a second corpus without a rewrite. The design
plan and decision log are kept privately by the maintainer and are not in this repository;
this file is the quick-reference for conventions.

**Current status:** Sprints 0-5 are done and merged to `main` (the FIR form excepted), and
**Sprint 6 (testing, deploy, compliance, documentation) is in progress** on the `sprint-6`
branch. The app has a real frontend (Jinja `base.html` shell, strict CSP, vendored
`marked` + `DOMPurify`, SSE streaming chat, Lighthouse a11y 1.00), IPC + BNS answering with
a human-reviewed crosswalk (all 380 rows), and -- new in Sprint 6 -- DPDP/CERT-In compliance:
self-declared role + affirmative consent at signup, a bilingual `/privacy` notice, enforced
chat retention (Mongo TTL), a 180-day on-VM security log, a production start-up guard,
role-based disclaimers, a production compose overlay with Caddy, backup/restore/uptime
scripts, and a full README. CI gates coverage at 70% overall and 100% on the auth/ownership
files.

**Deliberately not built / not done:**
- The **FIR form** (plan Sprint 5 step 6, issues #22/#43) is **blocked until the user supplies
  real-world FIR requirements** -- do not start it. `/firform` is intentionally not served.
- The production deployment has **not been run on a real Oracle VM** -- the deployment files are
  validated locally only. The Hindi privacy text needs native-speaker review and the notice
  needs legal review before a real launch.
- Hindi / exact-section-number retrieval (#58, #59) and the crosswalk data-quality
  questions (#74-#78) are open. The router has no subject-area notion, so do not enable
  BNSS/BSA before reading the README's add-a-corpus caveat.

**MVP constraints — read before choosing any dependency:**
- **Free/open-source only.** No paid API, managed service, or SaaS at MVP stage — Groq
  and Mistral free tiers for the LLM, self-hosted Qdrant + MongoDB, self-hosted JWT auth,
  Oracle Cloud Always Free hosting. Paid alternatives (Anthropic/Bedrock, Atlas, Firebase)
  are recorded as funded-phase swaps behind an interface, never the default.
- **India-only compliance.** DPDP Act 2023 and CERT-In Directions 2022 — not GDPR, not
  CCPA. Security logs stay on the India-hosted VM, retained 180 days, never sent to a
  foreign-hosted logging service even on a free tier.
- **No model fine-tuning**, at any phase — not the generator, not now, not post-funding.
  RAG already reduces the model's job to summarizing retrieved, cited statute text; a
  fine-tuned model trades away citation provenance for no real gain. See "Model
  strategy" in the plan before proposing a training step for anything other than the
  embedding model (which is a legitimate, cheap, later improvement).

## Relationship to `jurisai/` (the legacy prototype)

A working prototype exists at `../jurisai/` (sibling directory). It is **read-only
reference material**:

- Never edit files under `../jurisai/`.
- Never bulk-copy or `git mv` it into this repo.
- Pull specific things out of it deliberately: the RAG logic in `Backend/app.py` (as a
  reference while porting to `backend/app/**`), the working Web Speech mic input in
  `static/index.js:16-30`, the visual identity in `static/index.css`, and the source
  `ipc-data.pdf`. Everything else is rebuilt against the target architecture, not copied.
- It also contains two real, live credentials (Mongo Atlas password, Mistral API key) —
  do not copy these into this repo even temporarily. New credentials are generated fresh
  per the plan's Sprint 0 and live only in a local, gitignored `.env`.

## Repository target

This directory's contents are the repository at **https://github.com/innovator-sh/jurisai**
(`main` branch, private). All changes go on a branch (`sprint-N` for sprint work, a short
descriptive name for fixes) and land on `main` through a pull request; CI must be green.
Commit messages: one single-line subject, a blank line, then the details.

## Build & run

```
uv sync                          # installs backend/app's dependencies
cp .env.example .env             # then fill in real values — see comments in the file
docker compose up                # app + self-hosted Mongo + Qdrant
python scripts/ingest.py --corpus ipc   # builds the Qdrant index for one corpus
python scripts/ingest.py --corpus bns   # (re-run after data/ipc/ or data/bns/ changes)
```

`uv run pytest -q --cov` runs the test suite (and the coverage gate) without needing Docker — Mongo, Qdrant, and the
LLM provider are all mocked (`backend/tests/conftest.py`), so it doesn't need a real
database, a running Qdrant, or the ~400MB embedding model. `uv run ruff check .` and
`uv run mypy backend/app` are the other two local gates; all three also run in CI.
`python scripts/eval.py --corpus ipc` (or `--corpus bns`) runs the retrieval-hit-rate
report — self-contained against an in-memory Qdrant, so it doesn't need `docker compose up`
either, but it does download the real embedding model and parse the real PDF, so it's slow
(a minute or two per corpus).

## Directory structure (target — see the plan for the full annotated tree)

```
jurisai_greenfield/
├── backend/app/            # FastAPI app: api/, core/, llm/, corpora/, rag/, models/, repositories/
├── backend/app/templates/  # Jinja: base.html shell, _sidebar.html, one template per page
├── backend/static/         # CSS/JS, vendored marked + DOMPurify, favicon
├── backend/tests/
├── data/                   # ipc/, bns/ (LFS); crosswalk/ipc_bns.csv (plain text, human-reviewed by hand)
├── scripts/                # ingest.py, eval.py, build_crosswalk.py, seed/migrate (later)
├── DISCREPANCIES.MD        # pointer only — issues tracked in the repo's Issues tab
├── pyproject.toml
├── Dockerfile / docker-compose.yml / docker-compose.prod.yml / Caddyfile
├── .env.example
└── .github/workflows/ci.yml
```

## Conventions (to hold once code lands)

- Python: FastAPI + Pydantic v2, `ruff` + `mypy` clean, `pytest` for tests. No bare
  `except:`, no `str(e)` returned to a client — see `core/errors.py` in the plan.
- Every corpus reference goes through the `corpora/registry.py` abstraction — never a
  literal `"ipc"` or `"bns"` string outside `corpora/definitions.yaml`.
- A source document gets its own module in `corpora/loaders/`, dispatched by the
  registry's `loader` field — never assume two statutes share a parser. Confirmed
  necessary, not theoretical: the IPC and BNS loaders find zero sections in each
  other's source PDF.
- **Never let an unreviewed `data/crosswalk/*.csv` row reach a live answer.**
  `corpora/crosswalk.py` loads whatever the CSV says without judging it — the
  `confidence` column is what tracks review status, set by a human, not this code.
  Wiring a crosswalk assertion into a prompt while its row is still `unreviewed` is
  the exact "hallucinated section mapping" failure the plan calls the worst one this
  product can have.
- Every LLM call goes through the `LLMProvider` protocol in `llm/base.py` — never call
  Groq/Mistral SDKs directly from route code. `LLM_PROVIDER` in config picks the
  implementation (`groq` default for MVP).
- Every protected route depends on `CurrentUser` (`app/core/security.py`) and every
  `ChatRepository` query is scoped by `user_id` — never trust a client-supplied user id,
  and never add a session/chat query that skips the `user_id` filter.
- Frontend stays vanilla ES6 + Jinja (no framework), rendered with `textContent` /
  `DOMPurify` — never raw `innerHTML` on model or user-controlled content.
- Logging via `structlog` to stdout, JSON — never write user query text to a local file.
- Security events go through `core/security_log.audit()` (180-day rotating file on the VM,
  CERT-In). Never put a password, token, raw email address or question text in it -- tests
  assert this against the real file. Never ship logs to a foreign-hosted service.
- Signup requires a `role` and `consent: true` (`Literal[True]`); the consent text's version
  is `core.compliance.CONSENT_VERSION` -- bump it when `templates/privacy.html` changes
  materially. Every deployment-specific value on `/privacy` is rendered from settings.
- Blocking work (embedding, Qdrant) inside an `async` route goes through `asyncio.to_thread`;
  `tests/test_concurrency.py` fails if retrieval stalls the event loop.
- Auth/ownership files are held at 100% coverage in CI (list in `.github/workflows/ci.yml`);
  a new branch in any of them needs a test. Tests that exercise the `Secure` refresh cookie
  must use an `https://` client base URL or they pass vacuously.
- No inline `style=` / `on*=` attributes or inline `<script>` anywhere -- the CSP blocks them
  silently (an inline `display:none` just leaves the element visible). `test_pages.py` guards it.

## Rules when editing

- **Open issues live in the repo's Issues tab, not in a committed file.**
  `DISCREPANCIES.MD` is a pointer only — see "Open-issue tracking" in the plan for why
  (short version: a committed register can't be cleanly removed from git history if this
  repo ever goes public). File findings as issues immediately, labeled `severity:SX` and
  `sprint:N`; a sprint closes only the issues labeled for it.
- **Never hardcode credentials.** All config comes from environment variables via
  `app/config.py` (pydantic-settings), which fails fast at startup if one is missing.
- **Do not use "capstone" or "diploma" framing** in code comments, docs, or the UI — this
  is being pitched and evaluated as a real operational tool.
- Follow the sprint order in the plan; in particular, don't build BNS-specific logic
  (Sprint 3B) before the corpus abstraction (Sprint 3) exists — that recreates the
  single-corpus hardcoding this design exists to avoid.
