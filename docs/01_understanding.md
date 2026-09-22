# Standards360 — System Understanding & Architectural Analysis

## 1. Purpose in Five Sentences
Standards360 is an automated compliance and recommendation engine designed for Indian public procurement officials drafting tenders and manufacturers verifying product statutory obligations. Users submit tender documents, technical specifications, product names, or specification screenshots in English or any of the 22 scheduled Indian languages. The system normalises and extracts structured technical requirements, checks existing citations for validity and currency, discovers primary and allied Indian Standards (IS), and determines mandatory Quality Control Orders (QCO) and testing laboratory availability. It outputs an authentic, audit-defensible deliverable: either an appended "Annexure — Applicable Indian Standards" completing an uploaded tender or a standalone compliance checklist report. By decoupling offline ingestion from an offline-capable online pipeline and enforcing a strict validity guard, the system guarantees that no fictitious or superseded standard is ever recommended.

---

## 2. Module Index (19 Modules)

| ID | Name | One-Line Job | Inputs | Outputs | Stack | Depends On | Runs Online / Offline |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **A1** | Standards Data Collector | Scrapes and ingests BIS catalogue metadata, QCO orders, lab directory, and SP 21 corpus. | BIS portal, SP 21 PDF, QCO PDFs, lab lists | Normalized catalogue records, QCO lookup, lab registry in DB | Python, httpx, BeautifulSoup/Playwright, pandas, PostgreSQL/SQLite | None (Starts Day 1) | Offline |
| **A2** | Document Parser & Clause Splitter | Parses standard PDFs and segments them into discrete numbered clauses with headings. | Standard PDFs (e.g. SP 21 / individual IS PDFs) | Structured clauses JSON (`is_number`, `clause`, `title`, `text`) | PyMuPDF, Tesseract/PaddleOCR (scanned), regex | A1 | Offline |
| **A3** | Cross-Reference Extractor | Extracts citations from Clause 2 of standards and classifies relational edge types. | Clause 2 text from A2 clauses | Typed edges (`from_is`, `relation`, `to_is`, `source_clause`) | Regex (`IS\s?\d{3,5}`), Small LLM classifier, PostgreSQL/NetworkX | A2 | Offline |
| **A4** | Index Builder | Generates dense vector embeddings and BM25 sparse indices for all parsed clauses. | `clauses.json` from A2 | `faiss.index`, `bm25.pkl`, `id_map.json` | BAAI/bge-m3, sentence-transformers, FAISS, rank_bm25 | A2 | Offline |
| **B1** | Input Handler | Ingests PDF, text, screenshot images, or product names and normalizes to text payload. | Tender PDF, image/screenshot, raw text, or product string | Normalized text payload, metadata, source type, richness flag | FastAPI, python-multipart, PyMuPDF, python-docx, Tesseract/PaddleOCR, Pillow | None | Online |
| **B2** | Language Handler | Detects input language, translates query to English, and preserves original language for replies. | Raw text from B1 | Detected language code, English translated text, reply language | langdetect/fastText, IndicTrans2 (local CPU), Sarvam Mayura API (fallback) | B1 | Online |
| **B3** | Requirement Extractor | Extracts structured product attributes, cited standards, and missing fields into schema. | English text from B2 | `RequirementObject` JSON | Regex, LLM with strict JSON schema, Pydantic | B2 | Online |
| **B4** | Citation Validator | Verifies existing tender citations for existence, currency, and domain relevance (Scenario S2). | `cited_standards` from B3, `RequirementObject` | Array of `CitationVerdict` JSON | Catalogue DB (A1), C3 (currency), C1 (relevance scoring) | B3, A1, C1, C3 | Online (Conditional: S2) |
| **B5** | Sufficiency Gate & Clarifier | Evaluates input sufficiency against required fields and confidence score, prompting for gaps. | `RequirementObject` (B3), confidence score (C5) | `SufficiencyResult` JSON (proceed or clarifying questions) | Category YAML rules, threshold logic, LLM phrasing | B3, C5 | Online (Conditional Loop) |
| **C1** | Hybrid Retrieval Engine | Executes concurrent dense and sparse searches over clauses, fuses with RRF, and reranks. | Search query constructed from `RequirementObject` | Top candidate standards with winning evidence clauses and scores | FAISS (bge-m3), rank_bm25, RRF ($k=60$), bge-reranker-v2-m3 | B3, A4 | Online |
| **C2** | Allied Standards Expander | Traverses relationship graph 2 hops outward from C1 seeds, weighting and grouping by relation type. | C1 seeds ($\ge 0.80$ score), edge table | Grouped allied standards (`test_method`, `normative`, `terminology`, etc.) | NetworkX / Recursive SQL over A3 edge table | C1, A3 | Online |
| **C3** | Version & Amendment Resolver | Resolves canonical IS identifiers, checks supersession chains, and attaches amendments. | Cited standards (B3/B4) and recommended standards (C1/C2) | Resolved current standards, typed warnings (high, med, low) | PostgreSQL/SQLite catalogue queries, Python datetime | A1, C1, B3/B4 | Online |
| **C4** | Certification & QCO Engine | Matches product category to mandatory QCO schemes, checks enforcement dates, and maps labs. | Product category from B3, persona type | Certification status, scheme (ISI/CRS), QCO citation, lab count | Catalogue DB/QCO table (A1), fuzzy category matcher, lab registry | B3, A1 | Online (Parallel with C1) |
| **C5** | Confidence Scorer | Computes calibrated confidence score and band from reranker score, runner-up margin, fields, and graph. | Top reranker score, runner-up margin, required field ratio, graph agreement | Confidence score ($0\dots 1$), band (high/med/low), drivers | Deterministic Python arithmetic, gold set calibration | C1, C2, B3 | Online |
| **D1** | Validity Guard | Sanitizes generated explanatory prose by deleting any IS number absent from the full catalogue. | Generated explanation text from D2 | Cleaned text, removed invalid IS numbers, rejection audit log | Regex extraction, full catalogue set lookup (~22,689 IS) | D2, A1 | Online |
| **D2** | Recommendation Composer | Synthesizes upstream findings into 3 cumulative citation depths and generates explanatory prose. | Outputs from B3, B4, C1–C5 | Three depth options (A: Min, B: Rec, C: Comp) with confidence, evidence, prose | Jinja2 templates, constrained LLM phrasing call | C1, C2, C3, C4, C5, B3, B4 | Online |
| **D3** | Document Generator | Renders output PDF: Mode 1 (appended Annexure to original PDF) or Mode 2 (standalone report). | Selected depth option, original file, persona, language | `completed_tender.pdf` (Annexure) or `standards_report.pdf` | HTML/CSS templates, WeasyPrint, PyMuPDF, ReportLab | D2, B1 | Online |
| **D4** | API Layer | Single REST API endpoint exposing end-to-end analysis for UI and external portals (GeM/CPPP). | HTTP POST request (JSON payload or multipart file upload) | `AnalyzeResponse` JSON | FastAPI, Pydantic, OpenAPI spec, Docker | B1–B5, C1–C5, D1–D3 | Online |
| **D5** | Web Interface | User-facing portal providing dual persona front doors, chat-style intake, findings panel, and PDF download. | User file upload, text prompt, persona selection, clarification replies | Interactive findings UI, graph visualization, PDF download | Next.js, React, Tailwind CSS, Framer Motion | D4 | Online |

