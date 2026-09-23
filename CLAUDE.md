# Standards360

AI-powered recommendation engine that maps a procurement specification to the applicable
Indian Standards (IS), their allied/normative references, current versions, and mandatory
certification obligations.

## Problem Statement (fixed — do not restate or re-scope without the user)

- **PS ID:** 26108 (Smart India Hackathon)
- **Title:** AI-Powered Recommendation Engine for Identifying Applicable Indian Standards for Procurement Specifications
- **Organization:** Ministry of Consumer Affairs, Food & Public Distribution
- **Department:** Department of Consumer Affairs (DoCA)
- **Category / Theme:** Software / Smart Automation

### Background
Government departments, PSEs, procurement agencies and private organizations procure goods and
services through e-procurement portals. Officials drafting technical specifications must reference
the appropriate Indian Standards, but identifying the correct standard is hard: the catalogue is
large, scopes overlap, revisions are frequent, and normative/allied references must also be
considered. Result: tenders omit relevant standards, cite outdated versions, or carry incomplete
technical requirements — causing ambiguity, poor product quality, and procurement disputes.

### Required features
1. Accept product descriptions, technical specifications, or full tender documents as input.
2. Recommend the most relevant Indian Standard(s) via **semantic** understanding, not keyword matching.
3. Identify **allied standards**: normative references, test methods, terminology, safety,
   installation, and related product standards.
4. Highlight the **latest published version and amendments**.
5. Suggest **mandatory certification requirements** where applicable (BIS Product Certification /
   ISI mark, CRS, Hallmarking).
6. Support **multilingual input** and natural-language queries.

## Hard constraints (architecture-defining)

- **Copyright in every Indian Standard vests in BIS.** Full text must never be redistributed.
  Store embeddings + short extracts; always cite and deep-link to the BIS portal.
- Full-text IS PDFs are downloadable **free with registration** at `standardsbis.bsbedge.com`.
  Acquisition is account-bound and rate-limited — respect ToS, no aggressive scraping.
- **No official public BIS bulk/metadata API.** `standards.bis.gov.in` is JS-rendered and uses
  encrypted record IDs. Collection therefore uses the public detail pages on `services.bis.gov.in`
  (see Implementation decisions → A1).
- Uploaded tender documents may be **pre-tender confidential** — no third-party LLM calls without
  a no-retention guarantee; prefer open-weight/on-prem for the confidential path.
- Timeline: **10 days**. Metadata coverage broad, full-text coverage deep on a few sectors only.

## Key numbers (cite these, they are verified)

- ~22,689 Indian Standards in force (PIB, Mar 2025).
- 187 Quality Control Orders covering 769 products under compulsory certification (PIB, Mar 2025).

## Engineering approach

This project is deliberately run as a **textbook Software Engineering lifecycle** — the user wants
documented SE artifacts at each phase, version-controlled under `docs/`, not just working code.
Produce real artifacts (SRS, UML, ADRs, test plans), never placeholder checklists.

## Build manual — ground every answer in it

The build manual is the plan for this project. It is imported below, so it is always loaded.

@docs/04-build-manual.md

Rules for using it:

- Answer questions about architecture, modules, scope, storage, schedule and team allocation from
  the manual. Name the section or module ID the answer comes from (for example "§11" or "C3").
- Where the manual and the **Implementation decisions** section below disagree, the decisions below
  are current. Say explicitly that the manual is out of date on that point.
- When a decision changes during work, update the Implementation decisions section in the same turn.
- `docs/02-architecture-draft.md` and `docs/03-innovation-strategy.md` are earlier drafts. Where
  they disagree with the manual, the manual wins. In particular, the restrictive-specification
  detector and the impact radar from `03` are listed as "not building" in manual §11.
- Every IS number in the manual is illustrative unless it also appears under verified data below.

## Where we are

Current phase (23 Sep 2026): **Stage A complete for A1–A3; A4 is next**.

- **A1 done.** The full crawl finished and `load` rebuilt the database. `data/catalogue.db` holds
  35,553 records: 24,101 current and 11,452 withdrawn, of which 6,822 name their replacement.
  Also 165,657 cross-reference links, 12,105 lab rows (502 distinct labs across 28 states),
  28,144 gazette notices, 4,545 amendments, 1,636 product manuals, 777 category pairs.
  725 standards carry a QCO; 1,405 have a summary-PDF link.
