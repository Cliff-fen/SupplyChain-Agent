import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  build: {
    // ECharts is loaded only by the dashboard route. Keep its vendor payload out of the app shell;
    // the library's minified runtime is intentionally above Vite's generic 500 kB advisory.
    chunkSizeWarningLimit: 1100,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom"],
          icons: ["lucide-react"],
        },
      },
    },
  },
});
