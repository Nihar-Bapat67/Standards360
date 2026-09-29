import { Link } from 'react-router-dom'
import { Atmosphere } from '../components/Atmosphere'
import { ProductName } from '../components/ProductName'
import { Chip, Icon, Label, SectionLabel, Skeleton } from '../components/ui'
import { useMeta } from '../hooks/useMeta'
import { formatNumber } from '../lib/format'
import { LanguageSelector } from '../components/LanguageSelector'
import { useT } from '../i18n'

/**
 * The landing page.
 *
 * Every figure on it comes from /v1/meta, which reads the live catalogue and the frozen gold set.
 * That is not a technical nicety: this product's entire claim is that it does not state things it
 * cannot show, and a marketing page with hand-typed numbers would break that claim before anyone
 * reached the workspace.
 */

const SITUATIONS = [
  {
    id: 'S1',
    arrives: 'landing.doors.s1.arrives',
    response: 'landing.doors.s1.response',
  },
  {
    id: 'S2',
    arrives: 'landing.doors.s2.arrives',
    response: 'landing.doors.s2.response',
  },
  {
    id: 'S3',
    arrives: 'landing.doors.s3.arrives',
    response: 'landing.doors.s3.response',
  },
  { id: 'S4', arrives: 'landing.doors.s4.arrives', response: 'landing.doors.s4.response' },
  {
    id: 'S5',
    arrives: 'landing.doors.s5.arrives',
    response: 'landing.doors.s5.response',
  },
] as const

const STAGES = [
  { id: '01', module: 'B1 · B3', name: 'landing.stage.understand', detail: 'landing.stage.understand.detail' },
  { id: '02', module: 'C1', name: 'landing.stage.retrieve', detail: 'landing.stage.retrieve.detail' },
  { id: '03', module: 'C2', name: 'landing.stage.expand', detail: 'landing.stage.expand.detail' },
  { id: '04', module: 'C3 · C4', name: 'landing.stage.verify', detail: 'landing.stage.verify.detail' },
  { id: '05', module: 'D1 · D3', name: 'landing.stage.deliver', detail: 'landing.stage.deliver.detail' },
] as const

