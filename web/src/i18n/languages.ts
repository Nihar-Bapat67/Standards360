/**
 * The languages the interface offers.
 *
 * Kept in step with `app/understand/language.py`, which is the authority: the codes here are what
 * the API accepts as `lang`, and Odia is `od` rather than the `or` of ISO 639-1 because that is
 * what Sarvam's endpoints expect.
 */

export interface LanguageOption {
  code: string
  english: string
  /** The language's name in its own script, which is what a selector should show. */
  native: string
}

export const LANGUAGES: readonly LanguageOption[] = [
  { code: 'en', english: 'English', native: 'English' },
  { code: 'hi', english: 'Hindi', native: 'हिन्दी' },
  { code: 'mr', english: 'Marathi', native: 'मराठी' },
  { code: 'gu', english: 'Gujarati', native: 'ગુજરાતી' },
  { code: 'bn', english: 'Bengali', native: 'বাংলা' },
  { code: 'ta', english: 'Tamil', native: 'தமிழ்' },
  { code: 'te', english: 'Telugu', native: 'తెలుగు' },
  { code: 'kn', english: 'Kannada', native: 'ಕನ್ನಡ' },
  { code: 'ml', english: 'Malayalam', native: 'മലയാളം' },
  { code: 'pa', english: 'Punjabi', native: 'ਪੰਜਾਬੀ' },
  { code: 'od', english: 'Odia', native: 'ଓଡ଼ିଆ' },
  { code: 'as', english: 'Assamese', native: 'অসমীয়া' },
] as const

export type LanguageCode = (typeof LANGUAGES)[number]['code']

export const DEFAULT_LANGUAGE = 'en'

export function isSupported(code: string | null | undefined): boolean {
  return !!code && LANGUAGES.some((language) => language.code === code)
}

export function languageOf(code: string): LanguageOption {
  return LANGUAGES.find((language) => language.code === code) ?? LANGUAGES[0]
}