- **A2 and A3 merged** from the `vishwajeet_dev` branch (commit `fec411d`), code only. The branch
  shared no history with `main` and carried data, BIS PDFs, a vendored PyMuPDF and a nested
  repository; none of that was merged. Data is regenerated locally and stays git-ignored.
- **Verified on four current-edition standards** (CED: IS 1786:2008, IS 1489 Part 1:2015;
  MTD: IS 1161:2014, IS 280:2006): all four match the right `record_id`, and all four yield a scope
  clause and a references clause. A3 produced no false edges for IS 1161 and found seven genuine
  references that BIS's own cross-reference list omits for IS 1786.
- **A4 done.** `data/index/` holds a bge-m3 index of 4,130 clauses from 261 standards (1024
  dimensions, 3h58m to build on CPU), plus the BM25 index and the row map.
- **Gold set frozen.** `eval/gold_set.json` holds 50 validated records (27 CED, 23 MTD), and
  `eval/run_eval.py` reports Hit@1/3/5 and MRR@5 by sector and difficulty. First measurement:
  raw Hit@3 0.500, but on the 27 gold standards whose text is in the index, Hit@1 0.889,
  Hit@3 0.926, MRR@5 0.901. Coverage, not retrieval, is the limit.
- **C3, C4 and D1 done.** Version and supersession resolution, certification with QCO dates and
  labs, and the validity guard. All three are catalogue lookups with no model, and are covered by
  tests that run against the real database.
- Next: C1 as a service over the A4 index, C2 allied expansion, C5 confidence, then Stage B and D.

### Measured limits of this laptop (i5-1334U, 7.7 GB RAM, no GPU)
- A2 parsing: about 35 s per standard with 4 workers.
- A4 embedding with bge-m3: 0.29 clauses/s, so 4,130 clauses take about 4 hours. Index rebuilds
  must run overnight, and A4 needs an append mode before the corpus grows further.
- One search query, embed plus BM25 plus fusion: 1.92 s.
- The manual's `bge-reranker-v2-m3` is not usable here; scoring 25 candidates would take over a
  minute. C1 should use a small cross-encoder such as `ms-marco-MiniLM-L-6-v2` instead.

Run `python ingest/collect.py stats` for live progress. Update this section when the phase changes.

## Implementation decisions (verified during the build; these supersede the manual)

### A1 — data source and collector
- Source: public BIS "Know Your Standards" detail pages on `services.bis.gov.in`, one page per
  standard at `.../knowyourstandards/Indian_standards/isdetails/<base64 of record ID>`. Server-rendered
  HTML; plain `requests` works. Not the JS-rendered `standards.bis.gov.in` portal.
- Record IDs form two ranges: 1–34,300 (main) and 65,500–67,400 (2026-era standards). A final
  closure pass fetches any cross-referenced record outside those ranges.
- The server takes about 4.5 s per page. Crawl politely: 4 workers, short delay. Full catalogue
  ≈ 36,000 pages ≈ 15–18 hours, run overnight; the crawl is resumable.
- The site's bulk search endpoint refuses scripted requests. Do not attempt to work around it.
- Seeds and gold set: BIS category pages give 777 product → standard pairs covering 725 distinct
  standards across 28 categories (`data/bis/categories.jsonl`). These are the evaluation answer key
  and the priority-crawl seeds. They are not the recommendation engine.
- Collected per standard: number, title, superseding IS, equivalence, revisions, amendment text,
  aspect, language, reaffirmation year, department, committee, group / sub group / sub sub group,
  certification status, counts (amendments, gazette, licences, product manuals, labs, corrigenda),
  cross-references in both directions with record IDs, and via JSON endpoints: labs (name, city,
  state), product manuals, gazette notices, amendments.
- Deliberately not collected: licence-holder lists, committee member emails and names (not needed;
  personal data).
- Present in the saved raw pages but **not yet parsed**: "QCO Notified & Implemented" with its
  implementation date (needed by C4.4), and the link to a one-page summary PDF (possible source of
  scope text). Add to the parser and re-parse saved pages; no re-crawl needed.

### A2 and A3 — parser and cross-reference extractor
- `ingest/parse_clauses.py` takes a single standard PDF, a directory of PDFs, or a compilation such
  as SP 21, and writes `clauses.json`, `parse_manifest.json` and `quarantine.json`. Every clause
  carries `record_id`, so it joins to the catalogue directly; `clause_id` is `<is>#<clause>`.
