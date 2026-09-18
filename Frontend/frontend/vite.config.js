import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The dev server must run on http://localhost:5173 — that origin is
// explicitly allowed by the FastAPI backend's CORS configuration.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: 'localhost',
  },
});
