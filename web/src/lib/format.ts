/**
 * Presentation helpers.
 *
 * The rule these all serve: the interface must never state something the engine did not say. Where
 * BIS leaves a field blank the wording is "not stated by BIS", never "not required" — a blank
 * certification field in the catalogue means BIS has not published a position, and turning that
 * into "no licence needed" would be the single most damaging thing this product could do.
 */

import type { Band, Severity } from '../types/api'

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return value.toLocaleString('en-US')
}

export function bandLabel(band: Band): string {
  return { high: 'High confidence', medium: 'Moderate confidence', low: 'Low confidence' }[band] ?? band
}

export function bandColor(band: Band): string {
  return { high: 'text-green', medium: 'text-amber', low: 'text-red' }[band] ?? 'text-secondary'
}

export function bandRing(band: Band): string {
  return (
    {
      high: 'border-[rgb(114_214_165/0.35)] bg-[rgb(114_214_165/0.10)] text-green',
      medium: 'border-[rgb(255_138_91/0.35)] bg-[rgb(255_138_91/0.10)] text-amber',
      low: 'border-[rgb(255_107_107/0.35)] bg-[rgb(255_107_107/0.10)] text-red',
    }[band] ?? 'border-white/10 bg-white/5 text-secondary'
  )
}

export function severityStyle(severity: Severity): string {
  return (
    {
      high: 'border-[rgb(255_107_107/0.32)] bg-[rgb(255_107_107/0.08)]',
      medium: 'border-[rgb(255_138_91/0.30)] bg-[rgb(255_138_91/0.07)]',
      low: 'border-white/8 bg-white/[0.03]',
    }[severity] ?? 'border-white/8 bg-white/[0.03]'
  )
}

export function severityDot(severity: Severity): string {
  return { high: 'bg-red', medium: 'bg-amber', low: 'bg-blue' }[severity] ?? 'bg-muted'
}

/** The role an allied standard plays, in words a procurement officer uses. */
export const RELATION_LABELS: Record<string, string> = {
  normative_reference: 'Normative references',
  test_method: 'Test methods',
  terminology: 'Terminology',
  safety: 'Safety',
  installation: 'Installation',
  related_product: 'Related products',
}

export const RELATION_TINTS: Record<string, string> = {
  normative_reference: '#5B8CFF',
  test_method: '#72D6A5',
  terminology: '#B99CE0',
  safety: '#FF6B6B',
  installation: '#FF8A5B',
  related_product: '#E95D9C',
}

export function relationLabel(relation: string): string {
  return RELATION_LABELS[relation] ?? relation.replace(/_/g, ' ')
}

export const VERDICT_STYLE: Record<string, { label: string; className: string }> = {
  keep: { label: 'Keep', className: 'text-green border-[rgb(114_214_165/0.35)] bg-[rgb(114_214_165/0.10)]' },
  replace: { label: 'Replace', className: 'text-amber border-[rgb(255_138_91/0.35)] bg-[rgb(255_138_91/0.10)]' },
  remove: { label: 'Remove', className: 'text-red border-[rgb(255_107_107/0.35)] bg-[rgb(255_107_107/0.10)]' },
  add: { label: 'Add', className: 'text-blue border-[rgb(91_140_255/0.35)] bg-[rgb(91_140_255/0.10)]' },
  verify: { label: 'Verify', className: 'text-secondary border-white/12 bg-white/5' },
}

/** How an evidence line should read. A summary has no numbered clause and must not pretend to. */
export function evidenceWhere(clause: string, role: string, page: number | null): string {
  if (role === 'summary') return 'BIS one-page summary of this standard'
  const where = `Clause ${clause}`
  const kind = role && role !== 'other' ? ` · ${role.replace(/_/g, ' ')}` : ''
  return page ? `${where}${kind} · page ${page}` : `${where}${kind}`
}

export function relativeTime(at: number): string {
  const seconds = Math.round((Date.now() - at) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.round(hours / 24)
  if (days < 7) return `${days} d ago`
  return new Date(at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** The stage names the pipeline reports, expanded for someone who has not read the build manual. */
export const MODULE_NAMES: Record<string, string> = {
  B1: 'Read the input',
  B3: 'Extract the requirement',
  B4: 'Judge existing citations',
  B5: 'Check sufficiency',
  C1: 'Retrieve',
  C2: 'Expand allied standards',
  C3: 'Resolve versions',
  C4: 'Certification',
  C5: 'Score confidence',
  D1: 'Guard the prose',
  D2: 'Compose the answer',
}
