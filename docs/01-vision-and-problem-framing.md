# Phase 1 — Vision & Problem Framing

**Project:** Standards360 · **PS ID:** 26108 (DoCA, Ministry of Consumer Affairs)
**Status:** Baselined · **Timebox:** 10 days

---

## 1. One-Page Problem Statement

### 1.1 Who hurts

**Primary — the tender-drafting official.**
A procurement officer, executive engineer, or stores officer in a government department, PSU, or
municipal body. Critically: **a domain generalist, not a standards expert.** They are asked to write
a technical specification for, say, *90 W LED street luminaires, IP66* and must cite the correct
Indian Standards. To do it properly they would have to:

- select from **~22,689 standards in force** (PIB, Mar 2025) with overlapping scopes;
- follow the **normative references** listed in Clause 2 of each chosen standard — and then *their*
  references, transitively;
- confirm the **current version**, because the standard may have been revised, reaffirmed,
  amended, or withdrawn since the last tender;
- check whether the product falls under one of **187 Quality Control Orders covering 769 products**
  under compulsory certification (PIB, Mar 2025), and if so under which scheme — ISI mark, CRS
  registration, or Hallmarking.

No human does this reliably. The observed workaround is one of: copy last year's tender, ask a
colleague, search the portal by keyword, **or ask the vendor** — the last being an active
procurement-capture and bid-rigging vector.

**Secondary sufferers**

| Stakeholder | Harm |
|---|---|
| Bidders, especially MSMEs | Ambiguous or wrong specs cause bid rejection, rework, disqualification, and disputes |
| BIS | Its standards are under-cited in public procurement — the opposite of its statutory mandate |
| Citizens | Substandard goods bought with public money: unsafe electricals, failing infrastructure |
| CVC / CAG / audit | Tender re-floats, arbitration, audit paragraphs traced to defective specification |

### 1.2 Why now

1. **The compliance surface is moving faster than any human can track.** QCO coverage expanded
   sharply through 2025–26 across electricals, chemicals, aluminium, furniture, and textiles.
   A specification correct last year is wrong this year.
2. **Policy mandates standards-based specification.** GFR 2017 and the *Manual for Procurement of
   Goods, 2024* require specs to reference Indian Standards, and GeM/CPPP are now the default
   channel — so the failure is systematic and centralized, which also means a single integration
   can fix it at scale.
3. **The technology only just became adequate.** Keyword search provably fails on this corpus:
   a spec saying "cement" must disambiguate to IS 269 (OPC), IS 1489 (PPC), or IS 455 (slag)
   — the discriminating information is in the *scope* text, not the title. Multilingual semantic
   retrieval plus citation-graph traversal makes this tractable for the first time.
4. **An integration point now exists.** e-procurement portals expose the drafting step where the
   intervention belongs.

### 1.3 What "remarkable" means here

The unremarkable version of this project is a RAG chatbot over BIS PDFs. That will be built by
many teams and it does not solve the problem. Standards360 is remarkable only if it delivers these
eight properties:

| # | Property | Why it is the differentiator |
|---|---|---|
| **R1** | **Graph, not just vectors** | "Allied standards" is a *transitive closure over a typed citation graph* (normative-reference, test-method, terminology, superseded-by, amended-by). Vector similarity cannot compute it. This is the core technical claim. |
| **R2** | **Currency is a correctness property** | A withdrawn or superseded standard must be *impossible* to recommend — not merely unlikely. Version + amendment state is a hard constraint, not a display field. |
| **R3** | **Compliance overlay** | Product → QCO / CRS / Hallmarking obligation. This is what turns a search tool into a *procurement* tool. |
| **R4** | **Zero fabricated identifiers** | The LLM may only *select* from retrieved candidates; it never emits an IS number free-form. A hallucinated "IS 12345:2019" inside a live tender is a catastrophic, legally consequential failure. |
| **R5** | **Output is a paste-ready tender clause** | Not a chat reply. A specification block with standards, versions, test methods, and certification requirements, in the format the officer must actually submit. |
| **R6** | **Explainability** | "Why this standard?" with the matching scope text highlighted and linked. For a government user, trust — not accuracy — is the adoption bottleneck. |
| **R7** | **Genuinely multilingual** | Hindi and regional-language input into the same semantic space, not a translation shim. |
| **R8** | **Embeddable, not an island** | An API and a drop-in widget for GeM/CPPP, plus offline-capable demo. |

