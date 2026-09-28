/**
 * Where to get a product tested: the interface for module C4.5.
 *
 * A manufacturer who has just been told that compulsory certification applies has one immediate
 * question, which is where they physically take the product. This answers it with the BIS
 * recognised-laboratory directory: the laboratory's name and address as BIS holds them, how far away
 * it is, a directions link, and a telephone number and email address to ring first.
 *
 * Three things this component is careful about.
 *
 * The distance is a straight line between two town centres, and every place it appears says so. The
 * road distance is longer, and the directions link is what gives it, so the figure here is only for
 * choosing between laboratories rather than for planning a journey.
 *
 * Location is never taken without being asked for. The list loads unordered first, and the user
 * chooses between sharing their device location and typing a town. If they refuse, or the browser
 * blocks it, the list stays exactly as useful as it was — only unsorted — and the directions links
 * still work, because Google Maps then starts from wherever the user is.
 *
 * Opening times are not shown, because BIS does not publish them. The note says that plainly instead
 * of leaving a reader to assume the field was simply forgotten.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { api, ApiError } from '../services/api'
import type { Lab, LabAnswer } from '../types/api'
import { Icon, Label } from './ui'

type Status = 'idle' | 'loading' | 'locating' | 'error'

/** How long to wait for a device coordinate before giving up and saying so. */
const GEOLOCATION_TIMEOUT_MS = 12_000

export function TestingLabs({ standards, persona }: { standards: string[]; persona: string }) {
  const [answer, setAnswer] = useState<LabAnswer | null>(null)
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState('')
  const [place, setPlace] = useState('')
  const [expanded, setExpanded] = useState(false)

  // The standards array is rebuilt on every render of the parent, so the effect keys on its
  // contents rather than its identity.
  const key = standards.join('|')
  const latest = useRef(0)

  const load = useCallback(
    async (where: { lat?: number; lon?: number; place?: string }) => {
      if (standards.length === 0) return
      const ticket = ++latest.current
      setStatus('loading')
      setError('')
      try {
        const result = await api.labs({ standards, limit: 24, ...where })
        if (ticket !== latest.current) return // a later request already answered
        setAnswer(result)
        setStatus('idle')
      } catch (cause) {
        if (ticket !== latest.current) return
        setError(cause instanceof ApiError ? cause.friendly : 'The laboratory list could not be loaded.')
        setStatus('error')
      }
    },
    [key], // eslint-disable-line react-hooks/exhaustive-deps
  )

  useEffect(() => {
    void load({})
  }, [load])

  function useMyLocation() {
    if (!('geolocation' in navigator)) {
      setError('This browser cannot share a location. Type your town instead.')
      setStatus('error')
      return
    }
    setStatus('locating')
    setError('')
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setPlace('')
        void load({ lat: position.coords.latitude, lon: position.coords.longitude })
      },
      (cause) => {
        setStatus('error')
        setError(
          cause.code === cause.PERMISSION_DENIED
            ? 'Location access was declined. Type your town instead — the directions links work either way.'
            : 'Your location could not be read. Type your town instead.',
        )
      },
      { timeout: GEOLOCATION_TIMEOUT_MS, maximumAge: 300_000 },
    )
  }

  if (standards.length === 0) return null

  const labs = answer?.labs ?? []
  const shown = expanded ? labs : labs.slice(0, 6)
  const busy = status === 'loading' || status === 'locating'

  return (
    <div className="flex flex-col gap-4">
      {/* ── the location control ─────────────────────────────────────── */}
      <div className="card flex flex-col gap-4 p-5 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <Label>
            {answer ? `${answer.total} recognised ${answer.total === 1 ? 'laboratory' : 'laboratories'}` : 'Laboratories'}
          </Label>
          <p className="mt-1.5 text-[13px] leading-relaxed text-secondary">
            {persona === 'manufacturer'
              ? 'BIS-recognised laboratories that can test your product against these standards.'
              : 'BIS-recognised laboratories a bidder can have the product tested at.'}
          </p>
        </div>

        <form
          className="flex shrink-0 flex-wrap items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            void load(place.trim() ? { place: place.trim() } : {})
          }}
        >
          <button
            type="button"
            onClick={useMyLocation}
            disabled={busy}
            className="btn btn-ghost h-9 px-3.5 text-[12.5px]"
          >
            <Icon.Locate />
            {status === 'locating' ? 'Locating' : 'Use my location'}
          </button>

          <div className="flex h-9 items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-3">
            <span className="text-muted">
              <Icon.Search />
            </span>
            <input
              value={place}
              onChange={(event) => setPlace(event.target.value)}
              placeholder="or type your town"
              aria-label="Your town or state"
              className="w-[9.5rem] bg-transparent text-[13px] text-text outline-none placeholder:text-muted"
            />
          </div>

          <button type="submit" disabled={busy} className="btn btn-primary h-9 px-4 text-[12.5px]">
            {status === 'loading' ? 'Finding' : 'Find nearest'}
          </button>
        </form>
      </div>

      {error && (
        <p className="px-1 text-[12.5px] leading-relaxed text-red" role="status">
          {error}
        </p>
      )}

      {answer && answer.note && (
        <p className="px-1 text-[12.5px] leading-relaxed text-muted" role="status">
          {answer.note}
        </p>
      )}

      {/* ── the laboratories ─────────────────────────────────────────── */}
      {labs.length > 0 && (
        <>
          <ul className="grid gap-3 lg:grid-cols-2">
            {shown.map((lab) => (
              <LabCard key={`${lab.name}-${lab.city}`} lab={lab} />
            ))}
          </ul>

          {labs.length > shown.length && (
            <button
              type="button"
              onClick={() => setExpanded(true)}
              className="btn btn-ghost h-9 self-start px-4 text-[12.5px]"
            >
              Show the other {labs.length - shown.length}
            </button>
          )}
        </>
      )}

      {answer && (
        <p className="border-t border-white/8 px-1 pt-4 text-[11.5px] leading-relaxed text-muted">
          {answer.hours_note}
          {answer.attribution && ` Distances use town coordinates from OpenStreetMap.`}
        </p>
      )}
    </div>
  )
}

