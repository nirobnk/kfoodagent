import type { CookieOptions } from '@supabase/ssr';

/** One cookie Supabase asks us to write back when it refreshes a session. */
export type CookieToSet = { name: string; value: string; options: CookieOptions };