- `ingest/extract_refs.py` reads those clauses and writes `edges.csv`, `edges.json` and
  `a3_manifest.json`: from, relation, to, clause, confidence and the evidence sentence.
- Defects fixed after the merge: `(2008)` was being read as a family part rather than a year;
  table figures and amendment pages were parsed as clause headings; clauses lacked `record_id`;
  named tests were not classified as test methods and sub-clauses did not inherit a parent's role;
  repeated citations produced duplicate edges; clauses sorted as text so "10" preceded "2"; and a
  withdrawn record could displace the current one for the same IS number in the lookup.
- A3 is complementary to the BIS links, not a replacement: for IS 1786:2008 the BIS page lists one
  cross-reference while A3 extracted eight, all genuine. Relation typing is still imperfect, so
  treat the relation as a hint and the evidence sentence as the proof.
- Data (`data/parsed/`, `clauses.json`, `edges.csv`) is never committed. `.gitignore` also blocks
  `catalogue/`, `pylib/`, `*.pdf` and `*.db`.

### A2 text acquisition and A4 index
- `ingest/fetch_texts.py` selects the current-edition standards of the frozen sectors and downloads
  their PDFs from the archive.org `gov.in.is.*` collection into `data/raw/bis_pdf/`, writing
  `data/text_manifest.json`. It never downloads an older edition. Coverage for the two sectors:
  2,698 standards have a current-edition text (CED 1,536, MTD 1,162) and 961 do not.
  `--priority` limits it to gold-set members, QCO products and standards cited five or more times.
- `ingest/build_index.py` is A4. It reads A2's `clauses.json` and writes `data/index/`:
  `faiss.index` (cosine over normalised vectors), `bm25.pkl`, `id_map.json` (row → record_id,
  IS number, clause, role, pages, text) and `meta.json` (model, filters, counts). Clauses flagged
  `standard_withdrawn` or `text_version_differs_from_current` are never indexed, foreword clauses
  are excluded by default, and what was skipped is reported. `--query` runs a dense + BM25 + RRF
  smoke test so the index can be checked on its own; the real retrieval is C1's job.
- Embedding model: `BAAI/bge-m3` as the manual specifies, overridable with `--model`.

### A3 — mostly replaced by BIS data
- BIS publishes each standard's cross-references as structured links, so relationships come from
  the `xrefs` table rather than Clause 2 extraction. The edge type comes from the **cited
  standard's own Aspect field** (for example "Methods of tests" → test method). Clause 2 extraction
  with a language model is now only a fallback for gaps.

### Storage
- The collector writes files first, then `load` builds the database:
  `data/raw/bis_html/<id>.html.gz` (original pages), `data/bis/standards.jsonl`,
  `data/bis/categories.jsonl`, `data/bis/empty_ids.txt` → `data/catalogue.db`.
- Database is **SQLite** (`data/catalogue.db`), not PostgreSQL as the manual states: no install
  needed, supports recursive queries for C2, and moving to PostgreSQL later only changes `load`.
  Switch when several processes must write at once on a server.
- Tables: `standards`, `xrefs` (citing_record, cited_record), `labs`, `product_manuals`, `gazette`,
  `amendments`, `categories`.
- Unchanged from the manual: FAISS index, BM25 pickle and `id_map.json` files built by A4. There is
  no vector database server. `data/` is git-ignored.

### Supersession field (verified on 583 standards)
- "Superseding IS" on a standard's page lists the **older** standard(s) that this standard replaced:
  in 571 of 583 readable cases the page's own standard is the newer one. So an edge reads
  "this standard supersedes the listed one", and C3 finds the current version by following it
  backwards from the old number.
- The field is free text and messy: `IS 14920:2001`, `14920:2001` (no "IS"), `[4536-1 to 3]`
  (a range), or the standard's own number for an earlier edition. C3.1 normalisation must handle
  these. A dozen rows contradict the direction and should be treated as data errors.

### Known data gaps
- Category record 27332 ("Tyres for Two & Three wheelers") has no IS number on the BIS category page
  and a blank detail page. This is a fault in BIS's data, not the collector.
- 11,872 record IDs appear in cross-reference links but are not collected yet; nearly all are
  standards that cite the collected ones. The full crawl fills these in.
