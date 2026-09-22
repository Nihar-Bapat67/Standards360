# Module A2 — Reconnaissance Report (Phase 0)

**Module:** A2 — Document Parser & Clause Splitter  
**Author:** Senior Backend & Data Engineering Engineer  
**Date:** September 22, 2026  
**Status:** Phase 0 Recon Complete — Proceed to Phase 1 Design  

---

## 1. Analysis of `Standards360` Directory and Previous Ingest Work

The `Standards360` repository at `e:\PICT 3RD SEM\scratchpad\scratchpad\Standards360` was inspected. It contains:
- `CLAUDE.md`: System framing, hard constraints (BIS copyright, offline-first execution, strict 10-day scope), crawl status notes, and architectural decisions.
- `docs/`: Comprehensive SE lifecycle artifacts:
  - `01-vision-and-problem-framing.md`: Stakeholder pain points (tender drafting official, MSME bidders, BIS, audit), why keyword search fails, and the 7 "remarkable" properties (R1–R7).
  - `02-architecture-draft.md`: Comparison with prior art (e.g. BIS-COMPASS Hit@3 100%, MRR@5 0.93 on flat retrieval). Concludes flat RAG is table stakes; typed knowledge graph + currency/QCO reasoning is the differentiator.
  - `03-innovation-strategy.md`: Five key capabilities (Specification Gap Auditor, Temporal Compliance, Citation-Closure Graph, Restrictive-Spec Detector, Impact Radar). Note: per `AGENTS.md` and manual §11, Restrictive Spec and Impact Radar are frozen out of scope for the 10-day build.
  - `04-build-manual.md` & `docs/artifacts/*.html`: Build manual v4 text and visual HTML specifications.
- `ingest/collect.py`: The A1 Standards Data Collector implementation. Scrapes BIS "Know Your Standards" detail pages (`services.bis.gov.in`), parses basic fields, cross-references, product manuals, gazette notices, amendments, and lab lists into `data/catalogue.db`.
- `requirements.txt`: Minimal baseline dependencies (`requests`, `beautifulsoup4`).

---

## 2. Real Outputs of Module A1 (Catalogue DB Schema & Mappings)

The verified SQLite database created by A1 is located at `catalogue/catalogue.db` (29,814,784 bytes, 29.8 MB). Schema inspection via `sqlite3` reveals 7 tables:

### 2.1 Table: `standards` (35,553 rows)
Contains the authoritative metadata for all Indian Standards collected:
- `record_id` (INTEGER, Primary Key): BIS internal database ID (ranges: 1–34,300 and 65,500–67,400).
- `is_number` (TEXT): Canonical standard identifier string (e.g. `IS 269 : 2015`, `IS 383:2016`, `IS 1489 (Part 1):2015`).
- `title` (TEXT): Official standard title (e.g. `Ordinary Portland Cement ― Specification`).
- `withdrawn` (INTEGER): `0` = Active in force, `1` = Withdrawn.
- `superseded_by` (TEXT): Comma-separated IS numbers replacing this standard (e.g. `IS/ISO 603_1,IS/ISO 603_2`).
- `superseding_is` (TEXT): Free-text older standard numbers replaced by this standard.
- `qco_status` (TEXT): QCO status if notified.
- `qco_date` (TEXT): Effective implementation date of QCO.
- `summary_pdf` (TEXT): 1,405 records have a direct link to a one-page BIS summary PDF on `services.bis.gov.in/tmp/...`.
- `equivalence` (TEXT): Degree of international equivalence (`Indigenous`, `Identical`, `Modified`).
- `revisions` (TEXT): Number of revisions (e.g. `5`, `2`).
- `amendments_text` (TEXT): Number of amendments issued.
- `aspect` (TEXT): Classification aspect (`Product Specification`, `Methods of tests`, `Code of Practice`, `Terminology`, `Safety Standard`, `Dimensions`, `N/A`).
- `language` (TEXT): Publication language (`English`, `Hindi`).
- `reaffirmation_year` (TEXT): Year of latest reaffirmation.
- `department` (TEXT): Division council and department (e.g. `CED (Civil Engineering Department)`).
- `committee` (TEXT): Sectional committee code and title (e.g. `CED 02 (Cement and Concrete Sectional Committee)`).
- `group_name`, `sub_group`, `sub_sub_group` (TEXT): Technical categorization hierarchy.
- `certification` (TEXT): Certification obligation (`Mandatory Certification`, `None`, or blank).
- `n_amendments`, `n_gazette`, `n_licences`, `n_product_manuals`, `n_labs`, `n_corrigenda` (INTEGER): Relationship counts.
- `also_numbered` (TEXT): JSON array of alternative numbers.
- `international_refs_text` (TEXT): Free-text international reference citations.

### 2.2 Table: `xrefs` (165,657 rows)
- `citing_record` (INTEGER): `record_id` of the standard making the citation.
- `cited_record` (INTEGER): `record_id` of the standard being cited.

