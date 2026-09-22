# Standards360 — Dependency-Ordered 10-Day Build Plan

This document establishes the strict task sequencing, module ownership, concurrency opportunities, and blocking relationships across the 10-day build. It enforces the manual's non-negotiable directive: contracts and data proof first, evaluation harness before retrieval code, API before website, and zero new code on Day 10.

---

## 1. Ownership & Team Allocation

- **Developer 1 (Data & Graph)**: A1, A2, A3, A4. (Inherits **C2** on Day 5).
- **Person 1 (ML / Intake)**: B1, B2, B3, multilingual evaluation.
- **Person 2 (ML / Retrieval & Eval)**: C1, evaluation harness, 50-pair gold set, C5 calibration.
- **Person 3 (AI / Logic & Reasoning)**: B4, B5, C3, C4, C5, D1, D2. (Initiates C2 and D3; offloads C2 to Dev 1 and D3 to Dev 2 on Day 5).
- **Developer 2 (API, UI & Delivery)**: D4, D5. (Inherits **D3** on Day 5).

---

## 2. Dependency-Ordered Task Schedule

```
[Day 1: Contracts + Fixtures + Data Proof]
       │
       ├─────────────────────────┬─────────────────────────┬─────────────────────────┐
       ▼                         ▼                         ▼                         ▼
Task 1.1: Pydantic Contracts  Task 1.2: A1/A2 Data Proof  Task 1.3: 50-Pair Gold Set Task 1.4: Mock D4 API
(Single truth: §9)            (SP 21 PDF + Clause 2)      (Written by hand)          (POST /v1/analyze mock)
       │                         │                         │                         │
       ├─────────────────────────┼─────────────────────────┘                         ▼
       ▼                         ▼                                            Task 1.5: D5 UI Shell
Task 2.1: B3 Schema Valid.    Task 2.2: A1 Catalogue DB                              (Dual persona entry)
(5 real tenders + screenshot) (Ingest ~22,689 metadata)
                                 │
                                 ▼
                              Task 3.1: A3 Ref Extractor ──► Task 3.2: A4 Index Builder
                              (Clause 2 typed edges)          (Dense FAISS + BM25)
                                 │                                   │
                                 │                                   ▼
                                 │                            Task 4.1: C1 Hybrid Engine
                                 │                            (RRF k=60 + bge-reranker)
                                 │                                   │
                                 ├───────────────────────────────────┤
                                 ▼                                   ▼
                              Task 5.1: C2 Allied Expander    Task 5.2: C3 Version Resolver
                              (2-hop traversal, decay 0.5)    (Supersession & amendments)
                                 │                                   │
                                 └─────────────────┬─────────────────┘
                                                   ▼
                                              Task 6.1: C5 Confidence Scorer
                                              (4 signals: s1, s2, s3, s4)
                                                   │
                                                   ▼
                                              Task 6.2: B5 Sufficiency Gate
                                              (Category rules + clarification loop)
                                                   │
                                                   ▼
                                              Task 7.1: D1 Validity Guard
                                              (Catalogue whitelist regex gate)
                                                   │
                                                   ▼
                                              Task 7.2: D2 Recommendation Composer
                                              (Three cumulative depth options)
                                                   │
                                                   ▼
                                              Task 8.1: D3 Document Generator
                                              (Mode 1 Annexure + Mode 2 Report)
                                                   │
                                                   ▼
                                              [Days 9–10: Hardening, Eval & Demo]
```

---

## 3. Detailed Daily Task Breakdown

### Days 1–2: Contracts, Ground Truth & Pipeline Skeleton

#### Task 1.1: Freeze Pydantic Contracts & Fake Fixtures
- **Owner**: Person 3 & Developer 2
- **Action**: Implement Pydantic models in `contracts/` for `RequirementObject`, `CitationVerdict`, `SufficiencyResult`, and `AnalyzeResponse`. Commit static JSON fixtures matching §9.
- **Can run in parallel with**: Tasks 1.2, 1.3.
- **Blocks**: Tasks 1.4, 2.1, 2.2, 4.1, 7.2.

#### Task 1.2: Prove the Ingestion Pipeline (Data Spike)
- **Owner**: Developer 1
- **Action**: Execute end-to-end spike on SP 21: parse PDF, split into clauses (A2), extract Clause 2 references (A3), and write 1 standard row with edges to SQLite.
- **Can run in parallel with**: Tasks 1.1, 1.3, 1.4.
- **Blocks**: Tasks 2.2, 3.1.

