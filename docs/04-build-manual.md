# Standards360 Build Manual

*PS 26108 · Department of Consumer Affairs · build manual v4*

*Text version of `docs/artifacts/build-manual.html`. Figures are described in words here; the drawings are in the HTML file. Where this manual and the implementation decisions in `CLAUDE.md` disagree, the decisions in `CLAUDE.md` are current.*

Nineteen modules, seven diagrams, what each part eats and produces, who builds it, and what we are not building. Read once, then use it to hand out tasks.

## §1 Read this first

> **WARNING:** Every IS number in this document is an **illustration of the shape of the data**, not a verified fact. Before any of these appear in a demo, look each one up on the BIS portal and confirm the number, year and status. The whole product is a promise that we do not invent standard numbers — that promise starts with this document.

### What A1, B3, C2 mean

Each module has a letter and a number. **The letter is the stage of the assembly line**; the number is only its position inside that stage. Work flows A → B → C → D. So `C3` is "the third module in the find-and-check stage" — the version resolver. `B5` is "the fifth module in the understand stage" — the one that asks clarifying questions. Modules with a blue tag are new since v1.

**Figure 1 — the four stages.**

Diagram: Stage A runs offline and writes four kinds of knowledge into three stores. Stages B, C and D run online per request and read from those same stores.

The split that matters: stage A can re-collect and re-index the whole corpus without B, C or D knowing, and B, C and D answer queries with no live dependency on the BIS website. They meet only at the three stores — which is also what makes an offline demo possible. Blue marks the relationship map and the module that builds it; that pairing is the part no competing system has.

## §2 Two stakeholders, two front doors

*The same engine answers two different people asking two different questions. This is a presentation difference, not an architecture difference — one API, two interfaces, two document templates.*

|  | Procurement official | Manufacturer |
|---|---|---|
| Their question | "Which standards must I cite in this tender?" | "Which standards must my product comply with?" |
| What they upload | A tender document, often partly drafted | A product description or category |
| Certification answer | "Bidders must hold a valid ISI licence — state it as an eligibility condition" | "**You** must obtain a BIS licence before you can sell this; here is the scheme and the labs" |
| Document they get | Completed tender, or a standards annexure | A compliance checklist — standards, tests, licence route, labs |
| What they care about | Completeness and currency of citations; defensibility in audit | Obligations, cost of compliance, which lab, how long |

**Figure 2 — two personas, one engine.**

Diagram: Two personas enter through separate front doors, share the identical understand and find-and-check stages, then diverge again into two different document templates.

The divergence is entirely at the two ends. Everything expensive — nineteen modules minus two templates — is shared, which is why the manufacturer side costs roughly one extra day once the procurement side is finished. Build them in sequence, never in parallel.

## §3 The five ways input arrives

*These are the real situations the system must survive. Every one routes through the same pipeline — what changes is which modules do the heavy lifting.*

| # | Situation | What makes it hard | Modules doing the work |
|---|---|---|---|
| S1 | Tender PDF uploaded. Has product description and technical specification, but **no Indian Standards at all** | Nothing to check against — we recommend from scratch. The baseline case | B1 B3 → C1–C5 → D2 D3 |
| S2 | Tender PDF uploaded **with standards the official already guessed** — from colleagues, seniors, or last year's tender | Their guesses may be right, outdated, irrelevant or incomplete. We must judge each one, not ignore them | B1 B3 **B4** → C1–C5 → D2 D3 |
| S3 | No document — just pasted text, or **a screenshot** of a specification | A screenshot is an image. It needs OCR before anything else can happen | B1 **(OCR)** B3 **B5** → C… |
| S4 | Just a **product name or category** — "steel tubes", "LED street light". Pure information-seeking | Almost no detail. Many standards match loosely. Must not pretend to be confident | B1 B3 **B5** → C1 C4 → D2 |
| S5 | Any of the above, but **the information is too thin to be confident** | Guessing here is the worst possible failure. The system must notice, work out what is missing, and ask | **B5** + **C5**, then re-run |

**Figure 3 — the online request path.**

Diagram: A vertical pipeline from input through language, extraction, citation validation, the sufficiency gate, the find-and-check core, the validity guard, option building and PDF generation. The sufficiency gate can loop back to extraction when the user answers a question.

One path, two conditional parts. B4 runs only when the tender already cites standards; B5 either lets the request through or bounces it back to B3 with the user's answer merged in. Everything below B5 sees a requirement object it can trust, which is why no module after this point ever has to guess.

> **NOTE:** **S2 is the most valuable scenario and the best demo.** It is also how procurement actually works today — officials copy standards from old tenders or ask a senior. Telling someone "three of your five citations are fine, one is superseded, one belongs to a different product, and you are missing two test-method standards" is far more impressive than answering a blank query, because it shows the system *reasoning about their work* rather than doing a search.

### On the chat interface

Earlier I advised against building a chatbot. The refined position, given your scenarios: **conversation is the right shape for intake and clarification; it is the wrong shape for the answer.** The user drops a file into something that looks like a chat, the system asks two or three clarifying questions, the user answers — and then the system produces a **document**, not a paragraph. Conversation in, document out. That is not a chatbot; it is an intake interview that terminates in a deliverable.

## §4 The two ways output leaves

*The main deliverable is a PDF. Which PDF depends on what the user wants done to their document.*

**Figure 4 — output modes.**

Diagram: Three options from D2 go to the user, who chooses between filling their own tender or receiving a separate report. Each choice routes to a different mode of the document generator.

Both modes consume exactly the same option object from D2 — the only difference is the template and whether the user's original file is carried through. Mode 1 is drawn in blue because the annexure approach is the deliberate simplification described below.

> **WARNING:** **Be realistic about O1.** Editing an arbitrary third-party PDF in place is genuinely fragile — layouts vary, text may be scanned, and a botched insertion looks worse than no insertion. Build the robust path first: generate an **"Annexure — Applicable Indian Standards"** appended to their original document. That is how government tenders actually carry this information, so it is authentic rather than a workaround. In-place insertion at a located anchor is the enhancement, not the foundation.

## §5 Does this cover the requirements?

| Requirement | Module | How it is satisfied | Status |
|---|---|---|---|
| Recommend standards + allied + normative | C1 C2 | C1 finds the primary by meaning; C2 walks the cross-reference map from A3 to pull normative, test-method, terminology, safety and installation standards | In scope |
| Integratable with portals | D4 | REST API first, website second. The website is just our own client of the same endpoint GeM or CPPP would call | In scope |
| Two stakeholder interfaces | D5 | One engine, two entry modes and two document templates | In scope |
| Accept PDF / text / screenshot / product name | B1 B3 | Four input types normalised to one text payload, then structured. Screenshot handled by OCR inside B1 | In scope |
| Semantic recommendation engine | C1 | Hybrid keyword + vector search, merged, then reranked | In scope |
| Validate standards the user already cited | B4 | Each citation judged on three axes: does it exist, is it current, is it relevant to this product | In scope |
| Allied standards by type | A3 C2 | A3 reads Clause 2 offline and records typed relationships; C2 traverses them at query time | In scope |
| Latest version + amendments | A1 C3 | Catalogue lookup and date comparison. No machine learning involved, which is why it is reliable | In scope |
| Mandatory certification — ISI, CRS, Hallmarking | A1 C4 | QCO and compulsory-certification lists loaded as lookup tables; matched on product category | In scope |
| Ask for missing information | B5 C5 | C5 scores confidence; B5 checks required fields for the product category and generates targeted questions | In scope |
| Multilingual input | B2 | Detect, then translate to English before retrieval. The embedding model is multilingual as well | In scope |
| PDF output, both modes | D3 | Mode 1 completes their tender; mode 2 generates a standalone report | In scope |
| Conversational replies in user's language | D5 | The intake conversation runs in the user's language; the deliverable is still a document | In scope |

