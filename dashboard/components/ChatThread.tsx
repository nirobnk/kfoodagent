'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createClient } from '@/lib/supabase';
import { api } from '@/lib/api';
import { canSendFreeText, contactLabel, formatDayLabel } from '@/lib/format';
import { useStickToBottom } from '@/lib/useStickToBottom';
import { Composer } from './Composer';
import { MessageBubble } from './MessageBubble';
import { TakeoverToggle } from './TakeoverToggle';
import { WindowBadge } from './WindowBadge';
import { Icon } from './ui/Icon';
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
  // The parent passes an inline arrow, so its identity changes on every render
  // of the inbox — and a new message re-renders the inbox. Held in a ref, that
  // churn cannot reach the effect below, which would otherwise tear down the
  // subscription and refetch the whole history on every incoming message.
  const patchRef = useRef(onContactPatch);
  patchRef.current = onContactPatch;

  const { scrollerRef, contentRef, onScroll, unseen, jumpToEnd } = useStickToBottom(
    messages.length,
    contact.id,
  );

  const append = useCallback((incoming: Message) => {
    setMessages((current) =>
      current.some((message) => message.id === incoming.id)
        ? current.map((message) => (message.id === incoming.id ? incoming : message))
        : [...current, incoming],
    );
  }, []);

  // Load history, then follow the thread live.
  //
  // Depends on the contact id alone. Anything else in here — a callback prop,
  // the contact object — changes identity when the inbox re-renders, and a
  // re-run empties the thread, refetches 200 rows and drops the realtime
  // subscription for as long as the round trip takes.
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
        (payload) => patchRef.current(payload.new as Partial<Contact>),
      )
      .subscribe();

    return () => {
      alive = false;
      void supabase.removeChannel(channel);
    };
  }, [contact.id, append]);

  // Clear the unread badge when staff open the chat.
  useEffect(() => {
    if (contact.unread_count > 0) {
      api
        .markRead(contact.id)
        .then(() => patchRef.current({ unread_count: 0 }))
        .catch(() => undefined);
    }
    // Only when a different chat is opened.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contact.id]);

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
    <section className="flex h-full min-w-0 flex-1 flex-col bg-wa-chat">
      <header className="flex min-h-[68px] flex-wrap items-center gap-3 border-b border-black/10 bg-wa-chrome px-3 py-2.5 sm:px-4">
        {onBack && (
          <button
            onClick={onBack}
            className="rounded-lg p-1 text-soy hover:bg-ink/5 hover:text-ink lg:hidden"
            aria-label="Back to chats"
          >
            <Icon name="back" />
          </button>
        )}
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-wa-green to-wa-dark font-display text-xs font-bold text-white shadow-card">
          {contactLabel(contact).slice(0, 2).toUpperCase()}
        </span>
        <div className="min-w-0 flex-1 sm:flex-none">
          <h2 className="truncate font-display text-base font-bold tracking-tight">
            {contactLabel(contact)}
          </h2>
          <p className="flex items-center gap-1.5 truncate text-xs text-soy">
            <span className={`h-1.5 w-1.5 rounded-full ${contact.human_takeover ? 'bg-broth' : 'bg-wa-green'}`} />
            {contact.human_takeover ? 'Staff handling' : 'Assistant active'} · +{contact.wa_id}
          </p>
        </div>
        <div className="scroll-thin order-last flex w-full items-center gap-2 overflow-x-auto pt-1 sm:order-none sm:ml-auto sm:w-auto sm:overflow-visible sm:pt-0">
          {/* The one link that makes this an inbox inside a CRM rather than
              beside one: who is this, what have they bought, what did we promise. */}
          <Link
            href={`/customers?id=${contact.id}`}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-black/10 bg-white/70 px-2.5 py-1.5 text-xs font-semibold text-ink transition hover:bg-white"
            title="Open this customer's record"
          >
            <Icon name="customers" className="h-4 w-4" />
            Record
          </Link>
          <WindowBadge contact={contact} />
          <TakeoverToggle contact={contact} onChange={onContactPatch} />
        </div>
      </header>

      <div className="relative flex min-h-0 flex-1 flex-col">
        <div
          ref={scrollerRef}
          onScroll={onScroll}
          className="chat-bg scroll-thin flex-1 overflow-y-auto px-3 py-5 sm:px-5"
        >
          <div ref={contentRef} className="mx-auto max-w-4xl space-y-2">
            {loading && (
              <p className="text-center font-mono text-2xs uppercase tracking-[0.14em] text-wa-meta">
                Loading
              </p>
            )}
            {error && (
              <p className="mx-auto max-w-sm rounded bg-chilli-wash p-3 text-center text-sm text-chilli-dark">
                {error}
              </p>
            )}
            {!loading && messages.length === 0 && (
              <p className="text-center text-sm text-wa-meta">No messages yet.</p>
            )}

            {grouped.map((group) => (
              <div key={group.day} className="space-y-1 pb-2">
                <div className="sticky top-0 z-10 flex justify-center py-1">
                  <span className="rounded-lg bg-[#F7FAFC]/95 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.05em] text-[#54656F] shadow-bubble backdrop-blur-sm">
                    {group.day}
                  </span>
                </div>
                {group.items.map((message, index) => {
                  // WhatsApp tails only the first bubble of a run, and labels
                  // who sent it once per run rather than on every line.
                  const previous = group.items[index - 1];
                  const startsRun =
                    !previous ||
                    previous.direction !== message.direction ||
                    previous.sender !== message.sender;
                  return (
                    <MessageBubble key={message.id} message={message} startsRun={startsRun} />
                  );
                })}
              </div>
            ))}
          </div>
        </div>

        {/* Arrived while you were reading something further up. */}
        {unseen > 0 && (
          <button
            onClick={() => jumpToEnd('smooth')}
            className="absolute bottom-3 left-1/2 flex -translate-x-1/2 items-center gap-1.5 rounded-full bg-wa-green px-3.5 py-1.5 text-xs font-medium text-white shadow-pop transition hover:bg-wa-green-dark"
          >
            {unseen} new {unseen === 1 ? 'message' : 'messages'}
            <span aria-hidden>↓</span>
          </button>
        )}
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
