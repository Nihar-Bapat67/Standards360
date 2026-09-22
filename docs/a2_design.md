# Module A2 — System Design Document (Phase 1)

**Module:** A2 — Document Parser & Clause Splitter  
**Author:** Senior Backend & Data Engineering Engineer  
**Date:** September 22, 2026  
**Status:** Baselined for Implementation  

---

## 1. Architectural Overview & Two-Stage Pipeline

Module A2 converts heterogeneous Indian Standards PDFs into clean, structured, deterministic clause records. It implements a two-stage architecture:

```
                  ┌───────────────────────────────────────────────┐
                  │          Input PDF (Single or Compilation)     │
                  └───────────────────────┬───────────────────────┘
                                          │
                        Is compilation? (e.g. SP 21)
                                ├── Yes ──────────┐
                                │                 │
                                ▼                 ▼
                    ┌───────────────────────┐   [Single Standard PDF]
                    │ Stage (i): Segmenter  │   (Skip segmentation)
                    │ - Detect boundaries   │             │
                    │ - Cross-ref catalogue │             │
                    │ - Emit page ranges    │             │
                    └───────────┬───────────┘             │
                                └───────────┬─────────────┘
                                            ▼
                  ┌───────────────────────────────────────────────┐
                  │ Stage (ii): Clause Parser Engine              │
                  │ - Span-level typography extraction (PyMuPDF)  │
                  │ - Geometric header/footer suppression         │
                  │ - Dehyphenation & Unicode NFC normalisation   │
                  │ - Table detection -> pipe-delimited text      │
                  │ - Multi-signal heading detection & rejection  │
                  │ - Semantic role classification                │
                  │ - Granularity & max-character chunk splitting │
                  │ - Version honesty & discrepancy flags         │
                  └───────────────────────┬───────────────────────┘
                                          ▼
                  ┌───────────────────────────────────────────────┐
                  │ Output Manifest & Contracts                   │
                  │ - data/parsed/<is_id>.json                    │
                  │ - data/clauses.json (A4 input)                │
                  │ - data/parse_manifest.json                    │
                  │ - data/quarantine.json                        │
                  └───────────────────────────────────────────────┘
```

---

## 2. Detailed Technical Design Decisions

### 2.1 Compilation Segmentation vs Per-Standard Ingestion
- **Stage (i) Segmenter:** For compilation volumes (e.g. SP 21), scans all pages for boundary banners (`SUMMARY OF \n IS <number> ...` in 14 pt bold text). Computes contiguous page ranges `[start_page, end_page]`.
- **Catalogue Boundary Validation:** Every segmented standard candidate is normalized and looked up in `catalogue.db` (table `standards`). Candidates matching an active or withdrawn BIS standard proceed to parsing. Those failing validation or lacking text are routed to quarantine with explicit error categorization.
- **Per-Standard Mode:** Individual PDFs (e.g. `is269_2013.pdf`) bypass Stage (i) and map their full page range directly to their catalogue entry.

### 2.2 Span-Level Text Extraction & Typography Signals
- Extraction uses PyMuPDF `page.get_text("dict")` rather than raw text dumps.
- Every text span captures: `font` name, `size` (pt), `flags` (bold bit 4, italic bit 1), `bbox` `(x0, y0, x1, y1)`.
- Bold spans (`flags & 16` or `flags & 2` or `Bold` in font name) with font sizes >= 10.0 pt provide the primary structural candidate signals for headings.

### 2.3 Noise Suppression, Dehyphenation & Text Cleaning
- **Positional Header/Footer Stripping:**
  - Running headers (`SP 21 : 2005`, standard numbers): Lines appearing in top margin ($y < 95$ pt) repeated across multiple pages are identified geometrically and stripped.
  - Running footers (pagination such as `1.5`, `1.10`, centered or aligned at $y > 750$ pt) are stripped.
- **Dehyphenation & Line Unwrapping:**
  - Words ending with a hyphen at line-end (e.g. `struc-` \n `tural`) where the next line continues with a lowercase alpha are merged into `structural`.
  - Wrapped lines within the same paragraph block are rejoined with single spaces.
- **Unicode Normalisation:**
  - Strict **Unicode NFC** (`unicodedata.normalize('NFC', text)`).
  - Explicitly **NO NFKC**, as NFKC normalizes superscripts/subscripts (`m²` $\to$ `m2`, destroying SI unit fidelity needed for specifications).
  - Explicit ligature expansion: `ﬁ` $\to$ `fi`, `ﬂ` $\to$ `fl`, `’` $\to$ `'`, `—` $\to$ `—`, preserving mathematical signs (`±`, `°C`, `≥`, `≤`).