#### Task 1.3: Build Hand-Crafted 50-Pair Gold Test Set
- **Owner**: Person 2
- **Action**: Author `eval/gold_set.json` with 50 diverse product description $\to$ correct primary IS pairs across cement, construction, and electrical sectors before writing retrieval code.
- **Can run in parallel with**: Tasks 1.1, 1.2, 1.4.
- **Blocks**: Tasks 4.2 (Retrieval Eval), 6.1 (Confidence Calibration).

#### Task 1.4: Scaffold Mock D4 REST API
- **Owner**: Developer 2
- **Action**: Implement FastAPI endpoint `POST /v1/analyze` returning hard-coded fake JSON validated against `AnalyzeResponse`.
- **Can run in parallel with**: Tasks 1.2, 1.3.
- **Blocks**: Task 1.5.

#### Task 1.5: Scaffold D5 Web Interface Shell
- **Owner**: Developer 2
- **Action**: Create Next.js application with dual persona front doors ("Drafting Tender" vs. "Manufacturing Product") and file dropzone, bound to the mock API.
- **Can run in parallel with**: Tasks 2.1, 2.2.
- **Blocks**: Tasks 3.5, 8.2.

#### Task 2.1: Validate B3 Requirement Schema on Real Tenders
- **Owner**: Person 1
- **Action**: Build prompt and JSON schema validation for B3; test on 5 real tender excerpts (including 1 Hindi text and 1 screenshot specification).
- **Can run in parallel with**: Tasks 2.2, 1.5.
- **Blocks**: Tasks 3.3, 3.4.

#### Task 2.2: Ingest Full National Catalogue Metadata (A1)
- **Owner**: Developer 1
- **Action**: Collect and populate `data/catalogue.db` with metadata for all ~22,689 Indian Standards (numbers, titles, status, supersessions, amendments, dates).
- **Can run in parallel with**: Tasks 2.1, 1.3, 1.5.
- **Blocks**: Tasks 5.2 (C3 Version), 7.1 (D1 Validity Guard).

---

### Day 3: Intake Handling & Scope Freeze

#### Task 3.0: Formal Scope Freeze
- **Owner**: All Team Members
- **Action**: Formally freeze scope strictly to 2 sectors (Cement/Construction via SP 21 + 1 Electrical category); lock "Not Building" register (§11).
- **Blocks**: Any feature creep.

#### Task 3.1: Build A3 Cross-Reference Extractor
- **Owner**: Developer 1
- **Action**: Parse Clause 2 of ingested standards via regex, classify relation types via constrained LLM prompt, and write `data/edges.csv` (from, relation, to, clause). Benchmark F1 on 20 hand-labelled standards (target $>0.85$).
- **Can run in parallel with**: Tasks 3.3, 3.4.
- **Blocks**: Task 5.1 (C2 Allied Expansion).

#### Task 3.2: Ingest SP 21 Clause Collection (A2)
- **Owner**: Developer 1
- **Action**: Run clause splitter on all 559 standards in SP 21, generating `clauses.json` with numbered clauses and section headings.
- **Can run in parallel with**: Tasks 3.3, 3.4.
- **Blocks**: Task 4.0 (A4 Indexing).

#### Task 3.3: Implement B1 Input Handler & OCR
- **Owner**: Person 1
- **Action**: Ingest PDF (PyMuPDF), DOCX, raw text, and images (Tesseract/PaddleOCR), outputting normalized text payload and metadata.
- **Can run in parallel with**: Tasks 3.1, 3.2.
- **Blocks**: Task 3.4.

#### Task 3.4: Implement B2 Language Handler
- **Owner**: Person 1
- **Action**: Integrate IndicTrans2 (local CPU) to detect language and translate to English; configure Sarvam Mayura fallback; retain original language tag.
- **Can run in parallel with**: Tasks 3.1, 3.2.
- **Blocks**: Task 3.5.

#### Task 3.5: Connect B1–B3 Intake to Chat Interface
- **Owner**: Person 1 & Developer 2
- **Action**: Enable file drop and text submission in D5 web UI, returning parsed requirement facts and display text back to user.
- **Can run in parallel with**: Task 4.0.
- **Blocks**: Task 6.3.

---

### Days 4–5: Retrieval, Core Verification & Workload Rebalance

#### Task 4.0: Build A4 Vector & BM25 Indices
- **Owner**: Developer 1
- **Action**: Embed clauses using `BAAI/bge-m3` into FAISS (`faiss.index`) and tokenize clauses for BM25 (`bm25.pkl`); emit `id_map.json`.
- **Can run in parallel with**: Tasks 4.3, 4.4.
- **Blocks**: Task 4.1.

