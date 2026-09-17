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
      className={`rounded-full px-2.5 py-1 text-xs font-medium ${
        !open
          ? 'bg-red-100 text-red-700'
          : low
            ? 'bg-amber-100 text-amber-800'
            : 'bg-emerald-100 text-emerald-800'
      }`}
    >
      {open ? `Free reply: ${formatRemaining(remaining)} left` : 'Window closed'}
    </span>
  );
}
