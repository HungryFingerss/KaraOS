/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx}',
    './components/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        mono:    ['var(--font-mono)'],
        display: ['var(--font-display)'],
      },
      colors: {
        acid:  '#b8ff35',
        night: '#090c0f',
        panel: '#0d1117',
        rail:  '#161b22',
        muted: '#30363d',
        dim:   '#8b949e',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'scan':       'scan 2s linear infinite',
        'flicker':    'flicker 4s ease-in-out infinite',
      },
      keyframes: {
        scan: {
          '0%':   { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100vh)' },
        },
        flicker: {
          '0%, 100%': { opacity: '1' },
          '92%':      { opacity: '1' },
          '93%':      { opacity: '0.6' },
          '94%':      { opacity: '1' },
          '96%':      { opacity: '0.8' },
          '97%':      { opacity: '1' },
        },
      }
    }
  },
  plugins: [],
}