#### Task 4.1: Implement C1 Hybrid Retrieval Engine
- **Owner**: Person 2
- **Action**: Construct ordered query from `RequirementObject`; execute concurrent dense (FAISS) and sparse (BM25) searches for top-25 clauses; fuse with RRF ($k=60$); rerank top 25 clauses with `bge-reranker-v2-m3`; roll up by maximum clause score.
- **Can run in parallel with**: Tasks 4.3, 4.4.
- **Blocks**: Tasks 4.2, 5.1, 6.1.

#### Task 4.2: Benchmark C1 Retrieval Against Gold Set
- **Owner**: Person 2
- **Action**: Run `eval/run_eval.py` over the 50-pair gold set. Measure and verify Hit@3 ($>85\%$) and MRR@5 ($>0.75$).
- **Can run in parallel with**: Tasks 4.3, 4.4, 4.5.
- **Blocks**: Task 6.1.

#### Task 4.3: Implement C4 Certification & QCO Engine
- **Owner**: Person 3
- **Action**: Load 187 QCOs covering 769 products; implement fuzzy product category matching; evaluate enforcement dates; query accredited testing laboratories; generate persona-specific advice.
- **Can run in parallel with**: Tasks 4.0, 4.1 (starts concurrently with C1).
- **Blocks**: Task 7.2 (D2 Composer).

#### Task 4.4: Implement C3 Version & Amendment Resolver
- **Owner**: Person 3
- **Action**: Canonicalize IS numbers; resolve current editions; traverse supersession chains to active endpoints; attach amendments; emit typed warnings (high/med/low).
- **Can run in parallel with**: Tasks 4.0, 4.1, 4.3.
- **Blocks**: Tasks 4.5, 7.2.

#### Task 4.5: Implement B4 Citation Validator (Scenario S2)
- **Owner**: Person 3
- **Action**: Audit cited standards in `RequirementObject`: verify existence via Catalogue DB, currency via C3, and relevance by scoring cited standards against requirements using C1.
- **Can run in parallel with**: Task 4.2.
- **Blocks**: Task 7.2.

#### Task 4.6: Planned Day 5 Workload Rebalance
- **Action**: Transfer **C2 (Allied Standards Expander)** to Developer 1. Transfer **D3 (Document Generator)** to Developer 2. Person 3 retains B4, B5, C3, C4, C5, D1, D2.

---

### Days 6–7: Reasoning, Clarification & Delivery Logic

#### Task 5.1: Implement C2 Allied Standards Expander
- **Owner**: Developer 1 (Rebalanced)
- **Action**: Filter C1 candidates with score $\ge 0.80$ as seeds; traverse edge table outward 2 hops with 0.5 decay penalty; apply relation weights; deduplicate paths; prevent graph cycles; group by relation type. Measure 1-hop allied recall ($>80\%$).
- **Can run in parallel with**: Tasks 5.2, 6.1.
- **Blocks**: Tasks 6.1, 7.2.

#### Task 6.1: Implement C5 Confidence Scorer & Formula Calibration
- **Owner**: Person 3 & Person 2
- **Action**: Compute $s_1$ (reranker score), $s_2$ (runner-up margin normalized by 0.30), $s_3$ (required field ratio), $s_4$ (graph agreement). Calculate confidence score via linear formula and assign High ($\ge 0.75$), Med ($0.50\text{–}0.75$), Low ($<0.50$) bands. Tune starting weights on gold set.
- **Can run in parallel with**: Task 7.1.
- **Blocks**: Tasks 6.2, 7.2.

#### Task 6.2: Implement B5 Sufficiency Gate & Clarification Loop (Scenario S5)
- **Owner**: Person 3
- **Action**: Build per-category required fields table (`required_fields.yaml`); check completeness and verify if confidence $<0.60$; trigger natural clarifying questions; merge user replies into B3 and re-score.
- **Can run in parallel with**: Task 7.1.
- **Blocks**: Task 7.2.

#### Task 7.1: Implement D1 Validity Guard
- **Owner**: Person 3
- **Action**: Implement regex extraction and set lookup against the full ~22,689 catalogue whitelist. Strip unverified standard numbers from generated prose; record rejection logs; enforce zero tolerance; forbid pipeline re-runs.
- **Can run in parallel with**: Tasks 6.1, 6.2.
- **Blocks**: Tasks 7.2, 8.1.

