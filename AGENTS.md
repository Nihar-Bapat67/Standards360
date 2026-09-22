# Standards360 — Non-Negotiable Engineering Rules
1. **Never Invent IS Numbers**: Numbers in manual are illustrative. Never invent or hardcode standard numbers; all test/demo data must come from contract fixtures or the official catalogue.
2. **D1 Validity Guard Constraints**: Sits as the final gate after D2; inspects ONLY generated prose (never structured recommendations); validates against all ~22,689 catalogue entries; NEVER triggers a pipeline re-run.
3. **Pydantic Contracts as Single Truth**: Pydantic models in `contracts/` are the sole source of truth; every module's input and output must strictly validate against them from Day 1.
4. **API Before Web Client**: Build and freeze the D4 REST API (`POST /v1/analyze`) first; the D5 website is just another client calling this endpoint.
5. **Annexure Approach First**: Output Mode 1 (appending "Annexure — Applicable Indian Standards" to uploaded PDF) is the deliverable; in-place PDF editing is out of scope / Phase 2.
6. **Strict Scope Freeze**: Two sectors only (Cement & Construction Materials from SP 21 + one Electrical category). Explicitly DO NOT build: restrictive spec detection, reverse-ref impact analysis, live portal scraping, or model fine-tuning.
7. **Offline-First Execution**: The entire system (retrieval, IndicTrans2 translation, graph traversal, PDF generation) must run fully offline; hosted LLMs are used solely for natural phrasing.
8. **Fixed Retrieval Constants**: Dense and sparse retrieve top-25 clauses each; Reciprocal Rank Fusion constant k=60 (fixed, untunable); cross-encoder rerank pool capped at <= 25 clauses.
9. **Fixed Graph Traversal Constants**: Seed score floor = 0.80; maximum hop depth = 2 (hard cap); hop decay factor = 0.5; edges weighted by relation type.
10. **Fixed Confidence & Clarification Constants**: Confidence = 0.45*s1 + 0.20*s2 + 0.25*s3 + 0.10*s4 (starting points to tune on 50-pair gold set); Bands: High >= 0.75, Medium 0.50-0.75, Low < 0.50; B5 triggers when confidence < 0.60 OR required field missing.
11. **Zero-Tolerance Release Blockers**: Zero invented IS numbers escaping D1, and zero superseded standards recommended without replacement warning.

