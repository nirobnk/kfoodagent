'use client';

import { useState } from 'react';
import { api, explainSendFailure } from '@/lib/api';
import { TemplatePicker } from './TemplatePicker';
import type { Contact } from '@/lib/types';

export function Composer({
  contact,
  windowOpen,
  onSent,
  onTakeover,
}: {
  contact: Contact;
  windowOpen: boolean;
  onSent: () => void;
  onTakeover: () => void;
}) {
  const [body, setBody] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send() {
    const text = body.trim();
    if (!text || busy) return;

    setBusy(true);
    setError(null);
    try {
      // Sending by hand means staff are taking this chat: the agent goes quiet
      // so the customer never gets two answers at once.
      const result = await api.sendMessage(contact.id, text, true);
      if (!result.ok) {
        setError(explainSendFailure(result.reason));
      } else {
        setBody('');
        onTakeover();
        onSent();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not send');
    } finally {
      setBusy(false);
    }
  }

  if (!windowOpen) {
    return (
      <div className="border-t border-line bg-paper">
        <TemplatePicker contactId={contact.id} onSent={onSent} />
      </div>
    );
  }

  return (
    <div className="border-t border-line bg-paper p-3">
      {error && <p className="mb-2 text-xs text-chilli">{error}</p>}
      <div className="flex items-end gap-2">
        <textarea
          rows={1}
          value={body}
          onChange={(event) => setBody(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              void send();
            }
          }}
          placeholder="Type a message. Enter to send, Shift+Enter for a new line."
          className="max-h-32 min-h-[42px] flex-1 resize-y rounded-2xl border border-line bg-card px-4 py-2.5 text-sm outline-none focus:border-ink"
        />
        <button
          onClick={send}
          disabled={busy || !body.trim()}
          className="h-[42px] rounded-full bg-ink px-5 text-sm font-medium text-white transition hover:bg-ink-raised disabled:opacity-50"
        >
          {busy ? '…' : 'Send'}
        </button>
      </div>
      {!contact.human_takeover && (
        <p className="mt-2 text-2xs text-soy">
          Sending switches this chat to you, so the agent stops replying.
        </p>
      )}
    </div>
  );
}
