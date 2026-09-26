import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { profile } from '../services/profile'

/**
 * Sends someone without a profile to the sign-in page, remembering where they were going.
 *
 * To be plain about what this is: a workflow gate, not a security boundary. There is no server-side
 * authentication behind it, so it keeps the flow coherent rather than keeping anyone out. Nothing
 * that matters should ever be protected by it.
 */
export function RequireProfile({ children }: { children: ReactNode }) {
  const location = useLocation()

  if (!profile.get()) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <>{children}</>
}
