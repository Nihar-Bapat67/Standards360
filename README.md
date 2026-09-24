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

eval/                    the frozen 50-record gold set and the harness that measures against it
```

Data lives in `data/` and is never committed: BIS holds copyright in every standard, so the corpus,
the database and the indexes stay local, and the product quotes only short extracts with a citation.

## Where it stands

Seventeen of nineteen modules are built, with 96 tests passing. On the frozen gold set the engine
scores Hit@3 0.82 across all 50 records, and Hit@1 0.879 on the 33 whose text we hold. What remains
is B2 (multilingual) and D5 (the web interface).

See `CLAUDE.md` for the decisions taken during the build and the measurements behind them, and
`docs/04-build-manual.md` for the plan.
