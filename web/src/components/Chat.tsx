import { type ChangeEvent, type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

import type { AnalyzeResponse, Question, StageEvent } from '../types/api'
import type { Message } from '../services/conversations'
import { CopyButton, ErrorState, Icon, Label } from './ui'
import { MODULE_NAMES, formatBytes, relativeTime } from '../lib/format'
import { useMediaQuery } from '../hooks/useMediaQuery'

/* ── the engine working, reported by the engine ───────────────────────────
   These stages are real: each one arrives from the pipeline's own callback as
   that module finishes. Nothing here is on a timer. */

export function StageStream({ stages }: { stages: StageEvent[] }) {
  // C5 reports a confidence score. The engine still computes it and the API still returns it — a
  // procurement portal needs it — but it is not shown to a person here, so its progress line is not
  // shown either.
  const shown = stages.filter((stage) => stage.module !== 'C5')

  return (
    <div className="card-quiet max-w-[440px] p-3.5">
      <div className="flex items-center gap-2">
        <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-amber" />
        <Label>Working</Label>
      </div>
      <div className="mt-3 space-y-1.5">
        <AnimatePresence initial={false}>
          {shown.map((stage, index) => (
            <motion.div
              key={`${stage.module}-${index}`}
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: index === shown.length - 1 ? 1 : 0.5, x: 0 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
              className="flex items-baseline gap-2.5"
            >
              <span className="mono w-7 shrink-0 text-[10px] text-amber">{stage.module}</span>
              <span className="min-w-0 flex-1 text-[12.5px] leading-snug text-secondary">
                {stage.message}
              </span>
            </motion.div>
          ))}
        </AnimatePresence>
        {shown.length === 0 && (
          <p className="text-[12.5px] text-muted">Loading the models. After a restart this takes a minute.</p>
        )}
      </div>
      {shown.length > 0 && (
        <p className="mt-3 border-t border-white/6 pt-2.5 text-[11px] text-muted">
          {MODULE_NAMES[shown[shown.length - 1].module] ?? 'Running'}
        </p>
      )}
    </div>
  )
}

/* ── one turn ─────────────────────────────────────────────────────────── */

function UserMessage({ message }: { message: Message }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
      className="flex flex-col items-end gap-2"
    >
      {message.attachment && (
        <div className="flex items-center gap-2.5 rounded-2xl border border-[rgb(91_140_255/0.28)] bg-[rgb(91_140_255/0.10)] px-3.5 py-2.5">
          <span className="text-blue">
            <Icon.Doc />
          </span>
          <div className="min-w-0">
            <p className="truncate text-[13px] font-medium text-text">{message.attachment.name}</p>
            <p className="text-[11px] text-secondary">{formatBytes(message.attachment.size)}</p>
          </div>
        </div>
      )}
      {message.text && (
        <div className="max-w-[min(560px,88%)] rounded-[20px] rounded-br-lg border border-[rgb(91_140_255/0.26)] bg-[rgb(91_140_255/0.13)] px-4 py-3">
          <p className="whitespace-pre-wrap text-[14.5px] leading-relaxed text-text">{message.text}</p>
        </div>
      )}
    </motion.div>
  )
}

function AssistantMessage({
  message,
  onAnswer,
  onRetry,
  onOpenFindings,
  isActive,
}: {
  message: Message
  onAnswer: (field: string, value: string) => void
  onRetry: () => void
  onOpenFindings: () => void
  isActive: boolean
}) {
  if (message.error) {
    return (
      <div className="max-w-[min(560px,92%)]">
        <ErrorState message={message.error} onRetry={onRetry} />
      </div>
    )
  }

  const result = message.result

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
      className="flex max-w-[min(620px,94%)] flex-col gap-3"
    >
      {message.text && (
        <div className="rounded-[20px] rounded-bl-lg border border-white/8 bg-white/[0.045] px-4 py-3">
          <p className="whitespace-pre-wrap text-[14.5px] leading-relaxed text-text">{message.text}</p>
        </div>
      )}

      {/* B5's clarifying questions. The gate asks rather than guessing, so the chat must make
          answering one tap and must not hide the option to press on regardless. */}
      {result?.questions && result.questions.length > 0 && (
        <QuestionCard questions={result.questions} onAnswer={onAnswer} disabled={!isActive} />
      )}

      {result?.primary && (
        <button
          type="button"
          onClick={onOpenFindings}
          className="card card-hover group w-full p-4 text-left"
        >
          <div className="flex items-baseline justify-between gap-3">
            <span className="mono text-[17px] font-medium text-text">{result.primary}</span>
            <span className="text-[12px] text-amber">Open →</span>
          </div>
          <p className="mt-1.5 line-clamp-2 text-[13px] leading-snug text-secondary">{result.primary_title}</p>
          <div className="mt-3 flex items-center justify-between">
            <span className="text-[11px] text-muted">{summarise(result)}</span>
            <span className="text-[12px] text-muted">Applicable standards</span>
          </div>
        </button>
      )}

      {message.text && (
        <div className="flex items-center gap-2">
          <CopyButton text={message.text} />
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex h-7 items-center gap-1.5 rounded-lg border border-white/8 bg-white/[0.03] px-2.5 text-[11px] text-secondary transition-colors hover:border-white/16 hover:text-text"
          >
            <Icon.Retry />
            Regenerate
          </button>
          <span className="text-[11px] text-muted">{relativeTime(message.at)}</span>
        </div>
      )}
    </motion.div>
  )
}

