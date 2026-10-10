/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: { navy: '#0B1120', cyan: '#22D3EE', success: '#34D399' },
      fontFamily: { sans: ['Inter', 'Poppins', 'ui-sans-serif', 'system-ui'] }
    }
  },
  plugins: []
};