- Certification is blank or "None" for most standards; only 186 of 2,808 say "Mandatory
  Certification". Blank means "not stated", not "not required".

### Sector freeze (decided by the user, 23 Sep 2026)
- The two sectors are **CED (Civil Engineering)** and **MTD (Metallurgical Engineering)**. This
  supersedes manual §11, which named cement and construction materials plus one electrical category.
- Reason, measured on our own catalogue: CED has the best data (79% of its current standards are
  usable, 94 QCO standards, 8.9 references each, the richest allied-standard network) and MTD is
  second (69% usable) while holding the most compulsory-certification standards of any department
  (154, of which 145 have text and labs). ETD was rejected at 36% usable.
- The two sectors interlock, which is the point: a real construction tender needs cement and
  aggregates from CED together with reinforcement bars, structural steel and tubes from MTD, so one
  tender demonstrates retrieval, allied expansion, version checking and certification across both.
- MTD has no BIS category page, so its share of the gold set must be written by hand.

### Trust over coverage (decided by the user, 19 Sep 2026)
- The prototype recommends only standards whose information is accurate and current. Where
  information is missing, the output says so explicitly; it never fills a gap with older or guessed data.
- Clause text (A2) is used only when it is the **current edition** of the standard. Older-edition text
  is not indexed and never quoted. Verified reason: archive.org has IS 269 only as 1989 and 2013; the
  2013 text covers grade 33 only, while IS 269:2015 covers 33, 43 and 53 grades, and 9 references on the
  2015 page are absent from the 2013 text.
- Text sources, in order: archive.org `gov.in.is.<number>[.<part>].<year>` items whose year equals the
  catalogue's current year (12,180 of 21,160 current standards; CED 1,536 of 1,883, ETD 664 of 1,568);
  BIS one-page summary PDFs from `summary_pdf` (1,204 current standards; always current edition);
  current editions downloaded **by hand** from the BIS store for gold-set and demo standards.
- The BIS store (`standardsbis.bsbedge.com`) is not scraped: its robots.txt disallows all automated
  access and downloads are tied to a logged-in account.
- Open: which fields must be complete for a standard to count as "accurate". BIS itself leaves
  certification and gazette lists blank for many standards, so those should be shown as
  "not stated by BIS" rather than excluding the standard. The full catalogue is still needed for
  validation (D1 existence check, C3/B4 withdrawn-citation check) even for standards not recommended.

### Open questions
- None for the A2 text source; see "Trust over coverage" above.

### Verified data (safe to cite)
- IS 269:2015 is record 111: Product Specification, Mandatory Certification, 48 labs, QCO implemented
  17-02-2003. It cites IS 4031 (Parts 1–13), IS 4032, IS 3535, IS 4905, IS 650 and IS 2580. Its
  detail page shows "Superseding IS: None", so the manual's IS 8112 → IS 269 example is unverified.
- Aspect counts across the 2,808 collected standards: Product Specification 1,467, Methods of tests
  720, Code of Practice 192, Others 139, N/A 97, Terminology 76, Safety Standard 47, Dimensions 36.
  These are the edge types C2 groups allied standards by.

## Environment

- Project folder: `D:\Standards360` (moved out of OneDrive to avoid sync locks on many small files).
- The user's terminal runs Miniconda `(base)` Python 3.14. Install dependencies with
  `python -m pip install -r requirements.txt`.
- Collector commands: `python ingest/collect.py categories | crawl --priority | crawl --recent |
  crawl --all | crawl --closure | load | stats | show "IS 269:2015"`.

## Repo layout

```
docs/                     SE lifecycle artifacts, numbered by phase
docs/artifacts/           HTML versions: build manual, concept prerequisites, team walkthrough
contracts/                Pydantic models for clauses and edges
common/is_normalizer.py   IS-number normalisation shared by A2, A3 and C3
ingest/collect.py         A1 collector
ingest/fetch_texts.py     current-edition PDFs for the frozen sectors (A2 input)
ingest/parse_clauses.py   A2 parser and clause splitter
ingest/parsing/           A2 internals: segmenter, heading detector, splitter, roles, tables
ingest/extract_refs.py    A3 cross-reference extractor
ingest/build_index.py     A4 index builder
tests/                    A2 and A3 tests
data/                     collected data, catalogue.db and data/index (git-ignored)
requirements.txt
```