> **NOTE:** **The retrieval engine is one module out of nineteen.** C1 — the part everyone thinks of as "the project" — is roughly a day of work using off-the-shelf models with published results. The other eighteen are what make the answer trustworthy and usable. Budget effort accordingly.

## §6 The eight words you need

*Assume no prior knowledge. Everything technical in this document is one of these eight ideas.*

- **EMBEDDING** — Turning a piece of text into a long list of numbers, arranged so that texts with similar *meaning* end up with similar numbers. It is how a computer compares meaning instead of spelling. Example: "cement for RCC work" and "binder for reinforced concrete" share almost no words, but their number-lists sit very close together.

- **VECTOR DATABASE** — A store that holds those number-lists and can answer "which stored items are closest to this one?" in milliseconds, across hundreds of thousands of entries. We use FAISS, which is a local file — no server to run. Example: Ask it with the numbers for "43 grade OPC" and it returns the clause texts whose numbers are nearest.

- **KEYWORD SEARCH (BM25)** — Ordinary exact-word matching, scored by how rare each word is. Old technology, still essential: embeddings smooth meaning out, which makes them bad at exact codes. Example: A query containing "IS 8112" or "IP66" is matched exactly by BM25; an embedding might blur it into "some electrical rating".

- **HYBRID SEARCH + FUSION** — Run both searches, then merge the two ranked lists. Reciprocal Rank Fusion is the merge rule — it only looks at positions, so there is nothing to tune. Example: Vector search ranks a standard 4th, keyword ranks it 2nd; fusion promotes it above something only one method liked.

- **RERANKER (CROSS-ENCODER)** — A slower, more careful model that reads the query and each candidate *together* and re-orders the top ~25. Too slow to scan everything, which is why it only ever sees a shortlist. Example: In the prior-art system this single step moved the correct standard from rank 2–3 up to rank 1.

- **RAG** — Retrieval-Augmented Generation. Fetch the real text first, then let a language model write using *only* that fetched text. The retrieval is what stops the model inventing things. Example: The model is handed Clause 1 of IS 269 and asked to explain the match — it cannot reach for a standard it was not given.

- **KNOWLEDGE GRAPH** — A plain table of "thing A relates to thing B, and here is the type of relation". Nothing exotic. It lets us walk from a product standard to its test methods to their terminology standards. Example: `IS 269 —test_method→ IS 4031`. Three columns: from, relation, to.

- **OCR** — Optical Character Recognition — reading text out of an image. Needed the moment a user pastes a screenshot instead of a file, and for older standards that were scanned rather than typed. Example: A phone photo of page 14 of a tender becomes the same plain text a PDF would have given.

## §7 One tender, all the way through

*Follow this single example. It is scenario S2 — the valuable one — and every module below shows its part of this same job.*

> **NOTE:** **The input.** A PWD tender PDF, page 14, mixed Hindi and English:
> `"आपूर्ति — 500 मीट्रिक टन 43 ग्रेड साधारण पोर्टलैंड सीमेंट, RCC कार्य हेतु, IS 8112:1989 के अनुसार"`
>
> **What should come out.** That the citation *IS 8112:1989* is no longer valid and the current standard is *IS 269:2015*; which test-method standards must also be cited; that cement is under compulsory BIS certification so bidders need a valid ISI licence; that the tender never specified a storage requirement or a testing frequency — and a completed annexure the officer can attach.

> **NOTE:** **How to read the next two diagrams.** Time runs downward. Each dashed vertical line is one component's lifeline. A horizontal arrow between two lifelines is one component calling another.
>
> **An arrow that leaves a lifeline and comes straight back to the same lifeline is not a loop.** It is standard sequence-diagram notation for *this component doing its own internal work without calling anybody* — thinking, not looping. Figure 5 has three of them, and none is a retry, a wait or a feedback cycle.
>
> The only genuine loop in the whole system is in Figure 6, where B5 goes back out to the *user* for an answer — and that fires only when information is actually missing.

**Figure 5 — sequence: tender with guessed standards (S2).**

Diagram: Sequence diagram. The user uploads a tender. Intake extracts requirements and cited standards. The validator judges each citation with help from the core. The core then produces the full recommendation, the guard removes anything invented, and the user receives three options and a PDF.

Note the double hop through the core: B4 borrows C1 to judge whether a cited standard is even relevant to this product, then hands control back before the full recommendation runs. That reuse is why the citation validator costs a day rather than a week.

**Figure 6 — sequence: not enough information (S5).**

Diagram: Sequence diagram. A bare product name arrives. The gate asks the scorer for confidence, gets a low score, asks the user two questions, merges the answers, re-checks, and only then allows the core to answer.

The gate never guesses and never silently proceeds. Two short questions move confidence from 0.38 to 0.87 — which is the entire argument for building B5 rather than returning a weak answer and hoping. Note that the user is a participant in the middle of the flow, not only at the ends.

## §8 The nineteen modules

*Badges: [core] the product fails without it · [supporting] needed for a credible solution · [future] defer without guilt. A blue module tag means added from your scenario list.*

### Stage A — build the knowledge base

Runs offline, before any user arrives. Owned by Developer 1. Must start on Day 1 — everything else waits on it.

#### A1 · Standards Data Collector [core]

Gathers the facts about every Indian Standard — number, title, scope, year, current status, amendments — plus the QCO list and the BIS-recognised laboratory list. A data-engineering job, not an AI job, and the single biggest risk in the project: if we cannot get the data, nothing downstream matters.

**Stack:** Python · httpx · BeautifulSoup or Playwright (the BIS portal is JavaScript-rendered) · pandas · PostgreSQL

**Input:**
```
BIS "Know Your Standards" pages
SP 21 PDF — 929 pages, 559 standards
QCO notification PDFs
BIS recognised-lab list
```

**Output — one row per standard:**
```
is_number: "IS 269"
year: 2015
title: "Ordinary Portland Cement"
status: "Current"
supersedes: ["IS 8112", "IS 12269"]
amendments: ["Amd 1:2017"]
scope_text: "This standard covers..."
```

#### A2 · Document Parser & Clause Splitter [core]

Turns each standard's PDF into clean text, split into numbered clauses rather than arbitrary chunks. Splitting by clause is what later lets us say "this comes from Clause 4.2" instead of waving at a whole document.