function QuestionCard({
  questions,
  onAnswer,
  disabled,
}: {
  questions: Question[]
  onAnswer: (field: string, value: string) => void
  disabled: boolean
}) {
  const [typed, setTyped] = useState('')
  const question = questions[0]

  // Where the question offers a choice — "Seamless, electric resistance welded, or galvanized?" — the
  // options become chips, because tapping one is faster and less error-prone than retyping it.
  const choices = extractChoices(question.ask)

  return (
    <div className="rounded-[20px] border border-[rgb(255_138_91/0.26)] bg-[rgb(255_138_91/0.055)] p-4">
      <Label className="text-amber">One thing is missing</Label>
      <p className="mt-2.5 text-[14.5px] leading-relaxed text-text">{question.ask}</p>

      {choices.length > 0 ? (
        <div className="mt-3.5 flex flex-wrap gap-2">
          {choices.map((choice) => (
            <button
              key={choice}
              type="button"
              disabled={disabled}
              onClick={() => onAnswer(question.field, choice)}
              className="rounded-xl border border-[rgb(255_138_91/0.4)] bg-[rgb(255_138_91/0.09)] px-3.5 py-2 text-[13px] text-[#FFB894] transition-colors hover:bg-[rgb(255_138_91/0.16)] disabled:opacity-50"
            >
              {choice}
            </button>
          ))}
        </div>
      ) : (
        <form
          className="mt-3.5 flex gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            if (typed.trim()) onAnswer(question.field, typed.trim())
          }}
        >
          <label className="sr-only" htmlFor={`answer-${question.field}`}>
            {question.ask}
          </label>
          <input
            id={`answer-${question.field}`}
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            disabled={disabled}
            placeholder="Your answer"
            className="h-10 flex-1 rounded-xl border border-white/10 bg-black/25 px-3.5 text-[13.5px] text-text placeholder:text-muted focus:border-amber/50 focus:outline-none"
          />
          <button type="submit" disabled={disabled || !typed.trim()} className="btn btn-ghost h-10 px-4 text-[13px]">
            Answer
          </button>
        </form>
      )}

      <p className="mt-3 text-[11.5px] text-muted">
        The engine asks instead of guessing. The answer below it is already usable if you would rather
        press on.
      </p>
    </div>
  )
}

/**
 * The one line under the answer card.
 *
 * It must not say "1 of your citations needs changing" when the tender cited nothing at all. B4
 * emits an `add` verdict for a standard that should be cited but is not, which is a different thing
 * from a citation that is wrong, so the two are counted separately and only what happened is said.
 */
function summarise(result: AnalyzeResponse): string {
  const wrong = result.verdicts.filter((v) => v.verdict === 'replace' || v.verdict === 'remove').length
  const missing = result.verdicts.filter((v) => v.verdict === 'add').length

  const parts: string[] = []
  if (wrong) parts.push(`${wrong} citation${wrong === 1 ? '' : 's'} to change`)
  if (missing) parts.push(`${missing} to add`)
  if (parts.length) return parts.join(' · ')

  const allied = Object.values(result.allied).flat().length
  return allied ? `${allied} allied standards` : 'View the findings'
}

/**
 * Pull "A, B, or C?" out of a question so it can be offered as chips.
 *
 * Only a closed choice becomes chips. An open question — "What nominal diameter, and which class?"
 * — also contains a comma and the word "and", and splitting it produced two chips reading "What
 * nominal diameter" and "And which class", which are not answers to anything. A question opening
 * with an interrogative is asking for a value, so it gets a text box instead.
 */
