/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Razorpay-inspired palette (teal/blue). Not their exact brand
        // tokens — deliberately distinct to avoid trademark/IP issues
        // while keeping the same visual "family."
        brand: {
          50: "#eef7f6",
          100: "#d6ebe8",
          500: "#0d7f76",
          600: "#0a6b63",
          700: "#08544e",
        },
      },
    },
  },
  plugins: [],
};
