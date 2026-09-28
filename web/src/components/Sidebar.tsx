import { useMemo, useState } from 'react'
import type { Conversation } from '../services/conversations'
import { searchConversations, titleFor } from '../services/conversations'
import type { Persona } from '../types/api'
import { Icon, Label } from './ui'
import { profile } from '../services/profile'
import { useT } from '../i18n'
import { Wordmark } from './Wordmark'
import { relativeTime } from '../lib/format'

/**
 * Conversation history and the persona switch.
 *
 * The persona is here rather than buried in settings because it changes the wording of the
 * certification answer — an eligibility condition for a procurement officer, an obligation and a
 * licence route for a manufacturer — and the person needs to see which one they are reading.
 */

interface SidebarProps {
  conversations: Conversation[]
  activeId: string | null
  persona: Persona
  onSelect: (id: string) => void
  onNew: () => void
  onDelete: (id: string) => void
  onTogglePin: (id: string) => void
  onPersona: (persona: Persona) => void
  onSignOut: () => void
  onClose?: () => void
}

export function Sidebar({
  conversations,
  activeId,
  persona,
  onSelect,
  onNew,
  onDelete,
  onTogglePin,
  onPersona,
  onSignOut,
  onClose,
}: SidebarProps) {
  const t = useT()
  const who = profile.get()
  const [term, setTerm] = useState('')
  const shown = useMemo(() => searchConversations(conversations, term), [conversations, term])

  return (
    <div className="flex h-full flex-col border-r border-white/6 bg-ink-1/80 backdrop-blur-xl">
      <div className="flex h-16 items-center gap-2 px-4">
        <Wordmark small />
        <div className="flex-1" />
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close the menu"
            className="flex h-9 w-9 items-center justify-center rounded-lg text-secondary hover:text-text lg:hidden"
          >
            <Icon.Close />
          </button>
        )}
      </div>

      <div className="px-3">
        <button type="button" onClick={onNew} className="btn btn-ghost h-10 w-full justify-start px-3 text-[13px]">
          <Icon.Plus />
          {t('workspace.newEnquiry')}
        </button>
      </div>

      <div className="px-3 pt-2.5">
        <div className="relative">
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted">
            <Icon.Search />
          </span>
          <label className="sr-only" htmlFor="search-conversations">
            Search your enquiries
          </label>
          <input
            id="search-conversations"
            value={term}
            onChange={(event) => setTerm(event.target.value)}
            placeholder={t('workspace.search')}
            className="h-9 w-full rounded-lg border border-white/8 bg-white/[0.03] pl-9 pr-3 text-[13px] text-text placeholder:text-muted focus:border-white/18 focus:outline-none"
          />
        </div>
      </div>

      <nav aria-label="Your enquiries" className="scroll-fade mt-3 flex-1 overflow-y-auto px-3 pb-3">
        {shown.length === 0 ? (
          <p className="px-2 py-6 text-[12.5px] leading-relaxed text-muted">
            {term ? t('workspace.noMatchSearch') : t('workspace.emptyHistory')}
          </p>
        ) : (
          <ul className="space-y-0.5">
            {shown.map((conversation) => {
              const active = conversation.id === activeId
              return (
                <li key={conversation.id} className="group relative">
                  <button
                    type="button"
                    onClick={() => onSelect(conversation.id)}
                    aria-current={active ? 'true' : undefined}
                    className={`w-full rounded-lg px-2.5 py-2.5 pr-14 text-left transition-colors ${
                      active ? 'bg-white/8 text-text' : 'text-secondary hover:bg-white/4 hover:text-text'
                    }`}
                  >
                    <span className="flex items-center gap-1.5">
                      {conversation.pinned && (
                        <span className="shrink-0 text-amber">
                          <Icon.Pin />
                        </span>
                      )}
                      <span className="truncate text-[13px]">{titleFor(conversation)}</span>
                    </span>
                    <span className="mt-0.5 block text-[11px] text-muted">
                      {relativeTime(conversation.updatedAt)}
                    </span>
                  </button>

                  <div className="absolute right-1.5 top-2 flex gap-0.5 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
                    <button
                      type="button"
                      onClick={() => onTogglePin(conversation.id)}
                      aria-label={conversation.pinned ? 'Unpin this enquiry' : 'Pin this enquiry'}
                      className="flex h-7 w-7 items-center justify-center rounded-md text-muted hover:bg-white/8 hover:text-text"
                    >
                      <Icon.Pin />
                    </button>
                    <button
                      type="button"
                      onClick={() => onDelete(conversation.id)}
                      aria-label="Delete this enquiry"
                      className="flex h-7 w-7 items-center justify-center rounded-md text-muted hover:bg-white/8 hover:text-red"
                    >
                      <Icon.Trash />
                    </button>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </nav>

      <div className="border-t border-white/6 p-3">
        <Label>{t('workspace.answeringAs')}</Label>
        <div
          role="radiogroup"
          aria-label="Persona"
          className="mt-2 grid grid-cols-2 gap-1 rounded-lg border border-white/8 bg-black/20 p-1"
        >
          {(['procurement', 'manufacturer'] as const).map((value) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={persona === value}
              onClick={() => onPersona(value)}
              className={`rounded-md px-2 py-2 text-[12px] capitalize transition-colors ${
                persona === value ? 'bg-white/10 text-text' : 'text-secondary hover:text-text'
              }`}
            >
              {value === 'procurement' ? t('workspace.officer') : t('workspace.manufacturer')}
            </button>
          ))}
        </div>
        <p className="mt-2 px-0.5 text-[11px] leading-relaxed text-muted">
          {persona === 'procurement'
            ? t('workspace.personaOfficer')
            : t('workspace.personaManufacturer')}
        </p>

        {who && (
          <div className="mt-3 flex items-center gap-2.5 border-t border-white/6 pt-3">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/8 text-[11px] font-medium text-secondary">
              {profile.initials(who)}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[12.5px] text-text">{who.name || who.email}</span>
              {who.organisation && (
                <span className="block truncate text-[11px] text-muted">{who.organisation}</span>
              )}
            </span>
            <button
              type="button"
              onClick={onSignOut}
              aria-label={t('action.signOut')}
              className="shrink-0 rounded-md px-2 py-1 text-[11px] text-muted transition-colors hover:bg-white/8 hover:text-text"
            >
              {t('action.signOut')}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
