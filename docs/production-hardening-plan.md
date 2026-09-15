# JurisAI — Production Hardening & Restructure Plan

## Context

JurisAI is a RAG chatbot over the Indian Penal Code, built as a single 290-line
Flask file (`Backend/app.py`) that serves six Jinja pages, ingests a 20 MB IPC PDF into
Chroma at import time, retrieves top-3 chunks, calls Mistral, and stores turns in
MongoDB Atlas keyed by a client-supplied `session_id`. It is being taken from a working
prototype to a tool pitched for real use inside a police department — the correctness
and security bar is the bar for a system handling real case queries and real users'
data, not a demo.

An audit of the tree, configs, and both surfaces found the app is not merely rough — it
is **exploitable and partly non-functional**:

- Two live credentials sit in the working tree (Atlas URI with password at `app.py:25`,
  Mistral key at `app.py:39`) and a third — a real Firebase Web API key — is committed
  in `templates/register.js:10`.
- There is **no authentication at all**. Every session route is an IDOR: any client can
  read, rename, or delete any conversation by guessing/enumerating a UUID, and `/history`
  returns every session in the database, unbounded.
- Stored XSS: LLM output and server errors go into `innerHTML` unescaped
  (`static/index.js:89`, `:334`, `:357`), so a poisoned answer executes in any viewer's browser.
- `debug=True` + `CORS(app)` (all origins) + `str(e)` returned to the client in 9 places
  means a Mongo error can plausibly echo the connection URI, and any uncaught exception
  exposes the Werkzeug console.
- `requirements.txt` is a 200-line `pip freeze` of an unrelated ML workstation that
  **omits every package the app imports** — a fresh install cannot run this project.
- Roughly half the UI is scaffolding: `login.html` fakes its submit with `setTimeout` +
  `console.log`, `firform.html` collects FIR data in `contenteditable` spans and sends it
  nowhere, `account.html` is a stub. No Jinja inheritance, so ~50-60% of ~2,900 template
  lines is duplicated shell/nav.
- No tests, no CI, no Dockerfile, no `.gitignore`, no migrations, no `.env`.

**Second driver — the corpus is about to change.** The Bharatiya Nyaya Sanhita (BNS, 2023)
replaced the IPC for offences committed on or after **1 July 2024**. The IPC is not
retired: it still governs every offence committed before that date, and will for years as
those cases move through the courts. So this is not a swap — it is permanently a
**two-corpus, date-dependent system**, and the same is true of CrPC→BNSS and
Evidence Act→BSA if those follow.

Today the codebase assumes one corpus everywhere and hardcodes it: a single
`DATA_DIR = "ipc-data"`, one unnamed Chroma collection, a prompt that says "legal
documents" with no statute identity, chunks carrying no act metadata, and a
client-side `containsIPC()` regex in `index.js:63`. Adding BNS on top of that would mean
a second hardcoded path and answers that silently mix two statutes — the worst possible
failure mode for a legal tool.

**Intended outcome:** a single containerized, deployable service with real auth, no
secrets in code, validated inputs, ownership-checked data access, streaming answers, a
test suite, and CI — and a **corpus-agnostic core** where adding BNS (or BNSS, or BSA) is
a config entry plus an ingest run, not a code change.

**Where this is built:** the legacy prototype at `jurisai/` stays exactly as it is —
**untouched, read-only** — and is used only as an audit source and a reference for logic
worth porting (the RAG flow, the working mic input, the CSS). All new work happens in
`jurisai_greenfield/`, which is the actual content of the target repository,
**https://github.com/innovator-sh/jurisai** (currently empty apart from an auto-generated
`README.md` on `main` — nothing to merge with, no history to preserve). Nothing from
`jurisai/` is bulk-copied or `git mv`'d into `jurisai_greenfield/`; specific assets
(e.g. the IPC source PDF) are deliberately copied over as needed, everything else is
rebuilt against the target architecture below.

