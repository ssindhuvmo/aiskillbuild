import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The browser only ever talks to the Vite server; /api is proxied to FastAPI.
// The Anthropic key lives in backend/.env and never reaches the frontend.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
});
