/**
 * The service layer. Every call the interface makes to the engine passes through here.
 *
 * No component constructs a URL, reads a response body, or decides what an error means. That keeps
 * the contract in one file: when `app/api/main.py` changes, exactly one file here changes with it.
 */

import type {
  AnalyzeRequest,
  AnalyzeResponse,
  DocumentRequest,
  HealthResponse,
  LabAnswer,
  LabsRequest,
  MetaResponse,
  StageEvent,
  StandardDetail,
  TranscribeResponse,
} from '../types/api'

/**
 * Empty in both environments, and deliberately so: in development Vite proxies /v1 to the API, and
 * in production FastAPI serves this bundle itself. An absolute URL would only be needed if the two
 * were split across origins, which is what VITE_API_BASE is for.
 */
const BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/$/, '')

/** A failure the interface can show a person, rather than a stack trace. */
export class ApiError extends Error {
  readonly status: number
  readonly detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }

  /** What to put on screen. Technical causes are translated; the engine's own words are kept. */
  get friendly(): string {
    if (this.status === 0) {
      return 'The engine is not answering. If you are running it yourself, check that the API is up on port 8000.'
    }
    if (this.status === 413) return 'That file is larger than 25 MB. Try the specification pages on their own.'
    if (this.status === 415) return 'That file type cannot be read. Use a PDF, DOCX, text file or a screenshot.'
    if (this.status === 422) return this.detail || 'There was not enough here to analyse.'
    if (this.status === 503) {
      return 'The engine is still loading its models. This takes about a minute after a restart.'
    }
    if (this.status >= 500) return 'The engine failed while answering. The details are in the server log.'
    return this.detail || 'Something went wrong.'
  }
}

const TIMEOUT_MS = 120_000

async function parseError(response: Response): Promise<ApiError> {
  let detail = response.statusText
  try {
    const body = await response.json()
    if (typeof body?.detail === 'string') detail = body.detail
    else if (Array.isArray(body?.detail)) detail = body.detail.map((d: { msg?: string }) => d.msg).join('; ')
  } catch {
    /* a non-JSON error body is not worth failing over */
  }
  return new ApiError(response.status, detail)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), TIMEOUT_MS)
  try {
    const response = await fetch(`${BASE}${path}`, { ...init, signal: controller.signal })
    if (!response.ok) throw await parseError(response)
    return (await response.json()) as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError(0, 'The request took too long and was stopped.')
    }
    throw new ApiError(0, 'Could not reach the engine.')
  } finally {
    window.clearTimeout(timer)
  }
}

const CONTEXT_FIELDS = ['history', 'previous_requirement'] as const

async function isLegacyContextRejection(response: Response): Promise<boolean> {
  if (response.status !== 422) return false
  try {
    const detail = (await response.clone().json()).detail
    if (!Array.isArray(detail) || detail.length === 0) return false
    return detail.every((error: { type?: string; loc?: unknown[] }) =>
      error.type === 'extra_forbidden'
      && CONTEXT_FIELDS.includes(error.loc?.[error.loc.length - 1] as typeof CONTEXT_FIELDS[number]),
    )
  } catch {
    return false
  }
}

function withoutConversationContext(body: AnalyzeRequest): AnalyzeRequest {
  const { history: _history, previous_requirement: _requirement, ...legacyBody } = body
  return legacyBody
}

async function postAnalyze(path: string, body: AnalyzeRequest, signal?: AbortSignal): Promise<Response> {
  const send = (requestBody: AnalyzeRequest) => fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(requestBody),
    signal,
  })
  let response = await send(body).catch(() => {
    throw new ApiError(0, 'Could not reach the engine.')
  })
  if (await isLegacyContextRejection(response)) {
    response = await send(withoutConversationContext(body)).catch(() => {
      throw new ApiError(0, 'Could not reach the engine.')
    })
  }
  return response
}

function withDefaultIntent(result: AnalyzeResponse): AnalyzeResponse {
  return { ...result, intent: result.intent || 'standards_recommendation' }
}

async function postUpload(form: FormData): Promise<Response> {
  const send = () => fetch(`${BASE}/v1/analyze/upload`, { method: 'POST', body: form })
  let response = await send().catch(() => {
    throw new ApiError(0, 'Could not reach the engine.')
  })
  if (form.has('history') || form.has('previous_requirement')) {
    if (await isLegacyContextRejection(response)) {
      form.delete('history')
      form.delete('previous_requirement')
      response = await send().catch(() => {
        throw new ApiError(0, 'Could not reach the engine.')
      })
    }
  }
  return response
}

