'use client';

import { useEffect, useState } from 'react';

import { api } from '@/lib/api';
import { Icon } from './ui/Icon';

// A photo the customer sent, or a photo or file staff sent, sits in private
// storage, so it has no public URL the way a catalogue photo does. The backend
// hands out a five-minute signed link; fetch one when the bubble renders and
// open the same link on click.
export function StoredMedia({
  messageId,
  kind,
  alt,
}: {
  messageId: string;
  kind: string;
  alt: string;
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

  const isImage = kind === 'image';

  if (failed) {
    return (
      <p className="mb-1.5 text-2xs italic text-wa-meta">
        {isImage ? 'Photo' : 'File'} could not be loaded.
      </p>
    );
  }
  if (!url) {
    return (
      <div
        className={`mb-1.5 animate-pulse rounded-md bg-black/5 ${isImage || kind === 'video' ? 'h-40 w-56' : 'h-10 w-56'}`}
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
  if (kind === 'document') {
    return (
      <a
        href={url}
        target="_blank"
        rel="noreferrer"
        className="mb-1.5 flex items-center gap-2 rounded-md border border-black/10 bg-white/60 px-3 py-2 text-xs font-medium text-wa-green-dark hover:bg-white"
      >
        <Icon name="file" className="h-4 w-4 shrink-0" />
        Open file
      </a>
    );
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
