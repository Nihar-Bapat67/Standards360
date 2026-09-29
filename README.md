# Standards360

<p align="center">
  <img src="https://img.shields.io/badge/Status-Final%20Prototype-blue" alt="Status" />
  <img src="https://img.shields.io/badge/Build-Validated-success" alt="Build" />
  <img src="https://img.shields.io/badge/Domain-Procurement%20Standards-orange" alt="Domain" />
  <img src="https://img.shields.io/badge/Theme-SIH%2026108-purple" alt="SIH" />
</p>

AI-powered recommendation engine that maps a procurement specification to the applicable Indian Standards, allied references, version validity, and mandatory certification obligations.

Built for Smart India Hackathon Problem Statement 26108, Department of Consumer Affairs, Government of India.

## Why this matters

Procurement teams often draft technical specifications without the right Indian Standards, creating ambiguity, compliance risk, and quality disputes. Standards360 helps officers, technical evaluators, and manufacturers identify the correct standards using semantic understanding rather than brittle keyword matching.

The system recommends:
- the most relevant Indian Standard(s)
- allied and normative references
- latest published versions and amendments
- mandatory certification requirements and testing labs
- a concise evidence-backed reasoning trail for each recommendation
- an annexure ready to attach to a tender or specification document

## Product snapshot

- Semantic retrieval over Indian Standard clauses and metadata
- Citation-aware recommendation pipeline
- Version and supersession validation
- BIS-linked allied standards and test methods
- Certification and QCO-driven compliance checks
- Multilingual input support for Indian language tender documents
- Deployment-ready FastAPI backend and React frontend

## Architecture at a glance

```text
Tender / specification input
            │
            ▼
B1 - Input understanding / language handling
            │
            ▼
C1 - Retrieval + allied standard expansion
            │
            ▼
C2 - Standard relationship mapping
            │
            ▼
C3 - Version & supersession validation
            │
            ▼
C4 - Certification / QCO / lab checks
            │
            ▼
D1 - Validity guard
            │
            ▼
D2 - Final recommendation composer
            │
            ▼
D3 / D4 - Annexure + API delivery
            │
            ▼
Web interface + procurement portal integration
```

## Key features

### 1. Semantic standard recommendation
The engine does not rely only on product names or keywords. It understands the tender requirement context and retrieves the most relevant standards along with supporting clauses.

### 2. Allied standards and references
The platform surfaces related standards, test methods, safety references, and best-practice standards connected to the principal recommendation.

### 3. Version-aware intelligence
It checks whether the cited standards are current, withdrawn, superseded, or amended, and warns where older or conflicting versions may create risk.

### 4. Certification and compliance intelligence
Where applicable, the model identifies mandatory certification obligations, relevant labs, and QCO-linked requirements.

### 5. Deployment-ready API and UI
The solution includes:
- a Python FastAPI backend
- a React + Vite frontend
- a single contract at `/v1/analyze`
- document generation/annexure support

## Tech stack

### Backend
- Python 3.11+
- FastAPI
- SQLite
- FAISS
- BM25 retrieval
- Sentence embeddings

### Frontend
- React
- Vite
- TypeScript
- Tailwind CSS
- Framer Motion

### Data and AI pipeline
- BIS catalogue ingestion
- clause and reference extraction
- index construction for dense + lexical retrieval
- multilingual request handling

## Demo and usage

### Run the backend

```bash
uvicorn app.api.main:app --port 8000
```

Open:
- API docs: http://localhost:8000/docs
- Main app: http://localhost:8000

### Run the web frontend

```bash
cd web
npm install
npm run dev
```

Then open:
- http://localhost:5173

### Example walkthroughs

```bash
python demo/walkthrough.py --scenario tubes --state Gujarat --pdf
python demo/walkthrough.py --text "Supply of HDPE pipes 110 mm PN 6 for rural water supply"
python demo/walkthrough.py --scenario thin --answers type="electric resistance welded"
```

## API overview

```text
GET  /health                  readiness + catalogue status
GET  /v1/meta                 UI metadata and evaluation stats
POST /v1/analyze              recommendation analysis payload
POST /v1/analyze/stream       streaming analysis response
POST /v1/analyze/upload       upload tender PDF / DOCX / text
POST /v1/document             generate PDF output
GET  /v1/standard/{is}        detail view for a standard
```

## Project structure

```text
Standards360/
├── app/                      # core analysis pipeline and API
├── common/                   # shared helpers
├── config/                  # config and validation data
├── contracts/                # API & domain contracts
├── data/                    # local catalogue and indexes
├── demo/                    # demo scenarios and walkthroughs
├── docs/                    # architecture, build manual, artifacts
├── eval/                    # gold set and evaluation harness
├── ingest/                  # crawler, parser, index builder
├── tests/                   # validation suite
├── web/                     # deployed frontend
├── .env.example             # environment template
├── requirements.txt         # Python dependencies
├── README.md                # project overview
├── CLAUDE.md                # build decisions and product rationale
└── LICENSE                  # licensing
```

## Local setup

### Python environment

```bash
python -m pip install -r requirements.txt
```

Copy the environment template:

```bash
copy .env.example .env
```

### Frontend setup

```bash
cd web
npm install
npm run build
```

## Validation

The current build has been validated with the production web build pipeline.

```bash
cd web
npm run build
```

This successfully compiles the TypeScript app and creates the production bundle in `web/dist`.

## Impact

Standards360 is positioned to reduce specification drafting errors, improve procurement quality, and make Indian Standards easier to discover and apply in real-world tendering environments. It brings together retrieval, compliance mapping, version awareness, and formal document generation in a single decision-support product.

## License

This project is distributed under the MIT License unless otherwise noted.

## Team and build note

This repository represents the final prototype state of the Standards360 solution, designed for demonstration, evaluation, and deployment readiness.

---

Built for the future of transparent, standards-aligned procurement.
