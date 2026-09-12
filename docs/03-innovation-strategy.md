# Phase 2b — Innovation Strategy

**Goal:** five capabilities that move Standards360 from "a good RAG demo" to "the system BIS should deploy."

**Selection criteria.** Each innovation had to clear all five:
(a) visible in an 8-minute demo · (b) technically defensible · (c) solves real DoCA/BIS pain ·
(d) buildable in 10 days · (e) **no competing team is likely to have it.**

Prior art check (see `02-architecture-draft.md`): flat retrieval is commoditized — BIS-COMPASS
already reports Hit@3 = 100%, MRR@5 = 0.93 at 0.45 s. None of the five below compete on retrieval.

---

## I1 — Specification Gap Auditor *(invert the product)*

**Claim.** Standards360 does not primarily answer *"which standard applies?"* It answers
*"what is wrong with this tender?"* Upload a live tender; receive a findings report: missing
parameters, outdated citations, absent test methods, incomplete safety clauses.

**Why it wins.** Read the PS text literally — it says specifications *"omit relevant standards,
reference outdated versions, or include incomplete technical requirements."* Those are three
**audit findings**, not three search results. Every other team will demo a search box; we demo a
reviewer, using the judge's own uploaded document. The framing shift is the single highest-leverage
decision in this project.

**How.** Derive a required-parameter checklist from each standard's own clause tree
(`CONTAINS` edges), diff it against the requirements extracted from the tender, emit typed findings
with severity.

**Cost.** Medium. Depends on the clause segmenter, which is needed anyway.
**Demo moment.** Judge uploads any GeM tender → six concrete findings in ~20 seconds.

---

## I2 — Temporal Compliance Engine

**Claim.** Every recommendation is snapped to the current version with amendments applied, and QCO
obligation is evaluated against the **tender's own delivery timeline**, not today's date.

> *"Tender cites IS XXXX:2018. Current is IS XXXX:2025 + Amendment 1. Delivery date 15-Sep-2026
> falls after the QCO enforcement date of 01-Jul-2026 — BIS certification is mandatory for this
> award."*

**Why it wins.** This is precisely what a vector database structurally **cannot** do, and precisely
what causes real procurement disputes. Date reasoning over enforcement schedules is something no
other team will attempt. The data is authoritative (BIS lifecycle records + QCO notifications), so
it is schema and rules — not ML — and therefore cheap and verifiable.

**Cost.** Low–medium.
**Demo moment.** The version-drift warning panel, showing a real outdated citation being caught.

---

## I3 — Citation-Closure Knowledge Graph with per-clause attribution

**Claim.** Allied standards are computed as a **typed k-hop closure** over a graph derived from
Clause 2 of each standard, with every edge traceable to the clause that asserts it.

**Why it wins.** "Identify allied standards" is a literal PS requirement and is provably not
solvable by embedding similarity — a transitive closure is not a nearest-neighbour query.
Per-clause attribution simultaneously delivers the audit trail CVC/CAG would demand. Grounded in
published work: *RefWalk* citation-closure retrieval (EMNLP 2026 Findings) and multi-agent
knowledge-graph construction for regulatory QA (arXiv 2508.09893).

**Cost.** High — this is the real engineering. Reference-extraction F1 must be measured explicitly,
not assumed.
**Demo moment.** The expanding subgraph: one standard → its test-method, terminology and safety
neighbours, each edge labelled with the clause that created it.

---

## I4 — Restrictive-Specification Detector

**Claim.** Flag tenders whose parameter combination is satisfiable by implausibly few products —
the signature of a specification written around one vendor.

**Why it wins.** **No competing team will have this.** It speaks to the Ministry and to CVC, not
only to the procurement officer, converting the tool from a productivity aid into a *governance
instrument* — which is what carries a Ministry-sponsored problem statement into the finals. The
technical story is clean: compare the tender's demanded ranges against the ranges the applicable
standard actually permits, and flag over-constraint.

**Cost.** Medium. A rule-based v1 grounded in the standard's own permitted value ranges is enough.
**Demo moment.** *"3 of 9 parameters are narrower than IS permits — this combination matches an
unusually small product space."*

---

## I5 — Standards Impact Radar *(reverse references)*

**Claim.** Invert the graph. Given a standard about to be revised, show every downstream standard
and every live tender that cites it.

**Why it wins.** It serves **BIS itself**, not just the procurement officer. Demonstrating a view
of the sponsor's *own* workflow is the strongest available signal of product understanding — and it
reuses the graph already built for I3, so marginal cost is near zero.

**Cost.** Low.
**Demo moment.** *"Revising IS 456 affects 34 downstream standards and 12 live tenders."*

---

## Explicitly not counted as innovations

- **Multilingual input** — a stated PS requirement, and `bge-m3` provides it essentially for free.
  Ship it; do not pitch it as novel.
- **Hybrid retrieval + reranking** — table stakes, already public prior art. Adopt, clear the
  rubric, move on.
- **A chatbot interface.** The main screen is an analyzer, not a chat window.

## Sequencing under the 10-day timebox

| Priority | Innovation | Rationale |
|---|---|---|
| 1 | I3 — graph | Everything else depends on it; highest risk, start Day 4 |
| 2 | I2 — temporal | Cheap, authoritative, high visible payoff |
| 3 | I1 — gap auditor | Defines the demo narrative |
| 4 | I5 — impact radar | Near-free once I3 exists |
| 5 | I4 — restrictive-spec | Highest novelty, but cut first if Day 8 is tight |