**Stack:** PyMuPDF for digital PDFs · Tesseract or PaddleOCR for scanned older standards · regex for clause headings

**Input:**
```
IS_269_2015.pdf
```

**Output:**
```
[{"is":"IS 269:2015",
  "clause":"1","title":"Scope",
  "text":"This standard covers..."},
 {"is":"IS 269:2015",
  "clause":"2","title":"References",
  "text":"IS 4031, IS 4032..."}]
```

#### A3 · Cross-Reference Extractor [core]

Reads Clause 2 — the references clause nearly every Indian Standard carries — pulls out every other IS number mentioned, and labels what *kind* of relationship it is. This module is the entire answer to the allied-standards requirement, and it is the thing no competing system has. Measure its accuracy explicitly; do not assume it.

**Stack:** regex `IS\s?\d{3,5}` for the numbers · one small LLM call to classify relation type · NetworkX or a plain three-column PostgreSQL table

**Input:**
```
Clause 2 text of IS 269:2015
```

**Output — typed edges:**
```
IS 269:2015 →test_method→ IS 4031
IS 269:2015 →test_method→ IS 4032
IS 269:2015 →terminology→ IS 3535
IS 456:2000 →product→ IS 269
each edge stores the clause
it was found in
```

**Figure 7 — what A3 actually builds.**

Diagram: A standard sits at the centre with a superseded predecessor pointing into it and four typed neighbours radiating out: two test methods, a terminology standard and a related product standard.

Three columns in a database table — from, relation, to — plus the clause each edge came from. The relation type is what lets C2 group its answer into test methods, terminology, safety and installation instead of returning an undifferentiated list, and it is what a similarity search can never recover.

#### A4 · Index Builder [core]

Converts every clause into an embedding and builds the keyword index alongside it. Run once, then only when the corpus changes. Produces files, not a service — which is what makes offline demo mode possible.

**Stack:** `BAAI/bge-m3` via sentence-transformers · FAISS · rank_bm25

**Input:**
```
clauses.json from A2
```

**Output:**
```
faiss.index
bm25.pkl
id_map.json  (row → IS + clause)
```

### Stage B — understand the input

Runs live, per request. Owned by Person 1. This stage carries the scenario logic — it decides whether we know enough to proceed at all.

#### B1 · Input Handler [core]

Accepts all four input types from §3 — tender PDF, pasted text, screenshot image, or a bare product name — and reduces every one of them to plain text plus a note of where it came from. The screenshot path makes OCR a core dependency, not an optional extra.

**Stack:** FastAPI · python-multipart · PyMuPDF · python-docx · **Tesseract or PaddleOCR** · Pillow

**Input — any of four:**
```
tender_PWD_2026.pdf  (24 pages)
spec_screenshot.png
"43 grade OPC for RCC"
"steel tubes"
```

**Output:**
```
{"source":"pdf",
 "pages":24,
 "text":"...आपूर्ति 500 मीट्रिक टन...",
 "spec_section_page":14,
 "input_richness":"full_tender"}
```

#### B2 · Language Handler [core]

Detects the language and translates to English before retrieval, then remembers the original so the conversation and the final document can be returned in it. The embedding model is itself multilingual, so Hindi would partly work without this — translating anyway makes results stable and explanations readable.

**Stack:** `langdetect` or fastText · **IndicTrans2** (AI4Bharat, MIT licence, free, offline, 22 scheduled languages) · **Sarvam Mayura** API as fallback — see §15

**Input:**
```
"500 मीट्रिक टन 43 ग्रेड साधारण
 पोर्टलैंड सीमेंट, RCC कार्य हेतु"
```

**Output:**
```
{"lang":"hi",
 "text_en":"500 metric tonnes of
  43 grade ordinary portland
  cement for RCC work",
 "reply_language":"hi"}
```

#### B3 · Requirement Extractor [core]

Pulls the structured facts out of the text and — just as important — records what the tender *failed* to specify, plus any standards it already cites. Use an LLM with a fixed JSON schema rather than training a custom NER model: in ten days, prompting beats training, and the schema keeps the output machine-readable.

**Stack:** regex for units and IS citations · one LLM call with a strict JSON schema · Pydantic for validation

**Input:**
```
English text from B2
```

**Output:**
```
{"product":"Ordinary Portland Cement",
 "category":"cement",
 "grade":"43",
 "quantity":"500 MT",
 "application":"RCC structural work",
 "cited_standards":["IS 8112:1989"],
 "not_specified":["storage",
   "testing frequency"]}
```

#### B4 · Citation Validator [core]

Serves **Scenario S2** — the tender already names standards

Judges every standard the official already cited on three separate questions: **does it exist**, **is it current**, and **is it actually relevant to this product**. Most officials get their standards from a senior or last year's tender, so their list is usually part right and part wrong — and saying precisely which part is the most persuasive thing this system does.

**Stack:** catalogue lookup from A1 for existence · reuses C3 for currency · reuses C1 to score the cited standard against the extracted requirement for relevance

**Input:**
```
cited: ["IS 8112:1989",
        "IS 456:2000",
        "IS 1786:2008"]
+ requirement object from B3
```

**Output — verdict per citation:**
```
IS 8112:1989  SUPERSEDED
  → replace with IS 269:2015
IS 456:2000   CORRECT — keep
IS 1786:2008  NOT RELEVANT
  → steel bars, no steel in scope
MISSING       IS 4031, IS 4032
  → test methods required
```

#### B5 · Sufficiency Gate & Clarifier [core]

Serves **Scenario S5**, and rescues S3 and S4

Decides whether we know enough to answer confidently. If not, it works out *exactly which facts are missing* and asks the user for them, one short question at a time, in their own language. Two inputs drive the decision: whether the required fields for this product category are present, and the confidence score from C5.

The required-field list is a small hand-written table per category — cement needs grade and application; an LED luminaire needs wattage, IP rating and mounting type. Boring, cheap, and it is what turns "I am not sure" into a specific, answerable question.

**Stack:** a per-category required-field table (YAML) · threshold rules · one LLM call purely to phrase the question naturally in the user's language

**Input:**
```
requirement object from B3
confidence from C5 = 0.38
category = "steel tubes"
```

**Output — either proceed or ask:**
```
{"status":"need_more_info",
 "confidence":0.38,
 "missing":["type","application"],
 "questions":[
  "Seamless or welded?",
  "Structural use, or for
   conveying fluid?"],
 "can_proceed_anyway":true}
```

### Stage C — find and check the standards

The heart of the system. C1 owned by Person 2; C2–C5 by Person 3, because they are the differentiator and must not bottleneck on one person.

#### C1 · Hybrid Retrieval Engine [core]

Searches the indexes two ways at once, merges the results, then re-orders the shortlist with a reranker. Use the exact model combination below — it is public prior art with published results on this corpus, so this module should work by Day 4 and then be left alone.

**Stack:** FAISS + `bge-m3` for meaning · rank_bm25 for exact terms · Reciprocal Rank Fusion to merge · `BAAI/bge-reranker-v2-m3` to re-order

