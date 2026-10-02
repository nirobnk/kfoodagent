'use client';

import { useEffect, useRef, useState } from 'react';
import { api, explainSendFailure } from '@/lib/api';
import { TemplatePicker } from './TemplatePicker';
import { Icon } from './ui/Icon';
import { messagePreview } from '@/lib/format';
import type { Contact, Message } from '@/lib/types';

// What WhatsApp will deliver, so a wrong file is caught here, before the
// upload, rather than coming back as an error. The backend checks again.
const ACCEPT =
  'image/jpeg,image/png,image/webp,image/gif,video/mp4,video/3gpp,audio/*,' +
  '.pdf,.txt,.doc,.docx,.xls,.xlsx,.ppt,.pptx';
const MB = 1024 * 1024;

function limitFor(file: File): number {
  if (file.type.startsWith('image/')) return 5 * MB;
  if (file.type.startsWith('video/') || file.type.startsWith('audio/')) return 16 * MB;
  return 25 * MB;
}

function sizeLabel(bytes: number): string {
  return bytes >= MB ? `${(bytes / MB).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export function Composer({
  contact,
  windowOpen,
  replyTo = null,
  contactName,
  onCancelReply,
  onSent,
  onTakeover,
}: {
  contact: Contact;
  windowOpen: boolean;
  replyTo?: Message | null;
  contactName?: string;
  onCancelReply?: () => void;
  onSent: () => void;
  onTakeover: () => void;
}) {
  const [body, setBody] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const picker = useRef<HTMLInputElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);

  // Choosing Reply on a message puts the cursor here, ready to type.
  useEffect(() => {
    if (replyTo) box.current?.focus();
  }, [replyTo]);

  // A thumbnail for a photo; freed when the file changes or the chat closes.
  useEffect(() => {
    if (!file || !file.type.startsWith('image/')) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function choose(next: File | null | undefined) {
    if (!next) return;
    if (next.size > limitFor(next)) {
      setError(explainSendFailure('file_too_large'));
      return;
    }
    setError(null);
    setFile(next);
  }

  async function send() {
    const text = body.trim();
    if ((!text && !file) || busy) return;

    setBusy(true);
    setError(null);
    try {
      // Sending by hand means staff are taking this chat: the agent goes quiet
      // so the customer never gets two answers at once. With a file, the text
      // goes as its caption.
      const result = file
        ? await api.sendMedia(contact.id, file, text, true, replyTo?.id)
        : await api.sendMessage(contact.id, text, true, replyTo?.id);
      if (!result.ok) {
        setError(explainSendFailure(result.reason));
      } else {
        setBody('');
        setFile(null);
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
    <div
      className={`border-t border-black/10 bg-wa-chrome px-3 py-2.5 sm:px-4 ${dragging ? 'ring-2 ring-inset ring-wa-green/40' : ''}`}
      onDragOver={(event) => {
        if (event.dataTransfer.types.includes('Files')) {
          event.preventDefault();
          setDragging(true);
        }
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        choose(event.dataTransfer.files[0]);
      }}
    >
      <div className="mx-auto max-w-4xl">
        {error && (
          <p className="mb-2 rounded-lg bg-chilli-wash px-3 py-2 text-xs text-chilli-dark">
            {error}
          </p>
        )}

        {replyTo && (
          // What this reply quotes, as WhatsApp shows above the box.
          <div className="mb-2 flex items-center gap-2 rounded-xl bg-card px-3 py-2 shadow-card">
            <div className="min-w-0 flex-1 border-l-4 border-wa-green pl-2">
              <p className="text-2xs font-semibold text-wa-green-dark">
                Replying to{' '}
                {replyTo.direction === 'in'
                  ? contactName || 'customer'
                  : replyTo.sender === 'agent'
                    ? 'the agent'
                    : 'you'}
              </p>
              <p className="truncate text-xs text-[#667781]">{messagePreview(replyTo)}</p>
            </div>
            <button
              onClick={onCancelReply}
              disabled={busy}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[#667781] hover:bg-black/5"
              aria-label="Cancel reply"
            >
              <Icon name="close" className="h-4 w-4" />
            </button>
          </div>
        )}

        {file && (
          <div className="mb-2 flex items-center gap-3 rounded-xl bg-card px-3 py-2 shadow-card">
            {preview ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={preview} alt="" className="h-14 w-14 shrink-0 rounded-md object-cover" />
            ) : (
              <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-md bg-wa-chrome text-wa-green-dark">
                <Icon name="file" className="h-6 w-6" />
              </span>
            )}
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{file.name}</p>
              <p className="font-mono text-2xs text-[#667781]">
                {sizeLabel(file.size)} · {body.trim() ? 'your text goes as the caption' : 'add a caption below if you like'}
              </p>
            </div>
            <button
              onClick={() => setFile(null)}
              disabled={busy}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[#667781] hover:bg-black/5"
              aria-label="Remove file"
            >
              <Icon name="close" className="h-4 w-4" />
            </button>
          </div>
        )}

        <div className="flex items-end gap-2.5">
          <input
            ref={picker}
            type="file"
            accept={ACCEPT}
            className="hidden"
            onChange={(event) => {
              choose(event.target.files?.[0]);
              event.target.value = '';
            }}
          />
          <button
            onClick={() => picker.current?.click()}
            disabled={busy}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-[#54656F] transition hover:bg-black/5 disabled:cursor-not-allowed"
            aria-label="Attach a photo or file"
            title="Attach a photo, video, audio or document"
          >
            <Icon name="clip" className="h-5 w-5" />
          </button>
          <textarea
            ref={box}
            rows={1}
            value={body}
            onChange={(event) => setBody(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                void send();
              }
            }}
            onPaste={(event) => {
              // A screenshot pasted straight into the box goes as a photo.
              const pasted = Array.from(event.clipboardData.files)[0];
              if (pasted) {
                event.preventDefault();
                choose(pasted);
              }
            }}
            aria-label="Message"
            placeholder={file ? 'Add a caption' : 'Type a message'}
            className="max-h-32 min-h-[44px] flex-1 resize-none rounded-xl border-0 bg-card px-4 py-3 text-sm shadow-card outline-none placeholder:text-[#667781] focus:ring-2 focus:ring-wa-green/20"
          />
          <button
            onClick={send}
            disabled={busy || (!body.trim() && !file)}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-wa-green text-white shadow-card transition hover:bg-wa-dark disabled:cursor-not-allowed disabled:bg-[#8696A0]"
            aria-label={file ? 'Send file' : 'Send message'}
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
