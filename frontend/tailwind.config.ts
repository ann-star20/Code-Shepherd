import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx,js,jsx}"],
  theme: {
    extend: {
      colors: {
        sidebar: {
          DEFAULT: "#f7f7f5",
          border: "#e9e9e7",
          hover: "#efefed",
          active: "#e8e8e5",
        },
        notion: {
          text: "#37352f",
          "text-secondary": "#787774",
          border: "#e9e9e7",
          bg: "#ffffff",
          "bg-secondary": "#f7f7f5",
        },
      },
    },
  },
  plugins: [],
};

export default config;
