import { type FormEvent, type ReactNode, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import { Atmosphere } from '../components/Atmosphere'
import { ProductName } from '../components/ProductName'
import { LanguageSelector } from '../components/LanguageSelector'
import { Icon, Label } from '../components/ui'
import { profile } from '../services/profile'
import { useT } from '../i18n'

/**
 * Sign in and create an account.
 *
 * The layout follows the supplied reference — form on the left, a brand panel on the right, fields
 * with the label sitting above the value and an icon on the trailing edge — rendered in this
 * product's own palette rather than the reference's blue, and over the same background every other
 * screen uses.
 *
 * What this page does NOT do, deliberately: there is no server-side authentication behind it. No
 * session is issued, nothing is verified, and no password leaves the browser. What it collects is
 * kept in this browser as a profile, and the page says so on screen rather than implying an account
 * exists. Wiring it to real accounts means OAuth credentials and session handling in the API, which
 * is a separate piece of work.
 */

type Mode = 'signin' | 'signup'

const STATES = [
  'Andhra Pradesh', 'Assam', 'Bihar', 'Chhattisgarh', 'Delhi', 'Goa', 'Gujarat', 'Haryana',
  'Himachal Pradesh', 'Jharkhand', 'Karnataka', 'Kerala', 'Madhya Pradesh', 'Maharashtra',
  'Odisha', 'Punjab', 'Rajasthan', 'Tamil Nadu', 'Telangana', 'Uttar Pradesh', 'Uttarakhand',
  'West Bengal',
]

interface Values {
  firstName: string
  lastName: string
  email: string
  organisation: string
  role: 'procurement' | 'manufacturer'
  state: string
  password: string
  confirm: string
}

const EMPTY: Values = {
  firstName: '',
  lastName: '',
  email: '',
  organisation: '',
  role: 'procurement',
  state: '',
  password: '',
  confirm: '',
}

export function Auth({ mode: initial = 'signin' }: { mode?: Mode }) {
  const navigate = useNavigate()
  const t = useT()
  const location = useLocation()
  // Where they were going before the gate sent them here.
  const destination = (location.state as { from?: string } | null)?.from ?? '/workspace'
  const [mode, setMode] = useState<Mode>(initial)
  const [values, setValues] = useState<Values>(EMPTY)
  const [errors, setErrors] = useState<Partial<Record<keyof Values, string>>>({})
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [showPassword, setShowPassword] = useState(false)

  const signup = mode === 'signup'
  const set = (key: keyof Values) => (value: string) => {
    setValues((prev) => ({ ...prev, [key]: value }))
    setErrors((prev) => ({ ...prev, [key]: undefined }))
  }

  const validate = useMemo(
    () => (): Partial<Record<keyof Values, string>> => {
      const found: Partial<Record<keyof Values, string>> = {}
        if (!values.email.trim()) found.email = t('auth.emailRequired')
      else if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(values.email.trim()))
          found.email = t('auth.emailInvalid')

        if (!values.password) found.password = t('auth.passwordRequired')
      else if (signup && values.password.length < 8)
          found.password = t('auth.passwordShort')

      if (signup) {
        if (!values.firstName.trim()) found.firstName = t('auth.required')
        if (!values.lastName.trim()) found.lastName = t('auth.required')
        if (!values.organisation.trim()) found.organisation = t('auth.required')
        if (!values.state) found.state = t('auth.stateRequired')
        if (values.confirm !== values.password) found.confirm = t('auth.passwordMismatch')
      }
      return found
    },
    [values, signup],
  )

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setNotice(null)
    const found = validate()
    setErrors(found)
    if (Object.keys(found).length > 0) return

    setBusy(true)
    // The password is never stored and never sent. Only the working preferences are kept, because
    // they are the two things the engine actually uses: the persona changes how certification is
    // worded, and the state decides which recognised laboratories are listed first.
    profile.save({
      name: `${values.firstName} ${values.lastName}`.trim(),
      email: values.email.trim(),
      organisation: values.organisation.trim(),
      role: values.role,
      state: values.state,
    })
    setBusy(false)
    navigate(destination, { replace: true })
  }

  return (
    <div className="relative min-h-dvh">
      <Atmosphere variant="hero" />

      <header className="relative z-10">
        <nav className="mx-auto flex h-16 max-w-6xl items-center gap-7 px-5 sm:px-8">
          <ProductName />
          <Link to="/" className="hidden text-[13px] text-secondary transition-colors hover:text-text sm:block">
            {t('nav.home')}
          </Link>
          <div className="flex-1" />
          <LanguageSelector compact />
        </nav>
      </header>

      <main className="relative z-10 mx-auto grid max-w-6xl gap-10 px-5 pb-16 pt-6 sm:px-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.85fr)] lg:gap-14 lg:pt-10">
        {/* ── the form ─────────────────────────────────────────────── */}
        <section className="w-full max-w-[560px]">
          <Label className="text-amber">{signup ? t('auth.startFree') : t('auth.welcomeBack')}</Label>

          <h1 className="mt-4 text-[clamp(2rem,4.6vw,2.9rem)] font-semibold leading-[1.08] tracking-[-0.03em]">
            {signup ? t('auth.createAccount') : t('auth.signIn')}
            <span className="text-ember">.</span>
          </h1>

          <p className="mt-3.5 text-[14px] text-secondary">
            {signup ? t('auth.alreadyMember') : t('auth.noAccount')}{' '}
            <button
              type="button"
              onClick={() => {
                setMode(signup ? 'signin' : 'signup')
                setErrors({})
                setNotice(null)
              }}
              className="text-amber underline-offset-4 transition-colors hover:text-coral hover:underline"
            >
              {signup ? t('auth.logIn') : t('auth.createOne')}
            </button>
          </p>

          <button
            type="button"
            onClick={() =>
              setNotice(
                t('auth.googleUnavailable'),
              )
            }
            className="mt-7 flex h-12 w-full items-center justify-center gap-3 rounded-[14px] border border-white/10 bg-white/[0.045] text-[14px] font-medium text-text transition-colors hover:border-white/20 hover:bg-white/[0.07]"
          >
            <GoogleMark />
            {t('auth.google')}
          </button>

          <div className="my-6 flex items-center gap-4">
            <span className="h-px flex-1 bg-white/8" />
            <span className="mono text-[10.5px] uppercase tracking-[0.14em] text-muted">{t('auth.or')}</span>
            <span className="h-px flex-1 bg-white/8" />
          </div>

          <form onSubmit={submit} noValidate className="flex flex-col gap-3">
            {signup && (
              <div className="grid gap-3 sm:grid-cols-2">
                <Field
                  id="firstName"
                  label={t('auth.firstName')}
                  value={values.firstName}
                  onChange={set('firstName')}
                  error={errors.firstName}
                  autoComplete="given-name"
                  icon={<PersonIcon />}
                />
                <Field
                  id="lastName"
                  label={t('auth.lastName')}
                  value={values.lastName}
                  onChange={set('lastName')}
                  error={errors.lastName}
                  autoComplete="family-name"
                  icon={<PersonIcon />}
                />
              </div>
            )}

            <Field
              id="email"
              label={signup ? t('auth.officialEmail') : t('auth.email')}
              type="email"
              value={values.email}
              onChange={set('email')}
              error={errors.email}
              autoComplete="email"
              icon={<MailIcon />}
            />

            {signup && (
              <>
                <Field
                  id="organisation"
                  label={t('auth.organisation')}
                  value={values.organisation}
                  onChange={set('organisation')}
                  error={errors.organisation}
                  autoComplete="organization"
                  icon={<BuildingIcon />}
                />

                <fieldset className="rounded-[14px] border border-white/10 bg-white/[0.035] px-4 py-3">
                  <legend className="px-1 text-[11px] text-muted">{t('auth.role')}</legend>
                  <div className="mt-1.5 grid grid-cols-2 gap-1.5">
                    {([
                      ['procurement', t('auth.roleProcurement')],
                      ['manufacturer', t('auth.roleManufacturer')],
                    ] as const).map(([value, text]) => (
                      <button
                        key={value}
                        type="button"
                        role="radio"
                        aria-checked={values.role === value}
                        onClick={() => setValues((prev) => ({ ...prev, role: value }))}
                        className={`rounded-lg px-3 py-2 text-[12.5px] transition-colors ${
                          values.role === value
                            ? 'bg-white/10 text-text'
                            : 'text-secondary hover:bg-white/5 hover:text-text'
                        }`}
                      >
                        {text}
                      </button>
                    ))}
                  </div>
                </fieldset>

                <SelectField
                  id="state"
                  label={t('auth.state')}
                  value={values.state}
                  onChange={set('state')}
                  error={errors.state}
                  options={STATES}
                />
              </>
            )}

            <Field
              id="password"
              label={t('auth.password')}
              type={showPassword ? 'text' : 'password'}
              value={values.password}
              onChange={set('password')}
              error={errors.password}
              autoComplete={signup ? 'new-password' : 'current-password'}
              icon={
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? t('auth.hidePassword') : t('auth.showPassword')}
                  className="text-muted transition-colors hover:text-text"
                >
                  {showPassword ? <EyeOffIcon /> : <EyeIcon />}
                </button>
              }
            />

            {signup && (
              <Field
                id="confirm"
                label={t('auth.confirmPassword')}
                type={showPassword ? 'text' : 'password'}
                value={values.confirm}
                onChange={set('confirm')}
                error={errors.confirm}
                autoComplete="new-password"
                icon={<LockIcon />}
              />
            )}

            {notice && (
              <p
                role="status"
                className="rounded-[14px] border border-[rgb(255_138_91/0.28)] bg-[rgb(255_138_91/0.07)] px-4 py-3 text-[13px] leading-relaxed text-secondary"
              >
                {notice}
              </p>
            )}

            <div className="mt-2 flex flex-col gap-2.5 sm:flex-row">
              <Link to="/" className="btn btn-ghost flex-1">
                {t('auth.backHome')}
              </Link>
              <button type="submit" disabled={busy} className="btn btn-primary flex-1">
                {busy ? t('auth.working') : signup ? t('auth.createAccount') : t('auth.logIn')}
                {!busy && <Icon.Arrow />}
              </button>
            </div>
          </form>

          <p className="mt-5 text-[11.5px] leading-relaxed text-muted">
            {t('auth.notice')}
          </p>
        </section>

        {/* ── the brand panel ──────────────────────────────────────── */}
        <aside className="card relative hidden overflow-hidden lg:block lg:min-h-[600px]">{/* A floor height, so the panel does not collapse to a stub in the shorter sign-in mode. */}
          <svg
            aria-hidden
            className="pointer-events-none absolute inset-0 h-full w-full"
            viewBox="0 0 400 700"
            preserveAspectRatio="none"
          >
            <path
              d="M -40 0 C 210 130, 40 330, 250 470 S 300 640, 240 760"
              fill="none"
              stroke="rgb(255 255 255 / 0.16)"
              strokeWidth="1.2"
              strokeDasharray="5 7"
            />
          </svg>

          <div className="relative flex h-full flex-col justify-between p-9">
            <div>
              <Label className="text-amber">{t('auth.panel.label')}</Label>
              <p className="mt-5 text-[19px] font-medium leading-[1.4] tracking-[-0.01em] text-text">
                {t('auth.panel.heading')}
              </p>

              <ul className="mt-8 flex flex-col gap-5">
                {([
                  { head: 'auth.panel.item1', body: 'auth.panel.item1body' },
                  { head: 'auth.panel.item2', body: 'auth.panel.item2body' },
                  { head: 'auth.panel.item3', body: 'auth.panel.item3body' },
                ] as const).map((item) => (
                  <li key={item.head} className="flex gap-3.5">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-amber" />
                    <div>
                      <p className="text-[14px] font-medium text-text">{t(item.head)}</p>
                      <p className="mt-1 text-[13px] leading-relaxed text-secondary">{t(item.body)}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </div>

            <div className="flex items-end justify-between">
              <p className="mono text-[10.5px] uppercase tracking-[0.14em] text-muted">
                PS 26108 · DoCA
              </p>
            </div>
          </div>
        </aside>
      </main>
    </div>
  )
}

/* ── fields ─────────────────────────────────────────────────────────────
   The reference puts the label above the value inside the same bordered box,
   with an icon on the trailing edge and a coloured ring on focus. */

function Field({
  id,
  label,
  value,
  onChange,
  error,
  icon,
  type = 'text',
  autoComplete,
}: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  error?: string
  icon?: ReactNode
  type?: string
  autoComplete?: string
}) {
  return (
    <div>
      <div
        className={`group flex items-center gap-3 rounded-[14px] border bg-white/[0.035] px-4 py-2.5 transition-all duration-300 focus-within:border-amber/70 focus-within:bg-white/[0.06] focus-within:shadow-[0_0_0_3px_rgb(255_138_91/0.15)] ${
          error ? 'border-[rgb(255_107_107/0.55)]' : 'border-white/10'
        }`}
      >
        <div className="min-w-0 flex-1">
          <label htmlFor={id} className="block text-[11px] text-muted">
            {label}
          </label>
          <input
            id={id}
            type={type}
            value={value}
            autoComplete={autoComplete}
            aria-invalid={!!error}
            aria-describedby={error ? `${id}-error` : undefined}
            onChange={(event) => onChange(event.target.value)}
            className="mt-0.5 w-full bg-transparent text-[14.5px] text-text outline-none placeholder:text-muted focus-visible:outline-none"
          />
        </div>
        {icon && <span className="shrink-0 text-muted">{icon}</span>}
      </div>
      {error && (
        <p id={`${id}-error`} className="mt-1.5 px-1 text-[12px] text-red">
          {error}
        </p>
      )}
    </div>
  )
}

