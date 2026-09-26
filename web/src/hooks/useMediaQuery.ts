import { useEffect, useState } from 'react'

/**
 * Whether a CSS media query currently matches.
 *
 * Used only where the difference is content rather than layout — a shorter placeholder on a phone,
 * for instance. Anything that is purely visual should be a Tailwind breakpoint class instead, so
 * that it works before JavaScript has run.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return false
    return window.matchMedia(query).matches
  })

  useEffect(() => {
    if (!window.matchMedia) return
    const list = window.matchMedia(query)
    const onChange = (event: MediaQueryListEvent) => setMatches(event.matches)
    setMatches(list.matches)
    list.addEventListener('change', onChange)
    return () => list.removeEventListener('change', onChange)
  }, [query])

  return matches
}
