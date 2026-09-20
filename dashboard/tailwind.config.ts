import type { Config } from 'tailwindcss';

/**
 * The palette comes off the shelf, not out of a dashboard template.
 *
 * `ink` is the near-black plum of a Shin Ramyun Black sleeve, `chilli` the red
 * on the original pack, `broth` the amber of the soup, `scallion` the green.
 * `buldak` is the hot pink of a Buldak sleeve and is rationed: it marks a VIP
 * and nothing else, so it keeps meaning something.
 *
 * The workspace is light and the chrome is dark. Staff use this on a counter
 * Mac under shop lights all day; a dark rail frames the work without turning
 * every figure on screen into glowing text.
 */
const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          DEFAULT: '#17121A',
          raised: '#241D29',
          line: '#332A38',
          soft: '#A197A9',
        },
        paper: '#F7F4F1',
        card: '#FFFFFF',
        line: '#E6DFDA',
        soy: '#6E625B',
        chilli: {
          DEFAULT: '#DE2B1F',
          dark: '#B31F16',
          wash: '#FCEDEB',
        },
        broth: {
          DEFAULT: '#E8930C',
          // Amber at full strength fails contrast as small text on its own
          // wash, so anything written in it uses this instead.
          dark: '#8A5406',
          wash: '#FDF3E2',
        },
        scallion: {
          DEFAULT: '#12715A',
          wash: '#E8F3EF',
        },
        buldak: {
          DEFAULT: '#EC3E7E',
          dark: '#A81A55',
          wash: '#FDEDF3',
        },

        /**
         * WhatsApp's own colours, and the one deliberate exception to the
         * palette above. They are scoped to the chat pane and used nowhere
         * else.
         *
         * The reason is not decoration. Staff read this thread with the real
         * WhatsApp open on a phone beside them, and a bubble that is green on
         * one screen and beige on the other costs a beat of translation on
         * every message. Matching the app the customer is actually using
         * makes the pane read at a glance: `out` is what we sent, `in` is
         * what they sent, and nobody has to learn that.
         */
        wa: {
          bg: '#EFEAE2',        // the chat wallpaper
          panel: '#F0F2F5',     // header and composer bars
          out: '#D9FDD3',       // our bubble
          in: '#FFFFFF',        // theirs
          divider: '#E9EDEF',
          meta: '#667781',      // timestamps, ticks before they turn blue
          tick: '#53BDEB',      // read
          green: '#00A884',
          'green-dark': '#008069',
        },
      },
      fontFamily: {
        // Set by next/font in app/layout.tsx.
        display: ['var(--font-display)', 'system-ui', 'sans-serif'],
        sans: ['var(--font-body)', 'system-ui', 'sans-serif'],
        // Every bill number, phone number, SKU and rupee figure in this app.
        mono: ['var(--font-mono)', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
      },
      letterSpacing: {
        tightest: '-0.04em',
      },
      borderRadius: {
        card: '0.625rem',
      },
      boxShadow: {
        // One shadow in the whole system, and it is barely there.
        card: '0 1px 2px rgba(23, 18, 26, 0.04)',
        // WhatsApp's bubble shadow: a single hairline, not a drop shadow.
        bubble: '0 1px 0.5px rgba(11, 20, 26, 0.13)',
        pop: '0 12px 32px -12px rgba(23, 18, 26, 0.28)',
      },
      keyframes: {
        rise: {
          from: { opacity: '0', transform: 'translateY(6px)' },
          to: { opacity: '1', transform: 'none' },
        },
      },
      animation: {
        rise: 'rise 220ms cubic-bezier(0.2, 0.7, 0.3, 1) both',
      },
    },
  },
  plugins: [],
};

export default config;
