# DISCREPANCIES — open-issue register

Seeded from the initial audit of the legacy prototype (`jurisai/`, untouched, read-only).
All evidence paths point into that legacy tree unless noted otherwise.

Frozen for the duration of a sprint — no edits mid-sprint. New findings discovered during
a sprint go into a scratch `DISCOVERED.md` and are merged in at the sprint boundary.

Severity: **S0** exploitable · **S1** broken · **S2** correctness · **S3** hygiene.
Status: `open` → `in-sprint-N` → `fixed` (+ commit SHA) → `wontfix` (+ reason).

| ID | Severity | Area | Issue | Evidence (file:line) | Sprint | Status |
|---|---|---|---|---|---|---|
| D001 | S0 | Secrets | Hardcoded MongoDB Atlas URI with real password | `jurisai/Backend/app.py:25` | 0 | open |
| D002 | S0 | Secrets | Hardcoded Mistral API key | `jurisai/Backend/app.py:39` | 0 | open |
| D003 | S0 | Secrets | Committed Firebase Web API key (unrestricted) | `jurisai/Backend/templates/register.js:10` | 0 | open |
| D004 | S0 | Auth | No authentication anywhere in the app | `jurisai/Backend/app.py` (all routes) | 2 | open |
| D005 | S0 | IDOR | Any client can read any session by guessing UUID | `jurisai/Backend/app.py:215-230` | 2 | open |
| D006 | S0 | IDOR | Any client can rename any session | `jurisai/Backend/app.py:233-252` | 2 | open |
| D007 | S0 | IDOR | Any client can delete any session | `jurisai/Backend/app.py:255-274` | 2 | open |
| D008 | S0 | IDOR | `/history` returns every session in the DB, unauthenticated, unbounded | `jurisai/Backend/app.py:186-212` | 2 | open |
| D009 | S0 | XSS | Stored XSS — LLM output into `innerHTML` unescaped | `jurisai/Backend/static/index.js:89` | 5 | open |
| D010 | S0 | XSS | Stored XSS — session replay into `innerHTML` unescaped | `jurisai/Backend/static/index.js:334,357` | 5 | open |
| D011 | S0 | XSS | Error messages into `innerHTML` unescaped | `jurisai/Backend/static/index.js:207,258,329,363` | 5 | open |
| D012 | S0 | Config | `debug=True` in production entrypoint (RCE surface via Werkzeug console) | `jurisai/Backend/app.py:288` | 4 | open |
| D013 | S0 | Config | `CORS(app)` — all origins allowed | `jurisai/Backend/app.py:15` | 4 | open |
| D014 | S0 | Info leak | `str(e)` returned to client on 500 (×9 routes) | `jurisai/Backend/app.py:118,127,136,145,154,163,+3` | 4 | open |
| D015 | S0 | Abuse | No rate limiting on the paid LLM route | `jurisai/Backend/app.py:172-183` | 2 | open |
| D016 | S1 | Deps | `requirements.txt` omits every package the app actually imports | `jurisai/requirements.txt` | 1 | open |
| D017 | S1 | Startup | Import-time RAG ingestion can abort startup (transformers/timm conflict) | `jurisai/Backend/app.py:41-99`, `jurisai/Backend/app.log` | 3 | open |
| D018 | S1 | Reliability | No timeout on `requests.post` to Mistral | `jurisai/Backend/app.py:89` | 3 | open |
| D019 | S1 | Auth UI | Login form fakes submit (`setTimeout` + `console.log`, no real request) | `jurisai/Backend/templates/login.html:686` | 2 | open |
| D020 | S1 | FIR | FIR form uses `contenteditable` spans with no submit handler — data is unrecoverable | `jurisai/Backend/templates/firform.html` | 5 | open |
| D021 | S1 | UI bug | `toggleForm()` throws TypeError — `nameGroup`/`nameInput` removed from markup | `jurisai/Backend/templates/login.html:590` | 5 | open |
| D022 | S1 | Dead file | `register.js` sits in `templates/`, is never served, holds a live secret (see D003) | `jurisai/Backend/templates/register.js` | 0 | open |
| D023 | S1 | Stub UI | `account.html` is a literal "coming soon" stub | `jurisai/Backend/templates/account.html:93-96` | 5 | open |
| D024 | S2 | RAG bug | Raw `Document` objects (repr, not text) f-string-interpolated into the prompt | `jurisai/Backend/app.py:98` | 3 | open |
| D025 | S2 | Correctness | Exception strings persisted to DB and shown as the assistant's answer | `jurisai/Backend/app.py:94` | 3 | open |
| D026 | S2 | Bug | `/rename_session` returns false 404 when rename is a no-op (`modified_count==0`) | `jurisai/Backend/app.py:233-252` | 4 | open |
| D027 | S2 | Bug | `KeyError` risk on missing `title` field (direct key access, not `.get`) | `jurisai/Backend/app.py:204` | 4 | open |
| D028 | S2 | Query | Mongo aggregation has no `$sort` after `$group` | `jurisai/Backend/app.py:186-212` | 4 | open |
| D029 | S2 | Reliability | Chat-persistence failure is silently swallowed | `jurisai/Backend/app.py:113-114` | 3 | open |
| D030 | S2 | Bug | Unhandled `KeyError` risk on a malformed Mistral response body | `jurisai/Backend/app.py:91` | 3 | open |
| D031 | S2 | RAG quality | No similarity-score threshold on retrieval — always returns top-3 even if irrelevant | `jurisai/Backend/app.py:96-98` | 3 | open |
| D032 | S2 | RAG quality | 500/200 character chunking = 40% overlap, cuts statutes mid-section | `jurisai/Backend/app.py:59` | 3 | open |
| D033 | S2 | Tech debt | Deprecated pre-0.1 LangChain import paths | `jurisai/Backend/app.py:8-11` | 3 | open |
| D034 | S2 | Corpus | `DATA_DIR = "ipc-data"` hardcoded — single corpus assumed everywhere | `jurisai/Backend/app.py:36` | 3 | open |
| D035 | S2 | Corpus | Unnamed Chroma collection — no way to address a corpus by name | `jurisai/Backend/app.py:50` | 3 | open |
| D036 | S2 | Corpus | Prompt says "legal documents" with no act identity — answers can't cite a statute | `jurisai/Backend/app.py:75-80` | 3 | open |
| D037 | S2 | Corpus | Chunks carry no act/section metadata | `jurisai/Backend/app.py:59` (ingest) | 3 | open |
| D038 | S2 | Corpus | Character-split chunking crosses section boundaries, breaking future crosswalk addressing | `jurisai/Backend/app.py:59` | 3 | open |
| D039 | S2 | Corpus | Client-side `containsIPC()` regex — corpus detection belongs server-side in the registry | `jurisai/Backend/static/index.js:63` | 3B | open |
| D040 | S2 | Corpus | No offence-date or corpus field on sessions — can't route IPC vs BNS | `jurisai/Backend/app.py` (session schema) | 3 | open |
| D041 | S2 | Corpus | FIR "Acts & Sections" is free text, no statute source of truth | `jurisai/Backend/templates/firform.html` | 3B | open |
| D042 | S3 | Hygiene | No `.gitignore` | — | 0 | open |
| D043 | S3 | Hygiene | Committed `config.cpython-312.pyc`, dead, no source, holds placeholder `JWT_SECRET_KEY` | `jurisai/Backend/__pycache__/config.cpython-312.pyc` | 0 | wontfix (legacy file, not ported) |
| D044 | S3 | Hygiene | Committed 11 MB orphan T5 model shard, unreferenced by any code | `jurisai/Backend/offload_weights/decoder.block.7...dat` | 0 | wontfix (legacy file, not ported) |
| D045 | S3 | Hygiene | 20 MB source PDF not in Git LFS | `jurisai/Backend/ipc-data/ipc-data.pdf` | 0 | open (re-added via LFS in greenfield) |
| D046 | S3 | Hygiene | Unrotated `app.log` — logs full user queries at DEBUG/INFO | `jurisai/Backend/app.log` | 4 | open |
| D047 | S3 | Hygiene | `logging.DEBUG` applied globally, floods logs with third-party output | `jurisai/Backend/app.py:18` | 4 | open |
| D048 | S3 | Hygiene | No Jinja inheritance — ~50-60% of ~2,900 template lines duplicated | `jurisai/Backend/templates/*.html` | 5 | open |
| D049 | S3 | Dead code | Entire second commented-out copy of the app | `jurisai/Backend/static/index.js:407-517` | 5 | open |
| D050 | S3 | Dead code | Dead markup block | `jurisai/Backend/templates/index.html:251-392` | 5 | open |
| D051 | S3 | Dead code | Stray Cloudflare challenge scripts, leftover | `jurisai/Backend/templates/account.html:149`, `firform.html:387` | 5 | open |
| D052 | S3 | Dead code | `package.json` declares an unused dependency (`date-fns`) | `jurisai/package.json` | 1 | open |
| D053 | S3 | Missing | No tests, no CI, no Dockerfile, no README content | — | 1 | open |
| D054 | S3 | UX | "Coming soon" stub buttons shipped in the UI | `jurisai/Backend/templates/settings.html`, `legal.html` | 5 | open |
| D055 | S3 | Dead code | Unused `fine_tuned_model` parameter, never varied | `jurisai/Backend/app.py:68` | 3 | open |
| D056 | S2 | Corpus | English-only embeddings can't serve Hindi/regional-language queries — needed once the userbase is citizens/lawyers, not just police | — (design gap, greenfield) | 3 | open |
| D057 | S2 | RAG quality | Dense-only retrieval misses exact section-number lookups ("धारा 302" / "section 302") — needs hybrid dense+sparse | — (design gap, greenfield) | 3 | open |
| D058 | S1 | Compliance | No DPDP-compliant consent notice, retention statement, or grievance-officer contact at signup | — (design gap, greenfield) | 6 | open |
| D059 | S1 | Compliance | No real account-deletion endpoint (chat history purge) — required under DPDP | — (design gap, greenfield) | 6 | open |
| D060 | S2 | Compliance | Security logs must be retained 180 days and stored within India per CERT-In Directions 2022 — no foreign-hosted log sink | — (design gap, greenfield) | 4 | open |
