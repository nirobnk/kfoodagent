import { formatTime } from '@/lib/format';
import type { Message } from '@/lib/types';

const TICKS: Record<string, string> = {
  queued: '🕘',
  sent: '✓',
  delivered: '✓✓',
  read: '✓✓',
  failed: '⚠️',
};

export function MessageBubble({ message }: { message: Message }) {
  const mine = message.direction === 'out';
  const fromAgent = message.sender === 'agent';
  const fromSystem = message.sender === 'system';

  return (
    <div className={`flex ${mine ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[78%] rounded-lg px-3 py-2 text-sm shadow-sm ${
          mine ? 'bg-wa-mine' : 'bg-wa-bubble'
        } ${message.status === 'failed' ? 'ring-1 ring-red-300' : ''}`}
      >
        {mine && (
          <div className="mb-0.5 text-[11px] font-medium text-wa-muted">
            {fromAgent ? '🤖 Agent' : fromSystem ? '🔔 Automatic' : '🧑 Staff'}
            {message.template_name && ` · template: ${message.template_name}`}
          </div>
        )}

        {message.media_url && (
          // Staff need to see the photo the customer got, not a line of text
          // describing it. The catalogue is served from kfoods.lk, so this is a
          // plain <img>: next/image cannot optimise a remote host that is not
          // declared, and a static export has no optimiser to run anyway.
          <a href={message.media_url} target="_blank" rel="noreferrer">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={message.media_url}
              alt={message.body || 'photo'}
              className="mb-1 max-h-60 w-auto rounded-md border border-black/5 object-cover"
              loading="lazy"
            />
          </a>
        )}

        <p className="whitespace-pre-wrap break-words">
          {message.body || <span className="italic text-wa-muted">[{message.message_type}]</span>}
        </p>

        <div className="mt-1 flex items-center justify-end gap-1 text-[11px] text-wa-muted">
          <span>{formatTime(message.created_at)}</span>
          {mine && <span title={message.status}>{TICKS[message.status] ?? ''}</span>}
        </div>

        {message.error && <p className="mt-1 text-[11px] text-red-600">{message.error}</p>}
      </div>
    </div>
  );
}
