import { Link } from 'react-router-dom'
import { Atmosphere } from '../components/Atmosphere'
import { Chip, Icon, Label, SectionLabel } from '../components/ui'
import { Wordmark } from '../components/Wordmark'
import { useMeta } from '../hooks/useMeta'
import { formatNumber } from '../lib/format'

/**
 * How the engine works, for someone evaluating it.
 *
 * It is written to be read rather than skimmed, because the interesting claim is not "we used a
 * vector database" — it is why four signals are fused, why the graph traversal cannot be replaced by
 * similarity search, and what happens to a number the model invents.
 */

const SIGNALS = [
  {
    name: 'BM25',
    kind: 'sparse',
    tint: '#FF8A5B',
    what: 'Exact tokens the embedding smooths away: an IS number, a grade like 43, a rating like IP66.',
  },
  {
    name: 'BGE-M3',
    kind: 'dense',
    tint: '#FF5F7A',
    what: 'Meaning. "Binder for reinforced concrete" and "cement for RCC work" share almost no words.',
  },
  {
    name: 'TITLES',
    kind: 'sparse',
    tint: '#E95D9C',
    what: 'BIS titles for every current standard, so a query outside our full-text corpus still lands somewhere real.',
  },
  {
    name: 'CITED',
    kind: 'graph',
    tint: '#5B8CFF',
    what: 'Standards named inside the best-matching clauses. When a clause cites an authority, that is a vote.',
  },
]

