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
  return (
    <div className="flex h-full flex-col bg-card">
      <div className="border-b border-line p-3">
        <div className="relative">
          <Icon
            name="search"
            className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-soy"
          />
          <input
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="Search name or number"
            className="field bg-paper pl-8"
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
                className={`flex w-full items-start gap-3 border-b border-line px-3 py-3 text-left transition hover:bg-paper ${
                  selected ? 'bg-paper' : ''
                }`}
              >
                <span
                  className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-md font-display text-xs font-bold ${
                    selected ? 'bg-ink text-white' : 'bg-paper text-soy'
                  }`}
                >
                  {contactLabel(contact).slice(0, 2).toUpperCase()}
                </span>

                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="truncate font-medium">{contactLabel(contact)}</span>
                    <span
                      className={contact.human_takeover ? 'text-broth' : 'text-soy'}
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
                    <span className="ml-auto shrink-0 font-mono text-2xs text-soy">
                      {formatRelative(preview?.created_at ?? contact.last_seen)}
                    </span>
                  </span>

                  <span className="mt-0.5 flex items-center gap-2">
                    <span className="truncate text-sm text-soy">
                      {preview?.direction === 'out' ? 'You: ' : ''}
                      {preview?.message_type === 'image' && '📷 '}
                      {preview?.body || 'No messages yet'}
                    </span>
                    {contact.unread_count > 0 && (
                      <span className="ml-auto shrink-0 rounded-full bg-chilli px-1.5 py-0.5 font-mono text-2xs font-semibold text-white tnum">
                        {contact.unread_count}
                      </span>
                    )}
                  </span>

                  {!windowOpen && (
                    <span className="eyebrow mt-1 inline-block text-soy/80">window closed</span>
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
