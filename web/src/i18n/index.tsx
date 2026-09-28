import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'

import { en, type Dictionary, type TranslationKey } from './en'
import { DEFAULT_LANGUAGE, LANGUAGES, isSupported } from './languages'
import { loaders } from './dictionaries'

/**
 * Interface translation.
 *
 * English is the source of truth in `en.ts`; every other language is a dictionary of the same keys.
 * A missing key falls back to English rather than showing the key itself, so a partially translated
 * language degrades into a readable mixture instead of a screen full of `results.showAll`.
 *
 * The chosen language does two things: it translates the interface here, and it travels to the API
 * as `lang` so the engine writes its answer in the same language. Detection still happens on the
 * server from what the person actually typed, so someone reading the interface in Tamil can paste a
 * Hindi tender and get a Tamil answer.
 */

const STORAGE_KEY = 'standards360.language.v1'

interface I18nValue {
  language: string
  setLanguage: (code: string) => void
  /** Translate a key, interpolating `{name}` placeholders. */
  t: (key: TranslationKey, vars?: Record<string, string | number>) => string
}

const I18nContext = createContext<I18nValue | null>(null)

function readStored(): string {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    if (isSupported(stored)) return stored as string
  } catch {
    /* private mode and blocked storage both land here */
  }

  // Nothing chosen yet: take the browser's preference when it is one we support.
  try {
    for (const tag of navigator.languages ?? []) {
      const base = tag.split('-')[0].toLowerCase()
      const code = base === 'or' ? 'od' : base // Odia is `od` here, matching Sarvam
      if (isSupported(code)) return code
    }
  } catch {
    /* navigator.languages is not always present */
  }
  return DEFAULT_LANGUAGE
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<string>(readStored)
  // The chosen language's dictionary, fetched on demand. Until it arrives — and for a language that
  // has none — every key falls back to English, so the interface is readable at all times rather
  // than blank while a chunk downloads.
  const [dictionary, setDictionary] = useState<Dictionary>({})

  const setLanguage = useCallback((code: string) => {
    if (!isSupported(code)) return
    setLanguageState(code)
    try {
      window.localStorage.setItem(STORAGE_KEY, code)
    } catch {
      /* the choice still applies for this session */
    }
  }, [])

  // `lang` on the document matters for hyphenation, for the font the browser picks for an Indic
  // script, and for a screen reader choosing a voice.
  useEffect(() => {
    document.documentElement.lang = language
  }, [language])

  useEffect(() => {
    let current = true
    const load = loaders[language]
    if (!load) {
      setDictionary({})
      return
    }
    load()
      .then((module) => {
        if (!current) return
        // The generated files export the dictionary under the language code.
        const found = (module as Record<string, unknown>)[language] ?? module.default
        setDictionary((found as Dictionary) ?? {})
      })
      .catch(() => current && setDictionary({}))
    return () => {
      current = false
    }
  }, [language])

  const t = useCallback(
    (key: TranslationKey, vars?: Record<string, string | number>) => {
      let text: string = dictionary[key] ?? en[key] ?? key
      if (vars) {
        for (const [name, value] of Object.entries(vars)) {
          text = text.replace(new RegExp(`\\{${name}\\}`, 'g'), String(value))
        }
      }
      return text
    },
    [dictionary],
  )

  const value = useMemo(() => ({ language, setLanguage, t }), [language, setLanguage, t])
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n(): I18nValue {
  const value = useContext(I18nContext)
  if (!value) throw new Error('useI18n must be used inside I18nProvider')
  return value
}

/** The common case: just the translate function. */
export function useT() {
  return useI18n().t
}

export { LANGUAGES, DEFAULT_LANGUAGE, isSupported }
export type { TranslationKey }