### 2.3 Other Tables
- `categories` (777 rows): Mappings from 28 BIS product categories to `record_id`, `is_number`, `product`, and `features`.
- `labs` (12,105 rows): BIS-recognized test laboratories with `name`, `city`, `state`.
- `product_manuals` (1,636 rows): BIS product manual documents.
- `gazette` (28,144 rows): Official Gazette of India notifications and S.O. numbers.
- `amendments` (4,545 rows): Issued amendments with amendment number, year, and file name.

---

## 3. SP 21 PDF Inspection & Empirical Answers

The SP 21 PDF (`sp21_2005.pdf`, 7,537,270 bytes, 929 pages) was obtained and subjected to thorough programmatic inspection using PyMuPDF (`fitz` 1.28.2).

### 2a. Text Layer Check (Digital vs Scanned)
- **Total pages:** 929 pages.
- **Pages with valid digital text layer:** 884 of 929 pages (**95.2%**).
- **Pages without text layer / scanned / blank:** 45 of 929 pages (**4.8%**).
- **Evidence:** Pages 2, 3, 4 are blank divider pages. Pages 8 and 12 are blank backings. The occasional scanned pages (e.g. pages 94, 95, 110, 111, 145) correspond to complex legacy engineering drawings or graphical charts. Over 95% of the document has crisp, selectable, searchable digital font spans.

### 2b. Compilation Structure & Boundary Marking
- **Compilation nature:** SP 21:2005 (*Handbook on Summaries of Indian Standards for Building Materials*) is a massive compilation containing **559 standard summaries** grouped into **18 distinct Sections** (Section 1: Cement and Concrete, Section 2: Building Limes, ..., Section 18: Welding Electrodes and Wires).
- **Bookmarks / Outline:** None (`doc.get_toc()` returns an empty list).
- **Table of Contents:**
  - Page 11 (printed page vii): Master table of contents listing the 18 Sections.
  - Page 14 (printed page 1.2): Section 1 Contents table listing each individual standard, title, and section-page (e.g., `IS 383 : 1970 ... Page 1.5`, `IS 269 : 1989 ... Page 1.10`).
- **Standard Boundaries:** Each standard boundary is marked unmistakably by a prominent multi-line header at the top of a page:
  ```
  SUMMARY OF
  IS <number> [ (PART <n>) ] : <year> <TITLE>
  (<Revision / Edition>)
  ```
  - `SUMMARY OF`: TimesNewRoman-Bold, 10.5 pt, centered (y ≈ 104.5).
  - `IS <number> ...`: TimesNewRoman-Bold, 14.0 pt, bold heading (y ≈ 124.7).
  - `(<Edition>)`: TimesNewRoman-Italic, 13.0 pt (y ≈ 143.6).

### 2c. Entry Depth & Clause 2 "References" Convention
**Crucial Finding:** Every entry in SP 21 is an authoritative **executive technical summary** of the standard, not an exhaustive clause-by-clause reproduction. Furthermore, **SP 21 entries do NOT follow the "Clause 2 = References" convention** that full-text standards follow!

Evidence across three distinct entries:
1. **Entry 1: IS 383 : 1970 (PDF Page 17, Section Page 1.5)**
   - *Clause 1:* `Scope — Requirements for aggregates, crushed or uncrushed...`
   - *Clause 2:* `Requirements` (2.1 Aggregates composition, 2.2 Deleterious Materials, 2.3 Aggregate crushing value).
   - *Clause 2 is NOT References.* References are cited inline within requirements (e.g., `Table 1 of the standard`).
2. **Entry 2: IS 269 : 1989 (PDF Page 22, Section Page 1.10)**
   - *Clause 1:* `Scope — Covers the manufacture and chemical and physical requirements of 33 grade ordinary Portland cement.`
   - *Clause 2:* `Chemical Requirements — When tested in accordance with the methods given in IS 4032 : 1985, 33 grade ordinary Portland cement shall comply...`
   - *Clause 2 is NOT References.* It cites the test method `IS 4032 : 1985` inline within the clause body.
3. **Entry 3: IS 1489 (Part 1) : 1991 (PDF Page 24, Section Page 1.12)**
   - *Clause 1:* `Scope — Covers the manufacture, physical and chemical requirements of Portland pozzolana cement using only fly ash pozzolana.`
   - *Clause 2:* `Raw Materials` (2.1.1 Fly ash shall conform to `IS 3812 : 1981*`, 2.2 Portland cement clinker shall conform to `IS 269 : 1989†`).
   - *Clause 2 is NOT References.* References are linked via footnotes and inline specifications.

**Implication for Downstream Modules:**
- Module A2 MUST classify clauses by **semantic role derived from the heading title and content**, NEVER by hardcoded clause number (i.e. never assume "Clause 2 == References").
- A3 must be capable of extracting references from inline mentions throughout clauses, as well as dedicated Reference annexes.

