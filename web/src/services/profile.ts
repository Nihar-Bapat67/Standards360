/**
 * The signed-in person's working profile, kept in this browser.
 *
 * This is not authentication. No session is issued and no password is stored or sent; what is kept
 * is the two facts the engine actually uses — the persona, which changes how certification is
 * worded, and the state, which decides which recognised laboratories are listed first — plus the
 * name and organisation used to address the person.
 *
 * The workspace is gated on the presence of this record. That gate is a workflow step, not a
 * security boundary, and nothing in the product should ever treat it as one.
 */

import type { Persona } from '../types/api'

export interface Profile {
  name: string
  email: string
  organisation: string
  role: Persona
  state: string
  savedAt: number
}

const KEY = 'standards360.profile.v1'

export const profile = {
  get(): Profile | null {
    try {
      const raw = window.localStorage.getItem(KEY)
      if (!raw) return null
      const parsed = JSON.parse(raw) as Partial<Profile>
      if (!parsed || typeof parsed.email !== 'string') return null
      return {
        name: parsed.name ?? '',
        email: parsed.email,
        organisation: parsed.organisation ?? '',
        role: parsed.role === 'manufacturer' ? 'manufacturer' : 'procurement',
        state: parsed.state ?? '',
        savedAt: parsed.savedAt ?? Date.now(),
      }
    } catch {
      return null
    }
  },

  save(value: Omit<Profile, 'savedAt'>): void {
    try {
      window.localStorage.setItem(KEY, JSON.stringify({ ...value, savedAt: Date.now() }))
    } catch {
      /* a blocked store is not worth stopping the person over */
    }
  },

  clear(): void {
    try {
      window.localStorage.removeItem(KEY)
    } catch {
      /* nothing to do */
    }
  },

  /** Initials for the avatar in the sidebar, falling back to the email when no name was given. */
  initials(value: Profile): string {
    const source = value.name.trim() || value.email
    const parts = source.split(/[\s@._-]+/).filter(Boolean)
    return (parts[0]?.[0] ?? '?').toUpperCase() + (parts[1]?.[0] ?? '').toUpperCase()
  },
}