**Confirmed constraint:** target is a single deployable service — managed backing
stores, single-host/PaaS (or on-prem, if that's how the department deploys) — not a
multi-region platform. It has to hold up to real users and real queries, not a grading rubric.

**MVP financial constraint:** this is unfunded. Every layer defaults to a **free or
open-source** option; nothing paid is assumed until funding lands. Where a paid option is
clearly better, it's recorded as the **funded-phase swap**, not the MVP default, and it
sits behind an interface so the swap is config, not a rewrite.

**Compliance scope:** India-only. DPDP Act 2023, the CERT-In Directions 2022 (6-hour
breach reporting, 180-day in-India log retention), and IT Act 2000 §43A. No GDPR/CCPA
framing, no foreign-compliance assumptions — they don't apply to this deployment and
designing for them would cost time and code for no real benefit right now.

**Assumptions made where the user did not specify** (flag now, cheap to reverse in Sprint 0):
1. **Stack churn: modernize backend, rebuild UI on a shared Jinja base.** FastAPI replaces
   Flask; the UI stays server-rendered Jinja + vanilla JS rather than moving to Next.js,
   but the pages are rebuilt on one base template since little working UI exists to preserve.
2. **Auth: self-hosted JWT (argon2 + refresh cookie), not Firebase.** Zero cost, no vendor
   dependency, and no cross-border question for user data — everything stays on the deploy
   VM. (`argon2-cffi` is already in requirements; the deleted legacy `config.py` held a
   `JWT_SECRET_KEY`, so this was the original intent anyway.) Phone-OTP signup is deferred
   to the funded phase — SMS delivery in India requires DLT template registration and a
   per-message cost, neither of which is free. An OIDC adapter seam is left in
   `core/security.py` so a departmental SSO can be wired in later without touching routes.
3. **LLM: a provider interface, defaulting to a free-tier API — Groq first, Mistral as the
   alternate.** Groq's free tier gives the fastest inference of the no-cost options, which
   matters for a chat UX; Mistral is kept as a second implementation (it's what the legacy
   app already used, and it's a plausible EU-hosted alternative if Groq's limits bite).
   Both sit behind the same `LLMProvider` protocol, selected by `LLM_PROVIDER` in config —
   swapping is a one-line env change, not a code change. Anthropic/Bedrock and self-hosted
   vLLM are funded-phase providers behind the same interface; see "Model strategy" below
   for why no model is fine-tuned at any phase.
4. **Vector store, chat store: self-hosted, not managed.** Qdrant OSS and MongoDB both run
   in `docker-compose` on the deploy VM — no Atlas, no Qdrant Cloud. Zero recurring cost,
   and it keeps user data in-country by construction rather than by configuration.
5. **Embeddings: BGE-M3 (hybrid dense + sparse), not `multi-qa-mpnet-base-dot-v1`.**
   MIT-licensed, multilingual (needed the moment a citizen asks a question in Hindi), and
   its sparse output gives lexical matching for exact section-number queries
   ("धारा 302" / "section 302") that pure dense retrieval reliably misses. Runs on CPU.
6. **Hosting: Oracle Cloud Always Free, Mumbai/Hyderabad region.** 4 ARM cores / 24 GB RAM
   at ₹0/month, in an Indian region by construction — the strongest free option available
   for a service that has to satisfy "deployable in India" from day one.

**Tooling note:** no ruflo MCP tools are exposed in this session (checked the registry —
`memory_store`, `swarm_init`, `agent_spawn` are absent). Parallelism will use Claude Code
subagents and the Workflow tool. If ruflo is wired up later, the sprint structure below
maps onto it unchanged.

---

## Working method (from the Tweag agentic-coding handbook)

The handbook's rules are adopted literally and govern every sprint:

- **Explore → Plan → Code → Commit.** No sprint starts without its slice of
  `DISCREPANCIES.md` read and its acceptance criteria written down.
- **Small, shippable vertical slices.** Each sprint below ends with a runnable app and a
  commit. No sprint spans more than one architectural concern.
- **Prompt with intent.** Every subagent gets testable acceptance criteria, not a vibe.
- **Never accept AI code blindly.** Every sprint ends with `/code-review` on the diff and a
  human read of the diff before merge. This is the handbook's core rule and it is not optional.
- **Validate in flow.** `ruff` + `mypy` + `pytest` run on every slice; CI enforces them.
- **Version control deliberately.** One branch per sprint, commit per slice, reset rather
  than accumulate confused state.
- **Legible, natural commit messages.** Imperative mood, one line stating what changed and
  why (`Add corpus registry so BNS onboarding is config, not code`), not `wip`, `fix`, or a
  restated diff. No AI-disclosure boilerplate, no emoji. The commit log itself is part of
  what makes this pitch-ready — a reviewer (or a procurement officer) reading `git log`
  should see a professional, deliberate build, not a scratch history.
- **Document tradeoffs.** Each sprint appends an ADR-style note to `docs/decisions.md`.

### Token discipline

- Subagents return **structured findings, not file dumps**; prompts say so explicitly.
- Exploration is delegated (`Explore` agents), synthesis stays in the main thread.
- Fan out only where slices are genuinely independent (see the swarm map per sprint);
  serial work stays serial rather than paying for coordination.
- `CLAUDE.md` (at `jurisai_greenfield/CLAUDE.md`) is the shared context so agents don't
  re-derive conventions. It is updated at the end of each sprint, not during.

### `DISCREPANCIES.md` — the open-issue register

Lives at `jurisai_greenfield/DISCREPANCIES.MD` (repo root once pushed) — already created;
seeded with the findings below as the first Sprint 0 commit. Frozen for the duration of a
sprint: **no edits mid-sprint.** It is reconciled only at a sprint boundary, in one commit.

Row format:

```
| ID | Severity | Area | Issue | Evidence (file:line) | Sprint | Status |
```

- `Severity`: S0 exploitable / S1 broken / S2 correctness / S3 hygiene.
- `Status`: `open` → `in-sprint-N` → `fixed` (with the commit SHA) → `wontfix` (with a reason).
- Seeded with the ~40 findings from this audit (enumerated in the appendix below).
- Anything discovered mid-sprint goes into a scratch `DISCOVERED.md` and is merged into the
  register at the boundary. This is what keeps the register a stable contract rather than a
  moving target.

---

## Target architecture

```
jurisai_greenfield/              # == repo root of github.com/innovator-sh/jurisai
├── backend/
│   ├── app/
│   │   ├── main.py             # FastAPI app factory, lifespan, middleware
│   │   ├── config.py           # pydantic-settings — ALL config from env
│   │   ├── deps.py             # DI: current_user, db, vector store, llm
│   │   ├── api/
│   │   │   ├── chat.py         # POST /api/chat (SSE stream)
│   │   │   ├── sessions.py     # session CRUD, all ownership-checked
│   │   │   ├── fir.py          # FIR draft persistence + PDF render
│   │   │   └── health.py       # /healthz, /readyz
│   │   ├── core/
│   │   │   ├── security.py     # JWT verification (argon2 + refresh cookie); OIDC-swappable
│   │   │   ├── errors.py       # exception handlers — never leak str(e)
│   │   │   └── logging.py      # structlog, JSON, request-id, PII redaction
│   │   ├── llm/
│   │   │   ├── base.py         # LLMProvider protocol (stream + complete)
│   │   │   ├── groq.py         # MVP default — free tier, fastest of the no-cost options
│   │   │   ├── mistral.py      # MVP alternate — matches legacy, config-swappable
│   │   │   ├── anthropic.py    # funded phase — prompt caching on retrieved context
│   │   │   └── bedrock.py      # funded phase — ap-south-1, in-country inference
│   │   ├── corpora/
│   │   │   ├── registry.py     # Corpus objects: id, act name, in-force dates, collection
│   │   │   ├── definitions.yaml# ipc / bns / (later bnss, bsa) — declarative, no code
│   │   │   ├── loaders/        # one parser per source format (PDF, XML, scraped HTML)
│   │   │   └── crosswalk.py    # IPC section ↔ BNS section mapping + lookup
│   │   ├── rag/
│   │   │   ├── ingest.py       # CLI: build an index PER CORPUS (NOT at import time)
│   │   │   ├── retriever.py    # corpus-scoped, score-thresholded, typed chunks
│   │   │   ├── router.py       # picks corpus/corpora from query + offence date
│   │   │   └── prompts.py      # versioned templates, per-corpus + hybrid variants
│   │   ├── models/             # Pydantic request/response + Mongo documents
│   │   └── repositories/       # Mongo access; every query filters by user_id
│   ├── templates/              # base.html + 6 pages extending it
│   ├── static/                 # index.css, app.js (escaped rendering)
│   └── tests/                  # unit / integration / e2e
├── data/
│   ├── ipc/                    # source documents per corpus (LFS)
│   ├── bns/
│   └── crosswalk/ipc_bns.csv   # reviewed section mapping, versioned
├── scripts/                    # ingest, seed, migrate, build-crosswalk
├── docs/decisions.md
├── DISCREPANCIES.md
├── CLAUDE.md
├── pyproject.toml              # deps + ruff + mypy + pytest config
├── Dockerfile                  # multi-stage, non-root
├── docker-compose.yml          # app + mongo + qdrant for local dev
├── .env.example
├── .gitignore
└── .github/workflows/ci.yml
```

## Recommended stack changes

MVP column is what ships now, at ₹0 recurring. Funded phase is the swap once there's a
budget — each one sits behind an interface already, so it's a config change, not a rewrite.

| Layer | Now | MVP (₹0) | Funded phase | Why |
|---|---|---|---|---|
| Web framework | Flask 3.1, sync | **FastAPI + uvicorn** | unchanged | Async (the LLM call currently blocks the whole server), Pydantic validation at the boundary kills a whole class of the bugs found, auto OpenAPI, first-class SSE streaming. |
| Server | Flask dev server, `debug=True` | **uvicorn workers behind gunicorn**, in Docker | unchanged | The current setup is an RCE surface if ever exposed. |
| Validation | none | **Pydantic v2** (already installed) | unchanged | `request.json` is read with zero validation in 4 routes. |
| Auth | none (dead Firebase stub) | **Self-hosted JWT** — argon2 password hashing + refresh cookie, `core/security.py` | departmental SSO / OIDC via the same adapter seam | Zero cost, no vendor account, no cross-border data question. Firebase phone-OTP would also require Indian DLT SMS registration — deferred either way. |
| Dependencies | 200-line `pip freeze`, missing the real ones | **`pyproject.toml` + `uv`**, lockfile committed | unchanged | Reproducible installs; drops TensorFlow/Jupyter/moviepy/PyAudio entirely (~2 GB of install). |
| RAG framework | `langchain` pre-0.1 paths | **Direct clients, no LangChain** — custom section-aware splitter, `corpora/loaders/`, `LLMProvider` protocol | unchanged | The current imports are deprecated and already crashed a startup (`transformers`/`timm` conflict). LangChain's generic splitters/chains can't express the section-shaped, cited-corpus retrieval this design needs anyway. |
| Vector store | Chroma, 76 MB SQLite in-repo path, one unnamed collection | **Qdrant OSS, self-hosted in `docker-compose`**, one collection per corpus + payload filters | Qdrant Cloud managed, if self-host ops becomes the bottleneck | Chroma's local-file mode doesn't survive containers or multiple workers. The decisive reason here is **BNS**: payload filtering scopes a query to `corpus in [ipc]`, `[bns]`, or both, and lets a corpus be re-ingested independently. Self-hosted is free and keeps data in-country by construction. |
| Corpus handling | `DATA_DIR = "ipc-data"` hardcoded, no act metadata on chunks | **Corpus registry** (`corpora/definitions.yaml`) + `corpus`, `act`, `section`, `in_force_from/to` on every chunk | unchanged | Adding BNS becomes a YAML entry + an ingest run. Every retrieved chunk knows which statute it came from, so citations can never be misattributed. |
| Embeddings | `multi-qa-mpnet-base-dot-v1` in-process | **BGE-M3** (hybrid dense+sparse, MIT, multilingual), built offline by `scripts/ingest.py` | unchanged, or a fine-tuned retriever once real query logs exist (see Model strategy) | English-only `mpnet` can't serve a Hindi query. BGE-M3's sparse output also catches exact section-number lookups ("धारा 302") that dense-only retrieval misses. |
| LLM | `requests.post` to Mistral, no timeout | **`LLMProvider` protocol — Groq (default) / Mistral (alternate)**, both free-tier | Bedrock `ap-south-1` (in-country) or self-hosted vLLM (full independence) | Timeouts, retries, streaming, and a config-only swap when funded. No model is fine-tuned — see "Model strategy" below. |
| Chat store | MongoDB Atlas, no user field | **Self-hosted MongoDB in `docker-compose`**, `user_id` on every doc, compound indexes | MongoDB Atlas M0/M-tier, Mumbai region | Zero cost, no managed-service account, and no data leaves the deploy VM. Adds the field every ownership check needs. |
| Logging | `logging.DEBUG` to unrotated `app.log` | **structlog** → stdout, JSON, request-id, query redaction, retained 180 days on the deploy VM | unchanged, or a managed log store *hosted in India* | Container-native; stops writing raw query text to disk. Retention and in-India storage are a CERT-In requirement, not a preference — see "Compliance" in Sprint 6. |
| Tests | none | **pytest + pytest-asyncio + httpx + mongomock** | unchanged | Handbook: "test everything before considering it complete." |
| Lint/type | none | **ruff + mypy (strict on `app/`)** | unchanged | The self-correction loop the handbook requires. |
| CI | none | **GitHub Actions** (free for this repo): ruff → mypy → pytest → `pip-audit` → `gitleaks` → docker build | unchanged | Secret scanning is non-negotiable given the history here. |
| Frontend | 6 standalone templates, 50-60% duplicated | **`base.html` + `{% extends %}`**, one `app.js`, `textContent`/DOMPurify, PWA manifest, self-hosted Devanagari font | unchanged | Removes the duplication and the XSS vector in one pass; PWA + self-hosted fonts matter on the patchy-connectivity, mid-range-Android profile of the wider userbase. |
| Hosting | none (local dev only) | **Oracle Cloud Always Free**, Mumbai/Hyderabad, `docker compose` + Caddy | AWS `ap-south-1` (ECS Fargate) or on-prem/NIC cloud | ₹0/month, 4 ARM cores / 24 GB RAM, in-country by construction. |

---

## Model strategy — why no fine-tuning

**The generator is never fine-tuned, at any phase.** RAG already reduces the model's job
to "summarize the retrieved statute text I handed you, in the user's language, with the
citations I gave you" — a task any reasonably capable model handles well without touching
its weights. Fine-tuning would trade that away for no benefit and one serious cost:

- **No provenance.** A fine-tuned model asked for a penalty produces fluent, plausible
  text with nothing to point at. RAG can show the retrieved section text next to the
  answer. For a tool where citation correctness *is* the product, that difference is the
  whole ballgame — a wrong fine-tuned answer is indistinguishable from a right one until
  someone checks the actual statute.
- **Statutes change.** BNS already replaced the IPC once; amendments will keep coming.
  RAG absorbs that as "drop in a PDF, re-run `scripts/ingest.py`." Fine-tuning would mean
  rebuilding a training set and retraining every time the law changes.
- **Cost is inverted at this stage.** Fine-tuning needs a lawyer-reviewed Q&A dataset
  (the expensive part) plus training compute plus still paying to host inference. RAG on
  a free-tier API costs nothing extra at pilot volume.

**What actually cuts cost and third-party dependency, in ROI order** (none require
training):

1. A **deterministic lookup path** for direct citations ("Section 302 IPC") — registry
   lookup + template render, no LLM call, no tokens.
2. **Semantic response caching** keyed on normalized query + corpus + language — real
   users converge hard on the same few hundred questions.
3. **Retrieval precision** (the BGE-M3 hybrid change above) — fewer, more relevant chunks
   in the prompt cuts tokens and improves the answer at the same time.
4. **Self-hosted open weights behind `LLMProvider`** (Qwen2.5-7B / Llama-3.1-8B /
   Sarvam-M) once GPU budget exists — this is the actual "stop depending on a third
   party" lever, and it's a provider swap, not a training run.

**Where fine-tuning does eventually earn a place**, once real query logs exist:
fine-tuning the **embedding model** (not the generator) on legal query→section pairs
directly improves retrieval hit-rate — cheap, measurable against the eval harness, and
the metric that actually determines answer quality. A small LoRA for **output format
only** (a department's exact FIR template, consistent Hindi legal register) is a
plausible funded-phase addition; facts still come from retrieval, never from the tuned
model's memory.

---

## Multi-corpus design (IPC → BNS → hybrid)

The single most important architectural decision in this plan. Everything below exists so
that BNS is **data and config**, never a code fork.

### The corpus registry

`corpora/definitions.yaml` declares each statute; nothing else in the codebase names one:

```yaml
corpora:
  - id: ipc
    act: "Indian Penal Code, 1860"
    short: IPC
    jurisdiction: IN
    in_force_from: 1862-01-01
    in_force_to: 2024-06-30      # offences on/after 1 Jul 2024 are BNS
    superseded_by: bns
    source: data/ipc/
    loader: pdf_sectioned
    collection: jurisai_ipc
  - id: bns
    act: "Bharatiya Nyaya Sanhita, 2023"
    short: BNS
    jurisdiction: IN
    in_force_from: 2024-07-01
    in_force_to: null
    supersedes: ipc
    source: data/bns/
    loader: pdf_sectioned
    collection: jurisai_bns
```

`registry.py` loads this into frozen `Corpus` objects. Adding BNSS or BSA later is four
more lines of YAML plus a loader if the source format differs. **No route, prompt, or
retriever ever hardcodes a corpus id.**

### Chunk metadata contract

Every chunk carries `corpus`, `act`, `section`, `section_title`, `page`,
`in_force_from`, `in_force_to`, `source_doc`, `ingest_version`. This is a hard schema
validated at ingest time — a chunk without it is rejected, not silently indexed. It is
what makes correct citation possible and what the crosswalk joins on.

### Section-aware chunking

The current 500/200 character split cuts statutes mid-section. Replace with a
**section-boundary splitter**: one chunk per section where it fits, sub-split long
sections with the section heading repeated in each part. Legal retrieval is
section-shaped, and this is also what lets the crosswalk address a chunk by
`(corpus, section)`.

### The IPC ↔ BNS crosswalk

`data/crosswalk/ipc_bns.csv` — a reviewed, versioned mapping with a `relation` column,
because the mapping is genuinely not 1:1:

| relation | meaning | example shape |
|---|---|---|
| `renumbered` | same offence, new number | IPC 302 → BNS 103(1) |
| `merged` | several IPC sections → one BNS section | IPC 299/300 handling |
| `split` | one IPC section → several BNS sections | offences separated by aggravation |
| `new` | no IPC ancestor | BNS 111 organised crime, BNS 113 terrorism |
| `repealed` | no BNS successor | IPC 377, IPC 497 (already struck down) |
| `modified` | mapped but the elements or penalty changed | flag prominently in answers |

Built once by `scripts/build_crosswalk.py` from an authoritative published concordance,
then **human-reviewed and committed as data**. It is never LLM-generated at query time —
a hallucinated section mapping in a legal tool is the highest-severity failure this
product can have. Rows carry a `confidence` and a `source` column; anything below
reviewed-confidence is surfaced to the user as uncertain rather than asserted.

### Query routing (`rag/router.py`)

Resolves which corpus/corpora a question needs, in this precedence:

1. **Explicit user selection** — a corpus switch in the UI (`IPC` / `BNS` / `Both`).
2. **Offence date** — if the user states or the session records a date of offence,
   the registry's in-force window decides. This is the legally correct rule and the
   reason dates are first-class in the schema.
3. **Explicit citation in the query** — "section 302 IPC" pins the corpus; a bare
   "section 302" does not and must not be guessed.
4. **Default: hybrid.** Retrieve from both, answer primarily from BNS as current law,
   and show the IPC counterpart via the crosswalk.

Ambiguity is never resolved silently — an undated query about a serious offence gets a
one-line clarifier ("was the offence before or after 1 July 2024?") before the answer,
because the answer genuinely differs.

### Answer contract

Every answer states **which statute it is quoting**, with act name, section number, and
source page. In hybrid mode the response is structured — current position under BNS, the
corresponding IPC provision, and an explicit note when `relation` is `modified`, `new`,
or `repealed`. Never present a section number without its act. The
"not legal advice" disclaimer is mandatory on every answer surface.

### Consequences elsewhere

- **Sessions** get a `corpus_mode` and optional `offence_date`, so a conversation stays in
  one legal frame and history replays under the same frame it was answered in.
- **Stored answers get `corpus` + `ingest_version`.** When BNS text is corrected or
  re-ingested, you can tell which historical answers were produced from stale text.
- **FIR form** — FIRs filed today cite BNS/BNSS sections. The form's "Acts & Sections"
  fields must be corpus-driven from the registry, not free text, and should default by
  the occurrence date already on the form.
- **`containsIPC()` in `index.js:63`** — delete it; corpus detection belongs on the server
  where the registry lives.
- **Eval harness** runs per corpus plus a hybrid set, so BNS onboarding is measured, not assumed.

---

## Sprints

Each sprint is a branch, ends with `/code-review` on the diff, a human read, a commit, an
ADR note, and a `DISCREPANCIES.md` reconciliation. **The app must run at the end of every sprint.**

### Sprint 0 — Contain the breach, stand up the real repo

Serial, no agents. Credential handling and repo initialization; not delegated or batched.

The target repo (`github.com/innovator-sh/jurisai`) is currently empty apart from an
auto-generated `README.md` — there is no history to purge and nothing to merge with. That
removes the history-rewrite step this sprint would otherwise need, but the two live
credentials are still real and still exposed on this machine, so they still get rotated.

1. **Rotate, by hand, outside any repo:** the Atlas database user's password and the
   Mistral API key (live in `jurisai/Backend/app.py:25,39`). Restrict the Firebase Web API
   key found in `jurisai/templates/register.js:10` to the app's domains in the Google
   Cloud console — it's leaving the legacy folder behind either way, but an unrestricted
   real key sitting on disk is still worth locking down.
2. In `jurisai_greenfield/`: `git init`, add the remote
   (`git remote add origin https://github.com/innovator-sh/jurisai.git`), confirm
   `main` as the default branch.
3. Add `.gitignore` (`.venv/`, `__pycache__/`, `*.log`, `db/`, `.env`, `offload_weights/`).
4. Create `.env.example` listing every config var by name, no values. New credentials
   (post-rotation) go only into a local `.env`, never into a tracked file.
5. Copy `DISCREPANCIES.MD` content in (seeded from the appendix below) as the first commit.
6. **Verify with `gitleaks detect` before the first push** — this repo has no history to
   worry about, but a clean first commit is the cheapest guarantee it stays that way.
7. First push to `main` (or a `sprint-0` branch if you'd rather review before it lands
   on `main` — your call, flag which you prefer).

**Exit criteria:** `github.com/innovator-sh/jurisai` contains `.gitignore`, `.env.example`,
and a seeded `DISCREPANCIES.MD`; `gitleaks` clean; rotated credentials confirmed working;
`jurisai/` (legacy) untouched on disk and never staged.

### Sprint 1 — Foundation: repo, deps, config, CI

1. Build the tree above fresh under `jurisai_greenfield/`, porting `jurisai/Backend/app.py`
   module by module (routes → `api/`, RAG setup → `rag/`, Mongo calls → `repositories/`)
   with **no behaviour change yet** beyond the split itself — this is "port, don't
   redesign" for this one slice, so the diff stays reviewable against the legacy file.
2. `pyproject.toml` with the ~15 real dependencies; delete `requirements.txt` and
   `package.json` (nothing uses `date-fns`). Commit `uv.lock`.
3. `app/config.py` with pydantic-settings: `MONGO_URI`, `LLM_PROVIDER` (`groq` default),
   `GROQ_API_KEY`, `MISTRAL_API_KEY`, `JWT_SECRET_KEY`, `QDRANT_URL`, `CORS_ORIGINS`,
   `LOG_LEVEL`. (`ANTHROPIC_API_KEY` / `BEDROCK_*` / `FIREBASE_*` are funded-phase vars —
   declared but optional, so switching providers later never touches this file's shape.)
   **Fail fast at startup if a required var is missing.**
4. `Dockerfile` (multi-stage, non-root, healthcheck) + `docker-compose.yml`.
5. CI pipeline; branch protection so it must pass.
6. `pytest` skeleton with one smoke test.

**Swarm:** 3 parallel subagents — (a) packaging + Docker, (b) config + CI, (c) module split.
They touch disjoint paths, so no worktree isolation is needed. Main thread integrates.

**Exit criteria:** `docker compose up` serves the existing UI with identical behaviour;
CI green; `uv sync` from scratch on a clean machine works.

### Sprint 2 — Authentication and authorization

1. Real signup/login in `login.html` (replacing the `setTimeout` fake) against a
   self-hosted email/password flow: `argon2-cffi` password hashing, JWT access token +
   refresh cookie. Access token held in memory and refreshed, **never in `localStorage`**.
   Phone-OTP signup is out of scope for MVP (needs Indian DLT SMS registration — funded
   phase); leave the field but don't wire it.
2. `app/core/security.py`: a `current_user` FastAPI dependency verifying the JWT on every
   protected route (signature, expiry, issuer). Structure it as a thin adapter so a
   departmental OIDC/SSO provider can be swapped in later without touching call sites.
3. Add `user_id` to every chat document; **backfill or drop the 5 existing test documents**.
4. Rewrite every session route to filter by `user_id` — `/history`, `/session/{id}`,
   `/rename_session/{id}`, `/delete_session`. A session that isn't yours returns 404, not 403
   (no existence oracle).
5. Real `/logout` (revoke refresh token) and a protected `/account` page showing real data.
6. Rate limit `/api/chat` per user (`slowapi`) — currently anyone can burn your LLM budget.

**Swarm:** 2 agents — backend auth dependency + repository changes; frontend auth flow.
Sequential handoff, not parallel: the frontend needs the token contract fixed first.

**Exit criteria:** an integration test proving user A gets 404 on every one of user B's
sessions across all four routes; unauthenticated requests get 401; rate limit trips under load.

### Sprint 3 — RAG correctness, corpus abstraction, and the LLM layer

**This sprint builds the corpus seams even though only IPC is loaded.** Doing it now costs
little; retrofitting it after BNS lands costs a rewrite of every prompt, chunk, and route.

1. `corpora/registry.py` + `definitions.yaml` with **`ipc` as the only entry, and `bns`
   declared but unbuilt**. Prove the abstraction by having every code path resolve the
   corpus from the registry — no literal `"ipc"` anywhere outside the YAML.
2. `scripts/ingest.py --corpus ipc` — a CLI that builds one corpus's index.
   **Delete the import-time ingestion.** The app connects to existing collections and
   fails readiness if a declared, enabled corpus is missing.
3. Section-aware chunking with the full metadata contract; reject chunks missing it.
4. Fix the prompt-construction bug: `app.py:98` currently f-strings raw `Document` objects
   into the prompt, so `Document(page_content=..., metadata={...})` reprs reach the model.
   Format `page_content` only, and carry **act + section + page** into the citation.
5. Restructure the prompt: instructions in a **system** message, retrieved context in a
   separate cached block labelled by corpus, user question last. Version the templates in
   `rag/prompts.py` with a per-corpus and a hybrid variant.
6. `rag/router.py` with the precedence rules above; for now it always resolves to `ipc`,
   but the seam and its tests exist. Session model gains `corpus_mode` + `offence_date`.
7. Retrieval: corpus-scoped payload filter, score threshold, configurable `k`; return
   "I don't have that in the {act}" when nothing clears the threshold, instead of
   hallucinating from weak chunks.
8. `LLMProvider` protocol; **Groq implementation as the default** (free tier, streaming,
   hard timeout), **Mistral as the alternate** (matches legacy, config-swappable via
   `LLM_PROVIDER`). Retry with backoff on 429/5xx — free tiers rate-limit harder than paid
   ones, so backoff matters more here, not less. Anthropic/Bedrock providers stubbed
   behind the same interface for the funded-phase swap.
9. **Stop persisting error strings as assistant answers** (`app.py:94`) — return a typed
   error, don't store it as a legal answer. Persist `corpus` + `ingest_version` on each turn.
10. Eval harness: ~30 IPC questions with expected sections, scored on retrieval-hit-rate
    and citation correctness. Parameterised by corpus from the start. CI runs it as a
    non-blocking report.

**Swarm:** a Workflow with a fan-out over the eval questions once the harness exists;
otherwise 3 agents in parallel — corpus registry + ingest, retriever + router, provider layer.

**Exit criteria:** cold start under 5 s; every answer names its act, section, and page;
`grep -ri '"ipc"' app/ --exclude-dir=corpora` returns nothing; the eval harness reports a
baseline; a killed provider endpoint yields a clean 503, not a hang.

### Sprint 3B — Onboard BNS and the hybrid model

Runs as its own sprint so the abstraction is proven by a real second corpus rather than by
assertion. If BNS source text isn't ready, this sprint waits — nothing downstream blocks on it.

1. Acquire authoritative BNS text (India Code / Gazette PDF). Put it in `data/bns/` under LFS,
   record provenance and retrieval date in `docs/decisions.md`. **Source authenticity matters
   more here than anywhere else in the project** — a wrong PDF poisons every answer.
2. Add the `bns` entry to `definitions.yaml`; run `scripts/ingest.py --corpus bns`.
   If no loader change is needed, the abstraction passed.
3. Build `data/crosswalk/ipc_bns.csv` from a published concordance via
   `scripts/build_crosswalk.py`; **human-review every row** before committing. Load it in
   `corpora/crosswalk.py` with lookup in both directions.
4. Implement hybrid retrieval + the structured answer contract (current BNS position,
   IPC counterpart, explicit `modified`/`new`/`repealed` flags).
5. Router: enable date-based resolution and the clarifying question for undated queries.
6. UI: corpus selector (IPC / BNS / Both) in the chat header, persisted on the session and
   shown on every replayed message. Delete `containsIPC()` (`index.js:63`).
7. FIR form: Acts & Sections driven by the registry, defaulted from the occurrence date.
8. Extend the eval set — 30 BNS questions, plus ~15 crosswalk questions
   ("what replaced IPC 302?", "does BNS still have 377?") with known-correct answers.

**Swarm:** 3 parallel agents — ingestion/loader for BNS, crosswalk build + review tooling,
hybrid prompt + answer contract. The crosswalk review itself is **human work, not delegated**.

**Exit criteria:** the same question answered under IPC, BNS, and hybrid modes returns three
correctly-cited answers; a pre-2024 offence date routes to IPC and a post-2024 one to BNS;
every crosswalk assertion traces to a reviewed CSV row; no answer ever cites a section
without its act; eval hit-rate on BNS within 10% of IPC.

### Sprint 4 — API hardening and observability

1. Pydantic request/response models on every route; reject unknown fields.
2. Global exception handlers — **never return `str(e)`**; log the detail with a request id,
   return `{"error": "...", "request_id": "..."}`. Removes all 9 leak sites.
3. `CORS_ORIGINS` from config, credentials-aware, not `CORS(app)`.
4. Security headers + a CSP (which also kills the inline `onclick` handlers), `SameSite`
   cookies, HTTPS redirect.
5. structlog JSON to stdout with request-id propagation; **redact query text at INFO**;
   silence third-party DEBUG (the current config logs 64 urllib3 lines per request cycle).
6. `/healthz` (liveness) and `/readyz` (Mongo + vector store + provider reachable).
7. Fix the `/rename_session` false-404 (`modified_count > 0` fails on a no-op rename) and
   the unbounded `/history` aggregation — add `$match` on `user_id`, `$sort`, `$limit`, and
   cursor pagination.

**Swarm:** 3 parallel agents on disjoint concerns — errors/validation, logging/health,
headers/CORS.

**Exit criteria:** a fuzz test over every route body returns 422, never 500; no response
body contains an exception string; `/readyz` correctly reports a downed dependency.

### Sprint 5 — Frontend rebuild

1. `base.html` with the shell, nav, and theme script; all six pages `{% extends %}` it.
   Removes ~1,400 duplicated lines.
2. Delete dead code: `index.html:251-392`, `index.js:407-517`, the commented `register.js`,
   and the stray Cloudflare challenge scripts in `account.html:149` / `firform.html:387`.
3. **Fix the XSS**: render message text with `textContent`; if markdown is wanted, use
   `marked` + `DOMPurify` with a strict allowlist. Same for every error path.
4. Streaming chat UI over SSE, with an abort button.
5. Persist `currentSessionId` (currently lost on reload) and reconcile it against the server.
6. **`firform.html`**: replace `contenteditable` spans with real inputs in a form that POSTs
   to `/api/fir`, persist drafts per user, and render the FIR to PDF server-side. Right now
   the entire FIR feature loses its data.
7. Make `settings.html` and `account.html` real, or remove their nav entries. Do not ship
   "coming soon" buttons in a tool being evaluated by a real department.
8. Accessibility pass: labels, focus states, keyboard nav, `aria-live` on the message list.

**Swarm:** 2 agents — templates/base extraction; JS rewrite + streaming. Parallel, disjoint files.

**Exit criteria:** Playwright e2e covering login → ask → stream → rename → delete → logout;
a `<img src=x onerror=alert(1)>` answer renders as text; Lighthouse a11y ≥ 90.

### Sprint 6 — Testing, deploy, compliance, documentation

1. Coverage to ≥ 70% on `app/`, with the auth and ownership paths at 100%.
2. Load-check `/api/chat` concurrency with a stubbed provider (proves the async fix).
3. Deploy to Oracle Cloud Always Free (Mumbai/Hyderabad): `docker compose up` running the
   app, self-hosted MongoDB, self-hosted Qdrant, and Caddy for TLS. Secrets in a gitignored
   `.env` on the VM (a real secret manager is a funded-phase upgrade). Uptime check via a
   free monitor (UptimeRobot free tier or a cron+curl check).
4. **India-only compliance pass** (DPDP Act 2023 + CERT-In Directions 2022 — no other
   jurisdiction's rules apply and none should be designed for):
   - Consent notice at signup stating purpose and retention period (English + Hindi).
   - A working account-deletion endpoint that actually purges chat history, not a soft flag.
   - A named grievance-officer contact, per DPDP.
   - Security logs retained **180 days, stored on the India-hosted VM** — never shipped to
     a foreign-hosted logging SaaS, even a free-tier one.
   - Per-role disclaimer strength: citizen-facing answers carry a louder
     "not legal advice, consult a lawyer" than the lawyer/police surfaces.
5. `README.md`: architecture diagram, setup, ingest, deploy, a **"How to add a corpus"**
   runbook (BNSS/BSA are the next candidates), corpus provenance table, the MVP-vs-funded
   stack table, and the disclaimer required by item 4.
6. Final `DISCREPANCIES.md` reconciliation; everything `fixed` or `wontfix` with a reason.
7. Update `CLAUDE.md` to the new structure.

**Exit criteria:** a clean clone → `docker compose up` → working app, guided only by the
README, at ₹0 recurring cost beyond an optional domain name.

---

## Critical files

All paths below are in the **legacy, untouched** `jurisai/` tree — read as reference and
ported into `jurisai_greenfield/`, never edited in place:

- `jurisai/Backend/app.py` — logic source for `jurisai_greenfield/backend/app/**`; the
  origin of nearly every S0/S1 finding.
- `jurisai/Backend/static/index.js` — XSS sinks at `:89`, `:334`, `:357`; dead code `:407-517`.
- `jurisai/Backend/templates/register.js` — committed Firebase key at `:10`; do not port this file.
- `jurisai/Backend/templates/login.html` — fake submit at `:686`; the whole auth entry point.
- `jurisai/Backend/templates/firform.html` — `contenteditable` form that discards FIR data.
- `jurisai/requirements.txt` — reference only for the real dependency list; superseded by
  `jurisai_greenfield/pyproject.toml`.

## Reuse rather than rewrite

- **Don't migrate the legacy Chroma index.** Those chunks predate the metadata contract
  and the section-aware splitter. Instead, copy the source `ipc-data.pdf` from
  `jurisai/Backend/ipc-data/` into `jurisai_greenfield/data/ipc/` and build the index fresh
  via `scripts/ingest.py` — cheaper than migrating vectors that need re-chunking anyway,
  and it guarantees IPC and BNS share one chunking strategy from day one.
- `argon2-cffi`, `pydantic`, `fastapi`, `uvicorn`, `httpx`, and `tenacity` — pull these into
  the new `pyproject.toml`; the retry/backoff layer should use `tenacity`, not a hand-rolled loop.
- `jurisai/Backend/static/index.css` (26 KB) carries the visual identity — port it as-is
  into `jurisai_greenfield/backend/static/`, then extract duplicated inline `<style>` blocks into it.
- The Web Speech mic input (`jurisai/Backend/static/index.js:16-30`) works — port it as-is.
- The `session_id`/aggregation shape in the legacy Mongo queries is sound — reimplement it
  with a `user_id` filter, not a redesign.

## Verification

Per sprint: `ruff check`, `mypy app/`, `pytest -q`, then `/code-review` on the diff, then a
human read. End-to-end, before calling it done:

1. `git clone` fresh → `uv sync` → `docker compose up` → app serves on first try.
2. `python scripts/ingest.py` builds the index from the PDF; app starts cold in < 5 s.
3. Sign up as user A, ask three questions, confirm streamed answers with act + section +
   page citations.
3b. Switch the corpus selector across IPC / BNS / Both on the same question — three
   correctly-attributed answers, no section quoted without its act.
3c. State an offence date of 2023-05-01 → answer routes to IPC; 2025-05-01 → BNS; omit the
   date on an offence-specific question → the app asks rather than guessing.
3d. Ask "what replaced IPC 302?" → answer traces to a reviewed crosswalk row, and a
   `repealed` section (IPC 377) is reported as having no BNS successor, not mapped to a
   plausible-looking one.
4. Sign up as user B; attempt A's `session_id` on `/session`, `/rename_session`,
   `/delete_session` → 404 on all three. This is the single most important test in the suite.
5. Send a malformed body to every route → 422, no stack trace, no exception text.
6. Force an LLM answer containing `<img src=x onerror=alert(1)>` → renders as literal text.
7. Kill Mongo → `/readyz` fails, `/healthz` still passes, chat returns 503 not a hang.
8. `gitleaks detect` on tree and history → clean. `pip-audit` → no highs.
9. Playwright e2e suite green in CI.
10. Eval harness reports retrieval hit-rate against the 30-question set.
11. Ask a question in Hindi ("धारा 302 की सज़ा क्या है") → retrieves the correct section via
    BGE-M3's cross-lingual match, answers in Hindi. A bare "section 302" (no act) triggers
    the router's clarifying question rather than a guess.
12. Confirm the account-deletion endpoint actually removes chat history from Mongo, not a
    soft-delete flag; confirm no query text appears in any log destination outside the VM.

## Risks

- **Free-tier LLM dependency.** Groq/Mistral free tiers can change limits or pricing with
  no notice — this is the one layer where "free" is a policy, not a property of the
  software. The `LLMProvider` protocol exists specifically so that's a config change if
  it happens, not an incident. Track usage against the free-tier ceiling from day one.
- **Self-hosted Qdrant + MongoDB on one free-tier VM** is a single point of failure with
  no managed backups. Acceptable for an MVP pilot; back up the Mongo volume on a cron job
  regardless, and treat "move to managed stores" as the first funded-phase infra spend.
- **Oracle Cloud Always Free capacity is not contractually guaranteed** the way a paid
  tier is — Oracle has reclaimed idle free-tier instances in the past. Keep the
  `docker-compose.yml` portable to any VM as the mitigation, not a dependency on Oracle specifically.
- **FastAPI migration is the largest single diff.** Sprint 1 keeps it behaviour-neutral
  precisely so the review stays tractable; do not let feature work leak into it.
- **Scope creep on the FIR feature.** It is currently non-functional; if Sprint 5 runs long,
  cutting the FIR page to "chat only, v1" is the right trade, recorded as `wontfix` with a reason.
- **The IPC↔BNS crosswalk is the highest-risk artefact in the product.** A wrong row produces
  a confident, wrong legal citation. Mitigations: it is committed data not model output, every
  row is human-reviewed against a published concordance, rows carry `confidence` and `source`,
  sub-threshold rows are surfaced as uncertain, and the crosswalk eval set runs in CI. If
  review capacity is short, ship **fewer reviewed rows**, never more unreviewed ones.
- **BNS source authenticity.** Ingesting an unofficial or draft PDF silently corrupts every
  BNS answer. Only India Code / Gazette text, with provenance recorded in `docs/decisions.md`
  and a checksum committed.
- **Sequencing.** Sprint 3B depends only on Sprint 3's abstraction, not on 4–6, so BNS can be
  pulled forward if the migration deadline moves. Do **not** pull it before Sprint 3 — that
  is exactly the second-hardcoded-path outcome this design exists to prevent.
- **Corpus drift.** BNS is new and will see corrections and amendments. `ingest_version` on
  chunks and on stored answers is what makes a re-ingest auditable; keep it populated.

## Appendix — `DISCREPANCIES.md` seed (to be created in Sprint 0)

**S0 — exploitable:** hardcoded Atlas URI `app.py:25` · hardcoded Mistral key `app.py:39` ·
committed Firebase key `register.js:10` · no authentication anywhere · IDOR on
`/session/{id}` `:215` · IDOR on `/rename_session` `:233` · IDOR on `/delete_session` `:255` ·
unbounded unauthenticated `/history` `:186` · stored XSS `index.js:89/334/357` ·
`debug=True` `:288` · `CORS(app)` all origins `:15` · `str(e)` to client ×9 ·
no rate limiting on the paid LLM route.

**S1 — broken:** `requirements.txt` omits every real dependency · import-time ingestion
aborts startup (`transformers`/`timm` failure in `app.log`) · no `requests` timeout `:89` ·
`login.html:686` fake submit · `firform.html` discards all FIR data · `toggleForm()`
TypeError on removed `nameGroup` · `register.js` in `templates/`, never served ·
`account.html` is a stub.

**S2 — correctness:** `Document` reprs interpolated into the prompt `:98` · error strings
persisted as assistant answers `:94` · `/rename_session` false 404 on no-op ·
`history` `KeyError` on missing `title` `:204` · no `$sort` after `$group` · silent
persistence failure `:113` · unhandled `KeyError` on malformed Mistral body `:91` ·
no score threshold on retrieval · 40% chunk overlap · deprecated LangChain imports `:8-11` ·
**single-corpus assumptions blocking BNS**: `DATA_DIR = "ipc-data"` hardcoded `:36`, one
unnamed Chroma collection `:50`, prompt says "legal documents" with no act identity `:98`,
chunks carry no act/section metadata, character-split cuts across section boundaries,
client-side `containsIPC()` regex `index.js:63`, no offence-date or corpus field on sessions,
FIR "Acts & Sections" is free text with no statute source.

**S3 — hygiene:** no `.gitignore` · committed `config.cpython-312.pyc` (dead, holds a
placeholder `JWT_SECRET_KEY`) · committed 11 MB orphan `offload_weights/` shard · 20 MB PDF
not in LFS · unrotated `app.log` with user queries · `logging.DEBUG` on all third-party
loggers · no Jinja inheritance (~1,400 duplicated lines) · dead code `index.html:251-392`,
`index.js:407-517` · stray Cloudflare scripts `account.html:149`, `firform.html:387` ·
`package.json` declares an unused dependency · no tests, CI, Dockerfile, or README content ·
"coming soon" buttons shipped in the UI · dead `fine_tuned_model` parameter `:68`.
