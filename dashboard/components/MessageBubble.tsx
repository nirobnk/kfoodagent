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
    <div className={`flex px-2 ${mine ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`message-bubble max-w-[86%] rounded-lg px-2.5 pb-1.5 pt-2 text-[13.5px] leading-[19px] shadow-bubble sm:max-w-[72%] ${
          mine ? 'message-bubble-out bg-wa-bubble' : 'message-bubble-in bg-card'
        } ${message.status === 'failed' ? 'ring-1 ring-chilli/40' : ''}`}
      >
        {mine && (
          <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-[0.05em] text-wa-dark/70">
            {fromAgent ? 'Agent' : fromSystem ? 'Automatic' : 'Staff'}
            {message.template_name && ` · ${message.template_name}`}
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
              className="mb-1.5 max-h-72 w-auto rounded-md border border-black/5 object-cover"
              loading="lazy"
            />
          </a>
        )}

        <p className="whitespace-pre-wrap break-words">
          {message.body || <span className="italic text-soy">[{message.message_type}]</span>}
        </p>

        <div className="-mb-0.5 ml-8 mt-0.5 flex items-center justify-end gap-1 text-[10px] leading-none text-[#667781] tnum">
          <span>{formatTime(message.created_at)}</span>
          {mine && (
            <span
              title={message.status}
              className={message.status === 'read' ? 'font-bold text-wa-blue' : 'text-[#667781]'}
            >
              {TICKS[message.status] ?? ''}
            </span>
          )}
        </div>

        {message.error && <p className="mt-1 text-2xs text-chilli">{message.error}</p>}
      </div>
    </div>
  );
}
