import { defineConfig } from "vite";
import { resolve } from "path";
import { fileURLToPath } from "url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  root: __dirname,
  build: {
    outDir: resolve(__dirname, "../static"),
    emptyOutDir: true,
  },
  test: {
    include: ["tests/**/*.test.js"],
    environment: "node",
  },
});