function SelectField({
  id,
  label,
  value,
  onChange,
  error,
  options,
}: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  error?: string
  options: string[]
}) {
  return (
    <div>
      <div
        className={`flex items-center gap-3 rounded-[14px] border bg-white/[0.035] px-4 py-2.5 transition-all duration-300 focus-within:border-amber/70 focus-within:bg-white/[0.06] focus-within:shadow-[0_0_0_3px_rgb(255_138_91/0.15)] ${
          error ? 'border-[rgb(255_107_107/0.55)]' : 'border-white/10'
        }`}
      >
        <div className="min-w-0 flex-1">
          <label htmlFor={id} className="block text-[11px] text-muted">
            {label}
          </label>
          <select
            id={id}
            value={value}
            aria-invalid={!!error}
            aria-describedby={error ? `${id}-error` : undefined}
            onChange={(event) => onChange(event.target.value)}
            className="mt-0.5 w-full appearance-none bg-transparent text-[14.5px] text-text outline-none focus-visible:outline-none"
          >
            <option value="" className="bg-ink-2">
              Select a state
            </option>
            {options.map((option) => (
              <option key={option} value={option} className="bg-ink-2">
                {option}
              </option>
            ))}
          </select>
        </div>
        <span className="shrink-0 text-muted">
          <ChevronIcon />
        </span>
      </div>
      {error && (
        <p id={`${id}-error`} className="mt-1.5 px-1 text-[12px] text-red">
          {error}
        </p>
      )}
    </div>
  )
}

