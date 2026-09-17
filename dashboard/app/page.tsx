'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { createClient } from '@/lib/supabase';
import { ChatList } from '@/components/ChatList';
import { ChatThread } from '@/components/ChatThread';
import { Nav } from '@/components/Nav';
import { contactLabel } from '@/lib/format';
import type { Contact, Message } from '@/lib/types';

export default function InboxPage() {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [previews, setPreviews] = useState<Record<string, Message>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [email, setEmail] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const patchContact = useCallback((id: string, patch: Partial<Contact>) => {
    setContacts((current) =>
      current.map((contact) => (contact.id === id ? { ...contact, ...patch } : contact)),
    );
  }, []);

  useEffect(() => {
    const supabase = createClient();
    let alive = true;

    supabase.auth.getUser().then(({ data }) => alive && setEmail(data.user?.email ?? null));

    async function load() {
      const [{ data: contactRows, error: contactError }, { data: messageRows }] = await Promise.all([
        supabase.from('contacts').select('*').order('last_seen', { ascending: false }).limit(200),
        supabase
          .from('messages')
          .select('*')
          .order('created_at', { ascending: false })
          .limit(500),
      ]);

      if (!alive) return;

      if (contactError) {
        setError(
          `${contactError.message}. If this says permission denied, add your user to business_members.`,
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
    <div className="flex h-screen flex-col">
      <Nav email={email} />

      <div className="flex min-h-0 flex-1">
        <aside
          className={`w-full border-r border-wa-border md:w-[340px] ${
            selected ? 'hidden md:block' : 'block'
          }`}
        >
          {loading ? (
            <p className="p-6 text-center text-sm text-wa-muted">Loading chats…</p>
          ) : error ? (
            <p className="m-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>
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
              onContactPatch={(patch) => patchContact(selected.id, patch)}
              onBack={() => setSelectedId(null)}
            />
          ) : (
            <div className="chat-bg flex h-full items-center justify-center">
              <p className="max-w-xs text-center text-sm text-wa-muted">
                Pick a chat on the left. The robot icon means the agent is answering; the person icon
                means a staff member has taken over.
              </p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
