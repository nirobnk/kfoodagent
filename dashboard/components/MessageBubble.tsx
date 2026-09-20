import { formatTime } from '@/lib/format';
import type { Message } from '@/lib/types';

// WhatsApp's own marks: one tick sent, two delivered, two blue read. Drawn as
// text because that is what they are — swapping in an icon set would put a
// different shape in front of staff than the one on their phone.
const TICKS: Record<string, string> = {
  queued: '🕘',
  sent: '✓',
  delivered: '✓✓',
  read: '✓✓',
  failed: '⚠️',
};

export function MessageBubble({
  message,
  startsRun = true,
}: {
  message: Message;
  startsRun?: boolean;
}) {
  const mine = message.direction === 'out';
  const fromAgent = message.sender === 'agent';
  const fromSystem = message.sender === 'system';

  const side = mine ? 'out' : 'in';
  const tail = startsRun ? `bubble-tail-${side}` : '';
  const failed = message.status === 'failed';

  return (
    <div className={`flex ${mine ? 'justify-end' : 'justify-start'} ${startsRun ? 'mt-2' : ''}`}>
      <div
        className={`bubble bubble-${side} ${tail} ${failed ? 'ring-1 ring-chilli/40' : ''}`}
      >
        {/* Not a WhatsApp element, and it stays anyway: the one thing this
            pane must show that a phone cannot is whether the shop or the
            agent said it. Once per run, so it does not become noise. */}
        {mine && startsRun && (
          <div className="mb-0.5 font-mono text-2xs uppercase tracking-[0.12em] text-wa-green-dark">
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
              className="mb-1 max-h-60 w-auto rounded-md border border-black/5 object-cover"
              loading="lazy"
            />
          </a>
        )}

        {/* The time sits in the last line of text, not under it — that is why
            a WhatsApp bubble is the width it is. The float reserves the
            corner so a short message keeps its stamp on the same line and a
            long one wraps around it. */}
        <p className="whitespace-pre-wrap break-words text-ink/90">
          {message.body || (
            <span className="italic text-wa-meta">[{message.message_type}]</span>
          )}
          <span className="float-right ml-2 mt-1 flex select-none items-center gap-0.5 font-mono text-2xs leading-none text-wa-meta tnum">
            {formatTime(message.created_at)}
            {mine && (
              <span
                title={message.status}
                className={message.status === 'read' ? 'text-wa-tick' : undefined}
              >
                {TICKS[message.status] ?? ''}
              </span>
            )}
          </span>
        </p>

        {message.error && <p className="clear-both mt-1 text-2xs text-chilli">{message.error}</p>}
      </div>
    </div>
  );
}