### 1.4 Non-goals (explicit, to protect the 10-day timebox)

Standards360 is **not** a tender-management system, **not** legal advice, **not** a substitute for
BIS certification or lab testing, **not** an auto-approver of specifications (human stays in the
loop and owns the decision), and does **not** cover ISO/IEC/EN standards except where an Indian
Standard normatively references them.

---

## 2. Success Metrics — defined before any code

**North Star:** *the share of tender specifications drafted with the tool that cite a **complete and
current** set of applicable standards.*

Everything below is measured against a **gold evaluation set the team builds in Phase 2**:
150–200 `(product description → correct primary IS, correct allied IS set)` pairs across the
chosen sectors. Ground truth for allied standards is cheap and objective — it is literally Clause 2
of the primary standard. Build the eval set **before** the retrieval pipeline.

### 2.1 Quality

| Metric | Target | How measured |
|---|---|---|
| Recall@10, primary standard | ≥ 0.90 | Gold set |
| Precision@3 / MRR, primary standard | ≥ 0.75 | Gold set |
| Allied-standard recall (1-hop normative refs) | ≥ 0.80 | vs. Clause 2 ground truth |
| **Version currency** | **100%** | Zero withdrawn/superseded standards ever recommended |
| **IS-number validity** | **100%** | Every emitted identifier resolves to a real catalogue record |
| QCO/CRS/Hallmarking flag | Precision ≥ 0.95, Recall ≥ 0.90 | vs. the 769-product list |
| Multilingual parity (Hindi vs. English) | Recall@10 within 5 pts | Translated subset of gold set |

The two 100% rows are **guardrails, not goals** — a release that misses them does not ship.

### 2.2 Performance

| Metric | Target |
|---|---|
| p95 end-to-end latency, short query | ≤ 3 s |
| p95 retrieval latency (pre-LLM) | ≤ 500 ms |
| p95 full tender document (≤ 20 pages) | ≤ 30 s |
| Concurrent users on demo hardware | 50 |

### 2.3 Adoption & user outcome (5–10 pilot testers, non-experts)

| Metric | Target |
|---|---|
| Task-time reduction vs. manual portal search | ≥ 70% (target ~25 min → ~5 min) |
| Task success rate, non-expert user | ≥ 90% |
| SUS usability score | ≥ 80 |
| NPS | ≥ 40 |
| **Trust rate** — recommendations accepted without external re-verification | ≥ 70% |

### 2.4 Coverage

| Metric | Target |
|---|---|
| Catalogue **metadata** indexed | ≥ 95% of ~22.7k standards |
| **Full-text** parsed (priority sectors) | 2,000–5,000 standards, 4–6 sectors |
| Citation-graph edges extracted | ≥ 25,000 typed edges |

### 2.5 Guardrails (must not regress)

- Zero redistribution of BIS full-text content.
- Zero leakage of uploaded tender documents to any retaining third party.
- Zero PII persisted from uploads.

---

## 3. Stakeholders

| Stakeholder | Role | What they need from us |
|---|---|---|
| **Procurement officer** | Primary user | Correct, current, complete, paste-ready specification — fast |
| **Indenting / technical dept.** | Reviewer, SME | Justification they can defend in a technical review |
| **Bidders & MSMEs** | Downstream consumer | Unambiguous specs that do not disqualify them arbitrarily |
| **BIS** | Data owner, domain authority | Adoption of *current* standards; respect for copyright |
| **DoCA / Min. of Consumer Affairs** | Problem sponsor, evaluator | Demonstrable reduction in defective specification |
| **GeM / NIC-CPPP** | Integration partner | A clean API and a security posture they can accept |
| **CVC / CAG** | Oversight | Auditability — why each standard was cited |
| **Testing labs & certification bodies** | Downstream | Correct scheme and test-method references |
| **SIH jury** | Immediate evaluator | A working, honest, differentiated demo in ~8 minutes |
| **Project team (6)** | Builders | A frozen scope by Day 3 |

---

## 4. Constraints

### 4.1 Legal & IP — the binding constraint

- **Copyright in every Indian Standard vests in BIS.** Full text may not be redistributed.
  → *Design consequence:* store embeddings and short scope extracts only; surface fair-use
  snippets; always deep-link to the BIS portal for the document itself.
