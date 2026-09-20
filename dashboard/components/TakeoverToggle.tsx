'use client';

import { useState } from 'react';
import { api } from '@/lib/api';
import { Icon } from './ui/Icon';
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
        className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-semibold transition disabled:opacity-60 ${
          human
            ? 'border-broth/30 bg-broth-wash text-broth-dark'
            : 'border-wa-green/30 bg-wa-wash text-wa-dark'
        }`}
      >
        <Icon name={human ? 'person' : 'bot'} className="h-4 w-4" />
        {human ? 'Staff replying' : 'Assistant replying'}
      </button>
      {error && <span className="text-xs text-chilli">{error}</span>}
    </div>
  );
}