/* ──────────────────────────────────────────────────────────────────────────
   One laboratory
   ────────────────────────────────────────────────────────────────────── */

function LabCard({ lab }: { lab: Lab }) {
  return (
    <li className="card flex flex-col gap-3.5 p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[14px] font-medium leading-snug text-text">{lab.name}</p>
          <p className="mt-0.5 text-[12px] text-muted">
            {[lab.city, lab.state].filter(Boolean).join(', ')}
          </p>
        </div>
        <Distance lab={lab} />
      </div>

      {lab.address && (
        <p className="whitespace-pre-line text-[12.5px] leading-relaxed text-secondary">{lab.address}</p>
      )}

      {lab.tests.length > 0 && (
        <p className="mono text-[11px] leading-relaxed text-muted">
          Recognised for {lab.tests.join(' · ')}
        </p>
      )}

      <div className="mt-auto flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-white/8 pt-3.5">
        {lab.phone && (
          <a
            href={`tel:${lab.phone.replace(/\s+/g, '')}`}
            className="flex items-center gap-1.5 text-[12.5px] text-secondary transition-colors hover:text-text"
          >
            <span className="text-muted">
              <Icon.Phone />
            </span>
            {lab.phone}
          </a>
        )}
        {lab.email && (
          <a
            href={`mailto:${lab.email}`}
            className="flex min-w-0 items-center gap-1.5 text-[12.5px] text-secondary transition-colors hover:text-text"
          >
            <span className="shrink-0 text-muted">
              <Icon.Mail />
            </span>
            <span className="truncate">{lab.email}</span>
          </a>
        )}
        {lab.directions_url && (
          <a
            href={lab.directions_url}
            target="_blank"
            rel="noreferrer noopener"
            className="ml-auto flex items-center gap-1.5 text-[12.5px] text-amber transition-opacity hover:opacity-75"
          >
            Directions
            <Icon.Arrow />
          </a>
        )}
      </div>
    </li>
  )
}

/** The distance badge, which says what kind of distance it is rather than only a number. */
function Distance({ lab }: { lab: Lab }) {
  if (lab.same_city) {
    return (
      <span className="chip chip-warm shrink-0 whitespace-nowrap">In your city</span>
    )
  }
  if (lab.distance_km === null) return null
  return (
    <span className="shrink-0 text-right">
      <span className="mono block text-[13px] text-text">{lab.distance_km.toLocaleString('en-US')} km</span>
      <span className="block text-[10.5px] leading-tight text-muted">straight line</span>
    </span>
  )
}
