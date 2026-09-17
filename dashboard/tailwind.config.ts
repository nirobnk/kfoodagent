import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // WhatsApp-like palette: staff already know this interface.
        wa: {
          green: '#128C7E',
          light: '#25D366',
          panel: '#f0f2f5',
          chat: '#efeae2',
          bubble: '#ffffff',
          mine: '#d9fdd3',
          border: '#e9edef',
          text: '#111b21',
          muted: '#667781',
        },
      },
      fontFamily: {
        sans: ['system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'Helvetica', 'Arial', 'sans-serif'],
      },
    },
  },
  plugins: [],
};

export default config;
