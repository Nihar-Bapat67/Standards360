# Module A3 — System Design Document (Phase 1)

**Module:** A3 — Cross-Reference Extractor  
**Author:** Senior ML / Backend Engineer  
**Date:** September 23, 2026  
**Status:** Baselined for Implementation  

---

## 1. Architectural Strategy & Scope

Module A3 extracts typed relationships between Indian Standards by reading every clause produced by A2, identifying target standard citations, normalizing identifiers, classifying the relationship type, and emitting directed edges with sentence-level evidence.

```
┌────────────────────────────────────────────────────────┐
│ Input: data/clauses.json (5,793 clauses from A2)       │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ Candidate Mention Scanner (All Clause Roles)           │
│ - Scan text with strict boundary regex (\bIS\b \d{3,5})│
│ - Capture surrounding context window (±120 chars)      │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ Filter & Normalisation Layer                           │
│ - common/is_normalizer.py: Canonicalise {fam, part, yr}│
│ - False-Positive Rejection:                            │
│   * Reflexive self-header mentions (from_is == to_is)  │
│   * Fragment numbers, page numbers, prices             │
│ - Catalogue Cross-Check (to_in_catalogue resolution)   │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ Relation Classification & Confidence Scoring           │
│ - If same family, different part -> same_family_part   │
│ - Prior: Cited standard's Aspect in catalogue.db       │
│ - Syntactic Pattern Matcher (test_method, safety, etc.)│
│ - LLM Classifier (cached, enum-constrained prompt)     │
│ - Confidence = 0.4*catalogue + 0.4*signal + 0.2*aspect │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ Output Contracts & Serialization                       │
│ - data/edges.json (Full JSON records)                  │
│ - data/edges.csv (Standard 6-column CSV for C2)        │
│ - data/a3_manifest.json (Per-standard diagnostics)     │
└────────────────────────────────────────────────────────┘
```

---

## 2. Detailed Component Design

### 2.1 Full-Corpus Scan (Every Clause Role)
Rather than restricting extraction to `references` clauses, A3 scans every clause. The clause `role` (e.g. `test_methods`, `marking`, `packing`) serves as a conditioning feature and confidence weight, not a filter.

### 2.2 Reusable Identifier Normalizer (`common/is_normalizer.py`)
Provides deterministic canonicalization across Standards360:
- Strips variable punctuation, colons, hyphens, and whitespace.
- Standardizes Part representations: `IS 10124 (PART 1)`, `IS 10124 (Part-1)`, `IS 10124 Part 1`, `IS 10124 (Part I)` $\to$ `IS 10124 (Part 1)`.
- Returns a structured dataclass:
  ```python
  class NormalizedIS:
      raw: str
      canonical: str       # 'IS 269:2015'
      family: str          # 'IS 269'
      part: Optional[str]  # '1', '2'
      year: Optional[int]  # 2015 or None (unspecified)
  ```

### 2.3 Self-Reference vs Allied Edge Handling
- When a clause in `IS 456 (Part 1)` cites `IS 456 (Part 2)`:
  - Both share the base family `IS 456`, but differ in `part`.
  - Emitted as a valid edge with relation `same_family_part`.
- When a clause in `IS 269` cites `IS 269` without part variation:
  - Classified as a reflexive self-header mention and rejected as a false positive.

### 2.4 Relation Classification & Enum Consistency
Relation types strictly match the manual's C2 traversal weights:
- `normative_reference`: General mandatory reference, materials/workmanship conformity.
- `test_method`: Method of testing, sampling, chemical/physical analysis.
- `terminology`: Definitions, symbols, glossaries.
- `safety`: Fire safety, electrical protection, structural safety.
- `installation`: Codes of practice for laying, installation, erection.
- `related_product`: Raw materials, companion products, sub-assemblies.
- `product`: Product specifications cited in guidelines/codes.
- `same_family_part`: Multipart standard sibling relations.

**Classification Architecture:**
1. **Rule/Prior Base:** Evaluates syntactic regex patterns (e.g. *"tested in accordance with..."*, *"definitions given in..."*) and combines them with the cited standard's catalogue `aspect` (e.g. `Methods of tests` $\to$ `test_method`).
2. **LLM Verification Layer:** Formulates a prompt presenting clause title, clause role, and evidence snippet. The LLM selects strictly from the closed enum.
3. **Caching:** Every call is hashed and cached in `data/a3_llm_cache.json` keyed on `(clause_id, target_is, hash(snippet))` to guarantee idempotency and zero token re-spend.

### 2.5 Confidence Scoring Formula
Each edge receives a calibrated confidence score $c \in [0.0, 1.0]$:
$$c = 0.40 \cdot s_{\text{catalogue}} + 0.40 \cdot s_{\text{syntax}} + 0.20 \cdot s_{\text{aspect}}$$
- $s_{\text{catalogue}} = 1.0$ if target exists in `catalogue.db`, else $0.5$.
- $s_{\text{syntax}} = 1.0$ for strong pattern match / strong clause role (`test_methods`, `references`), $0.8$ for standard normative requirement, $0.6$ for ambiguous prose.
- $s_{\text{aspect}} = 1.0$ if classified relation matches cited standard's catalogue aspect, else $0.7$.

### 2.6 Directionality & No Deduplication
- **Direction:** `from_is` = citing standard; `to_is` = cited standard. No direction flipping.
- **No Deduplication:** If `IS 269` cites `IS 4031` in Clause 2 and again in Clause 5.1, two separate records are emitted, each carrying its exact `clause_id` and evidence sentence. Downstream graph traversal (C2) owns graph deduplication.

