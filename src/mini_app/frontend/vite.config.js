import { defineConfig } from "vite";
import { resolve } from "path";
import { fileURLToPath } from "url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  root: __dirname,
  build: {
    outDir: resolve(__dirname, "../static"),
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: (chunkInfo) =>
          chunkInfo.name === "index" ? "assets/app.js" : `assets/${chunkInfo.name}.js`,
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: (assetInfo) => {
              if (assetInfo.name && assetInfo.name.endsWith(".css")) {
                return "assets/styles.css";
              }
              return "assets/[name][extname]";
            },
        manualChunks: {
          renderers: [resolve(__dirname, "assets/renderers.js")],
        },
      },
    },
  },
  test: {
    include: ["tests/**/*.test.js"],
    environment: "node",
  },
});