### 2d. Edition / Year Analysis (SP 21 vs A1 Catalogue)
SP 21 was finalized in 2005 and published in November 2009. The standards it contains reflect the editions in force as of December 31, 2004:
- In SP 21, Ordinary Portland Cement 33 Grade is `IS 269 : 1989 (Fourth Revision)`. In A1's catalogue, the current edition is `IS 269 : 2015 (Fifth/Sixth Revision)`.
- In SP 21, Coarse and Fine Aggregates is `IS 383 : 1970 (Second Revision)`. In A1's catalogue, the current standard is `IS 383 : 2016 (Third Revision)`.
- In SP 21, Pozzolana Cement is `IS 1489 (Part 1) : 1991 (Third Revision)`. In A1's catalogue, the current standard is `IS 1489 (Part 1) : 2015`.
- **Match Rate:** Out of 575 detected summary boundaries, **559 (97.2%)** match standards in `catalogue.db` (474 exact year matches, 85 family/part matches with newer current editions).
- **Design Requirement:** Module A2 must parse the exact year from the document text, record `text_year`, cross-reference with A1's `is_number`, and set `text_version_differs_from_current: true` when the document reflects an older edition.

### 2e. Layout Hazards Identified
1. **Running Headers:** `SP 21 : 2005` appears repeatedly at the top of pages (y ≈ 82.4 pt, font TimesNewRoman-Bold, 10.5 pt). Must be stripped by positional/frequency detection.
2. **Running Footers:** Section-page pagination (e.g. `1.5`, `1.10`, `vii`) appears at y ≈ 758–770 pt, centered or margin-aligned. Must be detected and stripped.
3. **Multi-Column Pages vs Single Column:** Section contents and introductory notes are multi-column; summary bodies are primarily full-width single column with occasional two-column requirement blocks.
4. **Tables:** Tables (e.g., `TABLE 1 CHEMICAL REQUIREMENTS...` on page 25) feature multi-line headers, cell numbers `(1)`, `(2)`, `(3)`, and fractional/scientific notations. Must be rendered cleanly as pipe-delimited text blocks with `has_table: true`.
5. **Hyphenation:** Words broken across line breaks (e.g. `wear-` \n `ing`, `con-` \n `crete`, `physi-` \n `cal`). Must be dehyphenated and joined cleanly.
6. **Ligatures and Symbols:** En-dashes (`–`), em-dashes (`—`), degree signs (`°C`), superscripts/subscripts (`m²`, `SO₃`, `C₃A`). Normalization must use **Unicode NFC** (never NFKC, which destroys `m²` into `m2` and `SO₃` into `SO3`). Explicit replacements must be provided for ligatures like `ﬁ` and `ﬂ`.

---

## 4. Comparison with Individual Per-Standard PDFs

Two individual per-standard PDFs were inspected:
1. **`is269_2013.pdf` (13 pages, Full-Text Standard):**
   - True full-text digital standard (Fifth Revision, March 2013).
   - Follows the formal BIS layout structure:
     - Page 1: Formal cover with Hindi/English titles, ICS 91.100.10, Price Group 5.
     - Page 2: Foreword with detailed revision history and committee composition.
     - Page 3+: Numbered clauses: `1 SCOPE`, `2 REFERENCES` (pointing to Annex A), `3 TERMINOLOGY`, `4 MANUFACTURE`, `5 CHEMICAL REQUIREMENTS`, `6 PHYSICAL REQUIREMENTS`, `7 STORAGE`, `8 SAMPLING`, `9 TESTS`, etc.
     - Page 8+: `ANNEX A (Clause 2) LIST OF REFERRED INDIAN STANDARDS` containing a structured table of normative references (`IS No.`, `Title`).
   - *Key difference from SP 21:* Full-text standards possess full clause hierarchies (1, 4.1, 4.2.1) and a dedicated `Clause 2 REFERENCES` citing an explicit `Annex A` table.
2. **`sum269.pdf` (1 page, BIS Portal Summary PDF):**
   - Downloaded from BIS portal `summary_pdf` URL (`services.bis.gov.in/tmp/...`).
   - Single-page Word-generated PDF containing a broad narrative overview of OPC 33, 43, 53 grades and applications.
   - Does not contain numbered technical clauses or requirement tables.

---

## 5. Verification of STOP CONDITIONS

| Stop Condition | Status | Evidence |
|---|---|---|
| 1. A1 outputs are missing or unreadable | **PASS** | `catalogue/catalogue.db` is present, verified, healthy, and populated with 35,553 standards, 165,657 cross-references, and 777 category rows. |
| 2. SP 21 is mostly scanned images | **PASS** | 884 of 929 pages (**95.2%**) have a complete digital text layer. Scanned pages are only 4.8%. |
| 3. Fewer than ~90% of expected entries match A1 catalogue rows | **PASS** | 559 entries out of 575 detected (**97.2%**) match catalogue rows. |

**Result:** All stop conditions evaluated to PASS. Phase 0 Reconnaissance is complete. Proceeding to Phase 1 Design.