---

## 3. Data Flow

### 3.1 Offline Path (Stage A $\to$ Knowledge Stores)
1. **A1 (Collect)** extracts metadata across the entire BIS catalogue (~22,689 standards), downloads QCO notifications, compiles the recognized testing laboratory registry, and pulls the SP 21 corpus (929 pages, 559 construction standards). It populates the **Catalogue DB** and the **Registry Store**.
2. **A2 (Parse)** converts standard PDFs into normalized text structures segmented into discrete numbered clauses (storing standard identifier, clause number, title, and body text).
3. **A3 (Cross-Refs)** reads Clause 2 ("References") of each parsed standard, extracts referenced IS numbers via regex, classifies the relationship type (`normative_reference`, `test_method`, `terminology`, `safety`, `installation`, `related_product`, or `superseded_by`) via a constrained LLM call, and populates the **Relationship Map / Edge Table**.
4. **A4 (Index)** encodes each clause text into dense embeddings using `bge-m3` stored in a local `faiss.index`, builds a sparse `bm25.pkl` index over the same clause tokens, and generates an `id_map.json` mapping matrix rows back to specific `(is_number, clause)` tuples.

### 3.2 Online Path (Stage B $\to$ Stage C $\to$ Stage D)
1. **B1 (Input)** accepts a tender PDF, plain text, screenshot image, or bare product name. If an image is received, OCR extracts the text. B1 outputs a normalized text payload and metadata.
2. **B2 (Language)** detects the language. If non-English (e.g., Hindi), it translates the query to English using local IndicTrans2 while storing the original language tag for localized output generation.
3. **B3 (Requirement Extractor)** parses the English text against a strict JSON schema to produce the canonical `RequirementObject` containing product name, category, attributes, pre-existing citations, and missing attributes.
4. **B4 (Citation Validator — Conditional Part 1)**: Executes **only if** `cited_standards` is non-empty (Scenario S2). It verifies each cited standard against the Catalogue DB for existence, calls C3 for currency/supersession, and invokes C1 to evaluate relevance against the extracted requirement.
5. **B5 (Sufficiency Gate — Conditional Part 2 Loop)**: Evaluates whether mandatory fields for the category are missing or if initial confidence from C5 is $< 0.60$.
   - **Loop Trigger**: If insufficient, B5 generates 1–2 specific clarifying questions in the user's language and pauses. When the user responds, the answers are merged into the `RequirementObject` at B3, and the flow re-evaluates.
   - **Pass-through**: If sufficient (or if the user explicitly overrides via `can_proceed_anyway`), the verified `RequirementObject` proceeds down the pipeline.