**Input:**
```
"43 grade ordinary portland
 cement for RCC structural work"
```

**Output — ranked, with evidence:**
```
1. IS 269:2015   0.94
   matched Clause 1 Scope
2. IS 456:2000   0.79
   matched Clause 5.1
3. IS 383:2016   0.62
```

#### C2 · Allied Standards Expander [core]

Takes what C1 found and walks the relationship map from A3 outward, two hops, then groups the result by relationship type. This is a graph traversal, not a search — which is exactly why a vector database alone can never produce it.

**Stack:** NetworkX, or a recursive SQL query over the A3 table. Neo4j only if edges exceed roughly 100,000 — otherwise it is a second database for no gain

**Input:**
```
["IS 269:2015"], depth = 2
```

**Output — grouped by type:**
```
test_method:     IS 4031, IS 4032
terminology:     IS 3535
related_product: IS 1489, IS 455
installation:    IS 456
each edge cites the clause
that asserts it
```

#### C3 · Version & Amendment Resolver [core]

Checks every standard — both the ones we recommend and the ones the tender already cites — against the catalogue, and raises a warning when something is superseded, withdrawn or amended. No machine learning here at all: a database lookup and some date comparisons, which is precisely why it is reliable.

**Stack:** PostgreSQL queries · Python `datetime`. Nothing else.

**Input:**
```
cited:      ["IS 8112:1989"]
recommended:["IS 269:2015"]
```

**Output — warnings:**
```
{"severity":"high",
 "cited":"IS 8112:1989",
 "message":"Superseded — merged
   into IS 269:2015",
 "action":"Replace citation"}
{"severity":"low",
 "message":"IS 269:2015 carries
   Amendment 1"}
```

#### C4 · Certification & QCO Engine [core]

Answers whether this product legally requires BIS certification before it can be supplied, and under which scheme — then phrases it differently for each stakeholder: an eligibility condition for the procurement official, an obligation and a licence route for the manufacturer. Grounded in the published lists — 187 Quality Control Orders covering 769 products under compulsory certification — loaded as a lookup table, so the answer is a citation rather than a guess.

**Stack:** PostgreSQL lookup · fuzzy matching on product category · the BIS recognised-laboratory list for the lab suggestion

**Input:**
```
{"product":"Ordinary Portland
  Cement","category":"cement"}
persona: "procurement"
```

**Output:**
```
{"certification_required":true,
 "scheme":"ISI Mark",
 "qco_reference":"verify exact QCO
   before demo",
 "for_procurement":"Bidders must
   hold a valid BIS licence",
 "labs_available":14}
```

#### C5 · Confidence Scorer [core]

Drives **B5**, and every number the user sees

Turns raw search scores into an honest confidence figure. This matters more than it sounds: a raw similarity score is **not** a probability, and showing one to a government user as though it were is dishonest. Combine four cheap signals — the reranker score, the gap between rank 1 and rank 2, whether the required fields were present, and whether the graph agrees with the retrieval — then map to High / Medium / Low bands with thresholds tuned on the gold test set.

**Stack:** plain Python · thresholds tuned on the 50-pair gold set · scikit-learn isotonic regression only if time allows

**Input:**
```
reranker_score: 0.94
margin_to_second: 0.15
required_fields_present: true
graph_agrees: true
```

**Output:**
```
{"score":0.91,
 "band":"high",
 "drivers":["strong scope match",
   "grade and application known",
   "test methods confirm product
    family"]}
```

### Stage D — deliver the answer

D1–D3 owned by Person 3; D4–D5 by Developer 2.

#### D1 · Validity Guard [core]

The last gate before anything reaches a user or a PDF. Every IS number appearing in any generated sentence is checked against the catalogue from A1; anything that does not exist is deleted, not softened. A fabricated standard number inside a live government tender is the one failure this project cannot survive, so this module is non-negotiable and takes about an afternoon to write.

> **NOTE:** **D1 only ever inspects generated prose, never the recommendation itself.** Trace where the recommended standards come from: C1 returns row numbers that the lookup table converts into real catalogue entries, C2 traverses edges whose endpoints are rows in a database table, and C3 performs catalogue lookups. Every standard in the structured output arrived from a database, so *by construction* it cannot be invented.
>
> The only component in the whole pipeline capable of producing a standard number that does not exist is the single language-model call in D2 that writes the human-readable explanation. That is the sole thing D1 guards. When D1 removes something, no gap appears in the answer — the set of recommended standards was fixed and correct before the model wrote a word, and it is unchanged afterwards.
>
> This is also why D1 firing must never trigger a re-run. Re-running C1 through C5 feeds identical input into deterministic modules and returns an identical result, so it costs the full latency budget to arrive back where you started. Frequent D1 rejections are a defect in the generation prompt, which should be given an explicit list of the standard numbers it is permitted to mention. Treat D1 as a seatbelt rather than a routine cleanup stage: one that engages on every journey means something is wrong with the driving.
>
> One consequence for implementation. D1 must validate against the **full catalogue metadata for all ~22,689 standards** collected by A1, not against the smaller set for which we hold full text. A real standard that falls outside our two ingested sectors still exists and must not be deleted as fabricated.

**Stack:** regex extraction + a Python set lookup. Roughly forty lines of code.

**Input:**
```
"Refer IS 269:2015 and also
 IS 99999:2021 for testing."
```

**Output:**
```
text: "Refer IS 269:2015 for testing."
removed: ["IS 99999:2021"]
reason: "not in catalogue"
```

#### D2 · Recommendation Composer [core]

Sets the **citation depth** — not three rival answers

Assembles everything upstream into *one* recommendation with an adjustable breadth. All three depths contain the **same primary standard**; they differ only in how many allied standards travel with it. This is the "options with confidence scores" requirement, and it is honest — the right amount of citation genuinely depends on the tender's value and risk, and that is the user's call, not ours.

> **WARNING:** **Do not confuse this with the top-3 standards.** C1 returns a *ranked list* — the three best-matching standards, most relevant first. D2 produces *depth levels* — how much to cite. Two different things. If the interface makes them look like three competing guesses, we have destroyed the user's confidence for no reason.

**Stack:** Jinja2 for the deterministic parts · one constrained LLM call for prose, run *before* D1 checks it

**Input:**
```
outputs of B3, B4, C1–C5
```

**Output — one answer, three depths:**
```
primary: IS 269:2015   conf 0.94
depth A "Minimum"
  IS 269:2015
depth B "Recommended" ★ default
  + IS 4031, IS 4032, IS 3535
depth C "Comprehensive"
  + IS 456:2000, IS 1489
```

**Figure 8 — one answer, three depths.**

Diagram: Three horizontal bars of increasing length. All three begin with the same primary standard segment; each deeper level adds more allied standard segments to the right.

The system never hedges about which standard applies. Every depth level names IS 269:2015 as the primary, with identical confidence and identical evidence. The slider only decides how many test-method, terminology and related-product standards get cited alongside it — which is a policy question about the tender, not a question the retrieval engine is uncertain about.

