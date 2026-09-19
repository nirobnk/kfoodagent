import type { Metadata, Viewport } from 'next';
import { Archivo, Instrument_Sans, Martian_Mono } from 'next/font/google';
import { AuthGuard } from '@/components/AuthGuard';
import { Chrome } from '@/components/AppShell';
import './globals.css';

/**
 * Three faces, three jobs.
 *
 * Archivo is the display face: a heavy grotesque that sits where the flat
 * lettering on a ramen sleeve sits — page titles, customer names, big figures.
 * Instrument Sans does the reading. Martian Mono carries anything that is a
 * code rather than a word: bill numbers like KF-MAC1-20260919-003, phone
 * numbers, SKUs, and the small caps labels above each block of data.
 *
 * Self-hosted by next/font at build time, so the shop is not waiting on Google
 * over a Sri Lankan mobile connection before the page has type.
 */
const display = Archivo({
  subsets: ['latin'],
  weight: ['600', '700', '800'],
  variable: '--font-display',
  display: 'swap',
});

const body = Instrument_Sans({
  subsets: ['latin'],
  variable: '--font-body',
  display: 'swap',
});

const mono = Martian_Mono({
  subsets: ['latin'],
  weight: ['400', '600'],
  variable: '--font-mono',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'K FOOD — Customers',
  description:
    'The customer book, chats, orders and takings for K FOOD staff, in one place.',
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#17121A',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable} ${mono.variable}`}>
      <body className="h-full font-sans">
        <AuthGuard>
          <Chrome>{children}</Chrome>
        </AuthGuard>
      </body>
    </html>
  );
}