6. **C1 & C4 (Concurrent Execution)**:
   - **C1 (Retrieval)** builds an ordered search query (`product + grade/rating + application`), fires dense FAISS search and sparse BM25 search concurrently, fuses candidate clauses via Reciprocal Rank Fusion (RRF $k=60$), reranks the top 25 clauses using `bge-reranker-v2-m3`, and rolls up clause scores to standards by taking the **maximum** clause score.
   - **C4 (Certification)** runs concurrently with C1 using only the product category from B3, matching against the QCO lookup table, checking enforcement dates, retrieving accredited labs, and formulating persona-tailored compliance advice.
7. **C2 & C3 (Allied Expansion & Version Check)**:
   - **C2 (Allied Expansion)** takes standards from C1 scoring $\ge 0.80$ as seeds, traverses the A3 edge store up to 2 hops with a 0.5 decay penalty per hop, weights edges by relationship type, deduplicates cycles, and groups allied standards by type.
   - **C3 (Version Resolver)** normalizes all candidate and cited IS identifiers, resolves family numbers to current revisions, tracks supersession chains to their current endpoints, attaches amendments, and emits typed warnings.
8. **C5 (Confidence Scorer)** computes the final score from reranker strength, margin to runner-up, required field completeness, and graph agreement, mapping into High ($\ge 0.75$), Medium ($0.50–0.75$), or Low ($< 0.50$) bands.
9. **D1 (Validity Guard)**: Inspects the generated explanation text produced by D2's language model call and deletes any IS citation not present in the ~22,689 catalogue whitelist. It never alters structured recommendations and never triggers a pipeline re-run.
10. **D2 (Recommendation Composer)** composes the single primary recommendation into three cumulative citation depths: Depth A (Minimum / legal standard only), Depth B (Recommended / default: adds direct test methods and terminology), and Depth C (Comprehensive: adds extended installation and related product standards).
11. **D3 (Document Generator)** formats the output into a PDF in the user's language: Mode 1 appends "Annexure A — Applicable Indian Standards" to the uploaded tender, while Mode 2 produces a standalone compliance report.
12. **D4 / D5 (Delivery)**: D4 serves the response via `POST /v1/analyze`, consumed by the Next.js D5 UI or external portal integrations (GeM/CPPP).

