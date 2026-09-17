'use client';

import { useState } from 'react';
import { api } from '@/lib/api';
import type { Contact } from '@/lib/types';

/**
 * The agent/human switch. While human_takeover is on, the webhook stores the
 * customer's messages but the agent never answers them.
 */
export function TakeoverToggle({
  contact,
  onChange,
}: {
  contact: Contact;
  onChange: (patch: Partial<Contact>) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const human = contact.human_takeover;

  async function toggle() {
    setBusy(true);
    setError(null);
    const next = !human;
    onChange({ human_takeover: next }); // optimistic
    try {
      await api.setTakeover(contact.id, next);
    } catch (err) {
      onChange({ human_takeover: human });
      setError(err instanceof Error ? err.message : 'Could not switch');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={toggle}
        disabled={busy}
        title={
          human
            ? 'Staff are handling this chat. Click to hand it back to the agent.'
            : 'The agent is answering. Click to take over.'
        }
        className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition disabled:opacity-60 ${
          human
            ? 'border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100'
            : 'border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-100'
        }`}
      >
        <span aria-hidden>{human ? '🧑' : '🤖'}</span>
        {human ? 'You are replying' : 'Agent is replying'}
      </button>
      {error && <span className="text-xs text-red-600">{error}</span>}
    </div>
  );
}