#### D3 · Document Generator [core]

Serves **output modes O1 and O2** — the main deliverable

Produces the PDF. **Mode 1** completes the user's own tender: generate an "Annexure — Applicable Indian Standards" and append it to their original document, with in-place insertion at a located anchor as a later enhancement. **Mode 2** generates a standalone recommendation report. Both carry confidence bands, evidence citations and version warnings, and both are produced in the user's language.

**Stack:** HTML template → WeasyPrint (easiest path to a well-typeset PDF) · PyMuPDF to append to or annotate the uploaded original · ReportLab only if precise layout control is needed

**Input:**
```
selected option = "B"
original_tender.pdf
persona = "procurement"
language = "hi"
```

**Output:**
```
completed_tender.pdf
  = original 24 pages
  + Annexure A: standards table
  + inserted clause, highlighted
  + confidence + evidence column
  + ⚠ IS 8112:1989 superseded
```

#### D4 · API Layer [core]

Portal integration. One documented endpoint that does the whole job. Build this *before* the website, so the website becomes just another client and integration with GeM or CPPP needs no rewrite. A ten-line demo showing an external page calling this endpoint is worth more to a judge than any slide about integration.

**Stack:** FastAPI · auto-generated OpenAPI spec · API-key auth · Docker for delivery

**Input:**
```
POST /v1/analyze
{"text":"...", "lang":"auto",
 "persona":"procurement",
 "output_mode":"annexure"}
or multipart file upload
```

**Output:**
```
200 OK
{"status":"complete" |
   "need_more_info",
 "questions":[...],
 "options":[A,B,C],
 "warnings":[...],
 "certification":{...},
 "evidence":[...],
 "pdf_url":"..."}
```

#### D5 · Web Interface [core]

Two front doors — "I am drafting a tender" and "I am manufacturing a product" — leading into a chat-shaped intake where the user drops a file, screenshot or sentence. The system asks its clarifying questions there, then switches to a findings panel: detected requirements, recommended standards with confidence bands and evidence, allied standards grouped by type, version warnings, certification status, and a prominent **Download PDF**.

Reference the BIS-COMPASS walkthrough for visual quality — confidence bands, clean panels, restrained motion. Match that polish, then beat it on the two things it does not do: conversational intake and a document as the output.

**Stack:** Next.js + React · Tailwind · Framer Motion for restrained transitions · file and image drop · a simple force-directed view for the allied-standards graph

**Input:**
```
user picks persona
drops tender.pdf
answers 2 questions in chat
picks option B
```

**Output:**
```
Findings screen +
completed_tender.pdf download
Total interaction: under
90 seconds
```

## §9 The JSON contracts

*Agree these on Day 1 and commit them with fake fixture data. This one file is what lets five people build nineteen modules without waiting for each other.*

### RequirementObject — B3 output, consumed by B4, B5, C1, C4

```
{
  "product":          "Ordinary Portland Cement",
  "category":         "cement",              // matches the required-field table
  "attributes": {
      "grade":          "43",
      "quantity":       "500 MT",
      "application":    "RCC structural work"
  },
  "cited_standards":  ["IS 8112:1989"],      // empty array for scenario S1
  "not_specified":    ["storage", "testing_frequency"],
  "language":         "hi",
  "source":           "pdf",                 // pdf | text | image | product_name
  "richness":         "full_tender"          // full_tender | spec_only | name_only
}
```

### CitationVerdict — B4 output, one per cited standard

```
{
  "citation":  "IS 8112:1989",
  "exists":    true,
  "status":    "superseded",   // current | superseded | withdrawn | not_found
  "relevant":  true,
  "verdict":   "replace",      // keep | replace | remove | add
  "replacement": "IS 269:2015",
  "reason":    "Merged into IS 269:2015",
  "severity":  "high"          // high | medium | low
}
```

### SufficiencyResult — B5 output, read by D4 to decide what to show

```
{
  "status":       "need_more_info",   // ok | need_more_info
  "confidence":   0.38,
  "missing":      ["type", "application"],
  "questions": [
      { "field": "type",        "ask": "Seamless or welded?" },
      { "field": "application", "ask": "Structural use, or for conveying fluid?" }
  ],
  "can_proceed_anyway": true       // user may override and accept a weak answer
}
```

### AnalyzeResponse — D4 output, the only contract the frontend and GeM ever see

```
{
  "status": "complete",             // complete | need_more_info
  "questions": [],                  // populated only when status is need_more_info
  "options": [
    { "id": "A", "label": "Mandatory only",  "confidence": 0.94, "band": "high",
      "standards": ["IS 269:2015"] },
    { "id": "B", "label": "Recommended",     "confidence": 0.88, "band": "high",
      "default": true,
      "standards": ["IS 269:2015","IS 4031","IS 4032","IS 3535"] },
    { "id": "C", "label": "Comprehensive",   "confidence": 0.71, "band": "medium",
      "standards": ["IS 269:2015","IS 4031","IS 4032","IS 3535","IS 456:2000"] }
  ],
  "allied": {
      "test_method":     ["IS 4031","IS 4032"],
      "terminology":     ["IS 3535"],
      "related_product": ["IS 1489"]
  },
  "warnings":      [ /* CitationVerdict + version warnings */ ],
  "certification": { "required": true, "scheme": "ISI Mark", "labs_available": 14 },
  "evidence": [
      { "standard": "IS 269:2015", "clause": "1", "quote": "This standard covers…" }
  ],
  "pdf_url": "/v1/document/8f3a21.pdf"
}
```

> **NOTE:** **Every module's real output must validate against these shapes from Day 1**, even while the values are fake. Use Pydantic models as the single source of truth and generate the fixtures from them — that way a contract change breaks the build instead of breaking the demo.

## §10 How we know it works

*Write the gold test set before the retrieval code. Fifty hand-written pairs of plain product description → the standard that is actually correct. Without it, every argument about whether a change helped becomes opinion.*

| What we measure | Target | How | Owner |
|---|---|---|---|
| Hit@3 — correct standard in top 3 | > 85% | Gold set of 50 pairs | Person 2 |
| MRR@5 | > 0.75 | Gold set | Person 2 |
| Allied recall — 1 hop | > 80% | Compare C2 output against Clause 2 read by hand for 20 standards | Person 3 |
| Cross-reference extraction F1 | > 0.85 | Hand-label Clause 2 of 20 standards, compare against A3 | Developer 1 |
| Invented IS numbers | exactly 0 | D1 rejection log must never be bypassed. A single escape is a release blocker | Person 3 |
| Superseded standard recommended | exactly 0 | C3 runs on every response, including B4 verdicts | Person 3 |
| Confidence calibration | High band ≥ 90% correct | Bucket gold-set results by band and check the hit rate matches the label | Person 2 |
| End-to-end latency, p95 | < 5 s text · < 30 s PDF | Measured on demo hardware, not a developer laptop | Developer 2 |
| Hindi vs English parity | within 5 points of Hit@3 | Translate 20 gold queries and re-run | Person 1 |
| All five scenarios pass | 5 / 5 | One scripted walkthrough per scenario, rehearsed on Day 9 | Everyone |

