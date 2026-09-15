# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

JurisAI is a RAG-based legal assistant for Indian criminal law, being built for real use
by police, lawyers, and the general public — not a demo or student project. It answers
questions against the Indian Penal Code (IPC) today and is being designed so the
Bharatiya Nyaya Sanhita (BNS), which replaced the IPC for offences on or after 1 July
2024, can be onboarded as a second corpus without a rewrite. See
`docs/production-hardening-plan.md` for the full architecture and sprint plan —
that file is the source of truth for design decisions; this file is the quick-reference
for conventions once code exists here.

**Current status:** pre-Sprint-0. This directory holds the plan and this file; the
application itself has not been built yet.

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
(`main` branch). As of the last check, that repo is empty except for an auto-generated
`README.md` — there is no history to reconcile, so builds proceed straight onto `main`
(or a `sprint-N` branch per the plan's sprint workflow).

## Build & run

Not yet applicable — no code exists here yet. Once Sprint 1 lands, this section will
document the real `pyproject.toml` / `docker compose up` workflow; do not write placeholder
run instructions before then.

## Directory structure (target — see the plan for the full annotated tree)

```
jurisai_greenfield/
├── backend/app/            # FastAPI app: api/, core/, llm/, corpora/, rag/, models/, repositories/
├── backend/templates/      # Jinja, base.html + extends
├── backend/static/         # CSS/JS
├── backend/tests/
├── data/                   # ipc/, bns/, crosswalk/ (LFS)
├── scripts/                # ingest, seed, migrate, build-crosswalk
├── docs/decisions.md       # ADR-style notes, one per sprint
├── DISCREPANCIES.MD        # open-issue register — see "Rules when editing" below
├── pyproject.toml
├── Dockerfile / docker-compose.yml
├── .env.example
└── .github/workflows/ci.yml
```

## Conventions (to hold once code lands)

- Python: FastAPI + Pydantic v2, `ruff` + `mypy` clean, `pytest` for tests. No bare
  `except:`, no `str(e)` returned to a client — see `core/errors.py` in the plan.
- Every corpus reference goes through the `corpora/registry.py` abstraction — never a
  literal `"ipc"` or `"bns"` string outside `corpora/definitions.yaml`.
- Every LLM call goes through the `LLMProvider` protocol in `llm/base.py` — never call
  Groq/Mistral SDKs directly from route code. `LLM_PROVIDER` in config picks the
  implementation (`groq` default for MVP).
- Frontend stays vanilla ES6 + Jinja (no framework), rendered with `textContent` /
  `DOMPurify` — never raw `innerHTML` on model or user-controlled content.
- Logging via `structlog` to stdout, JSON — never write user query text to a local file.

## Rules when editing

- **`DISCREPANCIES.MD` is frozen mid-sprint.** Read it at sprint start, don't edit it until
  the sprint boundary reconciliation. New findings mid-sprint go in a scratch
  `DISCOVERED.md` instead.
- **Never hardcode credentials.** All config comes from environment variables via
  `app/config.py` (pydantic-settings), which fails fast at startup if one is missing.
- **Do not use "capstone" or "diploma" framing** in code comments, docs, or the UI — this
  is being pitched and evaluated as a real operational tool.
- Follow the sprint order in the plan; in particular, don't build BNS-specific logic
  (Sprint 3B) before the corpus abstraction (Sprint 3) exists — that recreates the
  single-corpus hardcoding this design exists to avoid.
