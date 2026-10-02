'use client';

import { useEffect, useState } from 'react';

import { api } from '@/lib/api';
import { fileKind, fileSize } from '@/lib/format';
import { Icon } from './ui/Icon';

// Everything a customer sends, and every photo or file staff send, sits in
// private storage, so it has no public URL the way a catalogue photo does. The
// backend hands out a five-minute signed link; fetch one when the bubble
// renders and open the same link on click.
export function StoredMedia({
  messageId,
  kind,
  alt,
  filename,
  size,
  mime,
}: {
  messageId: string;
  kind: string;
  alt: string;
  filename?: string | null;
  size?: number | null;
  mime?: string | null;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    api
      .messageMedia(messageId)
      .then((result) => live && setUrl(result.url))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [messageId]);

  if (kind === 'document') {
    // A file card, as WhatsApp draws one: the name, what kind, how big.
    const details = [fileKind(filename, mime), fileSize(size)].filter(Boolean).join(' · ');
    const card = (
      <span className="mb-1.5 flex min-w-[220px] max-w-xs items-center gap-3 rounded-lg bg-black/[0.04] px-3 py-2.5">
        <span className="flex h-10 w-9 shrink-0 items-center justify-center rounded-md bg-chilli/90 font-mono text-[9px] font-bold text-white">
          {fileKind(filename, mime).slice(0, 4)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-ink">{filename || 'Document'}</span>
          <span className="block font-mono text-2xs text-wa-meta">
            {failed ? 'Could not be loaded' : details}
          </span>
        </span>
        {url && <Icon name="file" className="h-4 w-4 shrink-0 text-wa-green-dark" />}
      </span>
    );
    return url ? (
      <a href={url} target="_blank" rel="noreferrer" title="Open file" className="block">
        {card}
      </a>
    ) : (
      card
    );
  }

  const isImage = kind === 'image' || kind === 'sticker';

  if (failed) {
    return (
      <p className="mb-1.5 text-2xs italic text-wa-meta">
        {isImage ? 'Photo' : kind === 'audio' || kind === 'voice' ? 'Voice message' : 'File'} could
        not be loaded.
      </p>
    );
  }
  if (!url) {
    return (
      <div
        className={`mb-1.5 animate-pulse rounded-md bg-black/5 ${
          kind === 'sticker' ? 'h-28 w-28' : isImage || kind === 'video' ? 'h-40 w-56' : 'h-10 w-56'
        }`}
        aria-label="Loading"
      />
    );
  }

  if (kind === 'video') {
    return (
      <video src={url} controls preload="metadata" className="mb-1.5 max-h-72 w-full max-w-xs rounded-md" />
    );
  }
  if (kind === 'audio' || kind === 'voice') {
    return <audio src={url} controls preload="metadata" className="mb-1.5 w-64 max-w-full" />;
  }
  if (kind === 'sticker') {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={url} alt="Sticker" className="h-28 w-28 object-contain" loading="lazy" />;
  }
  return (
    <a href={url} target="_blank" rel="noreferrer">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={url}
        alt={alt}
        className="mb-1.5 max-h-72 w-auto rounded-md border border-black/5 object-cover"
        loading="lazy"
      />
    </a>
  );
}
