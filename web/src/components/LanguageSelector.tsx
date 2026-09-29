import { useEffect, useRef, useState } from 'react'

import { LANGUAGES, useI18n } from '../i18n'

/**
 * The language switch.
 *
 * Compact by design — it sits in a navbar beside the primary action and must not compete with it.
 * Each language is written in its own script, because someone looking for Tamil is looking for
 * "தமிழ்", not for the word "Tamil".
 *
 * Every supported language is offered. The dictionary is translated by the API when configured,
 * with checked-in dictionaries as an offline fallback.
 */
export function LanguageSelector({ compact = false }: { compact?: boolean }) {
  const { language, setLanguage, t } = useI18n()
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)

  const current = LANGUAGES.find((l) => l.code === language) ?? LANGUAGES[0]

  useEffect(() => {
    if (!open) return
    const away = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false)
    }
    const escape = (event: KeyboardEvent) => event.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', away)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('mousedown', away)
      document.removeEventListener('keydown', escape)
    }
  }, [open])

  return (
    <div ref={box} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={t('language.label')}
        className={`flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.035] text-secondary transition-colors hover:border-white/20 hover:text-text ${
          compact ? 'h-9 px-2.5 text-[12px]' : 'h-10 px-3 text-[13px]'
        }`}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden>
          <circle cx="12" cy="12" r="9" />
          <path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18" />
        </svg>
        <span className="max-w-[7rem] truncate">{current.native}</span>
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          aria-hidden
          className={`transition-transform duration-300 ${open ? 'rotate-180' : ''}`}
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>

      {open && (
        <ul
          role="listbox"
          aria-label={t('language.label')}
          className="card absolute right-0 top-full z-50 mt-2 max-h-[min(70vh,26rem)] w-56 overflow-y-auto p-1.5"
        >
          {LANGUAGES.map((option) => {
            const active = option.code === language
            return (
              <li key={option.code}>
                <button
                  type="button"
                  role="option"
                  aria-selected={active}
                  onClick={() => {
                    setLanguage(option.code)
                    setOpen(false)
                  }}
                  className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left transition-colors ${
                    active ? 'bg-white/10 text-text' : 'text-secondary hover:bg-white/5 hover:text-text'
                  }`}
                >
                  <span className="flex-1 truncate text-[13.5px]">{option.native}</span>
                  <span className="shrink-0 text-[11px] text-muted">{option.english}</span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