---

## 4. Knowledge Stores

| Store Name | Physical Implementation | Contents | Writing Module(s) | Reading Module(s) |
| :--- | :--- | :--- | :--- | :--- |
| **Catalogue DB & Whitelist** | SQLite / PostgreSQL table (`catalogue.db`) | Complete metadata for all ~22,689 Indian Standards (number, title, year, status, supersession pointers, amendments, scope summary, department). | **A1** (Collect) | **B4** (existence), **C3** (version/supersession), **D1** (validity whitelist check) |
| **Relationship Map (Edges)** | SQLite / PostgreSQL table or NetworkX graph (`edges.csv`) | Directed typed edges between standards: `from_is`, `relation` (`normative_reference`, `test_method`, `terminology`, `safety`, `installation`, `related_product`, `superseded_by`), `to_is`, and `source_clause`. | **A3** (Cross-Ref Extractor) | **C2** (Allied expansion), **C5** (Graph agreement signal) |
| **Vector + BM25 Indices** | Filesystem binary files: `faiss.index`, `bm25.pkl`, `id_map.json` | 1024-dim dense embeddings (`bge-m3`) of all individual standard clauses, BM25 inverted index of clause text tokens, and integer-to-clause metadata mapping. | **A4** (Index Builder) | **C1** (Hybrid retrieval), **B4** (borrowed for citation relevance check) |
| **Registry Store (QCO & Labs)** | SQLite / PostgreSQL lookup tables | 187 Quality Control Orders covering 769 mandatory products (order number, notified date, enforcement date, certification scheme: ISI/CRS/Hallmark), plus BIS-recognized testing laboratory directory. | **A1** (Collect) | **C4** (Certification & QCO Engine) |

---

## 5. The Five Input Scenarios (S1–S5)

| Scenario | Trigger / User Input | Core Challenge | Primary Modules Carrying the Work |
| :--- | :--- | :--- | :--- |
| **S1: Baseline Blank Tender** | Tender PDF with product description and specs, but zero cited IS numbers. | No baseline citations exist; recommendation must be generated purely from technical semantics. | **B1** $\to$ **B3** $\to$ **C1–C5** $\to$ **D2, D3** |
| **S2: Guessed Standards Tender** | Tender PDF citing existing standards copied from older tenders or colleagues. | User citations may be valid, superseded, off-topic, or incomplete; each must be audited and verified. | **B1** $\to$ **B3** $\to$ **B4** (evaluates citations) $\to$ **C1–C5** $\to$ **D2, D3** |
| **S3: Unstructured Text or Image** | Specification screenshot (image) or raw pasted snippet without metadata. | Image inputs contain no extractable text stream and require OCR before NLP parsing. | **B1** (OCR extraction) $\to$ **B3** $\to$ **B5** $\to$ **C1–C5** |
| **S4: Bare Product Name / Category** | Minimal input string (e.g., "steel tubes", "LED street light") seeking standards. | Sparse context matches dozens of standards loosely; must avoid artificial overconfidence. | **B1** $\to$ **B3** $\to$ **B5** (detects missing fields) $\to$ **C1, C4** $\to$ **D2** |
| **S5: Insufficient Information** | Any input where required product attributes (grade, application, rating) are missing. | Answering blindly leads to hallucinations or incorrect recommendations; system must detect gaps and ask. | **B5** (Sufficiency Gate) $\leftrightarrow$ **C5** (Scores low) $\to$ User interactive loop $\to$ Re-run pipeline |

---

## 6. JSON Contracts Summary

### 6.1 `RequirementObject` (Produced by B3; consumed by B4, B5, C1, C4)
The structured semantic representation of the user's intent. It standardizes disparate inputs into a clean schema: the detected `product` and normalized `category` (which keys into the required-field checklist), a key-value dictionary of extracted technical `attributes` (grade, rating, application), an array of already-`cited_standards` (empty for S1), an explicit list of attributes that were `not_specified` in the source text, the user's input `language`, the `source` media type (`pdf`, `text`, `image`, `product_name`), and the contextual `richness` level (`full_tender`, `spec_only`, `name_only`).