> **WARNING:** The two rows with a target of "exactly 0" are **release blockers, not targets**. Everything else can miss and we still have a product; those two failing means the system lies to a government officer inside a legal document.

## §11 Final scope

*Freeze this on Day 3. Anything not listed under "building" is not being built, however good the idea looks on Day 6.*

| Decision | What | Why |
|---|---|---|
| Building | All nineteen modules · all five input scenarios · both output modes · **two sectors only**: cement & construction materials, plus one electrical category | Two sectors done properly beats eight done shallowly. SP 21 gives us the construction corpus immediately, removing the data risk from Day 1 |
| Building | Full catalogue **metadata** for all ~22,689 standards | Cheap, and it makes C3 and D1 work across everything even where we lack full text |
| Building | Procurement persona complete; manufacturer persona as a second template | Same engine, different wording. Roughly one extra day once the first is done |
| Phase 2 | True in-place PDF editing beyond the annexure · remaining sectors · OCR for scanned *standards* · saved history and accounts | Each is additive. None changes the architecture |
| Not building | Restrictive-specification detection · reverse-reference impact analysis · live tender-portal scraping · fine-tuning any model | Good ideas that do not survive a ten-day budget. Keep them as roadmap slides, not promises |

## §12 Who builds what

| Person | Modules | First task, Day 1 |
|---|---|---|
| Developer 1 | A1 A2 A3 A4 | Get SP 21 parsed and one standard's Clause 2 extracted. Everything waits on this |
| Person 1 · ML | B1 B2 B3 | Stand up the extraction JSON schema and test it on five real tender PDFs, one of them a screenshot |
| Person 2 · ML | C1 + eval harness | Build the gold test set: 50 hand-written *description → correct IS* pairs. Before any retrieval code |
| Person 3 · AI/RAG | B4 B5 C2 C3 C4 C5 D1 D2 D3 | Design the warning, confidence and option JSON shapes so D5 can be built against them immediately |
| Developer 2 | D4 D5 | Ship `POST /v1/analyze` returning hard-coded fake JSON, so the website can start on Day 1 |

> **NOTE:** **Person 3 is overloaded.** Nine modules is too many for one person — but most are small and rule-based. Move C2 to Developer 1 (it is a graph query over their own table) and D3 to Developer 2 (it is document rendering) as soon as Stage A is stable, around Day 5.

### Ten days

- **Days 1–2** — agree all JSON contracts · A1/A2 running · gold test set started · fake API live · website shell with both personas
- **Day 3** — **scope freeze** · A3 producing real edges · B3 extracting real requirements · chat intake accepting files
- **Days 4–5** — A4 indexes built · C1 working and measured · B4 validating citations · website on real data · **rebalance Person 3's load**
- **Days 6–7** — C2–C5 real · B5 asking real questions · D1 guard in place · D2 producing three options
- **Day 8** — D3 generating both PDF modes · manufacturer template · multilingual path tested end to end · first full dry run
- **Day 9** — hardening · offline package · measure and write down the real numbers · all five scenarios rehearsed
- **Day 10** — demo script, three rehearsals, backup recording. No new code.

## §13 What could go wrong

| Risk | Impact | What we do about it |
|---|---|---|
| BIS data cannot be collected at volume | Fatal | Day-1 spike before anything else. Fallback: SP 21 alone gives 559 standards in one PDF — enough for a complete two-sector demo |
| Clause 2 extraction is noisy | High | Clause 2 has rigid formatting, so regex catches most of it; use an LLM only to classify relation type, and measure F1 on 20 hand-labelled standards |
| A fabricated IS number reaches a user | Fatal to trust | D1 is mandatory and unbypassable. Write it on Day 2, not Day 8 |
| In-place PDF editing breaks on real tenders | Medium | Annexure path is the default; in-place insertion is opt-in and can be dropped without losing the feature |
| OCR quality on phone screenshots | Medium | Show the extracted text back to the user in the chat before proceeding — a cheap correction loop that also looks good in the demo |
| Person 3 becomes the bottleneck | High | Planned rebalance on Day 5, written into the schedule above |
| Venue wifi fails during the demo | High | Everything except the optional LLM phrasing runs offline. Package by Day 9 and record a backup video |
| Scope creep after Day 3 | High | §11 is a written freeze. The "not building" row is binding, not advisory |

## §14 Repository layout

```
standards360/
├── docs/                    SE lifecycle artifacts, numbered by phase
├── contracts/               §9 Pydantic models + fake fixtures  ← Day 1
├── ingest/                  Stage A — runs offline
│   ├── collect.py               A1
│   ├── parse_clauses.py         A2
│   ├── extract_refs.py          A3
│   └── build_index.py           A4
├── app/
│   ├── understand/              Stage B — B1…B5
│   ├── core/                    Stage C — C1…C5
│   ├── deliver/                 Stage D — D1…D3
│   └── api/                     D4 — FastAPI routes
├── web/                     D5 — Next.js, two personas
├── data/
│   ├── catalogue.db             A1 output
│   ├── edges.csv                A3 output — from, relation, to, clause
│   ├── faiss.index              A4 output
│   └── required_fields.yaml     B5 per-category checklist
├── eval/
│   ├── gold_set.json            50 pairs — written before C1
│   └── run_eval.py              §10 metrics
└── demo/                    scripted walkthrough per scenario
```

## §15 Language and the conversational layer

### Translation — module B2, required

Use **IndicTrans2** from AI4Bharat. MIT-licensed and free, covers all 22 scheduled Indian languages, and the distilled 200M variant runs on a laptop CPU. Critically it runs *offline*, which matters twice over: venue wifi fails, and tender documents may be pre-tender confidential, so sending them to a hosted API is a real objection from a government customer. Self-hosting turns that objection into a selling point.

Keep **Sarvam's Mayura** translation API configured as a one-line fallback — same 22 languages, roughly ₹20 per 10,000 characters with free starting credits. Trivial money at demo volume, and useful if IndicTrans2 struggles on a specific language on the day.

### The conversation — modules B5 and D5

Do **not** train or fine-tune anything. There is no time, no data and no benefit. The language model's only jobs are to phrase B5's clarifying questions naturally and to phrase D2's explanation — every fact it speaks was retrieved by your own pipeline, and everything it writes passes through D1 before anyone sees it.

Sarvam is the natural choice for that phrasing layer given the Indian-language requirement: chat-completion pricing in the tens of rupees per million tokens, and they open-sourced Sarvam-30B and Sarvam-105B in March 2026, so there is a self-hosting path if a judge asks about data sovereignty. "Hosted for the demo, open weights available for deployment" is a strong answer.

> **WARNING:** Whatever model phrases the reply, the output still passes through **D1**. A conversational layer that invents an IS number is worse than no conversational layer at all.

## §16 Do these three things first