/* ── icons local to this page ───────────────────────────────────────── */

function GoogleMark() {
  return (
    <svg width="17" height="17" viewBox="0 0 48 48" aria-hidden>
      <path fill="#4285F4" d="M45.1 24.5c0-1.6-.1-2.8-.4-4H24v7.3h12.1c-.2 2-1.6 5-4.5 7l6.9 5.3c4.1-3.8 6.6-9.4 6.6-15.6z" />
      <path fill="#34A853" d="M24 46c5.9 0 10.9-2 14.5-5.3l-6.9-5.4c-1.9 1.3-4.4 2.2-7.6 2.2-5.8 0-10.7-3.8-12.5-9.1l-7.1 5.5C8.1 41.1 15.5 46 24 46z" />
      <path fill="#FBBC05" d="M11.5 28.4c-.5-1.4-.7-2.9-.7-4.4s.3-3 .7-4.4l-7.1-5.6C2.9 17 2 20.4 2 24s.9 7 2.4 10z" />
      <path fill="#EA4335" d="M24 10.6c4.1 0 6.9 1.8 8.5 3.3l6.2-6C34.9 4.5 29.9 2 24 2 15.5 2 8.1 6.9 4.4 14l7.1 5.6C13.3 14.4 18.2 10.6 24 10.6z" />
    </svg>
  )
}

const PersonIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <rect x="3" y="5" width="18" height="14" rx="2.5" />
    <circle cx="9" cy="11" r="2" />
    <path d="M5.5 16.5c.8-1.6 2-2.2 3.5-2.2s2.7.6 3.5 2.2M15 10h4M15 13.5h4" />
  </svg>
)

const MailIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <rect x="3" y="5" width="18" height="14" rx="2.5" />
    <path d="m3.5 7 8.5 6 8.5-6" />
  </svg>
)

const BuildingIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M4 21V6a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2v15M15 21V11h3a2 2 0 0 1 2 2v8M4 21h17" />
    <path d="M8 8h3M8 12h3M8 16h3" />
  </svg>
)

const LockIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <rect x="4" y="10" width="16" height="11" rx="2.5" />
    <path d="M8 10V7a4 4 0 0 1 8 0v3" />
  </svg>
)

const EyeIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z" />
    <circle cx="12" cy="12" r="2.6" />
  </svg>
)

const EyeOffIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M3 3l18 18M10.6 6.1A9.6 9.6 0 0 1 12 6c6.4 0 10 6 10 6a17 17 0 0 1-3.2 3.9M6.5 8.2A16.6 16.6 0 0 0 2 12s3.6 6.5 10 6.5a9.9 9.9 0 0 0 3.4-.6" />
    <path d="M9.9 10a2.6 2.6 0 0 0 3.6 3.6" />
  </svg>
)

const ChevronIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="m6 9 6 6 6-6" />
  </svg>
)
