'use client';

import { useEffect, useState } from 'react';

import { api } from '@/lib/api';

// A photo the customer sent sits in private storage, so it has no public URL
// the way a catalogue photo does. The backend hands out a five-minute signed
// link; fetch one when the bubble renders and open the same link on click.
export function InboundPhoto({ messageId, alt }: { messageId: string; alt: string }) {
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

  if (failed) {
    return <p className="mb-1.5 text-2xs italic text-wa-meta">Photo could not be loaded.</p>;
  }
  if (!url) {
    return <div className="mb-1.5 h-40 w-56 animate-pulse rounded-md bg-black/5" aria-label="Loading photo" />;
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
