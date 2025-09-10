/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: '#E34234', // Vermilion
          600: '#cc3b2f',
          700: '#b2352a',
        },
      },
    },
  },
  plugins: [],
}
