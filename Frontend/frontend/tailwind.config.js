/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        night: {
          950: '#060913',
          900: '#0a0f1e',
          850: '#0d1428',
          800: '#111a35',
          700: '#1a2547',
          600: '#253259',
          500: '#334272',
        },
        signal: {
          DEFAULT: '#38bdf8',
          dim: '#0ea5e9',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'Segoe UI', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Consolas', 'monospace'],
      },
      boxShadow: {
        card: '0 1px 0 0 rgba(255,255,255,0.04) inset, 0 8px 24px -12px rgba(0,0,0,0.7)',
      },
    },
  },
  plugins: [],
};
