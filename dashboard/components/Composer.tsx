'use client';

import { useState } from 'react';
import { api, explainSendFailure } from '@/lib/api';
import { TemplatePicker } from './TemplatePicker';
import { Icon } from './ui/Icon';
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
      <div className="border-t border-black/10 bg-wa-chrome">
        <TemplatePicker contactId={contact.id} onSent={onSent} />
      </div>
    );
  }

  return (
    <div className="border-t border-black/10 bg-wa-chrome px-3 py-2.5 sm:px-4">
      <div className="mx-auto max-w-4xl">
        {error && (
          <p className="mb-2 rounded-lg bg-chilli-wash px-3 py-2 text-xs text-chilli-dark">
            {error}
          </p>
        )}
        <div className="flex items-end gap-2.5">
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
            aria-label="Message"
            placeholder="Type a message"
            className="max-h-32 min-h-[44px] flex-1 resize-none rounded-xl border-0 bg-card px-4 py-3 text-sm shadow-card outline-none placeholder:text-[#667781] focus:ring-2 focus:ring-wa-green/20"
          />
          <button
            onClick={send}
            disabled={busy || !body.trim()}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-wa-green text-white shadow-card transition hover:bg-wa-dark disabled:cursor-not-allowed disabled:bg-[#8696A0]"
            aria-label="Send message"
          >
            {busy ? (
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
            ) : (
              <Icon name="send" className="h-5 w-5" />
            )}
          </button>
        </div>
        {!contact.human_takeover && (
          <p className="mt-1.5 pl-2 text-[10px] text-[#667781]">
            Sending a message switches this chat from the assistant to you.
          </p>
        )}
      </div>
    </div>
  );
}
