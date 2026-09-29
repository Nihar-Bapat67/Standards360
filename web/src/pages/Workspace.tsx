import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { Atmosphere } from '../components/Atmosphere'
import { AssistantMessage, Composer, StageStream, UserMessage } from '../components/Chat'
import { Sidebar } from '../components/Sidebar'
import { ProductName } from '../components/ProductName'
import { Icon, Label } from '../components/ui'
import { LanguageSelector } from '../components/LanguageSelector'
import { useT } from '../i18n'
import { useAnalysis } from '../hooks/useAnalysis'
import { type Conversation, type Message, newId, store, titleFor } from '../services/conversations'
import { profile } from '../services/profile'
import type { AnalyzeResponse, Persona } from '../types/api'

/**
 * The workspace: the conversation, and nothing else.
 *
 * The answer used to sit in a 400px column beside this one, which put the standard, its evidence,
 * thirty allied standards, the certification position and the laboratory list into a strip narrower
 * than a phone. It now has a page of its own, and the conversation keeps only what a conversation is
 * for: saying what you need, and being asked for what is missing.
 *
 * When an answer arrives the page hands over to `/results/:id` by itself; coming back returns to this
 * same thread through `?c=<id>` so the enquiry can be refined and run again.
 */

const EXAMPLES = [
  'Supply of 500 MT ordinary Portland cement, 43 grade, for RCC structural work, as per IS 8112:1989',
  'Supply of 200 MT structural steel tubes YSt 240, 50 NB medium class, for pipe truss of an industrial shed',
  'Centrifugally cast ductile iron pipes, DN 300, class K9, for water distribution mains',
  'steel tubes',
]

