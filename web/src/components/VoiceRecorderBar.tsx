/**
 * VoiceRecorderBar: live waveform level meter, timer, and controls during dictation.
 *
 * Renders in place of the Composer textarea while dictating:
 *   - Real audio waveform bars driven by Web Audio AnalyserNode frequency bins.
 *   - mm:ss elapsed timer with an animate-pulse-dot status indicator.
 *   - Full keyboard accessibility: Enter = Confirm (✓), Escape = Cancel (✕).
 *   - Mobile touch targets >= 44px with responsive bar distribution.
 *   - Accessible aria-live status announcements.
 */

import { useEffect } from 'react'
import { motion } from 'framer-motion'
import { Icon } from './ui'
import { useT } from '../i18n'
import type { VoiceState } from '../hooks/useVoiceInput'

interface VoiceRecorderBarProps {
  state: VoiceState
  elapsedSeconds: number
  levels: number[]
  onConfirm: () => void
  onCancel: () => void
  disabled?: boolean
}

function formatTimer(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}

export function VoiceRecorderBar({
  state,
  elapsedSeconds,
  levels,
  onConfirm,
  onCancel,
  disabled = false,
}: VoiceRecorderBarProps) {
  const t = useT()

  // Full keyboard operation: Enter = confirm & transcribe, Esc = cancel recording
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (state === 'transcribing') return
      if (event.key === 'Escape') {
        event.preventDefault()
        onCancel()
      } else if (event.key === 'Enter') {
        event.preventDefault()
        onConfirm()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [state, onConfirm, onCancel])

  const liveAnnouncement =
    state === 'recording'
      ? `${t('composer.recording')} ${formatTimer(elapsedSeconds)}`
      : state === 'transcribing'
        ? t('composer.transcribing')
        : ''

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.99 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.99 }}
      transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
      className="flex min-h-[44px] flex-1 items-center justify-between gap-2 px-1 py-0.5 select-none"
    >
      <div className="sr-only" aria-live="polite">
        {liveAnnouncement}
      </div>

      {/* Timer and status indicator */}
      <div className="flex items-center gap-2 shrink-0 pl-1">
        <span
          className={`h-2.5 w-2.5 rounded-full ${
            state === 'transcribing' ? 'bg-amber animate-pulse' : 'bg-red animate-pulse-dot'
          }`}
          aria-hidden="true"
        />
        <span className="mono text-[13.5px] font-medium text-text tabular-nums">
          {formatTimer(elapsedSeconds)}
        </span>
      </div>

      {/* Middle: live VU meter bars or transcribing state */}
      <div className="flex flex-1 items-center justify-center min-w-0 px-2">
        {state === 'transcribing' ? (
          <div className="flex items-center gap-2">
            <svg
              className="h-4 w-4 animate-spin text-amber shrink-0"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="3"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
            <span className="text-[13px] font-medium text-secondary truncate">
              {t('composer.transcribing')}
            </span>
          </div>
        ) : (
          <div
            className="flex h-6 w-full max-w-[220px] sm:max-w-[280px] items-center justify-center gap-[3px] sm:gap-[4px] overflow-hidden"
            aria-hidden="true"
          >
            {levels.map((level, index) => (
              <div
                key={index}
                className="w-[2.5px] sm:w-[3px] rounded-full transition-[height] duration-75 shrink-0"
                style={{
                  height: `${Math.max(4, Math.round(level * 24))}px`,
                  background: 'linear-gradient(to top, #FF8A5B 0%, #FF5F7A 55%, #E95D9C 100%)',
                  opacity: 0.35 + level * 0.65,
                }}
              />
            ))}
          </div>
        )}
      </div>

      {/* Cancel and Confirm buttons */}
      <div className="flex items-center gap-1.5 shrink-0">
        <button
          type="button"
          onClick={onCancel}
          disabled={disabled || state === 'transcribing'}
          aria-label={t('composer.micCancel')}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-white/8 bg-white/[0.03] text-secondary transition-colors hover:border-white/16 hover:text-red disabled:opacity-40"
        >
          <Icon.Close />
        </button>

        <button
          type="button"
          onClick={onConfirm}
          disabled={disabled || state === 'transcribing'}
          aria-label={t('composer.micStop')}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-[#0A0508] transition-all duration-300 disabled:opacity-35"
          style={{ background: 'linear-gradient(145deg,#FF8A5B 0%,#FF5F7A 55%,#E95D9C 100%)' }}
        >
          <Icon.Check />
        </button>
      </div>
    </motion.div>
  )
}
