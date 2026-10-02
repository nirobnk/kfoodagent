'use client';

import { useState } from 'react';
import { formatTime } from '@/lib/format';
import type { Message } from '@/lib/types';
import { StoredMedia } from './StoredMedia';
import { Icon } from './ui/Icon';

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

// WhatsApp's quick reactions.
export const QUICK_REACTIONS = ['👍', '❤️', '😂', '😮', '😢', '🙏'];

export interface ShownReaction {
  emoji: string;
  mine: boolean;
}

const URL_RE = /(https?:\/\/[^\s]+)/g;

/** Text with its links made clickable, as WhatsApp does. */
function Linked({ text }: { text: string }) {
  const parts = text.split(URL_RE);
  return (
    <>
      {parts.map((part, index) =>
        index % 2 === 1 ? (
          <a
            key={index}
            href={part}
            target="_blank"
            rel="noreferrer"
            className="break-all text-[#027EB5] underline-offset-2 hover:underline"
          >
            {part}
          </a>
        ) : (
          part
        ),
      )}
    </>
  );
}

/** "[shared contact] Levi Perera +94 77 123 4567; Kasun +9477…" as cards. */
function ContactCards({ body }: { body: string }) {
  const people = body.replace(/^\[shared contact\]\s*/, '').split('; ');
  return (
    <div className="mb-1 space-y-1.5">
      {people.map((person, index) => {
        const phones = person.match(/\+?\d[\d\s-]{6,}\d/g) ?? [];
        const name = phones.reduce((rest, phone) => rest.replace(phone, ''), person).trim();
        return (
          <div key={index} className="min-w-[220px] rounded-lg bg-black/[0.04] px-3 py-2">
            <p className="flex items-center gap-2 text-sm font-medium text-ink">
              <Icon name="person" className="h-4 w-4 text-wa-green-dark" />
              {name || 'Contact'}
            </p>
            {phones.map((phone) => (
              <a
                key={phone}
                href={`https://wa.me/${phone.replace(/\D/g, '')}`}
                target="_blank"
                rel="noreferrer"
                className="mt-0.5 block font-mono text-xs text-[#027EB5] hover:underline"
              >
                {phone}
              </a>
            ))}
          </div>
        );
      })}
    </div>
  );
}

/** "[location] Home — https://maps.google.com/?q=…" as a map card. */
function LocationCard({ body }: { body: string }) {
  const rest = body.replace(/^\[location\]\s*/, '');
  const link = rest.match(URL_RE)?.[0];
  const place = rest.replace(link ?? '', '').replace(/\s*—\s*$/, '').trim();
  return (
    <a
      href={link}
      target="_blank"
      rel="noreferrer"
      className="mb-1 flex min-w-[220px] items-center gap-3 rounded-lg bg-black/[0.04] px-3 py-2.5 hover:bg-black/[0.07]"
    >
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-chilli/90 text-white">
        <Icon name="map" className="h-5 w-5" />
      </span>
      <span className="min-w-0">
        <span className="block truncate text-sm font-medium text-ink">{place || 'Shared location'}</span>
        <span className="block text-2xs text-[#027EB5]">Open in Google Maps</span>
      </span>
    </a>
  );
}

