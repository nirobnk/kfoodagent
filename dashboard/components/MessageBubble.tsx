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
