import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

import { api, ApiError } from '../services/api'
import type { StandardDetail } from '../types/api'
import { Chip, ErrorState, Icon, Label, Skeleton } from './ui'
import { RELATION_TINTS, relationLabel, severityDot, severityStyle } from '../lib/format'
import { useT } from '../i18n'

/**
 * Everything the catalogue holds about one standard.
 *
 * It exists mainly to settle one question that caused a real misreading during the build: an
 * amendment is not a new edition. A standard can carry three amendments and still be the 2014
 * edition, and a tender that cites it as amended is correct. The panel says so in those words.
 */

export function StandardDrawer({
  isNumber,
  onClose,
  onOpenStandard,
}: {
  isNumber: string | null
  onClose: () => void
  onOpenStandard: (isNumber: string) => void
}) {
  const t = useT()
  const [detail, setDetail] = useState<StandardDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!isNumber) return
    let alive = true
    setLoading(true)
    setError(null)
    setDetail(null)

    api
      .standard(isNumber)
      .then((data) => alive && setDetail(data))
      .catch((e: unknown) => {
        if (!alive) return
        setError(
          e instanceof ApiError && e.status === 404
            ? t('standard.missing', { standard: isNumber })
            : e instanceof ApiError
              ? e.friendly
              : t('standard.loadFailed'),
        )
      })
      .finally(() => alive && setLoading(false))

    return () => {
      alive = false
    }
  }, [isNumber, t])

  // Escape closes, as it must for anything that covers the page.
  useEffect(() => {
    if (!isNumber) return
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [isNumber, onClose])

  const resolved = detail?.resolved

  return (
    <AnimatePresence>
      {isNumber && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            onClick={onClose}
            className="fixed inset-0 z-50 bg-black/55 backdrop-blur-sm"
          />

          <motion.aside
            role="dialog"
            aria-modal="true"
            aria-label={t('standard.detailsFor', { standard: isNumber ?? '' })}
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
            className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[460px] flex-col border-l border-white/8 bg-ink-1/95 backdrop-blur-2xl"
          >
            <header className="flex h-16 shrink-0 items-center gap-3 border-b border-white/6 px-5">
              <Label>{t('standard.label')}</Label>
              <div className="flex-1" />
              <button
                type="button"
                onClick={onClose}
                aria-label={t('action.close')}
                autoFocus
                className="flex h-9 w-9 items-center justify-center rounded-lg border border-white/8 bg-white/[0.03] text-secondary transition-colors hover:text-text"
              >
                <Icon.Close />
              </button>
            </header>

            <div className="flex-1 overflow-y-auto px-5 py-5">
              {loading && (
                <div className="space-y-3">
                  <Skeleton className="h-8 w-48" />
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-3/4" />
                  <Skeleton className="h-28 w-full" />
                </div>
              )}

              {error && <ErrorState title={t('standard.notAvailable')} message={error} />}

              {resolved && (
                <div className="space-y-5">
                  <div>
                    <h2 className="mono text-[23px] font-medium tracking-tight text-text">
                      {resolved.current ?? isNumber}
                    </h2>
                    <p className="mt-2 text-[13.5px] leading-relaxed text-secondary">{resolved.title}</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Chip tone={resolved.withdrawn ? 'plain' : 'warm'}>
                        {resolved.withdrawn ? t('standard.withdrawn') : t('results.inForce')}
                      </Chip>
                      {detail.certification?.certification_required && <Chip>{t('results.isiCompulsory')}</Chip>}
                      {detail.certification?.labs_available > 0 && (
                        <Chip>{t('standard.labCount', { count: detail.certification.labs_available })}</Chip>
                      )}
                    </div>
                  </div>

                  {resolved.current && resolved.current !== isNumber && (
                    <div className="rounded-xl border border-[rgb(255_138_91/0.28)] bg-[rgb(255_138_91/0.07)] p-4">
                      <p className="text-[13px] leading-relaxed text-secondary">
                        {t('standard.editionNotice', { requested: isNumber, current: resolved.current })}
                      </p>
                    </div>
                  )}

                  {resolved.amendments.length > 0 && (
                    <section>
                      <Label>{t('standard.amendmentsInForce')}</Label>
                      <div className="mt-3 space-y-1.5">
                        {resolved.amendments.map((amendment) => (
                          <div
                            key={`${amendment.number}-${amendment.year}`}
                            className="card-quiet flex items-center gap-3 px-3.5 py-2.5"
                          >
                            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber" />
                            <span className="flex-1 text-[13px] text-text">{amendment.number}</span>
                            <span className="mono text-[12px] text-secondary">{amendment.year}</span>
                          </div>
                        ))}
                      </div>
                      <p className="mt-3 text-[12px] leading-relaxed text-muted">
                        {t('results.amendmentNote')}
                      </p>
                    </section>
                  )}

                  {resolved.warnings.length > 0 && (
                    <section>
                      <Label>{t('results.warnings')}</Label>
                      <div className="mt-3 space-y-2">
                        {resolved.warnings.map((warning, index) => (
                          <div
                            key={index}
                            className={`flex items-start gap-2.5 rounded-xl border p-3.5 ${severityStyle(warning.severity)}`}
                          >
                            <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${severityDot(warning.severity)}`} />
                            <p className="text-[13px] leading-snug text-text">{warning.message}</p>
                          </div>
                        ))}
                      </div>
                    </section>
                  )}

                  {detail.certification && (
                    <section>
                      <Label>{t('results.certification')}</Label>
                      <p className="mt-3 text-[13.5px] leading-relaxed text-text">
                        {detail.certification.statement}
                      </p>
                      {detail.certification.nearest_labs.length > 0 && (
                        <div className="mt-3 space-y-1.5">
                          {detail.certification.nearest_labs.slice(0, 3).map((lab) => (
                            <div
                              key={`${lab.name}-${lab.city}`}
                              className="card-quiet flex items-center gap-2.5 px-3 py-2.5"
                            >
                              <span className="text-blue">
                                <Icon.Lab />
                              </span>
                              <span className="min-w-0 flex-1 truncate text-[12.5px] text-text">{lab.name}</span>
                              <span className="shrink-0 text-[11px] text-muted">{lab.city}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </section>
                  )}

                  {Object.entries(detail.allied).filter(([, items]) => items.length > 0).length > 0 && (
                    <section>
                      <Label>{t('standard.alliedByRole')}</Label>
                      <div className="mt-3 space-y-3">
                        {Object.entries(detail.allied)
                          .filter(([, items]) => items.length > 0)
                          .map(([relation, items]) => (
                            <div key={relation}>
                              <div className="flex items-center gap-2">
                                <span
                                  className="h-2.5 w-0.5 rounded-full"
                                  style={{ background: RELATION_TINTS[relation] ?? '#71717A' }}
                                />
                                <span className="text-[12px] text-secondary">{relationLabel(relation)}</span>
                              </div>
                              <div className="mt-2 flex flex-wrap gap-1.5">
                                {items.slice(0, 12).map((item) => (
                                  <button
                                    key={item.is_number}
                                    type="button"
                                    onClick={() => onOpenStandard(item.is_number)}
                                    title={item.title}
                                    className="mono rounded-lg border border-white/8 bg-white/[0.03] px-2 py-1 text-[11px] text-secondary transition-colors hover:border-white/18 hover:text-text"
                                  >
                                    {item.is_number}
                                  </button>
                                ))}
                              </div>
                            </div>
                          ))}
                      </div>
                    </section>
                  )}
                </div>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}
