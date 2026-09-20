'use client';

import { useEffect, useState } from 'react';
import { formatRemaining, windowRemainingMs } from '@/lib/format';
import type { Contact } from '@/lib/types';

/**
 * "Free reply: 4h 12m left" — the single most important thing for staff to see.
 * Once it hits zero only approved templates may be sent.
 */
export function WindowBadge({ contact }: { contact: Contact }) {
  const [remaining, setRemaining] = useState(() => windowRemainingMs(contact));

  useEffect(() => {
    setRemaining(windowRemainingMs(contact));
    const timer = setInterval(() => setRemaining(windowRemainingMs(contact)), 30_000);
    return () => clearInterval(timer);
  }, [contact]);

  const open = remaining > 0;
  const low = open && remaining < 60 * 60 * 1000;

  return (
    <span
      title={
        open
          ? 'Free-form replies are allowed until this runs out'
          : 'The 24-hour window is closed. Only approved templates can be sent.'
      }
      className={`rounded-lg px-2.5 py-1.5 font-mono text-2xs font-semibold uppercase tracking-[0.06em] tnum ${
        !open
          ? 'bg-chilli-wash text-chilli-dark'
          : low
            ? 'bg-broth-wash text-broth'
            : 'bg-wa-wash text-wa-dark'
      }`}
    >
      {open ? `${formatRemaining(remaining)} to reply free` : 'Window closed'}
    </span>
  );
}