export const api = {
  health: () => request<HealthResponse>('/health'),

  meta: () => request<MetaResponse>('/v1/meta'),

  uiDictionary: (language: string) => request<Record<string, string>>(`/v1/i18n/${language}`),

  analyze: async (body: AnalyzeRequest) => {
    const response = await postAnalyze('/v1/analyze', body)
    if (!response.ok) throw await parseError(response)
    return withDefaultIntent((await response.json()) as AnalyzeResponse)
  },

  analyzeUpload: (
    file: File,
    persona: string,
    state?: string | null,
    lang?: string,
    context?: Pick<AnalyzeRequest, 'history' | 'previous_requirement'>,
  ) => {
    const form = new FormData()
    form.append('file', file)
    form.append('persona', persona)
    if (state) form.append('state', state)
    if (lang) form.append('lang', lang)
    if (context?.history) form.append('history', JSON.stringify(context.history))
    if (context?.previous_requirement) {
      form.append('previous_requirement', JSON.stringify(context.previous_requirement))
    }
    return postUpload(form).then(async (response) => {
      if (!response.ok) throw await parseError(response)
      return withDefaultIntent((await response.json()) as AnalyzeResponse)
    })
  },

  standard: (isNumber: string) =>
    request<StandardDetail>(`/v1/standard/${encodeURIComponent(isNumber)}`),

  /**
   * Module C4.5: the BIS-recognised laboratories that can test these standards.
   *
   * Deliberately a separate call from `analyze`. The user decides whether to share their location
   * after they have seen which standards apply, and answering that follow-up is a catalogue lookup
   * rather than another run of the pipeline.
   */
  labs: (body: LabsRequest) =>
    request<LabAnswer>('/v1/labs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),

  /**
   * The analysis, reported stage by stage.
   *
   * The engine takes several seconds because retrieval embeds the query and the composer calls a
   * language model. Rather than hide that behind a spinner, the pipeline reports each module as it
   * finishes and this reads those reports as they arrive. `onStage` fires per module; the promise
   * resolves with the same object `analyze` would have returned.
   */
  analyzeStream: async (
    body: AnalyzeRequest,
    onStage: (stage: StageEvent) => void,
    signal?: AbortSignal,
  ): Promise<AnalyzeResponse> => {
    const response = await postAnalyze('/v1/analyze/stream', body, signal)

    if (!response.ok) throw await parseError(response)
    if (!response.body) throw new ApiError(0, 'The engine returned no data.')

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let result: AnalyzeResponse | null = null

    // Server-Sent Events arrive as frames separated by a blank line. A chunk can split a frame in
    // half, so whatever follows the last blank line is kept for the next read.
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      const frames = buffer.split('\n\n')
      buffer = frames.pop() ?? ''

      for (const frame of frames) {
        const nameLine = frame.split('\n').find((line) => line.startsWith('event:'))
        const dataLine = frame.split('\n').find((line) => line.startsWith('data:'))
        if (!nameLine || !dataLine) continue

        const name = nameLine.slice(6).trim()
        let payload: unknown
        try {
          payload = JSON.parse(dataLine.slice(5).trim())
        } catch {
          continue
        }

        if (name === 'stage') onStage(payload as StageEvent)
        else if (name === 'result') result = payload as AnalyzeResponse
        else if (name === 'error') {
          throw new ApiError(500, (payload as { detail?: string }).detail ?? 'The engine failed.')
        }
      }
    }

    if (!result) throw new ApiError(0, 'The engine closed the connection before answering.')
    return withDefaultIntent(result)
  },

  /** The PDF, returned as a blob so the browser can save it without a round trip through a URL. */
  document: async (body: DocumentRequest): Promise<{ blob: Blob; filename: string }> => {
    const response = await fetch(`${BASE}/v1/document`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).catch(() => {
      throw new ApiError(0, 'Could not reach the engine.')
    })
    if (!response.ok) throw await parseError(response)

    const disposition = response.headers.get('Content-Disposition') ?? ''
    const match = /filename="?([^"]+)"?/.exec(disposition)
    return { blob: await response.blob(), filename: match?.[1] ?? 'standards360.pdf' }
  },

  documentUpload: async (
    file: File,
    opts: { persona: string; option_id: string; mode: 'annexure' | 'report'; reference?: string | null },
  ): Promise<{ blob: Blob; filename: string }> => {
    const form = new FormData()
    form.append('file', file)
    form.append('persona', opts.persona)
    form.append('option_id', opts.option_id)
    form.append('mode', opts.mode)
    if (opts.reference) form.append('reference', opts.reference)

    const response = await fetch(`${BASE}/v1/document/upload`, { method: 'POST', body: form }).catch(() => {
      throw new ApiError(0, 'Could not reach the engine.')
    })
    if (!response.ok) throw await parseError(response)

    const disposition = response.headers.get('Content-Disposition') ?? ''
    const match = /filename="?([^"]+)"?/.exec(disposition)
    return { blob: await response.blob(), filename: match?.[1] ?? 'standards360.pdf' }
  },

  transcribe: async (file: Blob, lang?: string): Promise<TranscribeResponse> => {
    const form = new FormData()
    const ext = file.type.includes('mp4') ? 'mp4' : file.type.includes('wav') ? 'wav' : 'webm'
    form.append('file', file, `audio.${ext}`)
    if (lang && lang !== 'auto') form.append('language', lang)
    const response = await fetch(`${BASE}/v1/transcribe`, {
      method: 'POST',
      body: form,
    }).catch(() => {
      throw new ApiError(0, 'Could not reach the engine.')
    })
    if (!response.ok) throw await parseError(response)
    return (await response.json()) as TranscribeResponse
  },
}

/** Hand a generated document to the browser and clean up the object URL afterwards. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