### 2.4 Table Detection & Formatting
- Tables are detected using PyMuPDF's built-in table finder (`page.find_tables()`).
- Cells are extracted and formatted as structured Markdown pipe-delimited tables:
  ```
  | Sl No. | Characteristic | Requirement |
  | --- | --- | --- |
  | (i) | Compressive Strength 28 days | 33 MPa |
  ```
- The owning clause retains the rendered table inline, and sets metadata flag `has_table: true`.
- Text inside tables is excluded from regular clause paragraph flow so table rows cannot be mistaken for numbered headings.

### 2.5 Multi-Signal Heading Detection & False-Positive Rejection
A candidate line is classified as a clause heading if and only if it satisfies all three gates:
1. **Gate 1 — Numbering Pattern:**
   - Matches hierarchical clause syntax: `^\d+(\.\d+)*\.?\s+` (e.g. `1`, `1.`, `2.1`, `4.2.1`) OR Annex syntax (`^ANNEX\s+[A-Z]`) OR Foreword (`^FOREWORD`).
2. **Gate 2 — Typography & Geometry:**
   - Font must be bold (`flags & 16` or `Bold` in font name) OR in uppercase letters.
   - Font size must be $\ge$ normal body text.
3. **Gate 3 — Sequence Sanity & Contextual Rejection:**
   - **Sequence sanity:** A sub-clause `4.2` can only appear if parent clause `4` or sibling `4.1` has been established. A jump like clause `1` $\to$ `43` is immediately rejected.
   - **False positive rejection:**
     - Reject lines starting with numbers that belong to specifications or quantities (e.g. `"43 grade ordinary Portland cement"`, `"28 days compressive strength"`).
     - Reject table cell contents starting with serial numbers (e.g. `1`, `2`, `(i)`, `(ii)`).
     - Reject lines whose trailing text is an unfinished sentence or lacks a heading title.

### 2.6 Semantic Clause Role Classification
Roles are determined strictly by **heading title semantics and body content**, never by hardcoding clause indices (proven necessary by Phase 0 Recon where SP 21 summaries place Requirements in Clause 2 instead of References):
- `scope`: Titles matching `SCOPE`, `FIELD OF APPLICATION`.
- `references`: Titles matching `REFERENCES`, `NORMATIVE REFERENCES`, `STANDARDS FOR REFERENCE`, or explicit reference tables.
- `terminology`: Titles matching `TERMINOLOGY`, `DEFINITIONS`, `SYMBOLS`.
- `requirements`: Titles matching `REQUIREMENTS`, `CHEMICAL REQUIREMENTS`, `PHYSICAL REQUIREMENTS`, `SPECIFICATION`, `PROPERTIES`, `RAW MATERIALS`.
- `test_methods`: Titles matching `TESTS`, `TEST METHODS`, `METHODS OF SAMPLING AND TEST`, `SAMPLING AND TESTING`.
- `sampling`: Titles matching `SAMPLING`, `LOT SIZE`.
- `marking`: Titles matching `MARKING`, `LABELLING`, `PACKING AND MARKING`.
- `packing`: Titles matching `PACKING`, `PACKAGING`, `DELIVERY`.
- `annex`: Headings matching `ANNEX\s+[A-Z]`, `APPENDIX\s+[A-Z]`.
- `foreword`: Headings matching `FOREWORD`, `PREFACE`.
- `other`: Any numbered clause not matching the above categories.

### 2.7 Granularity & Max-Clause Splitting
- **Default Rule:** One record per top-level clause (e.g. Clause 4).
- **Sub-clause Splitting:** If the total character length of a clause exceeds `MAX_CLAUSE_CHARS` (default: 3000, configurable in `config/parser_config.json`), the clause is recursively split into its distinct sub-clause records (`4.1`, `4.2`, etc.) while maintaining hierarchical `parent_clause` pointers and path traceability.
- **Inviolable Rule:** `scope` and `references` records are **always** emitted as dedicated standalone records regardless of size.

### 2.8 Version Honesty & Integrity Verification
- Document text is scanned for publication/revision year (e.g. `IS 269 : 1989`).
- Extracted year is cross-referenced with `catalogue.db`:
  - If document year matches current catalogue year $\to$ `flags: []`.
  - If document year is an older revision than the current catalogue standard $\to$ `flags: ["text_version_differs_from_current"]`.
- The system never conceals older edition text as current.

### 2.9 Determinism, Resumability & Manifest Delivery
- Output records have sorted dictionary keys and deterministic ordering.
- Resumability: Results are stored in intermediate `data/parsed/<clean_is_id>.json` before consolidation into `data/clauses.json`.
- Outputs generated:
  - `data/clauses.json`: Consolidated list of all validated clause objects.
  - `data/parse_manifest.json`: Execution log per standard including `status` (`parsed` | `quarantined`), `n_clauses`, `has_scope`, `has_references`, `text_coverage_ratio`, `sha256`.
  - `data/quarantine.json`: Quarantined standards with explicit reasons.

