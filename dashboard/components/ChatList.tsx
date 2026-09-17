'use client';

import { contactLabel, formatRelative, canSendFreeText } from '@/lib/format';
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
    <div className="flex h-full flex-col bg-white">
      <div className="border-b border-wa-border p-3">
        <input
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Search name or number"
          className="w-full rounded-lg bg-wa-panel px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-wa-green"
        />
      </div>

      <ul className="scroll-thin flex-1 overflow-y-auto">
        {contacts.length === 0 && (
          <li className="p-6 text-center text-sm text-wa-muted">
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
                className={`flex w-full items-start gap-3 border-b border-wa-border px-3 py-3 text-left transition hover:bg-wa-panel ${
                  selected ? 'bg-wa-panel' : ''
                }`}
              >
                <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-wa-panel text-sm font-semibold text-wa-muted">
                  {contactLabel(contact).slice(0, 2).toUpperCase()}
                </span>

                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="truncate font-medium">{contactLabel(contact)}</span>
                    <span
                      title={contact.human_takeover ? 'A human is handling this' : 'The agent is handling this'}
                      aria-label={contact.human_takeover ? 'human' : 'agent'}
                    >
                      {contact.human_takeover ? '🧑' : '🤖'}
                    </span>
                    <span className="ml-auto shrink-0 text-[11px] text-wa-muted">
                      {formatRelative(preview?.created_at ?? contact.last_seen)}
                    </span>
                  </span>

                  <span className="mt-0.5 flex items-center gap-2">
                    <span className="truncate text-sm text-wa-muted">
                      {preview?.direction === 'out' ? 'You: ' : ''}
                      {preview?.body || 'No messages yet'}
                    </span>
                    {contact.unread_count > 0 && (
                      <span className="ml-auto shrink-0 rounded-full bg-wa-light px-2 py-0.5 text-[11px] font-semibold text-white">
                        {contact.unread_count}
                      </span>
                    )}
                  </span>

                  {!windowOpen && (
                    <span className="mt-1 inline-block rounded bg-red-50 px-1.5 py-0.5 text-[10px] font-medium text-red-700">
                      window closed
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
