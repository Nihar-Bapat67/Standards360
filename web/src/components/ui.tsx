/**
 * The small shared pieces: labels, chips, states and copy.
 *
 * Everything here is presentational. Anything that needs to know about the engine belongs in a
 * feature component, and anything that needs to call it belongs in the service layer.
 */

import { type ReactNode, useState } from 'react'

/* ── instrumentation labels ─────────────────────────────────────────────── */

export function Label({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <span className={`label ${className}`}>{children}</span>
}

export function SectionLabel({ index, children }: { index?: string; children: ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <span className="h-px w-8 bg-gradient-to-r from-amber/70 to-transparent" />
      {index && <span className="label text-amber">{index}</span>}
      <Label>{children}</Label>
    </div>
  )
}

export function Chip({
  children,
  tone = 'plain',
  className = '',
}: {
  children: ReactNode
  tone?: 'plain' | 'warm'
  className?: string
}) {
  return <span className={`chip ${tone === 'warm' ? 'chip-warm' : ''} ${className}`}>{children}</span>
}

/* ── states ─────────────────────────────────────────────────────────────── */

export function ErrorState({
  title = 'That did not work',
  message,
  onRetry,
}: {
  title?: string
  message: string
  onRetry?: () => void
}) {
  return (
    <div
      role="alert"
      className="rounded-2xl border border-[rgb(255_107_107/0.28)] bg-[rgb(255_107_107/0.06)] p-5"
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[rgb(255_107_107/0.16)] text-red">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
            <path d="M12 8v5M12 17h.01" />
          </svg>
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-text">{title}</p>
          <p className="mt-1 text-sm leading-relaxed text-secondary">{message}</p>
          {onRetry && (
            <button type="button" onClick={onRetry} className="btn btn-ghost mt-3 h-9 px-4 text-[13px]">
              Try again
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-shimmer rounded-lg ${className}`} />
}

export function EmptyState({
  icon,
  title,
  children,
}: {
  icon?: ReactNode
  title: string
  children?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center px-6 py-14 text-center">
      {icon && (
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl border border-white/8 bg-white/[0.03] text-muted">
          {icon}
        </div>
      )}
      <p className="text-[15px] font-medium text-text">{title}</p>
      {children && <div className="mt-2 max-w-sm text-sm leading-relaxed text-secondary">{children}</div>}
    </div>
  )
}

/* ── copy ───────────────────────────────────────────────────────────────── */

export function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      // Clipboard access is refused in some contexts; fall back to a selection the person can copy.
      const area = document.createElement('textarea')
      area.value = text
      area.style.position = 'fixed'
      area.style.opacity = '0'
      document.body.appendChild(area)
      area.select()
      try {
        document.execCommand('copy')
      } catch {
        /* nothing more can be done; the button simply will not confirm */
      }
      area.remove()
    }
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1600)
  }

  return (
    <button
      type="button"
      onClick={copy}
      aria-label={copied ? 'Copied' : label}
      className="inline-flex h-7 items-center gap-1.5 rounded-lg border border-white/8 bg-white/[0.03] px-2.5 text-[11px] text-secondary transition-colors hover:border-white/16 hover:text-text"
    >
      {copied ? (
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
          <path d="M20 6 9 17l-5-5" />
        </svg>
      ) : (
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
          <rect x="9" y="9" width="12" height="12" rx="2.5" />
          <path d="M5 15V5a2 2 0 0 1 2-2h10" />
        </svg>
      )}
      {copied ? 'Copied' : label}
    </button>
  )
}

/* ── icons used in more than one place ──────────────────────────────────── */

export const Icon = {
  Send: () => (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 12h13M12 5l7 7-7 7" />
    </svg>
  ),
  Paperclip: () => (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21.4 11.05 12.2 20.2a5.5 5.5 0 0 1-7.8-7.8l9.2-9.1a3.7 3.7 0 0 1 5.2 5.2l-9.2 9.1a1.8 1.8 0 0 1-2.6-2.6l8.5-8.4" />
    </svg>
  ),
  Plus: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round">
      <path d="M12 5v14M5 12h14" />
    </svg>
  ),
  Search: () => (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round">
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.2-3.2" />
    </svg>
  ),
  Doc: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
    </svg>
  ),
  Download: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3v12M7 11l5 5 5-5M5 21h14" />
    </svg>
  ),
  Close: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M18 6 6 18M6 6l12 12" />
    </svg>
  ),
  Menu: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round">
      <path d="M4 7h16M4 12h16M4 17h16" />
    </svg>
  ),
  Trash: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />
    </svg>
  ),
  Retry: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 12a9 9 0 1 0 2.6-6.4M3 4v5h5" />
    </svg>
  ),
  Pin: () => (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 17v5M9 3h6l-1 6 3 3v2H7v-2l3-3z" />
    </svg>
  ),
  Lab: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 21s7-5.2 7-11a7 7 0 1 0-14 0c0 5.8 7 11 7 11z" />
      <circle cx="12" cy="10" r="2.5" />
    </svg>
  ),
  Arrow: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 12h13M12 5l7 7-7 7" />
    </svg>
  ),
}