function extractChoices(ask: string): string[] {
  const body = (/([^?]*)\?/.exec(ask)?.[1] ?? ask).trim()
  if (/^(what|which|how|where|when|why|describe|give|state|specify)/i.test(body)) return []
  if (!/ or /i.test(body)) return []

  const parts = body
    .split(/,| or /i)
    .map((part) => part.trim().replace(/^(is it|are they|should it be|and|the)\s+/i, ''))
    .filter(Boolean)

  // Every part has to look like a value: short, and not a question fragment of its own.
  const usable = parts.every(
    (part) => part.length > 1 && part.split(/\s+/).length <= 5 && !/(what|which|how)/i.test(part),
  )
  return usable && parts.length >= 2 && parts.length <= 4
    ? parts.map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    : []
}

/* ── the composer ─────────────────────────────────────────────────────── */

const ACCEPT = '.pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp'
const MAX_BYTES = 25 * 1024 * 1024

export function Composer({
  onSend,
  onFile,
  busy,
  placeholder = 'Describe the item, or paste a clause from the tender',
}: {
  onSend: (text: string) => void
  onFile: (file: File) => void
  busy: boolean
  placeholder?: string
}) {
  const narrow = useMediaQuery('(max-width: 640px)')
  const [text, setText] = useState('')
  const [fileError, setFileError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const area = useRef<HTMLTextAreaElement>(null)
  const picker = useRef<HTMLInputElement>(null)

  // Grow with the content up to a ceiling, so a pasted clause is readable without the composer
  // swallowing the conversation.
  useEffect(() => {
    const node = area.current
    if (!node) return
    node.style.height = 'auto'
    node.style.height = `${Math.min(node.scrollHeight, 168)}px`
  }, [text])

  const submit = (event?: FormEvent) => {
    event?.preventDefault()
    const value = text.trim()
    if (!value || busy) return
    onSend(value)
    setText('')
  }

  const keyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  const accept = (file: File | undefined) => {
    setFileError(null)
    if (!file) return
    const suffix = `.${file.name.split('.').pop()?.toLowerCase() ?? ''}`
    if (!ACCEPT.includes(suffix)) {
      setFileError('That file type cannot be read. Use a PDF, DOCX, text file or a screenshot.')
      return
    }
    if (file.size > MAX_BYTES) {
      setFileError('That file is larger than 25 MB. Try the specification pages on their own.')
      return
    }
    onFile(file)
  }

  const pick = (event: ChangeEvent<HTMLInputElement>) => {
    accept(event.target.files?.[0])
    event.target.value = ''
  }

  return (
    <div className="px-4 pb-4 pt-2 sm:px-6 sm:pb-6">
      {fileError && (
        <p role="alert" className="mb-2 text-[12.5px] text-red">
          {fileError}
        </p>
      )}

      <form
        onSubmit={submit}
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragging(false)
          accept(event.dataTransfer.files?.[0])
        }}
        className={`card flex items-end gap-2 p-2 transition-colors duration-300 ${
          dragging ? 'border-amber/50 bg-[rgb(255_138_91/0.06)]' : ''
        }`}
      >
        <input ref={picker} type="file" accept={ACCEPT} onChange={pick} className="sr-only" id="tender-file" />
        <button
          type="button"
          onClick={() => picker.current?.click()}
          disabled={busy}
          aria-label="Attach a tender, specification or screenshot"
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-white/8 bg-white/[0.03] text-secondary transition-colors hover:border-white/16 hover:text-text disabled:opacity-40"
        >
          <Icon.Paperclip />
        </button>

        <label className="sr-only" htmlFor="composer">
          Describe the item or paste a clause
        </label>
        <textarea
          ref={area}
          id="composer"
          rows={1}
          value={text}
          disabled={busy}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={keyDown}
          placeholder={
            dragging ? 'Drop the file to read it' : narrow ? 'Describe the item' : placeholder
          }
          className="max-h-[168px] min-h-[44px] flex-1 resize-none bg-transparent px-1 py-3 text-[14.5px] leading-snug text-text placeholder:text-muted focus:outline-none disabled:opacity-50"
        />

        <button
          type="submit"
          disabled={busy || !text.trim()}
          aria-label="Send"
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-[#0A0508] transition-all duration-300 disabled:opacity-35"
          style={{ background: 'linear-gradient(145deg,#FF8A5B 0%,#FF5F7A 55%,#E95D9C 100%)' }}
        >
          <Icon.Send />
        </button>
      </form>

      <p className="mt-2 px-1 text-[11px] leading-snug text-muted">
        <span className="hidden sm:inline">
          Enter to send, Shift+Enter for a new line. Uploads are read in memory and deleted immediately
          — a pre-tender document never lands on disk.
        </span>
        <span className="sm:hidden">Uploads are never written to disk.</span>
      </p>
    </div>
  )
}

export { UserMessage, AssistantMessage }
export type { AnalyzeResponse }
