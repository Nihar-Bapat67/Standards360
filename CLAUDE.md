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

Current phase (17 Sep 2026): **Stage A, module A1 (Standards Data Collector)**.

- Done: priority crawl. `data/catalogue.db` holds 2,808 standards (724 of 725 category standards plus
  all 2,065 standards they cite), 55,100 cross-reference links, 4,516 lab rows, 433 product manuals,
  1,978 gazette notices, 961 amendments. Every standard cited by a category standard is collected.
- Next: `crawl --recent` (2026-era block), then `crawl --all` overnight, then `load`.
- After A1: choose the document-text source for A2, then A2 and A4.

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

### Open questions
- Document text for A2/A4 is not on the detail pages (no full text, no scope). Source not chosen yet.
  Proposed: archive.org items `gov.in.is*` (22,022 items, plain `.txt` per item, about 950 MB total),
  joined to the catalogue on IS number, part and year.

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
docs/               SE lifecycle artifacts, numbered by phase
docs/artifacts/     HTML versions: build manual, concept prerequisites, team walkthrough, architecture
ingest/collect.py   A1 collector
data/               collected data and catalogue.db (git-ignored)
requirements.txt
```
