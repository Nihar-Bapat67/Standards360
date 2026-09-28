# Standards360

An engine that maps a procurement specification to the applicable Indian Standards, their allied
standards, the editions in force, and the certification obligations that follow. Built for Smart
India Hackathon problem statement 26108, Department of Consumer Affairs.

A tender line goes in. What comes back is a primary standard with the clause that justifies it,
the allied standards grouped by the role each plays, a verdict on every standard the tender already
cited, version and amendment warnings, certification with the laboratories that can test, an honest
confidence band, and a PDF annexure appended to the officer's own document.

## Requirements, and the one trap

Python 3.11 or later, and the packages in `requirements.txt`.

**This machine has two interpreters.** Everything is installed in
`C:\Users\DELL\AppData\Local\Programs\Python\Python311\python.exe`, while the terminal's `python`
is Miniconda 3.14, which has none of it. A command run in the terminal therefore fails with
`ModuleNotFoundError: No module named 'faiss'` even though faiss is installed. Either use the full
path to the 3.11 interpreter, or install the requirements into the conda environment once:

```
python -m pip install -r requirements.txt
```

The Hugging Face cache is shared between interpreters, so the embedding model is not downloaded
again.

## Try it

Stage by stage, which is also the demo driver:

```
python demo/walkthrough.py --scenario tubes --state Gujarat --pdf
python demo/walkthrough.py --text "Supply of HDPE pipes 110 mm PN 6 for rural water supply"
python demo/walkthrough.py --scenario thin --answers type="electric resistance welded"
```

As a service, which is what a procurement portal would call:

```
uvicorn app.api.main:app --port 8000        then open http://localhost:8000/docs
```

## The web interface

Two front doors — an officer drafting a tender, a manufacturer checking a product — leading into a
conversational intake that ends in a document. Built with Vite, React, TypeScript, Tailwind and
Framer Motion, and it is a client of the same `/v1` contract a procurement portal would call.

**Development**, with the interface and the API on separate ports:

```
uvicorn app.api.main:app --port 8000
cd web && npm install && npm run dev        then open http://localhost:5173
```

Vite proxies `/v1` and `/health` to port 8000, so nothing needs configuring.

**Production**, one process and one port:

```
cd web && npm install && npm run build
uvicorn app.api.main:app --host 0.0.0.0 --port 8000
```

FastAPI serves `web/dist` itself when that directory exists, so the whole product is at
`http://localhost:8000`. If you deploy the interface and the API to different hosts, set
`VITE_API_BASE` before building and narrow the CORS origins in `app/api/main.py`.

Three screens: the landing page, the workspace, and an architecture walkthrough at `/architecture`.
Every figure any of them prints is served from `/v1/meta`, which reads the live catalogue and the
frozen gold set — nothing is typed into the markup.

### Endpoints

```
GET  /health                  readiness, the loaded model, catalogue size
GET  /v1/meta                 catalogue, index and evaluation figures for the interface
POST /v1/analyze              the analysis, as one JSON response
POST /v1/analyze/stream       the same analysis, reported module by module as Server-Sent Events
POST /v1/analyze/upload       a tender PDF, DOCX, text file or screenshot
POST /v1/document             the report or annexure as a PDF
POST /v1/document/upload      the officer's own PDF with the annexure appended
GET  /v1/standard/{is}        everything the catalogue holds about one standard
```

## Languages

The interface and the answers are available in English, Hindi and Marathi. Module B2
(`app/understand/language.py`) detects the language a request arrives in, translates it to English
for retrieval — the clause index, the title index and the cross-encoder are all English — and writes
the answer back in the reader's language.

Two rules govern it. **Identifiers are never translated.** Left alone a translator transliterates
them, so "IS 269:2015" comes back as "आई.एस. 269:2015" and BIS as "बी.आई.एस.", and a citation written
that way cannot be pasted into a tender. Every identifier is masked before translation and restored
after, and a string that loses one falls back to English rather than shipping a broken citation.
**Authoritative BIS text is never translated at all** — a quoted clause and an official title stay
exactly as BIS published them, and only the writing around them is translated.

Interface strings live in `web/src/i18n/`. English is the source of truth in `en.ts`; the other
dictionaries are generated and committed, and any key missing from one falls back to English:

```
python ingest/translate_ui.py --only hi mr     regenerate after changing en.ts
python ingest/translate_ui.py --check          coverage per language
```

Without a configured LLM key, the whole thing still runs: language detection falls back to a Unicode
script heuristic, translation is skipped, and answers come back in English. Hosted LLM calls are
also disabled unless `LLM_NO_RETENTION_CONFIRMED=true` is explicitly set after confirming that the
selected provider guarantees no retention for tender/specification data. Configure `LLM_PROVIDER`,
`LLM_MODEL`, `LLM_BASE_URL` and `LLM_API_KEY` for a chat-compatible provider; Sarvam remains the
default and `SARVAM_API_KEY` continues to supply translation credentials.

## Configuration

Copy `.env.example` to `.env`. Every value is optional — the engine runs without a language-model
key and falls back to rules, saying so rather than failing. Nothing in `.env` is committed.

Tests and the accuracy measurement:

```
python -m pytest tests -q
python eval/run_eval.py --show-misses
```

The first request of a process takes about 90 seconds while the models load, then each one takes
two to three seconds.

## How it is put together

Stage A runs offline and builds the knowledge base. Stages B, C and D answer a request and never
touch the BIS website.

```
ingest/collect.py        A1  the BIS catalogue: 35,553 standards, cross-references, labs, QCOs
ingest/fetch_texts.py        current-edition PDFs for the two sectors
ingest/parse_clauses.py  A2  PDFs into numbered clauses
ingest/extract_refs.py   A3  clause-level cross-references with the sentence that asserts them
ingest/build_index.py    A4  FAISS, BM25 and a title index over every current standard

app/understand/          B1 input · B3 requirement · B4 citation verdicts · B5 the question loop
app/core/                C1 retrieval · C2 allied · C3 versions · C4 certification · C5 confidence
app/deliver/             D1 validity guard · D2 composer · D3 document
app/api/main.py          D4 the one endpoint a portal calls
app/pipeline.py              all of it, wired in order
web/                     D5 the interface: landing, workspace, architecture walkthrough

eval/                    the frozen 50-record gold set and the harness that measures against it
```

Data lives in `data/` and is never committed: BIS holds copyright in every standard, so the corpus,
the database and the indexes stay local, and the product quotes only short extracts with a citation.

## Where it stands

Eighteen of nineteen modules are built, with 96 tests passing. On the frozen 50-record gold set the
engine scores **Hit@1 0.820, Hit@3 0.960, Hit@5 0.960 and MRR@5 0.887**, against a corpus of 467
standards with full text. Both of the build manual's retrieval targets are met.

B2, the multilingual path, is now built: a Hindi tender is detected, translated for retrieval, and
answered in Hindi with every IS number intact. All nineteen modules exist.

Two honest limits. Interface translation currently covers Hindi and Marathi; the other Indian
languages need the generator re-run against an account with credits, and until then they would fall
back to English. And multilingual retrieval accuracy is not measured — the gold set is English, so
the Hindi path is verified to work but not scored.

See `CLAUDE.md` for the decisions taken during the build and the measurements behind them, and
`docs/04-build-manual.md` for the plan.
