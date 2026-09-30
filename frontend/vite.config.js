import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/**
 * Vite configuration.
 *
 * The dev server proxies `/api` to Django so the browser only ever talks to one
 * origin.  That matters for security: the JWT never has to be sent cross-origin,
 * the proxy handles the CORS preflight locally, and cookies (the CSRF cookie for
 * Django admin) stay same-origin.
 */
export default defineConfig(({ mode }) => ({
  plugins: [react()],

  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: process.env.VITE_PROXY_TARGET || "http://localhost:8000",
        changeOrigin: true,
        secure: false,
      },
      "/media": {
        target: process.env.VITE_PROXY_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },

  preview: { port: 4173, strictPort: true },

  build: {
    outDir: "dist",
    sourcemap: mode !== "production",
    // Split the vendor bundle so a content change does not invalidate the whole
    // cached bundle for returning students.
    rollupOptions: {
      output: {
        // Function form: Vite 8 (rolldown) rejects the object shorthand form for
        // manualChunks, so the split is expressed explicitly.
        manualChunks(id) {
          if (
            id.includes("node_modules/react") ||
            id.includes("node_modules/scheduler")
          ) {
            return "react";
          }
          if (id.includes("node_modules/axios")) return "http";
          return undefined;
        },
      },
    },
  },

  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.js"],
    css: false,
    include: ["src/**/*.{test,spec}.{js,jsx}"],
    coverage: { reporter: ["text", "html"], include: ["src/**/*.{js,jsx}"] },
  },
}));
