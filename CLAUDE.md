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
  encrypted record IDs.
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

## Repo layout

```
docs/    SE lifecycle artifacts, numbered by phase
```