1. **Prove the data.** Before any model code, get one Indian Standard end to end: PDF in, clauses out, Clause 2 references extracted, one row in the database. If this is hard, the project shape changes and we need to know on Day 1, not Day 6.
2. **Write the gold test set.** Fifty pairs of *plain product description → the standard that is actually correct*, written by hand. Without it nobody can tell whether a change improved anything.
3. **Freeze the JSON contracts.** §9, committed with fake fixture data. This is what lets five people build nineteen modules at once.

## §17 Appendix A — how Stage C actually produces a recommendation

*This is the engine room. Everything above describes what the C modules do; this section describes how, in enough detail that Person 2 and Person 3 can start writing code without asking further questions.*

### A.0 — What runs when

Stage C is not a single straight line. Two of its five modules can start immediately, before retrieval has finished, which is most of how we stay inside the latency budget.

| Step | Waits for | Can run in parallel with | Typical cost |
|---|---|---|---|
| C1 Retrieval | B3 requirement object | C4 | 400–900 ms |
| C4 Certification | **only the product category** from B3 | C1 — start it at the same instant | < 20 ms |
| C2 Allied expansion | C1 seeds | C3 | 20–80 ms |
| C3 Version resolution | C1 results + B3 citations | C2 | < 30 ms |
| C5 Confidence | C1 + C2 + B3 | — | < 5 ms |

> **NOTE:** **C4 does not need the retrieval result.** Whether cement is under a Quality Control Order depends on the product category, which B3 already knows. Fire C4 and C1 together and the certification panel is ready before the standards are. This one scheduling decision is worth several hundred milliseconds for free.

### A.1 — C1 Hybrid Retrieval, in six sub-steps

#### C1.1 · Build the search query from the requirement object

Do not pass the user's raw text to the search engine. Build a clean query string from the structured fields B3 produced, in a fixed order: product, then grade or rating, then application. Ordering matters because BM25 is position-insensitive but the reranker is not.

RequirementObject → `"Ordinary Portland Cement 43 grade RCC structural work"`

> **Gotcha:** exclude quantity and delivery terms. "500 MT" and "delivery within 90 days" carry no signal about which standard applies, and they actively pull BM25 toward irrelevant clauses that happen to mention tonnage.

#### C1.2 · Dense search — retrieve by meaning

Embed the query with `bge-m3` and search FAISS for the 25 nearest **clauses**. Note that we search clauses, not standards — a standard's scope clause is what actually describes what it covers, and burying it inside a whole-document embedding dilutes it.

query vector (1024-dim) → FAISS → top-25 clause ids + cosine distances

#### C1.3 · Sparse search — retrieve by exact words

Run the same query through BM25 over the same clause collection for a separate top-25. This is what catches exact tokens the embedding smooths away: an IS number the user mentioned, "IP66", "43 grade", a rare material name.

> **Gotcha:** run C1.2 and C1.3 concurrently, not one after the other. They are independent and each takes a few milliseconds; running them in sequence doubles the cheapest part of the pipeline for no reason.

#### C1.4 · Merge the two lists with Reciprocal Rank Fusion

RRF ignores the scores entirely and uses only the *positions*, which is exactly what we want because a cosine distance and a BM25 score are not comparable numbers. For every clause appearing in either list:

```
rrf_score(clause) = 1/(60 + rank_dense) + 1/(60 + rank_sparse)

a clause missing from one list simply contributes 0 from that side
```

The constant 60 is the standard value from the literature. It is not a tuning knob — leave it alone. Keep the top 25 of the fused list.

#### C1.5 · Rerank the shortlist with a cross-encoder

Feed each of the 25 surviving clauses to `bge-reranker-v2-m3` *together with* the query. Unlike an embedding, which compresses the query and the clause separately and then compares, a cross-encoder reads both at once and can notice that "43 grade" in the query matches a grade table in the clause. In the published prior-art ablation this single step was the largest accuracy gain in the whole pipeline.

> **Gotcha:** this is the slowest step by an order of magnitude. Never rerank more than about 25 candidates, and cap the pool lower on CPU-only machines. Latency scales linearly with pool size.

#### C1.6 · Roll clauses up into standards

The user asked for standards, but everything so far has been clauses. Group the reranked clauses by their parent standard and take the **maximum** clause score as the standard's score — not the mean, because a standard with one perfectly matching scope clause and forty irrelevant test-procedure clauses is still the right answer.

Keep the winning clause with each standard. That clause is the evidence shown to the user and quoted in the PDF, and it is what makes "why this standard?" answerable.

```
IS 269:2015   0.94   ← Clause 1, Scope
IS 456:2000   0.79   ← Clause 5.1
IS 383:2016   0.62   ← Clause 2
```

### A.2 — C2 Allied Expansion, in six sub-steps

#### C2.1 · Choose the seeds

Expand only from standards C1 scored above a confidence floor — start at 0.80. Expanding from a weak match multiplies the error: a wrong seed produces four wrong allied standards, and the user sees five mistakes instead of one.

seeds = [IS 269:2015] · IS 456 at 0.79 and IS 383 at 0.62 do not qualify

#### C2.2 · Hop one — direct references

Query the edge table A3 built for every edge whose source is a seed. Each edge carries its relation type and the clause it was extracted from.

```
SELECT to_is, relation, source_clause
FROM edges WHERE from_is = 'IS 269:2015'
```

#### C2.3 · Hop two — references of references, with decay

Repeat from each hop-one result, multiplying the inherited weight by a decay factor of about 0.5. A test method's own terminology standard is genuinely relevant, but less so than the test method itself, and the score must say so.

> **Gotcha:** stop at two hops. Standards reference each other densely, and hop three routinely pulls in a hundred standards with no real connection to the product. Depth is a hard cap, not a parameter to experiment with during the demo.

#### C2.4 · Weight by relation type

Not all edges deserve equal prominence. Weight them so the ordering inside each group is sensible, and so the citation-depth levels in D2 have a principled cut-off.

```
normative_reference  1.00     safety            0.85
test_method          0.95     installation      0.70
terminology          0.80     related_product   0.60
```

#### C2.5 · Deduplicate and keep the best path

The same standard will frequently be reachable by several routes — IS 3535 is a terminology standard for both IS 269 and IS 4031. Keep one entry, retain the **highest** weight, and remember every path so the interface can show all the reasons it was included.

#### C2.6 · Guard against cycles, then group

Standards cite each other in both directions, so an unguarded traversal loops forever. Maintain a visited set. Then group the survivors by relation type, which is the shape C2 hands to D2 and the shape the user finally reads.

```
test_method:     IS 4031 (0.95) · IS 4032 (0.95)
terminology:     IS 3535 (0.80)
related_product: IS 1489 (0.60)
```

### A.3 — C3 Version Resolution, in five sub-steps

#### C3.1 · Normalise the identifier first

Every downstream comparison depends on this and it is the most commonly skipped step. The same standard appears in tenders as `IS 269`, `IS 269:2015`, `IS-269`, `IS 269 : 2015`, `I.S. 269`. Canonicalise all of them to a family number and an optional year before touching the database.

```
"IS 269 : 2015"  →  { family: "IS 269", year: 2015 }
"IS-8112"        →  { family: "IS 8112", year: null }
```

