'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createClient } from '@/lib/supabase';
import { api } from '@/lib/api';
import { canSendFreeText, contactLabel, formatDayLabel } from '@/lib/format';
import { Composer } from './Composer';
import { MessageBubble } from './MessageBubble';
import { TakeoverToggle } from './TakeoverToggle';
import { WindowBadge } from './WindowBadge';
import type { Contact, Message } from '@/lib/types';

const PAGE_SIZE = 200;

export function ChatThread({
  contact,
  onContactPatch,
  onBack,
}: {
  contact: Contact;
  onContactPatch: (patch: Partial<Contact>) => void;
  onBack?: () => void;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const append = useCallback((incoming: Message) => {
    setMessages((current) =>
      current.some((message) => message.id === incoming.id)
        ? current.map((message) => (message.id === incoming.id ? incoming : message))
        : [...current, incoming],
    );
  }, []);

  // Load history, then follow the thread live.
  useEffect(() => {
    const supabase = createClient();
    let alive = true;

    setLoading(true);
    setError(null);
    setMessages([]);

    supabase
      .from('messages')
      .select('*')
      .eq('contact_id', contact.id)
      .order('created_at', { ascending: false })
      .limit(PAGE_SIZE)
      .then(({ data, error: loadError }) => {
        if (!alive) return;
        if (loadError) setError(loadError.message);
        else setMessages((data ?? []).slice().reverse() as Message[]);
        setLoading(false);
      });

    const channel = supabase
      .channel(`chat:${contact.id}`)
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'messages',
          filter: `contact_id=eq.${contact.id}`,
        },
        (payload) => append(payload.new as Message),
      )
      .on(
        'postgres_changes',
        {
          event: 'UPDATE',
          schema: 'public',
          table: 'messages',
          filter: `contact_id=eq.${contact.id}`,
        },
        (payload) => append(payload.new as Message),
      )
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'public', table: 'contacts', filter: `id=eq.${contact.id}` },
        (payload) => onContactPatch(payload.new as Partial<Contact>),
      )
      .subscribe();

    return () => {
      alive = false;
      void supabase.removeChannel(channel);
    };
  }, [contact.id, append, onContactPatch]);

  // Clear the unread badge when staff open the chat.
  useEffect(() => {
    if (contact.unread_count > 0) {
      api
        .markRead(contact.id)
        .then(() => onContactPatch({ unread_count: 0 }))
        .catch(() => undefined);
    }
    // Only when a different chat is opened.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contact.id]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  const windowOpen = canSendFreeText(contact);

  const grouped = useMemo(() => {
    const groups: { day: string; items: Message[] }[] = [];
    for (const message of messages) {
      const day = formatDayLabel(message.created_at);
      const last = groups[groups.length - 1];
      if (last && last.day === day) last.items.push(message);
      else groups.push({ day, items: [message] });
    }
    return groups;
  }, [messages]);

  return (
    <section className="flex h-full min-w-0 flex-1 flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-wa-border bg-white px-4 py-2.5">
        {onBack && (
          <button onClick={onBack} className="text-sm text-wa-muted md:hidden" aria-label="Back">
            ←
          </button>
        )}
        <div className="min-w-0">
          <h2 className="truncate font-semibold">{contactLabel(contact)}</h2>
          <p className="truncate text-xs text-wa-muted">
            +{contact.wa_id}
            {contact.takeover_by && contact.human_takeover ? ` · held by ${contact.takeover_by}` : ''}
          </p>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <WindowBadge contact={contact} />
          <TakeoverToggle contact={contact} onChange={onContactPatch} />
        </div>
      </header>

      <div className="chat-bg scroll-thin flex-1 space-y-2 overflow-y-auto px-4 py-4">
        {loading && <p className="text-center text-sm text-wa-muted">Loading…</p>}
        {error && (
          <p className="mx-auto max-w-sm rounded bg-red-50 p-3 text-center text-sm text-red-700">
            {error}
          </p>
        )}
        {!loading && messages.length === 0 && (
          <p className="text-center text-sm text-wa-muted">No messages yet.</p>
        )}

        {grouped.map((group) => (
          <div key={group.day} className="space-y-2">
            <div className="flex justify-center">
              <span className="rounded-full bg-white/80 px-3 py-1 text-[11px] text-wa-muted shadow-sm">
                {group.day}
              </span>
            </div>
            {group.items.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <Composer
        contact={contact}
        windowOpen={windowOpen}
        onSent={() => undefined}
        onTakeover={() => onContactPatch({ human_takeover: true })}
      />
    </section>
  );
}
