'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { createClient } from '@/lib/supabase';
import { ChatList } from '@/components/ChatList';
import { ChatThread } from '@/components/ChatThread';
import { Icon } from '@/components/ui/Icon';
import { Problem } from '@/components/ui/Bits';
import { contactLabel } from '@/lib/format';
import type { Contact, Message } from '@/lib/types';

export default function InboxPage() {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [previews, setPreviews] = useState<Record<string, Message>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const patchContact = useCallback((id: string, patch: Partial<Contact>) => {
    setContacts((current) =>
      current.map((contact) => (contact.id === id ? { ...contact, ...patch } : contact)),
    );
  }, []);

  // Stable for as long as the same chat is open. An inline arrow here changed
  // identity on every render of this page — and an incoming message re-renders
  // it — which made the open thread refetch its whole history and drop its
  // realtime subscription each time a message arrived.
  const patchSelected = useCallback(
    (patch: Partial<Contact>) => {
      if (selectedId) patchContact(selectedId, patch);
    },
    [selectedId, patchContact],
  );

  useEffect(() => {
    const supabase = createClient();
    let alive = true;

    async function load() {
      const [{ data: contactRows, error: contactError }, { data: messageRows }] = await Promise.all([
        supabase.from('contacts').select('*').order('last_seen', { ascending: false }).limit(200),
        supabase.from('messages').select('*').order('created_at', { ascending: false }).limit(500),
      ]);

      if (!alive) return;

      if (contactError) {
        setError(
          `${contactError.message}. If this says permission denied, your user is not in business_members yet.`,
        );
        setLoading(false);
        return;
      }

      const latest: Record<string, Message> = {};
      for (const message of (messageRows ?? []) as Message[]) {
        if (!latest[message.contact_id]) latest[message.contact_id] = message;
      }

      setContacts((contactRows ?? []) as Contact[]);
      setPreviews(latest);
      setLoading(false);
    }

    void load();

    // Live updates for the list itself: new chats, new previews, agent/human changes.
    const channel = supabase
      .channel('inbox')
      .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'messages' }, (payload) => {
        const message = payload.new as Message;
        setPreviews((current) => ({ ...current, [message.contact_id]: message }));
        setContacts((current) => {
          const index = current.findIndex((contact) => contact.id === message.contact_id);
          if (index < 0) return current;
          const moved = { ...current[index], last_seen: message.created_at };
          return [moved, ...current.filter((_, position) => position !== index)];
        });
      })
      .on('postgres_changes', { event: 'UPDATE', schema: 'public', table: 'contacts' }, (payload) => {
        const updated = payload.new as Contact;
        setContacts((current) =>
          current.map((contact) => (contact.id === updated.id ? { ...contact, ...updated } : contact)),
        );
      })
      .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'contacts' }, (payload) => {
        const created = payload.new as Contact;
        setContacts((current) =>
          current.some((contact) => contact.id === created.id) ? current : [created, ...current],
        );
      })
      .subscribe();

    return () => {
      alive = false;
      void supabase.removeChannel(channel);
    };
  }, []);

  // A chat is worth linking to from a customer record, and a static export
  // cannot read a route param — so the id rides in the query string, read once
  // on mount and written back whenever the selection changes.
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get('id');
    if (id) setSelectedId(id);
  }, []);

  useEffect(() => {
    const url = new URL(window.location.href);
    if (selectedId) url.searchParams.set('id', selectedId);
    else url.searchParams.delete('id');
    window.history.replaceState(null, '', url);
  }, [selectedId]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return contacts;
    return contacts.filter(
      (contact) =>
        contactLabel(contact).toLowerCase().includes(needle) || contact.wa_id.includes(needle),
    );
  }, [contacts, query]);

  const selected = contacts.find((contact) => contact.id === selectedId) ?? null;

  return (
    <div className="flex h-full min-h-0">
      <aside
        className={`w-full border-r border-line bg-card md:w-[336px] ${
          selected ? 'hidden md:block' : 'block'
        }`}
      >
        {loading ? (
          <p className="p-6 font-mono text-2xs uppercase tracking-[0.14em] text-soy">
            Loading chats
          </p>
        ) : error ? (
          <div className="p-3">
            <Problem>{error}</Problem>
          </div>
        ) : (
          <ChatList
            contacts={filtered}
            previews={previews}
            selectedId={selectedId}
            onSelect={(contact) => setSelectedId(contact.id)}
            query={query}
            onQueryChange={setQuery}
          />
        )}
      </aside>

      <main className={`min-w-0 flex-1 ${selected ? 'block' : 'hidden md:block'}`}>
        {selected ? (
          <ChatThread
            key={selected.id}
            contact={selected}
            onContactPatch={patchSelected}
            onBack={() => setSelectedId(null)}
          />
        ) : (
          <div className="chat-bg flex h-full items-center justify-center p-6">
            <div className="max-w-xs text-center">
              <Icon name="inbox" className="mx-auto h-8 w-8 text-ink/25" />
              <p className="mt-3 font-display text-base font-bold">Pick a chat</p>
              <p className="mt-1 text-sm text-soy">
                The robot icon means the agent is answering. The person icon means a staff member
                has taken over and the agent is staying quiet.
              </p>
              <Link
                href="/customers"
                className="mt-4 inline-flex text-sm font-medium text-chilli underline underline-offset-4"
              >
                Open the customer book instead
              </Link>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
