import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import flowbiteReact from "flowbite-react/plugin/vite";
import svgr from 'vite-plugin-svgr';
import dts from "vite-plugin-dts";

// https://vite.dev/config/
export default defineConfig({
  base: "/landing",
  build: {
    outDir: "build",
  },
  plugins: [
    react(),
    tailwindcss(),
    flowbiteReact(),
    svgr(),
    dts()
  ],
});