### 6.2 `CitationVerdict` (Produced by B4; consumed by C3, D2, D4)
The audit judgment for a single standard cited in an uploaded tender. It records the original `citation` string, a boolean indicating whether the standard `exists` in the national catalogue, its currency `status` (`current`, `superseded`, `withdrawn`, or `not_found`), whether it is semantically `relevant` to the tender's product, a definitive action `verdict` (`keep`, `replace`, `remove`, or `add`), any designated `replacement` IS number, an explanatory `reason`, and an audit `severity` level (`high` for superseded, `medium` for revision drift, `low` for amendments).

### 6.3 `SufficiencyResult` (Produced by B5; consumed by D4)
The gatekeeper decision object determining whether the online pipeline can proceed to final delivery. It contains an overall `status` flag (`ok` or `need_more_info`), the evaluated `confidence` score, an array of `missing` mandatory fields for that product category, an array of structured `questions` (pairing each missing field with a user-friendly question translated into the user's language), and a boolean `can_proceed_anyway` allowing a user to bypass clarification if they choose to accept a low-confidence answer.

### 6.4 `AnalyzeResponse` (Produced by D4; consumed by Frontend D5 and External Portals)
The universal public contract of the Standards360 API. It returns an execution `status` (`complete` or `need_more_info`), any pending `questions` (if more information is required), and when complete, an array of three cumulative citation `options` (Option A "Mandatory only", Option B "Recommended" [default], and Option C "Comprehensive"), each with an assigned confidence score, confidence band, and standard array. It further includes the `allied` standards grouped by relationship type, all audit `warnings` and `CitationVerdict` entries, mandatory `certification` details (scheme, QCO reference, available lab count), clause-level `evidence` quotes justifying the primary recommendation, and the download `pdf_url`.

---

## 7. Scope Boundaries

### 7.1 What Is Being Built (10-Day Build)
- All 19 modules across Stages A, B, C, and D.
- All five input scenarios (S1–S5), including OCR for specification screenshots and the B5 clarification loop.
- Both output modes: Mode 1 (appending "Annexure — Applicable Indian Standards" to uploaded tenders) and Mode 2 (generating standalone compliance reports).
- Two specific sectors in depth: **Cement & Construction Materials** (utilizing the complete SP 21 corpus of 559 standards) plus **one Electrical category** (e.g., luminaires/cables).
- Complete catalogue metadata database for all ~22,689 Indian Standards to ensure zero-hallucination validation and supersession tracking across the entire national corpus.
- Dual stakeholder interfaces and document templates: Procurement Official and Manufacturer.
- Local offline capability for the entire pipeline (including local IndicTrans2 translation and FAISS/BM25 retrieval), with hosted LLMs reserved solely for natural phrasing.

### 7.2 What Is Phase 2 (Post-Build Roadmap)
- True in-place PDF editing and text rewriting at detected anchor points inside uploaded PDFs.
- Ingestion and full-text clause indexing of the remaining 14 BIS technical sectors.
- Full OCR pipeline for historical scanned physical standard documents outside SP 21.
- User accounts, saved tender histories, institutional workspaces, and multi-user audit logs.

### 7.3 What Is Explicitly NOT Being Built
- **Restrictive specification detection** (anti-competitive clause flagging).
- **Reverse-reference impact analysis** (analyzing how changing one standard affects all other national standards).
- **Live tender portal web-scraping** (scraping live GeM or CPPP tenders dynamically).
- **Fine-tuning of any machine learning model** (no fine-tuning of embedding, reranker, translation, or LLM models; off-the-shelf weights with prompt engineering and strict schemas only).

---

## 8. Open Questions, Ambiguities, and Contradictions

### 8.1 Discrepancy: Confidence Scores Across the Three Depths
- **Manual Citation**: 
  - §8 D2 Figure 8 and text states: *"Every depth level names IS 269:2015 as the primary, with identical confidence and identical evidence. The slider only decides how many test-method, terminology and related-product standards get cited alongside it..."*
  - §9 `AnalyzeResponse` JSON example shows:
    ```json
    { "id": "A", "label": "Mandatory only", "confidence": 0.94, "band": "high" },
    { "id": "B", "label": "Recommended",    "confidence": 0.88, "band": "high" },
    { "id": "C", "label": "Comprehensive",  "confidence": 0.71, "band": "medium" }
    ```
- **Analysis**: Figure 8 and §8 D2 argue that confidence belongs to the primary standard recommendation (which is identical across all three options). However, the API contract in §9 assigns a decreasing confidence score to broader depth tiers (likely reflecting composite certainty or lower average affinity of distant allied standards).
- **Proposed Resolution (Pending Decision)**: Adopt the Figure 8 principle as ground truth for retrieval confidence: all three options reflect the primary standard's core recommendation score (e.g. 0.87 or 0.94). If option-specific scoring is desired by the UI, Option A displays the primary standard confidence, while Options B and C compute a weighted harmonic mean incorporating decayed allied edge weights. **Marked: PENDING USER DECISION.**

### 8.2 Discrepancy: C5 Module Card Output (0.91) vs. Appendix A.5/A.6 Formula (0.87)
- **Manual Citation**:
  - §8 C5 card states:
    `Input: reranker_score: 0.94, margin_to_second: 0.15, required_fields_present: true, graph_agrees: true`
    `Output: {"score": 0.91, "band": "high", ...}`
  - §17 Appendix A.5 formula:
    $$\text{confidence} = 0.45 \cdot s_1 + 0.20 \cdot s_2 + 0.25 \cdot s_3 + 0.10 \cdot s_4$$
    where $s_2 = \min(\text{margin} / 0.30, 1) = \min(0.15 / 0.30, 1) = 0.50$, $s_3 = 1.0$, $s_4 = 1.0$.
  - §17 Appendix A.6 calculates:
    $$0.45(0.94) + 0.20(0.50) + 0.25(1.00) + 0.10(1.00) = 0.423 + 0.100 + 0.250 + 0.100 = 0.873 \to 0.87$$
- **Analysis**: The C5 module card displays 0.91, whereas the exact arithmetic specified in Appendix A.5 and calculated in A.6 yields 0.87. (A score of 0.91 would only result if $s_2 = 0.70$ or if different component weights were used).
- **Proposed Resolution (Pending Decision)**: Treat Appendix A.5 and A.6 as the authoritative mathematical specification ($0.87$). The C5 card's "0.91" is an uncalibrated illustrative placeholder. **Marked: PENDING USER DECISION.**

### 8.3 Discrepancy: Number of Knowledge Stores (Three vs. Four)
- **Manual Citation**:
  - §1 Figure 1 and text states: *"They meet only at the three stores — which is also what makes an offline demo possible."* (Catalogue DB, Relationship Map, Vector + BM25).
  - §18 Appendix B Figure 9 and text states: *"The online and offline halves share no code path and meet only at the four stores... KNOWLEDGE STORES: CATALOGUE (+ whitelist), EDGES, VECTOR + BM25, REGISTRY (QCO · labs)"*.
- **Analysis**: Section 1 omitted the QCO and Laboratory registry as a distinct store or folded it into Catalogue DB, whereas Architecture Appendix B explicitly enumerates four independent stores.
- **Proposed Resolution (Pending Decision)**: Standardize on **four knowledge stores** as defined in Appendix B: (1) Catalogue DB + Whitelist, (2) Relationship Map / Edges, (3) Vector + BM25 Clause Index, and (4) Registry Store (QCO orders and accredited lab directory). **Marked: PENDING USER DECISION.**

### 8.4 Discrepancy: Standards Listed in Option C (Figure 8 vs. §9 Contract)
- **Manual Citation**:
  - §8 D2 Figure 8 lists Depth C "Comprehensive" as containing 6 standards: `IS 269:2015, IS 4031, IS 4032, IS 3535, IS 456, IS 1489`.
  - §9 `AnalyzeResponse` example lists Option C as containing 5 standards: `["IS 269:2015", "IS 4031", "IS 4032", "IS 3535", "IS 456:2000"]` (omitting `IS 1489`, although `IS 1489` appears under `"allied": {"related_product": ["IS 1489"]}`).
- **Analysis**: The contract fixture omitted `IS 1489` from Option C's list despite Figure 8 including it as an allied related-product standard.
- **Proposed Resolution (Pending Decision)**: Option C in test fixtures and runtime should include all traversed allied standards up to the depth cutoff, including `IS 1489`. **Marked: PENDING USER DECISION.**

### 8.5 Ambiguity: Directionality of Graph Traversal in C2
- **Manual Citation**:
  - §8 Figure 7 shows `IS 456:2000 →product→ IS 269` (an edge directed *into* IS 269).
  - §17 A.2 C2.2 states: `SELECT to_is, relation, source_clause FROM edges WHERE from_is = 'IS 269:2015'`.
  - §17 A.6 C5 states: `s4 = 1 (IS 456 appears in both C1's list and C2's expansion)`.
- **Analysis**: If C2 only queries `WHERE from_is = 'IS 269:2015'` (outgoing edges from Clause 2 of IS 269), it will find IS 4031, 4032, 3535, and 1489. It will *not* find IS 456 unless IS 269 also cites IS 456, or unless the graph query traverses bidirectional/undirected edges or checks reverse edges (`WHERE to_is = 'IS 269:2015'`).
- **Proposed Resolution (Pending Decision)**: C2 should query outgoing edges from seeds, but also inspect incoming edges with relation `product` or `normative_reference`, or treat reference links as an undirected graph with relation-dependent penalties. **Marked: PENDING USER DECISION.**

---

## 9. Self-Check (Comprehension Proof)

### a. Why does C4 start at the same time as C1?
C4 evaluates Quality Control Orders and mandatory certification requirements, which depend strictly on the statutory product category already extracted by B3 (e.g., "cement"), completely independent of retrieval text matching. Because C4 requires only a fast table lookup ($< 20\text{ ms}$) while C1's hybrid search and reranking takes $400\text{–}900\text{ ms}$, running them concurrently allows certification facts and accredited lab counts to be ready long before candidate standards are retrieved, saving hundreds of milliseconds for free (§17 A.0).

### b. Why must D1 validate against all ~22,689 catalogue entries, not just the standards we hold full text for?
The system indexes full text for only two target sectors during this build, but tenders routinely make cross-sector citations (such as structural steel or testing instruments) that fall outside those two sectors (§8 D1, §11). If D1 only checked against the subset of standards held in full text, genuine, active Indian Standards outside our ingested sectors would be falsely flagged as hallucinations and deleted from valid explanations.

### c. Why is "three depths" in D2 not "three competing answers"?
Every depth option (Minimum, Recommended, Comprehensive) recommends the exact same primary standard (e.g., IS 269:2015) based on the same evidence and single retrieval pass (§8 D2, Figure 8). The three depths represent policy choices regarding citation breadth—ranging from legal minimums to full test methods and installation codes based on tender risk and value—rather than competing algorithmic guesses.

### d. Why does C1 search clauses instead of whole standards, and why roll up by max, not mean?
A standard's specific scope and product applicability are concentrated in dedicated clauses (such as Clause 1 Scope), which get diluted and lost if compressed into a whole-document embedding (§17 A.1). Scores are rolled up by maximum rather than mean because an ideal standard may possess one perfectly matching scope clause alongside dozens of irrelevant specialized test procedures; averaging would unfairly penalize comprehensive standards.

### e. Why does a missing year in a citation mean "current version" in C3?
In Indian procurement and legal contracting conventions, citing a bare standard family number (e.g., "IS 269" without ":2015") signifies that the contractor or supplier must adhere to whichever edition is legally in force and current at the time of execution (§17 A.3). Treating an omitted year as an error or defaulting to an obsolete first edition would contradict standard administrative practice.

### f. What is the only genuine loop in the system, and when does it fire?
The only genuine feedback loop exists at module B5 (Sufficiency Gate), where control returns to the user via the conversational interface to ask targeted clarifying questions (§7 Figure 6). It fires only in Scenario S5, when either mandatory attributes for the category are missing from the input or C5's calculated confidence score falls below the $0.60$ threshold.