export function Workspace() {
  const t = useT()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()

  const [conversations, setConversations] = useState<Conversation[]>(() => store.all())
  const [activeId, setActiveId] = useState<string | null>(
    () => params.get('c') ?? store.all()[0]?.id ?? null,
  )
  const [persona, setPersona] = useState<Persona>(() => profile.get()?.role ?? 'procurement')
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const analysis = useAnalysis()
  const thread = useRef<HTMLDivElement>(null)

  const active = useMemo(
    () => conversations.find((c) => c.id === activeId) ?? null,
    [conversations, activeId],
  )

  const answered = useMemo(
    () => [...(active?.messages ?? [])].reverse().some((m) => m.result?.primary),
    [active],
  )

  const refresh = useCallback(() => setConversations(store.all()), [])

  const persist = useCallback(
    (conversation: Conversation) => {
      const updated = { ...conversation, updatedAt: Date.now() }
      updated.title = titleFor(updated)
      store.save(updated)
      refresh()
      return updated
    },
    [refresh],
  )

  useEffect(() => {
    thread.current?.scrollTo({ top: thread.current.scrollHeight, behavior: 'smooth' })
  }, [active?.messages.length, analysis.stages.length, analysis.state])

  // Keep the address bar in step, so a refresh or a return from the results page lands on the same
  // thread rather than on whichever one happens to be newest.
  useEffect(() => {
    if (activeId && params.get('c') !== activeId) setParams({ c: activeId }, { replace: true })
  }, [activeId, params, setParams])

  /* ── running a turn ───────────────────────────────────────────────── */

  const ensureConversation = useCallback((): Conversation => {
    if (active) return active
    const created = store.create(persona)
    store.save(created)
    setActiveId(created.id)
    refresh()
    return created
  }, [active, persona, refresh])

  const finish = useCallback(
    (conversation: Conversation, result: AnalyzeResponse | null, error: string | null) => {
      const assistant: Message = {
        id: newId(),
        role: 'assistant',
        at: Date.now(),
        text: error ? '' : result?.explanation || '',
        result: result ?? undefined,
        stages: analysis.stages,
        error: error ?? undefined,
      }
      persist({ ...conversation, messages: [...conversation.messages, assistant] })

    },
    [analysis.stages, persist],
  )

  const send = useCallback(
    async (text: string) => {
      const conversation = ensureConversation()
      const user: Message = { id: newId(), role: 'user', text, at: Date.now() }
      const withUser = persist({ ...conversation, messages: [...conversation.messages, user] })

      const result = await analysis.runText({
        text,
        persona,
        answers: Object.keys(withUser.answers).length ? withUser.answers : null,
        ...contextFor(withUser),
      })
      finish(withUser, result, result ? null : analysis.error ?? 'The engine failed while answering.')
    },
    [analysis, ensureConversation, finish, persist, persona],
  )

  const sendFile = useCallback(
    async (file: File) => {
      const conversation = ensureConversation()
      const user: Message = {
        id: newId(),
        role: 'user',
        text: '',
        at: Date.now(),
        attachment: { name: file.name, size: file.size },
      }
      const withUser = persist({ ...conversation, messages: [...conversation.messages, user] })

      const result = await analysis.runFile(file, persona, null, contextFor(withUser))
      finish(withUser, result, result ? null : analysis.error ?? t('error.cannotReadFile'))
    },
    [analysis, ensureConversation, finish, persist, persona, t],
  )

  /** B5's loop: the answer is merged into the requirement and the whole request runs again. */
  const answer = useCallback(
    async (field: string, value: string) => {
      if (!active) return
      const answers = { ...active.answers, [field]: value }
      const user: Message = { id: newId(), role: 'user', text: value, at: Date.now() }
      const withAnswer = persist({ ...active, answers, messages: [...active.messages, user] })

      const result = await analysis.runText({
        text: value,
        persona,
        answers,
        ...contextFor(withAnswer),
      })
      finish(withAnswer, result, result ? null : analysis.error ?? 'The engine failed while answering.')
    },
    [active, analysis, finish, persist, persona],
  )

  const retry = useCallback(async () => {
    if (!active) return
    const withoutLast = {
      ...active,
      messages: active.messages.filter((m) => m.role !== 'assistant' || !m.error),
    }
    const lastUser = [...withoutLast.messages].reverse().find((m) => m.role === 'user')
    if (!lastUser) return
    persist(withoutLast)

    const result = await analysis.runText({
      text: lastUser.text,
      persona,
      answers: Object.keys(withoutLast.answers).length ? withoutLast.answers : null,
      ...contextFor(withoutLast),
    })
    finish(withoutLast, result, result ? null : analysis.error ?? 'The engine failed while answering.')
  }, [active, analysis, finish, persist, persona])

  /* ── conversation management ──────────────────────────────────────── */

  const startNew = () => {
    const created = store.create(persona)
    store.save(created)
    setActiveId(created.id)
    analysis.reset()
    setSidebarOpen(false)
    refresh()
  }

  const remove = (id: string) => {
    store.remove(id)
    const rest = store.all()
    setConversations(rest)
    if (activeId === id) {
      setActiveId(rest[0]?.id ?? null)
      analysis.reset()
    }
  }

  const togglePin = (id: string) => {
    const conversation = store.get(id)
    if (conversation) persist({ ...conversation, pinned: !conversation.pinned })
  }

  const signOut = () => {
    profile.clear()
    navigate('/login', { replace: true })
  }

  const busy = analysis.state === 'running'
  const messages = active?.messages ?? []

  const sidebar = (onClose?: () => void) => (
    <Sidebar
      conversations={conversations}
      activeId={activeId}
      persona={persona}
      onSelect={(id) => {
        setActiveId(id)
        onClose?.()
      }}
      onNew={startNew}
      onDelete={remove}
      onTogglePin={togglePin}
      onPersona={setPersona}
      onSignOut={signOut}
      onClose={onClose}
    />
  )

  return (
    <div className="flex h-dvh overflow-hidden">
      <Atmosphere variant="work" />

      <div className="hidden w-[272px] shrink-0 lg:block">{sidebar()}</div>

      <AnimatePresence>
        {sidebarOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setSidebarOpen(false)}
              className="fixed inset-0 z-40 bg-black/55 backdrop-blur-sm lg:hidden"
            />
            <motion.div
              initial={{ x: '-100%' }}
              animate={{ x: 0 }}
              exit={{ x: '-100%' }}
              transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
              className="fixed left-0 top-0 z-50 h-full w-[280px] lg:hidden"
            >
              {sidebar(() => setSidebarOpen(false))}
            </motion.div>
          </>
        )}
      </AnimatePresence>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 shrink-0 items-center gap-3 border-b border-white/6 px-4 backdrop-blur-xl sm:px-6">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            aria-label={t('workspace.openMenu')}
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-white/8 bg-white/[0.03] text-secondary lg:hidden"
          >
            <Icon.Menu />
          </button>

          <div className="min-w-0 flex-1">
            <ProductName small />
            <p className="truncate text-[14px] font-medium text-text">
              {active ? titleFor(active) : t('workspace.newEnquiry')}
            </p>
            <p className="mono truncate text-[11px] text-muted">
              {persona === 'procurement' ? t('workspace.officer') : t('workspace.manufacturer')} ·{' '}
              {t('workspace.runsOffline')}
            </p>
          </div>

          <LanguageSelector compact />

          {answered && activeId && (
            <Link to={`/results/${activeId}`} className="btn btn-ghost h-9 px-3.5 text-[12.5px]">
              {t('workspace.applicableStandards')}
              <Icon.Arrow />
            </Link>
          )}
        </header>

        <div ref={thread} className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
          <div className="mx-auto flex max-w-[760px] flex-col gap-5">
            {messages.length === 0 && analysis.state === 'idle' && (
              <Welcome onPick={send} persona={persona} />
            )}

            {messages.map((message) =>
              message.role === 'user' ? (
                <UserMessage key={message.id} message={message} />
              ) : (
                <AssistantMessage
                  key={message.id}
                  message={message}
                  isActive={message.id === messages[messages.length - 1]?.id}
                  onAnswer={answer}
                  onFollowup={send}
                  onRetry={retry}
                  onOpenFindings={() => activeId && navigate(`/results/${activeId}`)}
                />
              ),
            )}

            {busy && <StageStream stages={analysis.stages} />}
          </div>
        </div>

        <div className="mx-auto w-full max-w-[760px] shrink-0">
          <Composer onSend={send} onFile={sendFile} busy={busy} />
        </div>
      </main>
    </div>
  )
}

