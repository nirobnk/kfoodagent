'use client';

import { contactLabel, formatRelative, canSendFreeText } from '@/lib/format';
import { Icon } from './ui/Icon';
import type { Contact, Message } from '@/lib/types';

export function ChatList({
  contacts,
  previews,
  selectedId,
  onSelect,
  query,
  onQueryChange,
}: {
  contacts: Contact[];
  previews: Record<string, Message>;
  selectedId: string | null;
  onSelect: (contact: Contact) => void;
  query: string;
  onQueryChange: (value: string) => void;
}) {
  const unread = contacts.reduce((sum, contact) => sum + contact.unread_count, 0);

  return (
    <div className="flex h-full flex-col bg-card">
      <div className="bg-wa-dark px-4 pb-3 pt-4 text-white">
        <div className="flex items-center gap-3">
          <div>
            <p className="font-display text-lg font-extrabold tracking-tight">Chats</p>
            <p className="mt-0.5 text-xs text-white/65">
              {contacts.length} conversation{contacts.length === 1 ? '' : 's'}
            </p>
          </div>
          {unread > 0 && (
            <span className="ml-auto rounded-full bg-wa-lime px-2.5 py-1 font-mono text-2xs font-semibold text-wa-deep tnum">
              {unread} unread
            </span>
          )}
        </div>
      </div>

      <div className="border-b border-line bg-wa-chrome p-2.5">
        <div className="relative">
          <Icon
            name="search"
            className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-soy"
          />
          <input
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="Search name or number"
            className="w-full rounded-lg border-0 bg-card py-2 pl-9 pr-3 text-sm shadow-card placeholder:text-soy/70 focus:outline-none focus:ring-2 focus:ring-wa-green/25"
          />
        </div>
      </div>

      <ul className="scroll-thin flex-1 overflow-y-auto">
        {contacts.length === 0 && (
          <li className="p-6 text-center text-sm text-soy">
            No chats yet. They appear here as soon as someone messages the WhatsApp number.
          </li>
        )}

        {contacts.map((contact) => {
          const preview = previews[contact.id];
          const selected = contact.id === selectedId;
          const windowOpen = canSendFreeText(contact);

          return (
            <li key={contact.id}>
              <button
                onClick={() => onSelect(contact)}
                className={`relative flex w-full items-start gap-3 border-b border-line/80 px-3 py-3 text-left transition hover:bg-wa-wash/60 ${
                  selected ? 'bg-wa-wash' : 'bg-card'
                }`}
              >
                {selected && <span className="absolute inset-y-0 left-0 w-1 bg-wa-green" />}
                <span
                  className="mt-0.5 flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-wa-green to-wa-dark font-display text-xs font-bold text-white shadow-card"
                >
                  {contactLabel(contact).slice(0, 2).toUpperCase()}
                </span>

                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="truncate font-semibold">{contactLabel(contact)}</span>
                    <span
                      className={contact.human_takeover ? 'text-broth-dark' : 'text-wa-green'}
                      title={
                        contact.human_takeover
                          ? 'A staff member is handling this'
                          : 'The agent is handling this'
                      }
                    >
                      <Icon
                        name={contact.human_takeover ? 'person' : 'bot'}
                        className="h-3.5 w-3.5"
                      />
                    </span>
                    <span
                      className={`ml-auto shrink-0 font-mono text-2xs ${
                        contact.unread_count > 0 ? 'font-semibold text-wa-green' : 'text-soy'
                      }`}
                    >
                      {formatRelative(preview?.created_at ?? contact.last_seen)}
                    </span>
                  </span>

                  <span className="mt-0.5 flex items-center gap-2">
                    <span className={`truncate text-sm ${contact.unread_count > 0 ? 'font-medium text-ink' : 'text-soy'}`}>
                      {preview?.direction === 'out' ? 'You: ' : ''}
                      {preview?.message_type === 'image' && '📷 '}
                      {preview?.body || 'No messages yet'}
                    </span>
                    {contact.unread_count > 0 && (
                      <span className="ml-auto flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full bg-wa-lime px-1.5 font-mono text-[10px] font-semibold text-wa-deep tnum">
                        {contact.unread_count}
                      </span>
                    )}
                  </span>

                  {!windowOpen && (
                    <span className="mt-1 inline-flex items-center gap-1 text-2xs font-medium text-soy">
                      <span className="h-1.5 w-1.5 rounded-full bg-soy/50" /> Reply window closed
                    </span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
