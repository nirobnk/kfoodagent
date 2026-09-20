/**
 * The icon set, inline.
 *
 * Nine glyphs do not justify a dependency, and a stroked 20px set drawn to one
 * grid stays consistent in a way a mixed-source set does not.
 */
const PATHS: Record<string, string> = {
  today: 'M3 10h18M7 3v3m10-3v3M5 6h14a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2Z',
  customers:
    'M16 20v-1.5a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4V20M9 10.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7ZM22 20v-1.5a4 4 0 0 0-3-3.87M16 3.63a4 4 0 0 1 0 7.75',
  inbox:
    'M21 12v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-6m18 0-2.5-7.4A2 2 0 0 0 16.6 3H7.4a2 2 0 0 0-1.9 1.6L3 12m18 0h-5l-1.5 3h-5L8 12H3',
  orders:
    'M6 2 4 6v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V6l-2-4H6ZM4 6h16M9 10a3 3 0 0 0 6 0',
  tasks: 'M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11',
  bills:
    'M6 2v20l2-1.5L10 22l2-1.5L14 22l2-1.5L18 22V2l-2 1.5L14 2l-2 1.5L10 2 8 3.5 6 2ZM9 8h6M9 12h6M9 16h3',
  insights: 'M3 3v18h18M7 15l3.5-4 3 3L20 7',
  catalogue:
    'M4 4h7v7H4V4Zm9 0h7v7h-7V4ZM4 13h7v7H4v-7Zm9 0h7v7h-7v-7Z',
  stock:
    'M21 8v8a2 2 0 0 1-1 1.73l-7 4a2 2 0 0 1-2 0l-7-4A2 2 0 0 1 3 16V8a2 2 0 0 1 1-1.73l7-4a2 2 0 0 1 2 0l7 4A2 2 0 0 1 21 8ZM3.3 7 12 12l8.7-5M12 22V12',
  search: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16ZM21 21l-4.3-4.3',
  plus: 'M12 5v14M5 12h14',
  close: 'M18 6 6 18M6 6l12 12',
  menu: 'M4 7h16M4 12h16M4 17h16',
  back: 'M19 12H5m0 0 6 6m-6-6 6-6',
  pin: 'M12 17v5M9 3h6l-1 6 3 3v2H7v-2l3-3-1-6Z',
  bot: 'M12 2v3M8 21h8M5 8h14a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-6a2 2 0 0 1 2-2ZM9 13h.01M15 13h.01',
  person: 'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z',
  warn: 'M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z',
  check: 'M20 6 9 17l-5-5',
  refresh: 'M21 12a9 9 0 1 1-2.6-6.4M21 3v6h-6',
  out: 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9',
  phone: 'M15.5 21A12.5 12.5 0 0 1 3 8.5 3.5 3.5 0 0 1 6.5 5l1.6 3.4-2 1.6a10 10 0 0 0 5.9 5.9l1.6-2L17 15.5A3.5 3.5 0 0 1 15.5 21Z',
  send: 'm22 2-7 20-4-9-9-4 20-7ZM11 13 22 2',
  history: 'M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 2',
  filter: 'M4 5h16M7 12h10M10 19h4',
  package: 'M4 7.5 12 12l8-4.5M12 12v9M5 7l7-4 7 4v10l-7 4-7-4V7Z',
  chevron: 'm9 18 6-6-6-6',
  dots: 'M5 12h.01M12 12h.01M19 12h.01',
  info: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20ZM12 11v6m0-10h.01',
};

export function Icon({
  name,
  className = 'h-5 w-5',
}: {
  name: keyof typeof PATHS | string;
  className?: string;
}) {
  const path = PATHS[name];
  if (!path) return null;
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d={path} />
    </svg>
  );
}
