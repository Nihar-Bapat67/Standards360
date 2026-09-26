import { useCallback, useRef, useState } from 'react'
import { api, ApiError } from '../services/api'
import type { AnalyzeRequest, AnalyzeResponse, Persona, StageEvent } from '../types/api'

export type RunState = 'idle' | 'running' | 'done' | 'error'

interface AnalysisState {
  state: RunState
  stages: StageEvent[]
  result: AnalyzeResponse | null
  error: string | null
}

const IDLE: AnalysisState = { state: 'idle', stages: [], result: null, error: null }

/**
 * Runs one analysis and reports the engine's own progress while it does.
 *
 * Text goes through the streaming endpoint so each module appears as it finishes; a file upload
 * cannot stream, so it reports a single stage and waits. Both end in the same AnalyzeResponse,
 * because there is one contract and the interface is only a client of it.
 */
export function useAnalysis() {
  const [analysis, setAnalysis] = useState<AnalysisState>(IDLE)
  const abort = useRef<AbortController | null>(null)

  const reset = useCallback(() => {
    abort.current?.abort()
    abort.current = null
    setAnalysis(IDLE)
  }, [])

  const runText = useCallback(
    async (request: AnalyzeRequest): Promise<AnalyzeResponse | null> => {
      abort.current?.abort()
      const controller = new AbortController()
      abort.current = controller
      setAnalysis({ state: 'running', stages: [], result: null, error: null })

      try {
        const result = await api.analyzeStream(
          request,
          (stage) => setAnalysis((prev) => ({ ...prev, stages: [...prev.stages, stage] })),
          controller.signal,
        )
        setAnalysis((prev) => ({ ...prev, state: 'done', result }))
        return result
      } catch (error) {
        if (controller.signal.aborted) return null
        setAnalysis((prev) => ({
          ...prev,
          state: 'error',
          error: error instanceof ApiError ? error.friendly : 'The engine failed while answering.',
        }))
        return null
      }
    },
    [],
  )

  const runFile = useCallback(
    async (file: File, persona: Persona, state?: string | null): Promise<AnalyzeResponse | null> => {
      abort.current?.abort()
      setAnalysis({
        state: 'running',
        stages: [{ module: 'B1', message: `Reading ${file.name}`, detail: {} }],
        result: null,
        error: null,
      })

      try {
        const result = await api.analyzeUpload(file, persona, state)
        setAnalysis((prev) => ({ ...prev, state: 'done', result }))
        return result
      } catch (error) {
        setAnalysis((prev) => ({
          ...prev,
          state: 'error',
          error: error instanceof ApiError ? error.friendly : 'The engine could not read that file.',
        }))
        return null
      }
    },
    [],
  )

  return { ...analysis, runText, runFile, reset }
}
