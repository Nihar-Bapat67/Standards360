/**
 * Conversation history, kept in this browser and nowhere else.
 *
 * This is a deliberate product decision rather than a shortcut. An uploaded tender may be
 * pre-tender confidential, so the engine already writes uploads to a temporary file, reads them and
 * deletes them. Storing the resulting conversations on a server would undo that. Everything here
 * lives in localStorage, belongs to the person at this machine, and never leaves it.
 */

import type { AnalyzeResponse, Persona, StageEvent } from '../types/api'

export interface Message {
  id: string
  role: 'user' | 'assistant'
  text: string
  at: number
  /** Present on an assistant message that carries a finished analysis. */
  result?: AnalyzeResponse
  /** The stages the engine reported while producing it, kept so a reopened thread still shows them. */
  stages?: StageEvent[]
  /** Set when the engine failed, so the thread can offer a retry rather than losing the turn. */
  error?: string
  /** The file this turn was about, if any. */
  attachment?: { name: string; size: number }
}

export interface Conversation {
  id: string
  title: string
  persona: Persona
  createdAt: number
  updatedAt: number
  messages: Message[]
  /** Answers already given to the engine's clarifying questions, merged into the next request. */
  answers: Record<string, string>
  pinned?: boolean
}

const KEY = 'standards360.conversations.v1'
const LIMIT = 60

export function newId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

/** localStorage throws in private mode and in some embedded browsers; never let that break the app. */
function safeRead(): Conversation[] {
  try {
    const raw = window.localStorage.getItem(KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as Conversation[]) : []
  } catch {
    return []
  }
}

function safeWrite(conversations: Conversation[]): void {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(conversations.slice(0, LIMIT)))
  } catch {
    /* a full or blocked store is not worth interrupting the person over */
  }
}

export const store = {
  all(): Conversation[] {
    return safeRead().sort((a, b) => {
      if (!!a.pinned !== !!b.pinned) return a.pinned ? -1 : 1
      return b.updatedAt - a.updatedAt
    })
  },

  get(id: string): Conversation | undefined {
    return safeRead().find((c) => c.id === id)
  },

  save(conversation: Conversation): void {
    const rest = safeRead().filter((c) => c.id !== conversation.id)
    safeWrite([conversation, ...rest])
  },

  remove(id: string): void {
    safeWrite(safeRead().filter((c) => c.id !== id))
  },

  clear(): void {
    safeWrite([])
  },

  create(persona: Persona): Conversation {
    const now = Date.now()
    return {
      id: newId(),
      title: 'New enquiry',
      persona,
      createdAt: now,
      updatedAt: now,
      messages: [],
      answers: {},
    }
  },
}

/**
 * A thread's name, taken from what the person actually asked.
 *
 * Once the engine has named a primary standard that becomes the title, because "IS 1161:2014" is
 * what someone scanning a sidebar is looking for. Until then the first line of their own words is
 * more use than "New enquiry".
 */
export function titleFor(conversation: Conversation): string {
  const answered = [...conversation.messages].reverse().find((m) => m.result?.primary)
  if (answered?.result?.primary) return answered.result.primary

  const first = conversation.messages.find((m) => m.role === 'user')
  if (!first) return 'New enquiry'

  const words = first.text.trim().split(/\s+/).slice(0, 7).join(' ')
  return words.length > 52 ? `${words.slice(0, 52)}…` : words || 'New enquiry'
}

export function searchConversations(conversations: Conversation[], term: string): Conversation[] {
  const needle = term.trim().toLowerCase()
  if (!needle) return conversations
  return conversations.filter((conversation) => {
    if (titleFor(conversation).toLowerCase().includes(needle)) return true
    return conversation.messages.some((message) => message.text.toLowerCase().includes(needle))
  })
}
