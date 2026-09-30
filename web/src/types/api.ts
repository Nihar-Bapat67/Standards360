/**
 * The published /v1 contract, mirrored from the Pydantic models in `app/api/main.py`.
 *
 * These are the only shapes the interface knows about. A procurement portal integrating with
 * Standards360 receives exactly the same objects, which is the point of D4: the website is one
 * client of the contract, not a privileged one.
 */

export type Persona = 'procurement' | 'manufacturer'
export type Band = 'high' | 'medium' | 'low'
export type Severity = 'high' | 'medium' | 'low'
export type AnalysisStatus = 'complete' | 'need_more_info' | 'no_match'

export interface Requirement {
  product: string
  category: string
  attributes: Record<string, string>
  cited_standards: string[]
  not_specified: string[]
  language: string
  source: string
  richness: string
  extracted_by: string
}

export interface Question {
  field: string
  ask: string
}

export interface Option {
  id: string
  label: string
  confidence: number
  band: Band
  standards: string[]
  default: boolean
  rationale: string
}

export interface AlliedStandard {
  is_number: string
  cited_as: string
  record_id: number
  title: string
  relation: string
  weight: number
  hops: number
  paths: string[][]
  evidence: string | null
  superseded: boolean
}

export interface Warning {
  severity: Severity
  cited?: string | null
  message: string
  action?: string | null
}

export interface Verdict {
  citation: string
  exists: boolean
  status: string
  relevant: boolean
  relevance_score: number
  verdict: 'keep' | 'replace' | 'remove' | 'add' | 'verify'
  replacement: string | null
  reason: string
  severity: Severity
  title: string
}

export interface Lab {
  name: string
  city: string
  state: string
  address: string | null
  phone: string | null
  email: string | null
  /** Straight line between town centres, in km. Absent when the location is unknown. */
  distance_km: number | null
  same_city: boolean
  same_state: boolean
  directions_url: string | null
  /** Always null. BIS publishes no opening times, and the interface says so rather than guessing. */
  hours: string | null
  /** Which of the standards asked about this laboratory is recognised for. */
  tests: string[]
}

/** Where C4.5 decided the user is, and how precisely. */
export interface Origin {
  label: string
  lat: number | null
  lon: number | null
  precision: 'device' | 'town' | 'state'
}

/** The answer to "where do I get this tested" (module C4.5, POST /v1/labs). */
export interface LabAnswer {
  standards: string[]
  total: number
  origin: Origin | null
  note: string
  labs: Lab[]
  hours_note: string
  attribution: string
}

export interface LabsRequest {
  standards: string[]
  lat?: number
  lon?: number
  place?: string
  limit?: number
}

export interface CertificationStandard {
  is_number: string
  record_id: number
  mandatory: boolean
  stated: boolean
  qco_status: string | null
  qco_date: string | null
  in_force: boolean
  scheme: string | null
  scheme_basis: string | null
  labs_available: number
  nearest_labs: Lab[]
}

export interface Certification {
  certification_required: boolean
  persona: string
  statement: string
  standards: CertificationStandard[]
  labs_available: number
  nearest_labs: Lab[]
  not_stated: string[]
}

export interface Evidence {
  standard: string
  clause: string
  role: string
  page: number | null
  quote: string
}

export interface Amendment {
  number: string
  year: string
  file?: string
}

export interface AnalyzeResponse {
  status: AnalysisStatus
  query: string
  requirement: Requirement
  questions: Question[]
  confidence: number
  band: Band
  confidence_drivers: string[]
  primary: string | null
  primary_title: string
  primary_as_cited: string
  amendments: Amendment[]
  options: Option[]
  allied: Record<string, AlliedStandard[]>
  warnings: Warning[]
  verdicts: Verdict[]
  certification: Certification | null
  evidence: Evidence[]
  explanation: string
  removed_by_guard: string[]
  pdf_url: string | null
  seconds: number
  intent: string
}

/** One `stage` event from POST /v1/analyze/stream. */
export interface StageEvent {
  module: string
  message: string
  detail: Record<string, unknown>
}

export interface HealthResponse {
  status: string
  index: { model: string; clauses: number; standards: number; built_at: string }
  catalogue: number
  llm: boolean
}

export interface MetaResponse {
  catalogue: {
    total: number | null
    current: number | null
    withdrawn: number | null
    with_replacement: number | null
    cross_references: number | null
    qco: number | null
    labs: number | null
    lab_states: number | null
  }
  index: { model: string; clauses: number; standards: number; built_at: string }
  evaluation: {
    gold_records?: number
    evaluated_at?: string
    'hit@1'?: number
    'hit@3'?: number
    'hit@5'?: number
    'mrr@5'?: number
  }
  sectors: string[]
}

export interface StandardDetail {
  resolved: {
    query: string
    exists: boolean
    current: string | null
    title: string
    withdrawn: boolean
    amendments: Amendment[]
    warnings: Warning[]
  }
  certification: Certification
  allied: Record<string, AlliedStandard[]>
}

export interface AnalyzeRequest {
  text: string
  lang?: string
  persona?: Persona
  output_mode?: string
  state?: string | null
  answers?: Record<string, string> | null
  history?: Array<{ role: 'user' | 'assistant'; text: string }>
  previous_requirement?: Requirement | null
}

export interface DocumentRequest extends AnalyzeRequest {
  option_id?: string
  mode?: 'annexure' | 'report'
  reference?: string | null
}

export interface TranscribeResponse {
  text: string
}