- Full-text PDFs are downloadable **free of cost with registration** via the BIS sales portal
  (`standardsbis.bsbedge.com`). Acquisition is therefore legal but **account-bound and
  rate-limited** — honour robots.txt and ToS; no aggressive crawling.
- **Uploaded tender documents may be pre-tender confidential.** Sending them to a retaining
  third-party LLM API is unacceptable to a government customer.
  → *Design consequence:* open-weight/self-hosted model on the confidential path, or a contractual
  no-retention tier. Architect the boundary explicitly.
- **DPDP Act, 2023** applies if any personal data appears in uploads.

### 4.2 Data

- **No official public bulk/metadata API.** `standards.bis.gov.in` is JS-rendered and record URLs
  carry encrypted IDs — acquisition needs a careful, polite harvester, budgeted as real work.
- Older standards are **scanned images** → OCR in the pipeline, with a quality gate.
- **Normative references live inside the PDF** (Clause 2). The citation graph must be *extracted*,
  not downloaded. This is the highest-risk, highest-value data task.
- **Amendments are separate documents** from the base standard and must be joined.

### 4.3 Technical & hardware

- Team laptops plus free-tier cloud; **no GPU cluster**.
  → Small multilingual embedding model (e.g. BGE-M3 / multilingual-E5) that solves R7 and the
  compute budget simultaneously; CPU-friendly cross-encoder reranker; hosted LLM for *generation
  only*, never for retrieval.
- **The demo must run fully offline.** Venue connectivity failure is a routine, foreseeable risk.

### 4.4 Schedule — 10 days

The timebox forces three decisions up front:

1. **Metadata broad, full text narrow.** Index all ~22.7k records' metadata; parse full text for
   4–6 sectors only. Pick sectors with high procurement volume and clean QCO overlap — e.g.
   *electricals/LED lighting, cement & construction materials, pipes & fittings, safety PPE,
   furniture, IT hardware*.
2. **Buy/borrow everything non-differentiating.** Postgres + pgvector (or Qdrant), Neo4j or a
   Postgres recursive CTE for the graph, an off-the-shelf reranker. Build only R1–R5.
3. **Scope freeze on Day 3.** No feature added after Day 3 ships.

**Indicative plan**

| Day | Focus |
|---|---|
| 1 | Vision baselined · sector selection · data-source spike (can we actually harvest?) |
| 2 | Requirements/SRS · gold eval set started · architecture ADRs |
| 3 | **Scope freeze** · ingestion pipeline running · schema locked |
| 4–5 | Corpus + OCR + citation-graph extraction · metadata for full catalogue |
| 6–7 | Hybrid retrieval (BM25 + dense + rerank) · graph closure · QCO overlay · eval loop |
| 8 | UI, tender-clause generator, multilingual path, API |
| 9 | Hardening · offline demo package · load test · security pass |
| 10 | Eval report · pitch, demo script, dry runs |

### 4.5 Budget & team

- Budget ≈ ₹0–5,000 (free tiers + one small LLM API spend).
- Team of 6. Suggested split: 2 data/ingestion+graph, 2 retrieval/ML+eval, 1 backend/API,
  1 frontend/UX — with the eval owner distinct from the retrieval owner.

---

## 5. Top Risks

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| 1 | Harvesting BIS data is blocked or too slow | **Fatal** | Day-1 spike. Fallback: manual/curated corpus for 4 sectors, and the Internet Archive's public IS mirror for older texts |
| 2 | Citation-graph extraction from PDFs is noisy | High | Clause-2 has rigid formatting → regex + LLM validator ensemble; measure extraction F1 explicitly |
| 3 | OCR quality on scanned older standards | Medium | Restrict full-text sectors to digitally-born PDFs; degrade to metadata-only retrieval |
| 4 | Hallucinated IS numbers | **Fatal (trust)** | Constrained selection from retrieved candidate set + post-generation validation against the catalogue |
| 5 | Demo fails on venue wifi | High | Fully offline build by Day 9; pre-recorded backup video |
| 6 | Scope creep past Day 3 | High | Written scope freeze; non-goals in §1.4 are binding |

---

## 6. Exit Criteria for Phase 1

- [x] Problem statement, "remarkable" definition, and non-goals written and agreed
- [x] Success metrics quantified with measurement method, before implementation
- [x] Stakeholders and constraints identified
- [ ] Sectors selected (Day 1)
- [ ] Data-acquisition spike returns GO/NO-GO (Day 1)