export function Landing() {
  const t = useT()
  const { data, loading } = useMeta()
  const c = data?.catalogue
  const e = data?.evaluation

  // The hero's figure strip, as data rather than markup, because the marquee has to render the
  // same set twice. Exactly the figures that were there before, in the same order; a figure the
  // engine did not return is left out rather than shown blank.
  const figures = (
    [
      c?.total != null && {
        text: `${formatNumber(c.total)} ${t('landing.stat.catalogued')}`,
        warm: false,
      },
      c?.current != null && { text: `${formatNumber(c.current)} ${t('landing.stat.current')}`, warm: false },
      c?.cross_references != null && {
        text: `${formatNumber(c.cross_references)} ${t('landing.stat.crossRefs')}`,
        warm: false,
      },
      c?.qco != null && {
        text: `${formatNumber(c.qco)} ${t('landing.stat.qco')}`,
        warm: false,
      },
      e?.['hit@3'] != null && { text: `Hit@3 ${e['hit@3'].toFixed(2)}`, warm: true },
      e?.['mrr@5'] != null && { text: `MRR@5 ${e['mrr@5'].toFixed(3)}`, warm: true },
    ] as ({ text: string; warm: boolean } | false | undefined)[]
  ).filter(Boolean) as { text: string; warm: boolean }[]

  return (
    <div className="relative min-h-screen">
      <Atmosphere variant="hero" />

      {/* ── navigation ───────────────────────────────────────────────── */}
      <header className="sticky top-0 z-40 border-b border-white/6 bg-ink-0/70 backdrop-blur-xl">
        <nav className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-5 sm:px-8">
          <ProductName />
          <div className="flex-1" />
          <Link
            to="/login"
            className="hidden text-[13px] text-secondary transition-colors hover:text-text sm:block"
          >
            {t('nav.signIn')}
          </Link>
          <LanguageSelector compact />
          <Link to="/workspace" className="btn btn-primary h-10 px-5 text-[13px]">
            {t('nav.findStandard')}
          </Link>
        </nav>
      </header>

      <main>
        {/* ── hero ───────────────────────────────────────────────────── */}
        <section className="mx-auto max-w-6xl px-5 pb-20 pt-20 sm:px-8 sm:pt-28">
          <div className="flex justify-center">
            <Label className="text-amber">{t('landing.eyebrow')}</Label>
          </div>

          <h1 className="mx-auto mt-7 max-w-[54rem] text-center text-[clamp(2.4rem,6vw,4.4rem)] font-semibold leading-[1.02] tracking-[-0.035em]">
            {t('landing.headline1')}
            <br />
            <span className="text-ember">{t('landing.headline2')}</span>
          </h1>

          <p className="mx-auto mt-7 max-w-[41rem] text-center text-[16.5px] leading-relaxed text-secondary">
            {t('landing.intro')}
          </p>

          <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link to="/workspace" className="btn btn-primary w-full px-7 sm:w-auto">
              {t('nav.findStandard')}
              <Icon.Arrow />
            </Link>
          </div>

          {/* Measured figures, served from the running engine.
              They travel as a slow marquee rather than sitting in a wrapped row. The track carries
              the set twice and moves exactly half its own width, so the point where it restarts is
              invisible; that only works if each figure owns its trailing gap as a margin, because a
              flex `gap` would leave one extra gap between the two halves and show a seam.
              The duplicate half is hidden from assistive technology so the numbers are not read out
              a second time. */}
          <div className="mt-12">
            {loading ? (
              <div className="flex flex-wrap items-center justify-center gap-3">
                <Skeleton className="h-10 w-48" />
                <Skeleton className="h-10 w-40" />
                <Skeleton className="h-10 w-44" />
                <Skeleton className="h-10 w-52" />
              </div>
            ) : (
              <div
                className="relative overflow-hidden"
                style={{
                  maskImage: 'linear-gradient(to right, transparent, #000 9%, #000 91%, transparent)',
                  WebkitMaskImage:
                    'linear-gradient(to right, transparent, #000 9%, #000 91%, transparent)',
                }}
              >
                <div className="flex w-max animate-marquee items-center">
                  {[...figures, ...figures].map((figure, index) => (
                    <span
                      key={`${figure.text}-${index}`}
                      aria-hidden={index >= figures.length}
                      className={`mono mr-3 flex h-11 shrink-0 items-center rounded-full border px-5 text-[13.5px] ${
                        figure.warm
                          ? 'border-[rgb(255_138_91/0.34)] bg-[rgb(255_138_91/0.09)] text-[#FFB894]'
                          : 'border-white/10 bg-white/[0.035] text-secondary'
                      }`}
                    >
                      {figure.text}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>

        {/* ── the problem, stated once ───────────────────────────────── */}
        <section className="mx-auto max-w-6xl px-5 py-16 sm:px-8">
          <div className="card overflow-hidden p-8 sm:p-11">
            <SectionLabel index="01">{t('landing.problem.label')}</SectionLabel>
            <h2 className="mt-5 max-w-3xl text-[clamp(1.6rem,3.4vw,2.4rem)] font-semibold leading-[1.15] tracking-[-0.02em]">
              {t('landing.problem.heading')}
            </h2>
            <p className="mt-5 max-w-3xl text-[15px] leading-relaxed text-secondary">
              {t('landing.problem.body')}
            </p>

            <div className="mt-9 grid gap-3 sm:grid-cols-3">
              {[
                {
                  figure: c?.withdrawn != null ? formatNumber(c.withdrawn) : '—',
                  label: t('landing.problem.withdrawn'),
                },
                {
                  figure: c?.with_replacement != null ? formatNumber(c.with_replacement) : '—',
                  label: t('landing.problem.replacement'),
                },
                {
                  figure: c?.labs != null ? formatNumber(c.labs) : '—',
                  label: c?.lab_states
                    ? t('landing.problem.labsAcross', { count: c.lab_states })
                    : t('landing.problem.labs'),
                },
              ].map((item) => (
                <div key={item.label} className="card-quiet p-5">
                  <div className="mono text-[26px] font-medium tracking-tight text-text">{item.figure}</div>
                  <div className="mt-1.5 text-[13px] leading-snug text-secondary">{item.label}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── five doors ─────────────────────────────────────────────── */}
        <section className="mx-auto max-w-6xl px-5 py-16 sm:px-8">
          <SectionLabel index="02">{t('landing.doors.label')}</SectionLabel>
          <h2 className="mt-5 max-w-3xl text-[clamp(1.6rem,3.4vw,2.4rem)] font-semibold leading-[1.15] tracking-[-0.02em]">
            {t('landing.doors.heading')}
          </h2>

          <div className="mt-9 overflow-hidden rounded-[20px] border border-white/8">
            <div className="hidden grid-cols-[64px_1fr_1fr] gap-px bg-white/6 sm:grid">
              <div className="bg-ink-1 px-4 py-3">
                <Label>{t('landing.doors.case')}</Label>
              </div>
              <div className="bg-ink-1 px-5 py-3">
                <Label>{t('landing.doors.arrives')}</Label>
              </div>
              <div className="bg-ink-1 px-5 py-3">
                <Label>{t('landing.doors.response')}</Label>
              </div>
            </div>

            <div className="grid gap-px bg-white/6">
              {SITUATIONS.map((s) => (
                <div
                  key={s.id}
                  className="grid gap-1 bg-ink-1/90 px-5 py-4 transition-colors hover:bg-ink-2 sm:grid-cols-[64px_1fr_1fr] sm:gap-0 sm:px-0"
                >
                  <div className="sm:px-4">
                    <span className="mono text-[11px] text-amber">{s.id}</span>
                  </div>
                  <div className="text-[14px] text-text sm:px-5">{t(s.arrives)}</div>
                  <div className="text-[14px] leading-snug text-secondary sm:px-5">{t(s.response)}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── the pipeline ───────────────────────────────────────────── */}
        <section className="mx-auto max-w-6xl px-5 py-16 sm:px-8">
          <SectionLabel index="03">{t('landing.pipeline.label')}</SectionLabel>
          <h2 className="mt-5 max-w-3xl text-[clamp(1.6rem,3.4vw,2.4rem)] font-semibold leading-[1.15] tracking-[-0.02em]">
            {t('landing.pipeline.heading')}
          </h2>
          <p className="mt-4 max-w-2xl text-[15px] leading-relaxed text-secondary">
            {t('landing.pipeline.body')}
          </p>

          <div className="mt-9 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {STAGES.map((stage) => (
              <div key={stage.id} className="card card-hover p-5">
                <div className="flex items-baseline justify-between">
                  <span className="mono text-[11px] text-amber">{stage.id}</span>
                  <span className="mono text-[10px] text-muted">{stage.module}</span>
                </div>
                <div className="mt-3 text-[15px] font-medium text-text">{t(stage.name)}</div>
                <p className="mt-2 text-[13px] leading-relaxed text-secondary">{t(stage.detail)}</p>
              </div>
            ))}
          </div>

          <div className="mt-6 flex flex-wrap items-center gap-2.5">
            {data?.index?.model && <Chip>{data.index.model}</Chip>}
            {data?.index?.clauses != null && (
              <Chip>{t('landing.pipeline.clausesIndexed', { count: formatNumber(data.index.clauses) })}</Chip>
            )}
            {data?.index?.standards != null && (
              <Chip>{t('landing.pipeline.standardsIndexed', { count: formatNumber(data.index.standards) })}</Chip>
            )}
            {data?.sectors?.map((sector) => <Chip key={sector}>{sector}</Chip>)}
          </div>
        </section>

        {/* ── the promise ────────────────────────────────────────────── */}
        <section className="mx-auto max-w-6xl px-5 py-16 sm:px-8">
          <div className="grid gap-3 lg:grid-cols-3">
            {([
              {
                title: 'landing.promise1.title',
                body: 'landing.promise1.body',
              },
              {
                title: 'landing.promise2.title',
                body: 'landing.promise2.body',
              },
              {
                title: 'landing.promise3.title',
                body: 'landing.promise3.body',
              },
            ] as const).map((item) => (
              <div key={item.title} className="card p-7">
                <h3 className="text-[16px] font-medium leading-snug text-text">{t(item.title)}</h3>
                <p className="mt-3 text-[14px] leading-relaxed text-secondary">{t(item.body)}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ── call to action ─────────────────────────────────────────── */}
        <section className="mx-auto max-w-6xl px-5 pb-24 pt-10 sm:px-8">
          <div className="card relative overflow-hidden px-8 py-14 text-center sm:px-14">
            <div
              aria-hidden
              className="ambient h-[24rem] w-[24rem]"
              style={{
                top: '-10rem',
                left: '50%',
                transform: 'translateX(-50%)',
                background: 'radial-gradient(circle, rgb(255 138 91 / 0.18) 0%, transparent 68%)',
              }}
            />
            <h2 className="relative text-[clamp(1.7rem,4vw,2.6rem)] font-semibold leading-tight tracking-[-0.025em]">
              {t('landing.cta.heading1')} <span className="text-ember">{t('landing.cta.heading2')}</span>
            </h2>
            <p className="relative mx-auto mt-5 max-w-xl text-[15px] leading-relaxed text-secondary">
              {t('landing.cta.body')}
            </p>
            <div className="relative mt-8 flex justify-center">
              <Link to="/workspace" className="btn btn-primary px-8">
                {t('nav.findStandard')}
                <Icon.Arrow />
              </Link>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-white/6">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-5 py-9 text-[13px] text-muted sm:flex-row sm:items-center sm:px-8">
          <ProductName small />
          <div className="flex-1" />
          <p className="max-w-xl leading-relaxed sm:text-right">
            {t('landing.footer')}
          </p>
        </div>
      </footer>
    </div>
  )
}