/* ── empty state ──────────────────────────────────────────────────────── */

function Welcome({ onPick, persona }: { onPick: (text: string) => void; persona: Persona }) {
  const t = useT()
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className="pt-10"
    >
      <Label className="text-amber">{t('workspace.intake')}</Label>
      <h1 className="mt-4 text-[clamp(1.5rem,4vw,2rem)] font-semibold leading-tight tracking-[-0.025em]">
        {persona === 'procurement'
          ? t('workspace.heading.officer')
          : t('workspace.heading.manufacturer')}
      </h1>
      <p className="mt-4 max-w-lg text-[15px] leading-relaxed text-secondary">
        {t('workspace.intro')}
      </p>

      <div className="mt-8">
        <Label>{t('workspace.tryOne')}</Label>
        <div className="mt-3 grid gap-2">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => onPick(example)}
              className="card card-hover px-4 py-3.5 text-left text-[13.5px] leading-snug text-secondary hover:text-text"
            >
              {example}
            </button>
          ))}
        </div>
      </div>
    </motion.div>
  )
}

/**
 * What the engine is asked.
 *
 * The pipeline is stateless per call, so a follow-up has to carry the context with it. The user's
 * own words are joined in order; the answers to clarifying questions travel separately in the
 * `answers` field, which is what B5 merges into the requirement.
 */
function contextFor(conversation: Conversation) {
  const previous = [...conversation.messages].reverse().find((message) => message.result?.requirement)
  return {
    history: conversation.messages.slice(-9, -1).map(({ role, text }) => ({ role, text })),
    previous_requirement: previous?.result?.requirement ?? null,
  }
}
