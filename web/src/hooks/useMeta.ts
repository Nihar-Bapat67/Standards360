import { useEffect, useState } from 'react'
import { api, ApiError } from '../services/api'
import type { MetaResponse } from '../types/api'

interface MetaState {
  data: MetaResponse | null
  loading: boolean
  error: string | null
}

/**
 * The figures the landing page prints, fetched from the live catalogue.
 *
 * Nothing on the marketing page is typed into the markup. If the engine cannot be reached the
 * numbers are simply absent rather than replaced by plausible-looking constants, because a figure
 * we cannot produce on demand is a figure we should not be showing.
 */
export function useMeta(): MetaState {
  const [state, setState] = useState<MetaState>({ data: null, loading: true, error: null })

  useEffect(() => {
    let alive = true
    api
      .meta()
      .then((data) => alive && setState({ data, loading: false, error: null }))
      .catch((error: unknown) =>
        alive &&
        setState({
          data: null,
          loading: false,
          error: error instanceof ApiError ? error.friendly : 'Could not reach the engine.',
        }),
      )
    return () => {
      alive = false
    }
  }, [])

  return state
}