export function Architecture() {
  const { data } = useMeta()

  return (
    <div className="relative min-h-screen">
      <Atmosphere variant="hero" />

      <header className="sticky top-0 z-40 border-b border-white/6 bg-ink-0/70 backdrop-blur-xl">
        <nav className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-5 sm:px-8">
          <Wordmark />
          <span className="hidden text-[13px] text-muted sm:block">· The engine</span>
          <div className="flex-1" />
          <Link to="/workspace" className="btn btn-primary h-10 px-5 text-[13px]">
            Find the standard
          </Link>
        </nav>
      </header>

      <main className="mx-auto max-w-6xl px-5 pb-24 pt-16 sm:px-8 sm:pt-20">
        <Label className="text-amber">Architecture walkthrough</Label>
        <h1 className="mt-5 max-w-3xl text-[clamp(2.1rem,5.5vw,3.5rem)] font-semibold leading-[1.05] tracking-[-0.03em]">
          Retrieval is one module.
          <br />
          <span className="text-ember">Trust is the other eighteen.</span>
        </h1>
        <p className="mt-6 max-w-2xl text-[16px] leading-relaxed text-secondary">
          Finding a plausible standard takes an afternoon with off-the-shelf models. Making the answer
          safe to paste into a government tender is the rest of the work, and it is where almost all of
          this system lives.
        </p>

        {/* ── stage 01 ─────────────────────────────────────────────── */}
        <section className="mt-20">
          <SectionLabel index="01">Stage A — build the knowledge base</SectionLabel>
          <h2 className="mt-5 text-[clamp(1.5rem,3.2vw,2.1rem)] font-semibold tracking-[-0.02em]">
            The catalogue is the foundation, not the model.
          </h2>
          <p className="mt-4 max-w-2xl text-[15px] leading-relaxed text-secondary">
            There is no official BIS bulk API, so every standard is collected from its own public detail
            page. That gives the number, the title, the status, the supersession chain, the amendments, the
            certification position, the recognised laboratories and the cross-references in both
            directions — as published data rather than as anything a model produced.
          </p>

          <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { value: data?.catalogue.total, label: 'standards catalogued' },
              { value: data?.catalogue.current, label: 'current' },
              { value: data?.catalogue.cross_references, label: 'cross-references' },
              { value: data?.catalogue.labs, label: 'recognised laboratories' },
            ].map((item) => (
              <div key={item.label} className="card p-5">
                <div className="mono text-[24px] font-medium tracking-tight text-text">
                  {formatNumber(item.value ?? null)}
                </div>
                <div className="mt-1.5 text-[12.5px] leading-snug text-secondary">{item.label}</div>
              </div>
            ))}
          </div>
        </section>

        {/* ── stage 02 ─────────────────────────────────────────────── */}
        <section className="mt-20">
          <SectionLabel index="02">Stage C1 — retrieve and fuse</SectionLabel>
          <h2 className="mt-5 text-[clamp(1.5rem,3.2vw,2.1rem)] font-semibold tracking-[-0.02em]">
            Four rankings <span className="text-ember">become one.</span>
          </h2>
          <p className="mt-4 max-w-2xl text-[15px] leading-relaxed text-secondary">
            Each signal is wrong in a different way, so they are merged by position rather than by score —
            a cosine distance and a BM25 score are not comparable numbers. Reciprocal Rank Fusion with the
            standard constant of 60, which is not a tuning knob.
          </p>

          <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-[1fr_1fr_1fr_1fr_1.1fr]">
            {SIGNALS.map((signal) => (
              <div key={signal.name} className="card p-4">
                <div className="flex items-center justify-between">
                  <span className="mono text-[11px]" style={{ color: signal.tint }}>
                    {signal.name}
                  </span>
                  <span className="mono text-[10px] text-muted">{signal.kind}</span>
                </div>
                <div className="mt-3 h-px w-full" style={{ background: `${signal.tint}40` }} />
                <p className="mt-3 text-[12.5px] leading-relaxed text-secondary">{signal.what}</p>
              </div>
            ))}

            <div className="card border-amber/30 bg-[rgb(255_138_91/0.05)] p-4">
              <div className="flex items-center justify-between">
                <span className="mono text-[11px] text-amber">FUSION</span>
                <span className="mono text-[10px] text-muted">rrf</span>
              </div>
              <code className="mono mt-3 block rounded-lg bg-black/35 px-2.5 py-2 text-[11px] leading-relaxed text-text">
                1 / (60 + rank)
              </code>
              <p className="mt-3 text-[12.5px] leading-relaxed text-secondary">
                Summed across the signals that found it. A standard two lists agree on beats one that a
                single list loved.
              </p>
            </div>
          </div>
        </section>

        {/* ── stage 03 ─────────────────────────────────────────────── */}
        <section className="mt-20">
          <SectionLabel index="03">Stage C2 — the graph</SectionLabel>
          <h2 className="mt-5 text-[clamp(1.5rem,3.2vw,2.1rem)] font-semibold tracking-[-0.02em]">
            The part a vector index can never produce.
          </h2>
          <p className="mt-4 max-w-2xl text-[15px] leading-relaxed text-secondary">
            Allied standards are not similar to the product standard — a test method for cement does not
            read like a cement specification, and no embedding will put them near each other. They are
            reached by walking BIS's own cross-reference graph two hops out, then grouped by the role each
            standard plays. The role comes from the cited standard's own Aspect field, which is BIS's
            classification rather than our guess.
          </p>

          <div className="mt-8 grid gap-3 sm:grid-cols-3">
            {[
              { label: 'Normative references', weight: '1.00', tint: '#5B8CFF' },
              { label: 'Test methods', weight: '0.95', tint: '#72D6A5' },
              { label: 'Terminology', weight: '0.80', tint: '#B99CE0' },
              { label: 'Safety', weight: '0.85', tint: '#FF6B6B' },
              { label: 'Installation', weight: '0.70', tint: '#FF8A5B' },
              { label: 'Related products', weight: '0.60', tint: '#E95D9C' },
            ].map((item) => (
              <div key={item.label} className="card flex items-center gap-3 p-4">
                <span className="h-7 w-0.5 rounded-full" style={{ background: item.tint }} />
                <span className="flex-1 text-[13.5px] text-text">{item.label}</span>
                <span className="mono text-[12px] text-muted">{item.weight}</span>
              </div>
            ))}
          </div>
          <p className="mt-4 text-[12.5px] text-muted">
            Two hops is a hard cap. At three, standards reference each other densely enough that a hundred
            unrelated ones arrive.
          </p>
        </section>

        {/* ── stage 04 ─────────────────────────────────────────────── */}
        <section className="mt-20">
          <SectionLabel index="04">Stage D1 — the guard</SectionLabel>
          <h2 className="mt-5 text-[clamp(1.5rem,3.2vw,2.1rem)] font-semibold tracking-[-0.02em]">
            A fabricated IS number inside a live tender is the one failure this cannot survive.
          </h2>
          <p className="mt-4 max-w-2xl text-[15px] leading-relaxed text-secondary">
            Trace where a recommended standard comes from. Retrieval returns row numbers that a lookup
            table turns into real catalogue entries. The graph traverses edges whose endpoints are rows in
            a table. Version resolution is a catalogue lookup. Every standard in the structured answer
            arrived from a database, so by construction it cannot be invented.
          </p>
          <p className="mt-4 max-w-2xl text-[15px] leading-relaxed text-secondary">
            The single component that could write a number that does not exist is the sentence a language
            model composes to explain the match. That sentence — and only that sentence — is checked
            against the full catalogue before anyone reads it. Anything not found is deleted, not softened,
            and the interface says what was removed.
          </p>
        </section>

        {/* ── measurement ──────────────────────────────────────────── */}
        <section className="mt-20">
          <SectionLabel index="05">How we know it works</SectionLabel>
          <h2 className="mt-5 text-[clamp(1.5rem,3.2vw,2.1rem)] font-semibold tracking-[-0.02em]">
            A frozen gold set, written before the retrieval code.
          </h2>
          <p className="mt-4 max-w-2xl text-[15px] leading-relaxed text-secondary">
            Fifty hand-written pairs of plain product description and the standard that is actually
            correct, across the two sectors. It is frozen so that it measures rather than guides.
          </p>

          <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { key: 'hit@1' as const, label: 'Hit@1', note: 'correct standard ranked first' },
              { key: 'hit@3' as const, label: 'Hit@3', note: 'correct standard in the top three' },
              { key: 'hit@5' as const, label: 'Hit@5', note: 'correct standard in the top five' },
              { key: 'mrr@5' as const, label: 'MRR@5', note: 'mean reciprocal rank' },
            ].map((metric) => {
              const value = data?.evaluation?.[metric.key]
              return (
                <div key={metric.key} className="card p-5">
                  <span className="mono text-[10px] uppercase tracking-[0.14em] text-muted">{metric.label}</span>
                  <div className="mono mt-2 text-[30px] font-medium tracking-tight text-ember">
                    {value != null ? value.toFixed(value >= 1 ? 2 : 3) : '—'}
                  </div>
                  <p className="mt-1.5 text-[12px] leading-snug text-secondary">{metric.note}</p>
                </div>
              )
            })}
          </div>

          <div className="mt-5 flex flex-wrap gap-2">
            {data?.evaluation?.gold_records != null && (
              <Chip>{data.evaluation.gold_records} gold records</Chip>
            )}
            {data?.index?.standards != null && (
              <Chip>{formatNumber(data.index.standards)} standards with full text</Chip>
            )}
            {data?.index?.clauses != null && <Chip>{formatNumber(data.index.clauses)} clauses indexed</Chip>}
            {data?.sectors?.map((sector) => <Chip key={sector}>{sector}</Chip>)}
          </div>

          <p className="mt-5 max-w-2xl text-[13px] leading-relaxed text-muted">
            The score is bounded by corpus coverage, not by the search engine: a standard whose text we do
            not hold cannot be retrieved from its clauses, only from its title. Both figures are reported
            for that reason — quoting the flattering one alone would be the kind of thing this product
            exists to stop.
          </p>
        </section>

        <div className="mt-20 flex justify-center">
          <Link to="/workspace" className="btn btn-primary px-7">
            Find the standard
            <Icon.Arrow />
          </Link>
        </div>
      </main>
    </div>
  )
}