#### Task 7.2: Implement D2 Recommendation Composer
- **Owner**: Person 3
- **Action**: Assemble C1 primary standard and C2 allied standards into 3 cumulative citation depths (A: Minimum, B: Recommended [default], C: Comprehensive). Generate constrained explanatory prose and run through D1.
- **Can run in parallel with**: Task 8.0.
- **Blocks**: Tasks 8.1, 8.2.

---

### Day 8: Document Generation, Multi-Persona & End-to-End Dry Run

#### Task 8.0: Scaffold HTML Document Templates
- **Owner**: Developer 2 (Rebalanced)
- **Action**: Create HTML/CSS templates for Mode 1 ("Annexure — Applicable Indian Standards" with evidence and warnings) and Mode 2 (Standalone Compliance Report).
- **Can run in parallel with**: Task 7.2.
- **Blocks**: Task 8.1.

#### Task 8.1: Implement D3 Document Generator
- **Owner**: Developer 2 (Rebalanced)
- **Action**: Render templates to PDF via WeasyPrint. For Mode 1, append the generated Annexure to the uploaded tender PDF using PyMuPDF. Support localized Hindi/English rendering.
- **Can run in parallel with**: Task 8.2.
- **Blocks**: Task 8.4.

#### Task 8.2: Connect D4 API & D5 Frontend to Full Pipeline
- **Owner**: Developer 2
- **Action**: Wire D4 endpoint to complete pipeline; render interactive findings screen, graph visualization, confidence pills, and download triggers.
- **Can run in parallel with**: Task 8.1.
- **Blocks**: Task 8.4.

#### Task 8.3: Multilingual & Persona Verification
- **Owner**: Person 1
- **Action**: Verify Hindi $\to$ English retrieval parity across 20 translated gold queries (within 5 points of Hit@3). Verify manufacturer persona checklist and lab outputs.
- **Can run in parallel with**: Tasks 8.1, 8.2.
- **Blocks**: Task 8.4.

#### Task 8.4: Day 8 First Full Dry Run
- **Owner**: All Team Members
- **Action**: Execute end-to-end runs across S1, S2, S3, S4, and S5. Verify execution times, PDF layout, and error-handling paths.

---

### Day 9: Hardening, Benchmarking & Scenario Rehearsal

#### Task 9.1: Offline Packaging & Network Isolation Test
- **Owner**: Developer 1 & Developer 2
- **Action**: Disconnect external network. Verify that IndicTrans2, FAISS, BM25, SQLite, and WeasyPrint execute completely offline.
- **Blocks**: Task 9.3.

#### Task 9.2: Comprehensive Benchmark Audit
- **Owner**: Person 2 & Person 3
- **Action**: Run evaluation suite and document final figures:
  - Hit@3 ($>85\%$), MRR@5 ($>0.75$).
  - 1-hop allied recall ($>80\%$), Clause 2 extraction F1 ($>0.85$).
  - High-confidence band calibration ($\ge 90\%$).
  - Zero invented IS numbers (D1 log audit — release blocker).
  - Zero superseded IS recommended without warning (release blocker).
  - Latency p95: $<5\text{ s}$ for text/analysis, $<30\text{ s}$ for PDF generation.
- **Blocks**: Task 9.3.

#### Task 9.3: Rehearse All Five Scenarios (S1–S5)
- **Owner**: All Team Members
- **Action**: Walk through all 5 scripted scenarios:
  1. *S1*: Blank tender PDF $\to$ fresh recommendation + Annexure.
  2. *S2*: Tender with outdated IS 8112 $\to$ supersession warning + IS 269 replacement.
  3. *S3*: Specification screenshot $\to$ OCR $\to$ standard extraction.
  4. *S4*: Bare product name "steel tubes" $\to$ low confidence + category matching.
  5. *S5*: Thin requirement $\to$ B5 clarification prompt $\to$ answer merge $\to$ confidence upgrade ($0.38 \to 0.87$).

---

### Day 10: Demo Script, Backup Recording & Code Freeze

#### Task 10.1: Strict Code Freeze
- **Owner**: All Team Members
- **Action**: Enforce total code freeze. No commits to codebase or configuration.

#### Task 10.2: Demo Rehearsals & Backup Recording
- **Owner**: All Team Members
- **Action**: Complete 3 timed live demo rehearsals (under 90 seconds per flow). Record a comprehensive high-definition backup screencast covering all five scenarios in case of venue failure.