> **Gotcha:** a missing year means "whatever version is current", not "the oldest one". Treat a bare family number as a request for the current version rather than as an error.

#### C3.2 · Resolve each family to its current version

A single catalogue lookup on the family number returns the current year and status. If the requested year differs from the current year, that is a version-drift warning — medium severity, because the standard still exists and the officer may have cited the old one deliberately.

#### C3.3 · Follow the supersession chain to its end

Supersession is not always one step. A withdrawn standard may point to another standard that was itself later merged elsewhere, so follow the chain until you reach something marked current — with a hop limit to survive bad data.

```
IS 8112 → superseded_by → IS 269:2015 → current · stop
```

This is high severity: the cited standard no longer exists as a separate document, so leaving it in the tender is a genuine defect.

#### C3.4 · Attach amendments

An amendment is a separate document that modifies a standard without replacing it, so a tender citing the base standard alone is incomplete. Attach every amendment to the resolved version and report it as low severity — informational rather than wrong.

#### C3.5 · Emit typed warnings

C3 runs over *both* the standards we are recommending and the standards the tender already cites, which is why B4 can borrow it wholesale rather than reimplementing version logic.

```
high    IS 8112:1989 superseded → replace with IS 269:2015
medium  cited IS 456:2000 · current is a later revision
low     IS 269:2015 carries Amendment 1
```

### A.4 — C4 Certification, in six sub-steps

#### C4.1 · Resolve the product to a BIS category

QCO lists are organised by product category, not by free text. Match B3's product string to a category with exact matching first, then fuzzy matching, and abstain if the best match is weak — a wrong certification claim is worse than none.

#### C4.2 · Look up the Quality Control Order

A straight table lookup against the published lists — 187 QCOs covering 769 products. If there is no row, the honest answer is "no compulsory certification found for this category", not silence.

#### C4.3 · Determine the scheme

The obligation differs by scheme: ISI mark under BIS product certification, CRS registration for specified electronics, Hallmarking for precious metals. The scheme decides the wording of everything downstream.

#### C4.4 · Check the enforcement date

A QCO notified today may only come into force months later. Compare the enforcement date against the tender's delivery timeline where one was extracted, and against today's date otherwise, so the answer is "mandatory for this award" rather than a vague "mandatory".

#### C4.5 · Find the testing laboratories

Join the BIS recognised-laboratory list on the standards being recommended, and return the count plus the nearest few. Cheap, concrete, and it is the part manufacturers care about most.

#### C4.6 · Phrase it for the persona

Identical facts, two sentences. For the procurement official: *"bidders must hold a valid BIS licence — state this as an eligibility condition."* For the manufacturer: *"you must obtain a BIS licence under this scheme before you can sell; 14 recognised labs can perform the testing."*

### A.5 — C5 Confidence, and the actual arithmetic

Four signals, combined linearly, then banded. Deliberately simple: a formula the team can explain to a judge in one sentence is worth more than a model nobody can defend.

```
s1  reranker score of the top standard                    0…1
s2  margin over the runner-up, as min(margin / 0.30, 1)   0…1
s3  required fields present / required fields total       0…1
s4  graph agreement — does C2's expansion of the winner
    contain other standards C1 also ranked highly?        0 or 1

confidence = 0.45·s1 + 0.20·s2 + 0.25·s3 + 0.10·s4

band:  high ≥ 0.75   ·   medium 0.50–0.75   ·   low < 0.50
B5 asks a question when confidence < 0.60 OR any required field is missing
```

**s2 is the signal most teams omit and it is the most informative one.** A top score of 0.94 means very little on its own; 0.94 when the runner-up scored 0.93 means the system is effectively guessing between two standards, while 0.94 against 0.62 is a decisive result. The margin is what separates those two situations, and nothing else in the pipeline can see the difference.

**The weights above are starting points, not truths.** Tune them on the fifty-pair gold set and record the numbers you settled on. Anyone who asks where 0.45 came from deserves a real answer.

### A.6 — The whole thing, with real numbers

Input: *"500 MT of 43 grade Ordinary Portland Cement for RCC structural work, as per IS 8112:1989"*

```
C1.1  query  = "Ordinary Portland Cement 43 grade RCC structural work"
C1.2  dense  → 25 clauses          C1.3  bm25 → 25 clauses   (concurrent)
C1.4  RRF    → 31 unique clauses, keep top 25
C1.5  rerank → cross-encoder scores each of the 25
C1.6  roll up to standards, keeping the best clause as evidence
          IS 269:2015  0.94   Clause 1 Scope
          IS 456:2000  0.79   Clause 5.1
          IS 383:2016  0.62   Clause 2

C4    (ran in parallel from the category "cement", finished long ago)
          QCO found · scheme ISI Mark · 14 recognised labs

C2.1  seeds  = [IS 269:2015]        only one clears the 0.80 floor
C2.2  hop 1  → IS 4031 test_method · IS 4032 test_method · IS 3535 terminology
C2.3  hop 2  → IS 4305 terminology, weight decayed to 0.40
C2.6  grouped and deduplicated

C3.1  normalise "IS 8112:1989" → { family: IS 8112, year: 1989 }
C3.3  chain  → IS 8112 superseded_by IS 269:2015 · current · stop
C3.5  warning, high severity: replace the citation

C5    s1 = 0.94
          s2 = (0.94 − 0.79) / 0.30 = 0.50
          s3 = 2 of 2 required fields present = 1.00   (grade, application)
          s4 = 1   (IS 456 appears in both C1's list and C2's expansion)

          confidence = 0.45(0.94) + 0.20(0.50) + 0.25(1.00) + 0.10(1.00)
                     = 0.423 + 0.100 + 0.250 + 0.100
                     = 0.87  →  band: high

          ≥ 0.60, so B5 asks nothing. Straight through to D1.
```

Everything after this point is assembly. D1 checks that all five IS numbers exist in the catalogue, D2 slices them into the three citation depths of Figure 8, and D3 renders the annexure. No further judgement is made about which standard is correct — that decision was finished at C1.6, and everything since has been about completeness, currency and presentation.

## §18 Appendix B — system architecture

*The whole manual on one page. Subsystems, not individual modules — the module IDs are printed inside each box so this stays readable at slide size.*

**Figure 9 — system architecture.**

Diagram: Two human personas and an external procurement portal reach the system through a web interface and a REST API. Requests flow down through the understand, find-and-check and deliver stages, producing two kinds of PDF. The online stages read four knowledge stores, which an offline ingestion pipeline writes nightly from BIS sources.

Three things this drawing is meant to settle. The API is not a wrapper around the website — both are equal clients of the same contract, which is what makes portal integration a configuration rather than a rewrite. The online and offline halves share no code path and meet only at the four stores, so the corpus can be rebuilt while the service is answering. And blue marks the one chain no competing system has: A3 extracts the typed relationships, the edge store holds them, and stage C is where they turn into an answer.

---
*Standards360 · build manual v4 · verify every IS number against the BIS portal before use*