export function MessageBubble({
  message,
  startsRun = true,
  reactions = [],
  quoted,
  contactName,
  highlighted = false,
  onReply,
  onReact,
  onJumpTo,
}: {
  message: Message;
  startsRun?: boolean;
  reactions?: ShownReaction[];
  quoted?: Message;
  contactName?: string;
  highlighted?: boolean;
  onReply?: () => void;
  onReact?: (emoji: string) => void;
  onJumpTo?: (messageId: string) => void;
}) {
  const [picking, setPicking] = useState(false);
  const mine = message.direction === 'out';
  const fromAgent = message.sender === 'agent';
  const fromSystem = message.sender === 'system';
  const kind = message.message_type;

  const side = mine ? 'out' : 'in';
  const tail = startsRun ? `bubble-tail-${side}` : '';
  const failed = message.status === 'failed';
  const body = message.body ?? '';
  const myReaction = reactions.find((reaction) => reaction.mine)?.emoji;
  const canReply = Boolean(message.wa_message_id) && !failed && Boolean(onReply);
  const canReact = !mine && Boolean(message.wa_message_id) && Boolean(onReact);

  const time = (
    <span className="float-right ml-2 mt-1 flex select-none items-center gap-0.5 font-mono text-2xs leading-none text-wa-meta tnum">
      {formatTime(message.created_at)}
      {mine && (
        <span title={message.status} className={message.status === 'read' ? 'text-wa-tick' : undefined}>
          {TICKS[message.status] ?? ''}
        </span>
      )}
    </span>
  );

  // Hover actions, beside the bubble as WhatsApp puts them. Always shown on a
  // phone-width screen, where there is no hover.
  const actions = (canReply || canReact) && (
    <div
      className={`relative flex items-center gap-0.5 self-center opacity-100 transition sm:opacity-0 sm:group-hover:opacity-100 sm:focus-within:opacity-100 ${
        mine ? 'order-first mr-1' : 'ml-1'
      }`}
    >
      {canReact && (
        <button
          onClick={() => setPicking((open) => !open)}
          className="flex h-7 w-7 items-center justify-center rounded-full text-[#54656F] hover:bg-black/5"
          aria-label="React"
          title="React"
        >
          <Icon name="smile" className="h-4 w-4" />
        </button>
      )}
      {canReply && (
        <button
          onClick={onReply}
          className="flex h-7 w-7 items-center justify-center rounded-full text-[#54656F] hover:bg-black/5"
          aria-label="Reply"
          title="Reply"
        >
          <Icon name="reply" className="h-4 w-4" />
        </button>
      )}
      {picking && (
        <div
          className={`absolute bottom-8 z-20 flex gap-1 rounded-full bg-white px-2 py-1 shadow-pop ${mine ? 'right-0' : 'left-0'}`}
        >
          {QUICK_REACTIONS.map((emoji) => (
            <button
              key={emoji}
              onClick={() => {
                setPicking(false);
                // The same emoji again takes it back, as on a phone.
                onReact?.(emoji === myReaction ? '' : emoji);
              }}
              className={`rounded-full px-1 text-lg leading-8 transition hover:scale-125 ${
                emoji === myReaction ? 'bg-wa-green/15' : ''
              }`}
              aria-label={`React ${emoji}`}
            >
              {emoji}
            </button>
          ))}
        </div>
      )}
    </div>
  );

  const reactionPills = reactions.length > 0 && (
    <div className={`-mt-1.5 flex gap-1 px-3 ${mine ? 'justify-end' : 'justify-start'}`}>
      {reactions.map((reaction, index) => (
        <span
          key={index}
          title={reaction.mine ? 'Your reaction' : 'Customer reaction'}
          className={`relative z-10 rounded-full border border-black/5 bg-white px-1.5 text-sm leading-6 shadow-bubble ${
            reaction.mine ? 'ring-1 ring-wa-green/40' : ''
          }`}
        >
          {reaction.emoji}
        </span>
      ))}
    </div>
  );

  // A sticker is drawn on its own, with no bubble behind it.
  if (kind === 'sticker' && message.media_path) {
    return (
      <div id={`msg-${message.id}`} className={`group ${startsRun ? 'mt-2' : ''}`}>
        <div className={`flex px-2 ${mine ? 'justify-end' : 'justify-start'}`}>
          {actions}
          <div className={`rounded-lg p-1 ${highlighted ? 'bg-wa-green/15' : ''}`}>
            <StoredMedia messageId={message.id} kind="sticker" alt="Sticker" />
            <p className="text-right font-mono text-2xs text-wa-meta">{formatTime(message.created_at)}</p>
          </div>
        </div>
        {reactionPills}
      </div>
    );
  }

  const quotedLabel = quoted
    ? quoted.direction === 'in'
      ? contactName || 'Customer'
      : quoted.sender === 'agent'
        ? 'Agent'
        : 'You'
    : mine
      ? contactName || 'Customer'
      : 'K FOOD';

  return (
    <div id={`msg-${message.id}`} className={`group ${startsRun ? 'mt-2' : ''}`}>
      <div className={`flex px-2 ${mine ? 'justify-end' : 'justify-start'}`}>
        <div
          className={`bubble bubble-${side} ${tail} ${failed ? 'ring-1 ring-chilli/40' : ''} ${
            highlighted ? 'ring-2 ring-wa-green/50' : ''
          }`}
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

          {message.forwarded && (
            <p className="mb-0.5 flex items-center gap-1 text-2xs italic text-wa-meta">
              <Icon name="reply" className="h-3 w-3 -scale-x-100" /> Forwarded
            </p>
          )}

          {message.reply_to_text && (
            <button
              onClick={() => quoted && onJumpTo?.(quoted.id)}
              disabled={!quoted}
              className="mb-1 block w-full rounded-md border-l-4 border-wa-green bg-black/[0.05] px-2 py-1 text-left disabled:cursor-default"
              title={quoted ? 'Go to the message' : undefined}
            >
              <span className="block text-2xs font-semibold text-wa-green-dark">{quotedLabel}</span>
              <span className="line-clamp-2 text-xs text-ink/70">{message.reply_to_text}</span>
            </button>
          )}

          {!mine && ['audio', 'voice'].includes(kind) && (
            <div className="mb-1 font-mono text-2xs uppercase tracking-[0.1em] text-wa-green-dark">
              {message.transcription_status === 'completed'
                ? 'Voice message · transcript below'
                : message.transcription_status === 'pending'
                  ? 'Transcribing voice…'
                  : 'Voice message'}
            </div>
          )}

          {message.media_path && !message.media_url && (
            // Whatever was kept: a customer's photo, voice note, video or
            // file, or a photo or file staff sent from here.
            <StoredMedia
              messageId={message.id}
              kind={kind}
              alt={body || (mine ? 'Photo sent' : 'Customer photo')}
              filename={message.media_filename}
              size={message.media_size}
              mime={message.media_mime}
            />
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
                alt={body || 'photo'}
                className="mb-1.5 max-h-72 w-auto rounded-md border border-black/5 object-cover"
                loading="lazy"
              />
            </a>
          )}

          {kind === 'contacts' && body && <ContactCards body={body} />}
          {kind === 'location' && body && <LocationCard body={body} />}

          {/* The time sits in the last line of text, not under it — that is why
              a WhatsApp bubble is the width it is. The float reserves the
              corner so a short message keeps its stamp on the same line and a
              long one wraps around it. */}
          <p className="whitespace-pre-wrap break-words text-ink/90">
            {kind === 'contacts' || kind === 'location' ? null : kind === 'unsupported' ? (
              <span className="italic text-wa-meta">
                WhatsApp did not pass this message on (an album, poll or view-once message). Check the
                phone.
              </span>
            ) : ['audio', 'voice'].includes(kind) && message.transcript ? (
              <span className="italic">“{message.transcript}”</span>
            ) : body && !(message.media_path && /^\[(photo|video|audio)\]$/.test(body)) &&
              !(kind === 'document' && message.media_path && body.startsWith('📄')) ? (
              <Linked text={body} />
            ) : message.media_path || message.media_url ? null : (
              <span className="italic text-wa-meta">[{kind}]</span>
            )}
            {time}
          </p>
          {kind === 'document' && message.media_path && body.includes('\n') && (
            // A document staff sent: its caption comes after the file name line.
            <p className="clear-both whitespace-pre-wrap text-ink/90">{body.split('\n').slice(1).join('\n')}</p>
          )}

          {message.error && <p className="clear-both mt-1 text-2xs text-chilli">{message.error}</p>}
          {!mine && message.image_analysis_status === 'completed' && message.image_description && (
            // What the agent was told the file shows. Worth a glance before
            // trusting its reply: this is a model's reading, not the customer's.
            <p className="clear-both mt-1 text-2xs text-wa-meta">
              {kind === 'document' ? 'File' : 'Photo'} read as: {message.image_description}
            </p>
          )}
          {message.transcription_status === 'failed' && (
            <p className="clear-both mt-1 text-2xs text-wa-meta">
              Could not transcribe — play it above, or ask the customer to type it.
            </p>
          )}
        </div>
        {actions}
      </div>
      {reactionPills}
    </div>
  );
}
