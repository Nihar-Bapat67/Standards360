import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { Atmosphere } from '../components/Atmosphere'
import { StandardDrawer } from '../components/StandardDrawer'
import { Chip, EmptyState, Icon, Label } from '../components/ui'
import { ApiError, api, saveBlob } from '../services/api'
import { type Conversation, store, titleFor } from '../services/conversations'
import { profile } from '../services/profile'
import type { AlliedStandard, AnalyzeResponse, Option } from '../types/api'
import {
  RELATION_TINTS,
  VERDICT_STYLE,
  evidenceWhere,
  formatNumber,
  relationLabel,
  severityDot,
  severityStyle,
} from '../lib/format'

/**
 * The answer, on a page of its own.
 *
 * It was previously a 400px column beside the conversation, which put the standard, its evidence,
 * thirty allied standards, the certification position and the laboratory list into a strip narrower
 * than a phone. Here each of those is a section with room to be read, in the order an officer needs
 * them: which standard applies, what proves it, what travels with it, what testing and certification
 * it obliges, what was already cited, and finally what to put in the tender.
 *
 * No confidence score appears anywhere. Where the engine is unsure it says so in words, and where a
 * required fact is missing the conversation asks for it rather than showing a number.
 */

export function Results() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [conversation, setConversation] = useState<Conversation | null>(null)
  const [drawerStandard, setDrawerStandard] = useState<string | null>(null)
  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState<string | null>(null)

  useEffect(() => {
    setConversation(id ? (store.get(id) ?? null) : null)
  }, [id])

  const result: AnalyzeResponse | null = useMemo(() => {
    const last = [...(conversation?.messages ?? [])].reverse().find((m) => m.result?.primary)
    return last?.result ?? null
  }, [conversation])

  const defaultOption = result?.options.find((o) => o.default) ?? result?.options[1] ?? result?.options[0]
  const [selected, setSelected] = useState<string | null>(null)
  const option: Option | undefined =
    result?.options.find((o) => o.id === (selected ?? defaultOption?.id)) ?? defaultOption

  const persona = conversation?.persona ?? profile.get()?.role ?? 'procurement'

  const download = async (mode: 'annexure' | 'report') => {
    if (!conversation || !option) return
    setDownloading(true)
    setDownloadError(null)
    try {
      const text = conversation.messages
        .filter((m) => m.role === 'user' && m.text.trim())
        .map((m) => m.text.trim())
        .join('. ')
      const { blob, filename } = await api.document({
        text,
        persona,
        option_id: option.id,
        mode,
        answers: Object.keys(conversation.answers).length ? conversation.answers : null,
      })
      saveBlob(blob, filename)
    } catch (error) {
      setDownloadError(error instanceof ApiError ? error.friendly : 'The document could not be generated.')
    } finally {
      setDownloading(false)
    }
  }

  const backToChat = () => navigate(id ? `/workspace?c=${id}` : '/workspace')

  /* ── nothing to show ──────────────────────────────────────────────── */

  if (!result) {
    return (
      <div className="relative min-h-dvh">
        <Atmosphere variant="work" />
        <TopBar onBack={backToChat} title="No answer yet" />
        <main className="mx-auto max-w-2xl px-5 pt-24">
          <EmptyState icon={<Icon.Doc />} title="There is no answer on this enquiry yet">
            Ask about an item in the conversation, or drop a tender in, and the applicable standards will
            appear here.
          </EmptyState>
          <div className="mt-6 flex justify-center">
            <button type="button" onClick={backToChat} className="btn btn-primary px-6">
              Back to the conversation
            </button>
          </div>
        </main>
      </div>
    )
  }

  const evidence = result.evidence[0]
  const alliedGroups = Object.entries(result.allied).filter(([, items]) => items.length > 0)
  const totalAllied = alliedGroups.reduce((sum, [, items]) => sum + items.length, 0)
  const cert = result.certification
  const wrongCitations = result.verdicts.filter((v) => v.verdict !== 'add')
  const toAdd = result.verdicts.filter((v) => v.verdict === 'add')

  return (
    <div className="relative min-h-dvh pb-24">
      <Atmosphere variant="work" />
      <TopBar onBack={backToChat} title={conversation ? titleFor(conversation) : 'Applicable standards'} />

      <main className="mx-auto max-w-5xl px-5 sm:px-8">
        {/* ── 1 · the standard ───────────────────────────────────────── */}
        {/* The engine nearly always has one more thing it would like to know. It is shown here
            rather than hidden back in the conversation, because the answer below was reached
            without it and the officer should see that plainly. */}
        {result.questions.length > 0 && (
          <div className="mt-8 flex flex-col gap-3 rounded-[20px] border border-[rgb(255_138_91/0.26)] bg-[rgb(255_138_91/0.055)] p-5 sm:flex-row sm:items-center">
            <div className="min-w-0 flex-1">
              <Label className="text-amber">This would sharpen the answer</Label>
              <p className="mt-2 text-[14.5px] leading-snug text-text">{result.questions[0].ask}</p>
            </div>
            <button type="button" onClick={backToChat} className="btn btn-ghost shrink-0 px-5">
              Answer it
            </button>
          </div>
        )}

        <section className="pt-10 sm:pt-14">
          <Label className="text-amber">The standard that applies</Label>

          <div className="mt-5 flex flex-wrap items-baseline gap-x-5 gap-y-2">
            <button
              type="button"
              onClick={() => result.primary && setDrawerStandard(result.primary)}
              className="mono text-[clamp(2rem,5vw,3rem)] font-medium tracking-tight text-text transition-colors hover:text-amber"
            >
              {result.primary}
            </button>
          </div>

          <p className="mt-3 max-w-3xl text-[16px] leading-relaxed text-secondary">{result.primary_title}</p>

          <div className="mt-5 flex flex-wrap gap-2">
            <Chip>In force</Chip>
            {result.amendments.length > 0 && (
              <Chip tone="warm">
                {result.amendments.length} amendment{result.amendments.length === 1 ? '' : 's'}
              </Chip>
            )}
            {cert?.certification_required && <Chip tone="warm">ISI mark compulsory</Chip>}
            {cert && cert.labs_available > 0 && <Chip>{formatNumber(cert.labs_available)} laboratories</Chip>}
          </div>

          {result.amendments.length > 0 && (
            <div className="card mt-7 p-6">
              <Label>How to cite it</Label>
              <p className="mt-3 text-[14.5px] leading-relaxed text-secondary">
                {result.amendments.map((a) => `${a.number} (${a.year})`).join(' · ')}. An amendment changes
                a standard without replacing it, so the edition year does not move. Cite it as amended.
              </p>
              {result.primary_as_cited && (
                <div className="mt-4 flex flex-wrap items-center gap-3">
                  <code className="mono flex-1 rounded-xl border border-white/8 bg-black/35 px-4 py-3 text-[13.5px] text-text">
                    {result.primary_as_cited}
                  </code>
                  <CopyLine text={result.primary_as_cited} />
                </div>
              )}
            </div>
          )}
        </section>

        {/* ── 2 · the proof ──────────────────────────────────────────── */}
        {evidence && (
          <Section title="Why this standard" hint="The passage in the standard itself that decides it.">
            <div className="card p-6">
              <p className="mono text-[11px] text-amber">
                {evidenceWhere(evidence.clause, evidence.role, evidence.page)}
              </p>
              <blockquote className="mt-4 border-l-2 border-amber/40 pl-5 text-[15px] leading-relaxed text-secondary">
                {evidence.quote}
              </blockquote>
              <div className="mt-5 flex items-center justify-between gap-3">
                <p className="text-[11.5px] text-muted">
                  A short extract, quoted with its source. Copyright in the standard vests in BIS.
                </p>
                <CopyLine text={evidence.quote} />
              </div>
            </div>
          </Section>
        )}

        {/* ── 3 · allied standards ───────────────────────────────────── */}
        {alliedGroups.length > 0 && (
          <Section
            title="What has to be cited with it"
            count={totalAllied}
            hint="Reached by following BIS's own cross-references outward, then grouped by the job each standard does."
          >
            <div className="grid gap-3 md:grid-cols-2">
              {alliedGroups.map(([relation, items]) => (
                <AlliedGroup
                  key={relation}
                  relation={relation}
                  items={items}
                  onOpen={setDrawerStandard}
                />
              ))}
            </div>
            <p className="mt-4 text-[11.5px] text-muted">
              A dot marks a standard the source cited under an older number; the edition in force is shown.
            </p>
          </Section>
        )}

        {/* ── 4 · testing and certification ──────────────────────────── */}
        {cert && (
          <Section
            title="Testing and certification"
            hint={
              persona === 'manufacturer'
                ? 'What you must hold before this product may be supplied.'
                : 'What a bidder must hold, and where the product can be tested.'
            }
          >
            <div className="grid gap-3 lg:grid-cols-[1.15fr_1fr]">
              <div className="card p-6">
                <div className="flex items-start justify-between gap-3">
                  <Label>{cert.certification_required ? 'Compulsory' : 'Not stated by BIS'}</Label>
                  <span
                    className={`h-2 w-2 shrink-0 rounded-full ${cert.certification_required ? 'bg-amber' : 'bg-muted'}`}
                  />
                </div>
                <p className="mt-4 text-[15px] leading-relaxed text-text">{cert.statement}</p>

                {cert.standards.filter((s) => s.scheme).length > 0 && (
                  <dl className="mt-6 grid gap-4 border-t border-white/8 pt-5 sm:grid-cols-2">
                    {cert.standards
                      .filter((s) => s.scheme)
                      .slice(0, 2)
                      .map((s) => (
                        <div key={s.is_number}>
                          <dt className="mono text-[11px] text-muted">{s.is_number}</dt>
                          <dd className="mt-1.5 text-[13px] leading-snug text-secondary">{s.scheme}</dd>
                          {s.qco_date && (
                            <dd className="mt-1 text-[12px] text-muted">
                              In force since {new Date(s.qco_date).toLocaleDateString('en-IN', {
                                day: 'numeric',
                                month: 'short',
                                year: 'numeric',
                              })}
                            </dd>
                          )}
                        </div>
                      ))}
                  </dl>
                )}

                {cert.not_stated.length > 0 && (
                  <p className="mt-5 border-t border-white/8 pt-4 text-[12.5px] leading-relaxed text-muted">
                    BIS publishes no certification position for {cert.not_stated.join(', ')}. That means the
                    position is unpublished, not that certification is not required.
                  </p>
                )}
              </div>

              <div className="card p-6">
                <div className="flex items-baseline justify-between gap-3">
                  <Label>Recognised laboratories</Label>
                  <span className="mono text-[11px] text-muted">{formatNumber(cert.labs_available)}</span>
                </div>

                {cert.nearest_labs.length > 0 ? (
                  <>
                    <ul className="mt-4 flex flex-col gap-1.5">
                      {cert.nearest_labs.slice(0, 6).map((lab) => (
                        <li
                          key={`${lab.name}-${lab.city}`}
                          className="card-quiet flex items-center gap-3 px-3.5 py-2.5"
                        >
                          <span className="text-blue">
                            <Icon.Lab />
                          </span>
                          <span className="min-w-0 flex-1 truncate text-[13px] text-text">{lab.name}</span>
                          <span className="shrink-0 text-[11.5px] text-muted">{lab.city}</span>
                        </li>
                      ))}
                    </ul>
                    <p className="mt-4 text-[11.5px] leading-relaxed text-muted">
                      BIS-recognised laboratories able to test against this standard, nearest first.
                    </p>
                  </>
                ) : (
                  <p className="mt-4 text-[13px] leading-relaxed text-secondary">
                    BIS lists no recognised laboratory against this standard.
                  </p>
                )}
              </div>
            </div>
          </Section>
        )}

        {/* ── 5 · the tender's own citations ─────────────────────────── */}
        {result.verdicts.length > 0 && (
          <Section
            title={wrongCitations.length > 0 ? 'The standards already cited' : 'Not yet cited'}
            hint={
              wrongCitations.length > 0
                ? 'Each citation in the tender, judged on whether it exists, whether it is current, and whether it fits this product.'
                : 'Recommended for this product but absent from the tender.'
            }
          >
            <div className="flex flex-col gap-2">
              {[...wrongCitations, ...toAdd].map((verdict) => {
                const style = VERDICT_STYLE[verdict.verdict] ?? VERDICT_STYLE.verify
                return (
                  <div key={`${verdict.citation}-${verdict.verdict}`} className="card p-5">
                    <div className="flex flex-wrap items-center gap-2.5">
                      <button
                        type="button"
                        onClick={() => setDrawerStandard(verdict.citation)}
                        className={`mono text-[15px] transition-colors hover:text-amber ${
                          verdict.verdict === 'remove' || verdict.verdict === 'replace'
                            ? 'text-secondary line-through decoration-white/30'
                            : 'text-text'
                        }`}
                      >
                        {verdict.citation}
                      </button>
                      <span className={`rounded-md border px-2 py-0.5 text-[10.5px] ${style.className}`}>
                        {style.label}
                      </span>
                      {verdict.replacement && (
                        <>
                          <span className="text-muted">→</span>
                          <button
                            type="button"
                            onClick={() => setDrawerStandard(verdict.replacement!)}
                            className="mono text-[15px] text-amber hover:underline"
                          >
                            {verdict.replacement}
                          </button>
                        </>
                      )}
                    </div>
                    {verdict.title && (
                      <p className="mt-2 text-[13px] leading-snug text-muted">{verdict.title}</p>
                    )}
                    <p className="mt-2 text-[14px] leading-relaxed text-secondary">{verdict.reason}</p>
                  </div>
                )
              })}
            </div>
          </Section>
        )}

        {/* ── 6 · warnings ───────────────────────────────────────────── */}
        {result.warnings.length > 0 && (
          <Section title="Version warnings">
            <div className="flex flex-col gap-2">
              {result.warnings.map((warning, index) => (
                <div
                  key={`${warning.message}-${index}`}
                  className={`flex items-start gap-3 rounded-2xl border p-5 ${severityStyle(warning.severity)}`}
                >
                  <span className={`mt-2 h-1.5 w-1.5 shrink-0 rounded-full ${severityDot(warning.severity)}`} />
                  <div>
                    <p className="text-[14.5px] leading-snug text-text">{warning.message}</p>
                    {warning.action && (
                      <p className="mt-1.5 text-[13px] text-secondary">{warning.action}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* ── 7 · put it in the tender ───────────────────────────────── */}
        {result.options.length > 0 && option && (
          <Section
            title="Put it in the tender"
            hint={`Every depth names ${result.primary} as the primary standard with the same evidence. The choice is only how many allied standards travel with it.`}
          >
            <div
              role="radiogroup"
              aria-label="Citation depth"
              className="grid gap-2 sm:grid-cols-3"
            >
              {result.options.map((o) => {
                const active = o.id === option.id
                return (
                  <button
                    key={o.id}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    onClick={() => setSelected(o.id)}
                    className={`card card-hover p-5 text-left transition-colors ${
                      active ? 'border-amber/45 bg-[rgb(255_138_91/0.06)]' : ''
                    }`}
                  >
                    <div className="flex items-baseline justify-between">
                      <span className="mono text-[11px] text-muted">{o.id}</span>
                      <span className="mono text-[12px] text-secondary">{o.standards.length}</span>
                    </div>
                    <p className="mt-2.5 text-[15px] font-medium text-text">{o.label}</p>
                  </button>
                )
              })}
            </div>

            <p className="mt-5 text-[14px] leading-relaxed text-secondary">{option.rationale}</p>

            <div className="mt-4 flex flex-wrap gap-1.5">
              {option.standards.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setDrawerStandard(s)}
                  className="mono rounded-lg border border-white/8 bg-white/[0.03] px-2.5 py-1.5 text-[11.5px] text-secondary transition-colors hover:border-amber/45 hover:text-amber"
                >
                  {s}
                </button>
              ))}
            </div>

            <div className="mt-7 flex flex-col gap-2.5 sm:flex-row">
              <button
                type="button"
                onClick={() => download('report')}
                disabled={downloading}
                className="btn btn-primary px-7"
              >
                {downloading ? 'Generating…' : 'Download the report'}
                {!downloading && <Icon.Download />}
              </button>
              <button
                type="button"
                onClick={() => download('annexure')}
                disabled={downloading}
                className="btn btn-ghost px-7"
              >
                Annexure only
              </button>
              <button type="button" onClick={backToChat} className="btn btn-ghost px-7">
                Refine in the conversation
              </button>
            </div>
            {downloadError && <p className="mt-3 text-[13.5px] text-red">{downloadError}</p>}
          </Section>
        )}

        {/* ── the guard ──────────────────────────────────────────────── */}
        {result.removed_by_guard.length > 0 && (
          <Section title="Removed before you saw it">
            <div className="card border-[rgb(255_107_107/0.25)] p-5">
              <p className="text-[14px] leading-relaxed text-secondary">
                {result.removed_by_guard.join(', ')} appeared in the written explanation but is not in the
                BIS catalogue, so it was deleted. The standards above are unaffected: they come from the
                database and cannot be invented.
              </p>
            </div>
          </Section>
        )}
      </main>

      <StandardDrawer
        isNumber={drawerStandard}
        onClose={() => setDrawerStandard(null)}
        onOpenStandard={setDrawerStandard}
      />
    </div>
  )
}

/* ── layout pieces ──────────────────────────────────────────────────── */

/**
 * One role's worth of allied standards.
 *
 * A dense product can reach seventy allied standards, and test methods alone can be thirty-seven of
 * them — printing all of them turned this section into the wall of chips the page exists to avoid.
 * Twelve is enough to see what kind of standards these are; the rest are one press away.
 */
const VISIBLE = 12

function AlliedGroup({
  relation,
  items,
  onOpen,
}: {
  relation: string
  items: AlliedStandard[]
  onOpen: (isNumber: string) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const shown = expanded ? items : items.slice(0, VISIBLE)
  const hidden = items.length - shown.length

  return (
    <div className="card h-fit p-5">
      <div className="flex items-center gap-2.5">
        <span
          className="h-4 w-0.5 rounded-full"
          style={{ background: RELATION_TINTS[relation] ?? '#71717A' }}
        />
        <h3 className="flex-1 text-[14px] font-medium text-text">{relationLabel(relation)}</h3>
        <span className="mono text-[11px] text-muted">{items.length}</span>
      </div>

      <div className="mt-4 flex flex-wrap gap-1.5">
        {shown.map((item) => (
          <button
            key={`${relation}-${item.is_number}`}
            type="button"
            onClick={() => onOpen(item.is_number)}
            title={item.title}
            className="mono rounded-lg border border-white/8 bg-white/[0.03] px-2.5 py-1.5 text-[11.5px] text-secondary transition-colors hover:border-white/20 hover:text-text"
          >
            {item.is_number}
            {item.superseded && <span className="ml-1 text-amber">·</span>}
          </button>
        ))}
      </div>

      {(hidden > 0 || expanded) && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-3 text-[12px] text-amber transition-colors hover:text-coral"
        >
          {expanded ? 'Show fewer' : `Show all ${items.length}`}
        </button>
      )}
    </div>
  )
}

function TopBar({ onBack, title }: { onBack: () => void; title: string }) {
  return (
    <header className="sticky top-0 z-30 border-b border-white/6 bg-ink-0/75 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-5xl items-center gap-4 px-5 sm:px-8">
        <button
          type="button"
          onClick={onBack}
          className="flex h-9 items-center gap-2 rounded-lg border border-white/8 bg-white/[0.03] px-3 text-[13px] text-secondary transition-colors hover:border-white/18 hover:text-text"
        >
          <span className="rotate-180">
            <Icon.Arrow />
          </span>
          Conversation
        </button>
        <p className="min-w-0 flex-1 truncate text-[14px] font-medium text-text">{title}</p>
        <Link to="/workspace" className="hidden text-[13px] text-secondary hover:text-text sm:block">
          New enquiry
        </Link>
      </div>
    </header>
  )
}

function Section({
  title,
  hint,
  count,
  children,
}: {
  title: string
  hint?: string
  count?: number
  children: React.ReactNode
}) {
  return (
    <section className="mt-14 border-t border-white/6 pt-10">
      <div className="flex items-baseline gap-3">
        <h2 className="text-[clamp(1.25rem,2.4vw,1.6rem)] font-semibold tracking-[-0.02em] text-text">
          {title}
        </h2>
        {count != null && <span className="mono text-[12px] text-muted">{count}</span>}
      </div>
      {hint && <p className="mt-2.5 max-w-3xl text-[14px] leading-relaxed text-secondary">{hint}</p>}
      <div className="mt-6">{children}</div>
    </section>
  )
}

function CopyLine({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text)
        } catch {
          /* clipboard access can be refused; the button simply will not confirm */
        }
        setCopied(true)
        window.setTimeout(() => setCopied(false), 1600)
      }}
      className="inline-flex h-9 shrink-0 items-center gap-2 rounded-lg border border-white/8 bg-white/[0.03] px-3.5 text-[12.5px] text-secondary transition-colors hover:border-white/18 hover:text-text"
    >
      {copied ? 'Copied' : 'Copy'}
    </button>
  )
}
